import { PerceptionEngine } from "./perception.js";
import { ActionExecutor } from "./executor.js";
import { BrowserAction } from "./types.js";

// WorkKnightBot Default Candidate Ground Truth
const CANDIDATE_PROFILE = {
  first_name: "Alex",
  last_name: "Rivera",
  full_name: "Alex Rivera",
  email: "alex.rivera.dev@example.com",
  phone: "+1 (415) 890-4321",
  linkedin_url: "https://linkedin.com/in/alex-rivera-systems",
  github_url: "https://github.com/alexrivera-ai",
  portfolio_url: "https://alexrivera.dev",
  work_auth: "Yes",
  sponsorship: "No",
  gender: "Decline to self-identify",
  veteran_status: "Decline to self-identify",
};

const ALWAYS_SKIP_FIELDS = [
  "cover_letter",
  "cover letter",
  "referral",
  "how did you hear",
  "twitter",
  "blog",
];

// Content script message listener
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "PING") {
    sendResponse({ status: "ok", url: window.location.href, title: document.title });
    return true;
  }

  if (message.type === "CAPTURE_SNAPSHOT") {
    try {
      const snapshot = PerceptionEngine.captureSnapshot(message.sessionId || "default");
      sendResponse({ status: "success", snapshot });
    } catch (err: any) {
      sendResponse({ status: "error", error: err.message });
    }
    return true;
  }

  if (message.type === "EXECUTE_ACTION") {
    const action: BrowserAction = message.action;
    ActionExecutor.execute(action)
      .then((outcome) => {
        sendResponse({ status: "success", outcome });
      })
      .catch((err) => {
        sendResponse({ status: "error", error: err.message });
      });
    return true;
  }

  if (message.type === "AUTOFILL_PAGE") {
    executeAutofill()
      .then((result) => {
        sendResponse({ status: "success", ...result });
      })
      .catch((err) => {
        sendResponse({ status: "error", error: err.message });
      });
    return true;
  }

  return false;
});

async function executeAutofill() {
  const snapshot = PerceptionEngine.captureSnapshot("autofill-run");
  let filledCount = 0;
  let skippedCount = 0;

  for (const control of snapshot.controls) {
    const norm = (control.name || "").toLowerCase().replace(/_/g, " ").trim();
    const selectorStr = control.selector.primary_selector;

    // Check intentional skip rule
    if (ALWAYS_SKIP_FIELDS.some((skip) => norm.includes(skip))) {
      skippedCount++;
      continue;
    }

    let valueToFill: string | null = null;

    if (norm.includes("first name")) {
      valueToFill = CANDIDATE_PROFILE.first_name;
    } else if (norm.includes("last name")) {
      valueToFill = CANDIDATE_PROFILE.last_name;
    } else if (norm.includes("email")) {
      valueToFill = CANDIDATE_PROFILE.email;
    } else if (norm.includes("phone")) {
      valueToFill = CANDIDATE_PROFILE.phone;
    } else if (norm.includes("linkedin")) {
      valueToFill = CANDIDATE_PROFILE.linkedin_url;
    } else if (norm.includes("github")) {
      valueToFill = CANDIDATE_PROFILE.github_url;
    } else if (norm.includes("portfolio")) {
      valueToFill = CANDIDATE_PROFILE.portfolio_url;
    } else if (norm.includes("sponsorship")) {
      valueToFill = CANDIDATE_PROFILE.sponsorship;
    } else if (norm.includes("work auth") || norm.includes("authorized")) {
      valueToFill = CANDIDATE_PROFILE.work_auth;
    } else if (norm.includes("gender")) {
      valueToFill = CANDIDATE_PROFILE.gender;
    } else if (norm.includes("veteran")) {
      valueToFill = CANDIDATE_PROFILE.veteran_status;
    }

    if (valueToFill) {
      await ActionExecutor.executeFill(
        {
          target: { primary_selector: selectorStr },
          value: valueToFill,
          is_secret: false,
          clear_first: true,
          typing_delay_ms: 10,
        },
        performance.now()
      );
      filledCount++;
      // Brief pause between fields for human simulation
      await new Promise((r) => setTimeout(r, 60));
    }
  }

  return { filledCount, skippedCount, totalDetected: snapshot.controls.length };
}
