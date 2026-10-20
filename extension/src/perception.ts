import { FormControlEvidence, PageSnapshot, ControlOption } from "./types.js";

export class PerceptionEngine {
  public static captureSnapshot(sessionId: string): PageSnapshot {
    const controls: FormControlEvidence[] = [];
    const elements = document.querySelectorAll(
      "input, select, textarea, button, [role='button'], [role='textbox'], [role='combobox'], [role='checkbox'], [role='radio']"
    );

    let index = 0;
    elements.forEach((el) => {
      if (!(el instanceof HTMLElement)) return;
      if (!this.isVisible(el)) return;

      // Skip submit buttons from normal form-fill extraction (they are handled as explicit submit triggers)
      const inputType = el instanceof HTMLInputElement ? el.type.toLowerCase() : undefined;
      if (inputType === "hidden") return;

      index++;
      const controlId = `ctrl_${index}`;
      const name = this.computeAccessibleName(el);
      const role = el.getAttribute("role") || el.tagName.toLowerCase();
      const selector = this.computeSelector(el);
      const rect = el.getBoundingClientRect();

      const options: ControlOption[] = [];
      if (el instanceof HTMLSelectElement) {
        Array.from(el.options).forEach((opt) => {
          options.push({
            value: opt.value,
            text: opt.text.trim(),
            is_selected: opt.selected,
          });
        });
      }

      const sectionHeading = this.findSectionHeading(el);
      const nearbyLabels = this.findNearbyLabels(el);

      controls.push({
        control_id: controlId,
        selector: {
          primary_selector: selector,
          accessible_role: role,
          accessible_name: name,
          bounding_box: {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
          },
        },
        tag_name: el.tagName.toLowerCase(),
        input_type: inputType,
        role,
        name: name || el.getAttribute("placeholder") || el.getAttribute("name") || "",
        placeholder: el.getAttribute("placeholder") || undefined,
        is_required: el.hasAttribute("required") || el.getAttribute("aria-required") === "true",
        is_disabled: el.hasAttribute("disabled") || el.getAttribute("aria-disabled") === "true",
        is_readonly: el.hasAttribute("readonly"),
        current_value: this.getControlValue(el),
        options,
        section_heading: sectionHeading || undefined,
        nearby_labels: nearbyLabels,
      });
    });

    return {
      session_id: sessionId,
      url: window.location.href,
      title: document.title,
      timestamp_ms: Date.now(),
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      controls,
    };
  }

  private static isVisible(el: HTMLElement): boolean {
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  private static computeAccessibleName(el: HTMLElement): string {
    // 1. Check aria-label
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

    // 2. Check aria-labelledby
    const ariaLabelledBy = el.getAttribute("aria-labelledby");
    if (ariaLabelledBy) {
      const labelEl = document.getElementById(ariaLabelledBy);
      if (labelEl && labelEl.textContent?.trim()) {
        return labelEl.textContent.trim();
      }
    }

    // 3. Check for associated <label for="...">
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label && label.textContent?.trim()) {
        return label.textContent.trim();
      }
    }

    // 4. Check wrapping <label>
    const parentLabel = el.closest("label");
    if (parentLabel && parentLabel.textContent?.trim()) {
      return parentLabel.textContent.trim();
    }

    // 5. Fallback to name or placeholder
    const placeholder = el.getAttribute("placeholder");
    if (placeholder && placeholder.trim()) return placeholder.trim();

    const nameAttr = el.getAttribute("name");
    if (nameAttr && nameAttr.trim()) return nameAttr.trim();

    // 6. Text content for buttons
    if (el instanceof HTMLButtonElement || el.getAttribute("role") === "button") {
      if (el.innerText && el.innerText.trim()) return el.innerText.trim();
    }

    return "";
  }

  private static computeSelector(el: HTMLElement): string {
    if (el.id) return `#${CSS.escape(el.id)}`;
    if (el.getAttribute("name")) {
      return `${el.tagName.toLowerCase()}[name="${CSS.escape(el.getAttribute("name")!)}"]`;
    }
    const dataTestId = el.getAttribute("data-testid") || el.getAttribute("data-test");
    if (dataTestId) {
      return `[data-testid="${CSS.escape(dataTestId)}"]`;
    }

    // Generate path
    const path: string[] = [];
    let curr: HTMLElement | null = el;
    while (curr && curr.nodeType === Node.ELEMENT_NODE && curr !== document.body) {
      let selector = curr.tagName.toLowerCase();
      if (curr.id) {
        path.unshift(`#${CSS.escape(curr.id)}`);
        break;
      } else {
        let siblingIndex = 1;
        let sibling = curr.previousElementSibling;
        while (sibling) {
          if (sibling.tagName === curr.tagName) siblingIndex++;
          sibling = sibling.previousElementSibling;
        }
        selector += `:nth-of-type(${siblingIndex})`;
        path.unshift(selector);
      }
      curr = curr.parentElement;
    }
    return path.join(" > ");
  }

  private static findSectionHeading(el: HTMLElement): string | null {
    const container = el.closest("fieldset, section, form");
    if (container) {
      const legend = container.querySelector("legend, h1, h2, h3, h4");
      if (legend && legend.textContent) return legend.textContent.trim();
    }
    return null;
  }

  private static findNearbyLabels(el: HTMLElement): string[] {
    const nearby: string[] = [];
    const prev = el.previousElementSibling;
    if (prev && prev.textContent && prev.textContent.trim().length < 60) {
      nearby.push(prev.textContent.trim());
    }
    return nearby;
  }

  private static getControlValue(el: HTMLElement): string | undefined {
    if (el instanceof HTMLInputElement) {
      if (el.type === "checkbox" || el.type === "radio") {
        return el.checked ? "checked" : "unchecked";
      }
      return el.value;
    }
    if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) {
      return el.value;
    }
    return undefined;
  }
}
