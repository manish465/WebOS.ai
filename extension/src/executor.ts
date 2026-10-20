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

  private static async executeFill(action: FillAction, startTime: number): Promise<VerificationOutcome> {
    const el = document.querySelector(action.target.primary_selector);
    if (!el || !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
      return {
        Failed: {
          rule: { ValueReflected: { target: action.target, expected_value: action.value } },
          reason: `Target element not found: ${action.target.primary_selector}`,
          expected: action.value,
          actual: "element_not_found",
        },
      };
    }

    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.focus();

    if (action.clear_first) {
      el.value = "";
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }

    // Human-like keystroke emulation
    const delay = action.typing_delay_ms || 15;
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

    // Verify DOM value reflection
    if (el.value === action.value) {
      return {
        Passed: {
          duration_ms: Math.round(performance.now() - startTime),
          observed_state: `Value '${action.is_secret ? "[SECRET]" : action.value}' reflected in DOM`,
        },
      };
    } else {
      return {
        Failed: {
          rule: { ValueReflected: { target: action.target, expected_value: action.value } },
          reason: "DOM value did not reflect expected typed string",
          expected: action.value,
          actual: el.value,
        },
      };
    }
  }

  private static async executeClick(action: ClickAction, startTime: number): Promise<VerificationOutcome> {
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

    return {
      Passed: {
        duration_ms: Math.round(performance.now() - startTime),
        observed_state: "Element clicked successfully",
      },
    };
  }

  private static async executeSelect(action: SelectAction, startTime: number): Promise<VerificationOutcome> {
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

    if (action.option_value) {
      el.value = action.option_value;
    } else if (action.option_text) {
      const match = Array.from(el.options).find(
        (o) => o.text.trim().toLowerCase() === action.option_text!.trim().toLowerCase()
      );
      if (match) {
        el.value = match.value;
      }
    } else if (action.option_index !== undefined) {
      el.selectedIndex = action.option_index;
    }

    el.dispatchEvent(new Event("change", { bubbles: true }));

    return {
      Passed: {
        duration_ms: Math.round(performance.now() - startTime),
        observed_state: `Selected option '${el.value}'`,
      },
    };
  }
}
