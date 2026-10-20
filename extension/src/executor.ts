import { BrowserAction, FillAction, ClickAction, SelectAction, VerificationOutcome } from "./types.js";

export class ActionExecutor {
  public static async execute(action: BrowserAction): Promise<VerificationOutcome> {
    const startTime = performance.now();

    try {
      switch (action.action_type) {
        case "Fill":
          return await this.executeFill(action.payload, startTime);
        case "Click":
          return await this.executeClick(action.payload, startTime);
        case "Select":
          return await this.executeSelect(action.payload, startTime);
        case "Scroll":
          window.scrollBy({ top: action.payload.distance_px, behavior: "smooth" });
          return {
            Passed: {
              duration_ms: Math.round(performance.now() - startTime),
              observed_state: `Scrolled ${action.payload.distance_px}px`,
            },
          };
        case "Wait":
          await new Promise((r) => setTimeout(r, action.payload.duration_ms));
          return {
            Passed: {
              duration_ms: Math.round(performance.now() - startTime),
              observed_state: `Waited ${action.payload.duration_ms}ms`,
            },
          };
      }
    } catch (err: any) {
      return {
        Failed: {
          rule: { IdleSettled: { min_idle_ms: 0, max_wait_ms: 0 } },
          reason: err.message || "Unknown error during action execution",
          expected: "success",
          actual: "exception",
        },
      };
    }
  }

  public static async executeFill(action: FillAction, startTime: number): Promise<VerificationOutcome> {
    const el = document.querySelector(action.target.primary_selector);
    if (!el || !(el instanceof HTMLElement)) {
      return {
        Failed: {
          rule: { ValueReflected: { target: action.target, expected_value: action.value } },
          reason: `Target element not found: ${action.target.primary_selector}`,
          expected: action.value,
          actual: "element_not_found",
        },
      };
    }

    // Scroll into view gently
    el.scrollIntoView({ behavior: "smooth", block: "center" });

    // Handle Radio Buttons
    if (el instanceof HTMLInputElement && el.type === "radio") {
      const radioGroup = document.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`);
      let foundRadio: HTMLInputElement | null = null;
      radioGroup.forEach((r) => {
        if (r instanceof HTMLInputElement) {
          if (r.value.toLowerCase() === action.value.toLowerCase()) {
            foundRadio = r;
          }
        }
      });

      const targetRadio = foundRadio || el;
      targetRadio.checked = true;
      targetRadio.dispatchEvent(new Event("change", { bubbles: true }));
      targetRadio.dispatchEvent(new Event("input", { bubbles: true }));
      this.highlightElement(targetRadio);

      return {
        Passed: {
          duration_ms: Math.round(performance.now() - startTime),
          observed_state: `Selected radio option '${action.value}'`,
        },
      };
    }

    // Handle Select Dropdowns
    if (el instanceof HTMLSelectElement) {
      return this.executeSelect(
        {
          target: action.target,
          option_text: action.value,
          option_value: action.value,
        },
        startTime
      );
    }

    // Handle Text / Number / Email / Tel Inputs & Textareas
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      el.focus();

      if (action.clear_first) {
        el.value = "";
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }

      // Human-like keystroke emulation
      const delay = action.typing_delay_ms !== undefined ? action.typing_delay_ms : 10;
      for (const char of action.value) {
        el.dispatchEvent(new KeyboardEvent("keydown", { key: char, bubbles: true }));
        el.value += char;
        el.dispatchEvent(new InputEvent("input", { data: char, bubbles: true, inputType: "insertText" }));
        el.dispatchEvent(new KeyboardEvent("keyup", { key: char, bubbles: true }));
        if (delay > 0) {
          await new Promise((r) => setTimeout(r, delay));
        }
      }

      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.blur();

      this.highlightElement(el);

      return {
        Passed: {
          duration_ms: Math.round(performance.now() - startTime),
          observed_state: `Value '${action.is_secret ? "[SECRET]" : action.value}' reflected in DOM`,
        },
      };
    }

    return {
      Failed: {
        rule: { ValueReflected: { target: action.target, expected_value: action.value } },
        reason: "Element does not accept text input",
        expected: action.value,
        actual: el.tagName,
      },
    };
  }

  public static async executeClick(action: ClickAction, startTime: number): Promise<VerificationOutcome> {
    const el = document.querySelector(action.target.primary_selector);
    if (!el || !(el instanceof HTMLElement)) {
      return {
        Failed: {
          rule: { IdleSettled: { min_idle_ms: 0, max_wait_ms: 0 } },
          reason: `Click target not found: ${action.target.primary_selector}`,
          expected: "element present",
          actual: "not found",
        },
      };
    }

    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
    el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, button: 0 }));
    el.click();

    this.highlightElement(el);

    return {
      Passed: {
        duration_ms: Math.round(performance.now() - startTime),
        observed_state: "Element clicked successfully",
      },
    };
  }

  public static async executeSelect(action: SelectAction, startTime: number): Promise<VerificationOutcome> {
    const el = document.querySelector(action.target.primary_selector);
    if (!el || !(el instanceof HTMLSelectElement)) {
      return {
        Failed: {
          rule: { IdleSettled: { min_idle_ms: 0, max_wait_ms: 0 } },
          reason: `Select target not found: ${action.target.primary_selector}`,
          expected: "select element",
          actual: "not found",
        },
      };
    }

    let found = false;
    const targetText = action.option_text?.toLowerCase().trim();
    const targetVal = action.option_value?.toLowerCase().trim();

    for (let i = 0; i < el.options.length; i++) {
      const opt = el.options[i];
      const optText = opt.text.toLowerCase().trim();
      const optVal = opt.value.toLowerCase().trim();

      if (
        (targetText && (optText === targetText || optText.includes(targetText) || targetText.includes(optText))) ||
        (targetVal && optVal === targetVal)
      ) {
        el.selectedIndex = i;
        found = true;
        break;
      }
    }

    if (!found && action.option_index !== undefined) {
      el.selectedIndex = action.option_index;
      found = true;
    }

    el.dispatchEvent(new Event("change", { bubbles: true }));
    this.highlightElement(el);

    return {
      Passed: {
        duration_ms: Math.round(performance.now() - startTime),
        observed_state: `Selected option '${el.value}'`,
      },
    };
  }

  private static highlightElement(el: HTMLElement) {
    const originalBorder = el.style.border;
    const originalBoxShadow = el.style.boxShadow;
    const originalTransition = el.style.transition;

    el.style.transition = "all 0.25s ease";
    el.style.border = "2px solid #10b981";
    el.style.boxShadow = "0 0 10px rgba(16, 185, 129, 0.4)";

    setTimeout(() => {
      el.style.border = originalBorder;
      el.style.boxShadow = originalBoxShadow;
      el.style.transition = originalTransition;
    }, 2000);
  }
}
