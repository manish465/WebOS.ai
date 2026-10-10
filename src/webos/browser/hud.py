"""
Interactive Browser HUD Overlay and Pause/Record/Resume controller in Shadow DOM.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from webos.browser.cdp_client import CDPClient

logger = logging.getLogger(__name__)


class HUDOverlay:
    """
    Manages the floating HUD widget injected into the active browser page.
    Encapsulated inside a Shadow DOM to avoid CSS conflicts.
    """

    HUD_INJECTION_SCRIPT = """
    (() => {
        if (document.getElementById('webos-hud-host')) return;

        const host = document.createElement('div');
        host.id = 'webos-hud-host';
        host.style.position = 'fixed';
        host.style.bottom = '20px';
        host.style.right = '20px';
        host.style.zIndex = '2147483647';
        host.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

        const shadow = host.attachShadow({ mode: 'open' });
        shadow.innerHTML = `
            <style>
                .pill {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    background: rgba(15, 23, 42, 0.92);
                    backdrop-filter: blur(8px);
                    color: #f8fafc;
                    padding: 8px 16px;
                    border-radius: 9999px;
                    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    font-size: 13px;
                    font-weight: 500;
                    user-select: none;
                }
                .brand {
                    color: #38bdf8;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }
                .status {
                    color: #e2e8f0;
                    max-width: 250px;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .btn {
                    background: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    color: #ffffff;
                    padding: 4px 10px;
                    border-radius: 9999px;
                    cursor: pointer;
                    font-size: 11px;
                    font-weight: 600;
                    transition: all 0.15s ease;
                }
                .btn:hover {
                    background: rgba(255, 255, 255, 0.2);
                }
                .btn-paused {
                    background: #f59e0b;
                    color: #000;
                    border-color: #d97706;
                }
            </style>
            <div class="pill">
                <span class="brand">WebOS.ai</span>
                <span class="status" id="webos-status">Ready</span>
                <button class="btn" id="webos-pause-btn">Pause</button>
            </div>
        `;

        document.body.appendChild(host);
        window.__webos_paused = false;
        window.__webos_recorded_events = [];

        const btn = shadow.getElementById('webos-pause-btn');
        btn.addEventListener('click', () => {
            window.__webos_paused = !window.__webos_paused;
            btn.textContent = window.__webos_paused ? 'Resume' : 'Pause';
            btn.className = window.__webos_paused ? 'btn btn-paused' : 'btn';
            const statusEl = shadow.getElementById('webos-status');
            if (window.__webos_paused) {
                statusEl.textContent = 'Paused (Recording user actions...)';
            } else {
                statusEl.textContent = 'Running';
            }
        });
    })()
    """

    def __init__(self) -> None:
        self._active_cdp: Optional[CDPClient] = None

    async def inject_hud(self, cdp: CDPClient) -> None:
        """Injects the floating HUD into the active document."""
        self._active_cdp = cdp
        await cdp.evaluate(self.HUD_INJECTION_SCRIPT)

    async def set_status(
        self, cdp_or_msg: Any, message: Optional[str] = None, mode: str = "running"
    ) -> None:
        """Updates the status message displayed inside the HUD."""
        if isinstance(cdp_or_msg, str):
            actual_msg = cdp_or_msg
            cdp = self._active_cdp
        else:
            cdp = cdp_or_msg
            actual_msg = message or ""
            self._active_cdp = cdp

        if not cdp or not getattr(cdp, "is_connected", False):
            return

        safe_msg = json.dumps(actual_msg)
        script = f"""
        (() => {{
            const host = document.getElementById('webos-hud-host');
            if (!host || !host.shadowRoot) return;
            const statusEl = host.shadowRoot.getElementById('webos-status');
            if (statusEl) statusEl.textContent = {safe_msg};
        }})()
        """
        try:
            await cdp.evaluate(script)
        except Exception:
            pass

    async def is_paused(self, cdp: CDPClient) -> bool:
        """Checks if the user has hit the Pause button."""
        val = await cdp.evaluate("window.__webos_paused === true")
        return bool(val)

    async def enable_recording(self, cdp: CDPClient) -> None:
        """Attaches DOM listeners to record manual user interventions while paused."""
        record_script = """
        (() => {
            if (window.__webos_recording_active) return;
            window.__webos_recording_active = true;
            window.__webos_recorded_events = [];

            window.__webos_record_handler = (e) => {
                const target = e.target;
                if (!target || target.closest && target.closest('#webos-hud-host')) return;

                const eventData = {
                    type: e.type,
                    tag: target.tagName ? target.tagName.toLowerCase() : '',
                    id: target.id || '',
                    name: target.name || '',
                    value: target.value || target.innerText || '',
                    timestamp: Date.now()
                };
                window.__webos_recorded_events.push(eventData);
            };

            document.addEventListener('click', window.__webos_record_handler, true);
            document.addEventListener('change', window.__webos_record_handler, true);
        })()
        """
        await cdp.evaluate(record_script)

    async def disable_recording(self, cdp: CDPClient) -> List[Dict[str, Any]]:
        """Retrieves captured events and removes the recording event listeners."""
        get_and_clean_script = """
        (() => {
            const events = window.__webos_recorded_events || [];
            if (window.__webos_record_handler) {
                document.removeEventListener('click', window.__webos_record_handler, true);
                document.removeEventListener('change', window.__webos_record_handler, true);
                window.__webos_record_handler = null;
            }
            window.__webos_recording_active = false;
            window.__webos_recorded_events = [];
            return events;
        })()
        """
        events = await cdp.evaluate(get_and_clean_script)
        return events or []
