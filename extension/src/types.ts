export interface TargetSelector {
  primary_selector: string;
  accessible_role?: string;
  accessible_name?: string;
  text_anchor?: string;
  bounding_box?: BoundingBox;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ControlOption {
  value: string;
  text: string;
  is_selected: boolean;
}

export interface FormControlEvidence {
  control_id: string;
  selector: TargetSelector;
  tag_name: string;
  input_type?: string;
  role: string;
  name: string;
  placeholder?: string;
  is_required: boolean;
  is_disabled: boolean;
  is_readonly: boolean;
  current_value?: string;
  options: ControlOption[];
  section_heading?: string;
  nearby_labels: string[];
}

export interface PageSnapshot {
  session_id: string;
  url: string;
  title: string;
  timestamp_ms: number;
  viewport_width: number;
  viewport_height: number;
  controls: FormControlEvidence[];
}

export type BrowserAction =
  | { action_type: "Click"; payload: ClickAction }
  | { action_type: "Fill"; payload: FillAction }
  | { action_type: "Select"; payload: SelectAction }
  | { action_type: "Scroll"; payload: ScrollAction }
  | { action_type: "Wait"; payload: WaitAction };

export interface ClickAction {
  target: TargetSelector;
  click_count: number;
  button: "Left" | "Right" | "Middle";
  modifiers: string[];
}

export interface FillAction {
  target: TargetSelector;
  value: string;
  is_secret: boolean;
  clear_first: boolean;
  typing_delay_ms?: number;
}

export interface SelectAction {
  target: TargetSelector;
  option_value?: string;
  option_text?: string;
  option_index?: number;
}

export interface ScrollAction {
  direction: "Up" | "Down" | "Left" | "Right";
  distance_px: number;
  target?: TargetSelector;
}

export interface WaitAction {
  duration_ms: number;
}

export type PostconditionRule =
  | { ValueReflected: { target: TargetSelector; expected_value: string } }
  | { AttributeToggled: { target: TargetSelector; attribute_name: string; expected_value: string } }
  | { ElementAppeared: { selector: TargetSelector; timeout_ms: number } }
  | { ElementDisappeared: { selector: TargetSelector; timeout_ms: number } }
  | { UrlChanged: { previous_url: string; expected_pattern?: string } }
  | { IdleSettled: { min_idle_ms: number; max_wait_ms: number } };

export type VerificationOutcome =
  | { Passed: { duration_ms: number; observed_state: string } }
  | { Failed: { rule: PostconditionRule; reason: string; expected: string; actual: string } }
  | { Timeout: { rule: PostconditionRule; elapsed_ms: number } };

export interface ActionExecutionReceipt {
  action: BrowserAction;
  outcome: VerificationOutcome;
  duration_ms: number;
  timestamp_utc: string;
}
