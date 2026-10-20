import { useState } from "react";

interface ControlItem {
  id: string;
  name: string;
  role: string;
  required: boolean;
  value?: string;
}

interface FlightEvent {
  id: string;
  domain: string;
  action: string;
  durationMs: number;
  outcome: "Passed" | "Failed" | "Pending";
}

export default function App() {
  const [isFilling, setIsFilling] = useState(false);
  const [controls] = useState<ControlItem[]>([
    { id: "ctrl_1", name: "First Name", role: "textbox", required: true, value: "Alex" },
    { id: "ctrl_2", name: "Last Name", role: "textbox", required: true, value: "Rivera" },
    { id: "ctrl_3", name: "Email Address", role: "textbox", required: true, value: "alex.rivera.dev@example.com" },
    { id: "ctrl_4", name: "Phone Number", role: "textbox", required: false, value: "+1 (415) 890-4321" },
    { id: "ctrl_5", name: "Requires Visa Sponsorship?", role: "radio", required: true, value: "No" },
  ]);

  const [flightEvents, setFlightEvents] = useState<FlightEvent[]>([
    { id: "evt-01", domain: "myworkdayjobs.com", action: "Perception Snapshot", durationMs: 42, outcome: "Passed" },
    { id: "evt-02", domain: "myworkdayjobs.com", action: "Fill: First Name", durationMs: 25, outcome: "Passed" },
    { id: "evt-03", domain: "myworkdayjobs.com", action: "Fill: Last Name", durationMs: 22, outcome: "Passed" },
    { id: "evt-04", domain: "myworkdayjobs.com", action: "Fill: Email Address", durationMs: 28, outcome: "Passed" },
    { id: "evt-05", domain: "myworkdayjobs.com", action: "Fill: Phone Number", durationMs: 20, outcome: "Passed" },
  ]);

  const handleFillForm = () => {
    setIsFilling(true);
    setTimeout(() => {
      setIsFilling(false);
      setFlightEvents((prev) => [
        {
          id: `evt-${Date.now().toString().slice(-4)}`,
          domain: "myworkdayjobs.com",
          action: "Verified Fill Complete",
          durationMs: 110,
          outcome: "Passed",
        },
        ...prev,
      ]);
    }, 1200);
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px", color: "#f3f4f6" }}>
      {/* Header */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          paddingBottom: "16px",
          borderBottom: "1px solid #1f293d",
          marginBottom: "24px",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 700, letterSpacing: "-0.5px" }}>
            WebOS.ai <span style={{ color: "#3b82f6" }}>Control Plane</span>
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#9ca3af" }}>
            Local-First Browser Automation Runtime & Flight Recorder
          </p>
        </div>

        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "#151c2c",
              border: "1px solid #1f293d",
              padding: "6px 12px",
              borderRadius: "9999px",
              fontSize: "12px",
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#10b981" }}></span>
            <span>Policy Guard Active</span>
          </div>

          <button
            style={{
              background: "#ef4444",
              border: "none",
              color: "white",
              padding: "8px 14px",
              borderRadius: "6px",
              fontWeight: 600,
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            ⏸ Pause Engine (Esc)
          </button>
        </div>
      </header>

      {/* Action Bar */}
      <section
        style={{
          display: "flex",
          gap: "16px",
          background: "#151c2c",
          border: "1px solid #1f293d",
          padding: "16px",
          borderRadius: "10px",
          marginBottom: "24px",
          alignItems: "center",
        }}
      >
        <button
          onClick={handleFillForm}
          disabled={isFilling}
          style={{
            background: isFilling ? "#2563eb" : "#3b82f6",
            border: "none",
            color: "white",
            padding: "12px 24px",
            borderRadius: "8px",
            fontWeight: 700,
            fontSize: "15px",
            cursor: "pointer",
            boxShadow: "0 2px 8px rgba(59, 130, 246, 0.3)",
          }}
        >
          {isFilling ? "⚡ Executing Verified Fill..." : "⚡ Fill Active Form"}
        </button>

        <div style={{ fontSize: "13px", color: "#9ca3af" }}>
          Target: <strong style={{ color: "#f3f4f6" }}>Active Chrome Tab</strong> (Reusing Authenticated User Session)
        </div>
      </section>

      {/* Main Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        {/* Left: Perception & Model Intelligence */}
        <div>
          {/* Perception Inspector */}
          <div
            style={{
              background: "#151c2c",
              border: "1px solid #1f293d",
              borderRadius: "10px",
              padding: "18px",
              marginBottom: "24px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "14px" }}>
              <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Active Perception Inspector</h2>
              <span style={{ fontSize: "12px", color: "#10b981", fontWeight: 600 }}>Zero-Token AX (&lt; 50ms)</span>
            </div>

            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ color: "#9ca3af", borderBottom: "1px solid #1f293d", textAlign: "left" }}>
                  <th style={{ padding: "8px 0" }}>Control</th>
                  <th style={{ padding: "8px 0" }}>Role</th>
                  <th style={{ padding: "8px 0" }}>Status</th>
                  <th style={{ padding: "8px 0" }}>Resolved Value</th>
                </tr>
              </thead>
              <tbody>
                {controls.map((ctrl) => (
                  <tr key={ctrl.id} style={{ borderBottom: "1px solid #1a233a" }}>
                    <td style={{ padding: "10px 0", fontWeight: 500 }}>
                      {ctrl.name} {ctrl.required && <span style={{ color: "#ef4444" }}>*</span>}
                    </td>
                    <td style={{ padding: "10px 0", color: "#9ca3af" }}>{ctrl.role}</td>
                    <td style={{ padding: "10px 0" }}>
                      <span
                        style={{
                          background: "#064e3b",
                          color: "#34d399",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                        }}
                      >
                        Mapped
                      </span>
                    </td>
                    <td style={{ padding: "10px 0", color: "#60a5fa", fontFamily: "monospace" }}>{ctrl.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Model Intelligence Status */}
          <div
            style={{
              background: "#151c2c",
              border: "1px solid #1f293d",
              borderRadius: "10px",
              padding: "18px",
            }}
          >
            <h2 style={{ margin: "0 0 14px", fontSize: "16px", fontWeight: 600 }}>Model Intelligence Subsystem</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", fontSize: "13px" }}>
              <div style={{ background: "#0b0f19", padding: "12px", borderRadius: "8px" }}>
                <div style={{ color: "#9ca3af" }}>Tier 1: Exact Cache</div>
                <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#10b981" }}>94.2% Hit Rate</div>
              </div>
              <div style={{ background: "#0b0f19", padding: "12px", borderRadius: "8px" }}>
                <div style={{ color: "#9ca3af" }}>Tier 2: Learned Mappings</div>
                <div style={{ fontSize: "18px", fontWeight: 700, marginTop: "4px", color: "#3b82f6" }}>&lt; 1ms (0 tok)</div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Flight Recorder Audit Log */}
        <div>
          <div
            style={{
              background: "#151c2c",
              border: "1px solid #1f293d",
              borderRadius: "10px",
              padding: "18px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "14px" }}>
              <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Flight Recorder Audit Log</h2>
              <span style={{ fontSize: "12px", color: "#9ca3af" }}>SQLite WAL Append-Only</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {flightEvents.map((evt) => (
                <div
                  key={evt.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    background: "#0b0f19",
                    padding: "10px 14px",
                    borderRadius: "6px",
                    fontSize: "13px",
                    borderLeft: "3px solid #10b981",
                  }}
                >
                  <div>
                    <strong style={{ color: "#f3f4f6" }}>{evt.action}</strong>
                    <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>{evt.domain}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{ color: "#10b981", fontWeight: 600 }}>{evt.outcome}</span>
                    <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>{evt.durationMs}ms</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
