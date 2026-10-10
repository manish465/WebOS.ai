"""
Chrome DevTools Protocol (CDP) WebSocket client for real browser automation.
"""

import asyncio
import json
import logging
import sys
from urllib.parse import quote
from typing import Optional, Dict, Any, Callable, List
import httpx
import websockets

logger = logging.getLogger(__name__)


class CDPClient:
    """Asynchronous JSON-RPC client connecting to Chrome via CDP WebSocket."""

    def __init__(self) -> None:
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id: int = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._event_listeners: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._connected: bool = False
        self.target_id: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self.ws is not None

    async def connect(
        self, host: str = "127.0.0.1", port: int = 9222, target_index: int = 0
    ) -> str:
        """
        Discovers targets via HTTP /json and opens a WebSocket to the active tab.
        Returns the connected target ID.
        """
        json_url = f"http://{host}:{port}/json"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(json_url)
            resp.raise_for_status()
            targets = resp.json()

        # Filter out UI self-reference (localhost:8080) and internal chrome pages
        page_targets = [
            t for t in targets
            if t.get("type") == "page"
            and ":8080" not in t.get("url", "")
            and not t.get("url", "").startswith("chrome://")
        ]
        if not page_targets:
            page_targets = [t for t in targets if t.get("type") == "page"]

        if not page_targets:
            raise RuntimeError(f"No accessible page targets found on {host}:{port}")

        target = page_targets[min(target_index, len(page_targets) - 1)]
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError(f"Target {target.get('id')} has no webSocketDebuggerUrl")

        self.target_id = target.get("id")
        self.ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
        self._connected = True
        self._listener_task = asyncio.create_task(self._listen_loop())

        # Enable essential CDP domains
        await self.send("Page.enable")
        await self.send("DOM.enable")
        await self.send("Accessibility.enable")

        logger.info("Connected to CDP target %s at %s", self.target_id, ws_url)
        return self.target_id

    async def get_all_page_targets(self, host: str = "127.0.0.1", port: int = 9222) -> List[Dict[str, Any]]:
        """Queries /json to get all accessible browser page targets."""
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(f"http://{host}:{port}/json")
                if resp.status_code == 200:
                    targets = resp.json()
                    return [
                        t for t in targets
                        if t.get("type") == "page"
                        and ":8080" not in t.get("url", "")
                        and not t.get("url", "").startswith("chrome://")
                    ]
        except Exception as e:
            logger.warning("Could not list page targets: %s", e)
        return []

    async def create_new_tab(self, url: str, host: str = "127.0.0.1", port: int = 9222) -> Dict[str, Any]:
        """
        Creates a brand new tab in Chrome, connects CDP client to it, and brings Chrome to front.
        """
        safe_url = quote(url, safe=":/%#?=&")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.put(f"http://{host}:{port}/json/new?{safe_url}")
            resp.raise_for_status()
            target_data = resp.json()

        target_id = target_data.get("id")
        ws_url = target_data.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError(f"New tab {target_id} has no webSocketDebuggerUrl")

        await self.close()
        self.target_id = target_id
        self.ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
        self._connected = True
        self._listener_task = asyncio.create_task(self._listen_loop())

        await self.send("Page.enable")
        await self.send("DOM.enable")
        await self.send("Accessibility.enable")
        await self.bring_to_front()
        return target_data

    async def activate_tab(self, target_id: str, host: str = "127.0.0.1", port: int = 9222) -> None:
        """Activates a target tab in Chrome and brings Chrome window to the front."""
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.get(f"http://{host}:{port}/json/activate/{target_id}")

        if self.target_id != target_id:
            await self.switch_to_target(target_id, host=host, port=port)
        else:
            await self.bring_to_front()

    async def switch_to_target(self, target_id: str, host: str = "127.0.0.1", port: int = 9222) -> None:
        """Switches CDP client session to a specified target tab."""
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"http://{host}:{port}/json")
            resp.raise_for_status()
            targets = resp.json()

        matching = [t for t in targets if t.get("id") == target_id]
        if not matching:
            raise RuntimeError(f"Target {target_id} not found in Chrome")

        ws_url = matching[0].get("webSocketDebuggerUrl")
        await self.close()
        self.target_id = target_id
        self.ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
        self._connected = True
        self._listener_task = asyncio.create_task(self._listen_loop())

        await self.send("Page.enable")
        await self.send("DOM.enable")
        await self.send("Accessibility.enable")
        await self.bring_to_front()

    async def bring_to_front(self) -> None:
        """Brings the active tab to front and focuses the Chrome desktop window."""
        try:
            await self.send("Page.bringToFront")
        except Exception as e:
            logger.debug("Page.bringToFront failed: %s", e)

        self._focus_window_os()

    def _focus_window_os(self) -> None:
        """Focuses the Chrome window in Windows using user32 APIs so it physically pops up."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            found_hwnds = []

            def enum_proc(hwnd, lParam):
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buf, 256)
                if "Chrome_WidgetWin_1" in class_buf.value and user32.IsWindowVisible(hwnd):
                    found_hwnds.append(hwnd)
                return True

            user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
            for hwnd in found_hwnds:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                break
        except Exception as e:
            logger.debug("OS focus window failed: %s", e)


    async def call(
        self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 18.0
    ) -> Dict[str, Any]:
        """Compatibility alias for send()."""
        return await self.send(method, params, timeout=timeout)

    async def send(
        self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 18.0
    ) -> Dict[str, Any]:
        """Sends a JSON-RPC command and awaits its matching result."""
        if not self.ws or not self._connected:
            raise ConnectionError("CDPClient is not connected to a browser target.")

        self._msg_id += 1
        msg_id = self._msg_id

        payload = {"id": msg_id, "method": method, "params": params or {}}
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[msg_id] = future

        await self.ws.send(json.dumps(payload))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(msg_id, None)
            raise TimeoutError(f"CDP command {method} (id={msg_id}) timed out after {timeout}s")

    async def evaluate(self, expression: str, await_promise: bool = True) -> Any:
        """Helper to evaluate a JavaScript expression in the page context."""
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
        )
        return result.get("result", {}).get("value")

    def on(self, event_name: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a listener callback for a CDP notification event."""
        if event_name not in self._event_listeners:
            self._event_listeners[event_name] = []
        self._event_listeners[event_name].append(callback)

    async def _listen_loop(self) -> None:
        """Background task processing inbound WebSocket messages."""
        try:
            while self._connected and self.ws:
                raw_msg = await self.ws.recv()
                data = json.loads(raw_msg)

                # 1. Match response to pending request ID
                if "id" in data:
                    req_id = data["id"]
                    future = self._pending_requests.pop(req_id, None)
                    if future and not future.done():
                        if "error" in data:
                            future.set_exception(
                                RuntimeError(f"CDP Error ({req_id}): {data['error']}")
                            )
                        else:
                            future.set_result(data.get("result", {}))

                # 2. Match notification events
                elif "method" in data:
                    method = data["method"]
                    params = data.get("params", {})
                    for callback in self._event_listeners.get(method, []):
                        try:
                            callback(params)
                        except Exception as e:
                            logger.error("Error in CDP event callback for %s: %s", method, e)

        except websockets.ConnectionClosed:
            logger.info("CDP WebSocket connection closed.")
        except Exception as e:
            logger.error("Unexpected error in CDP listener loop: %s", e)
        finally:
            self._connected = False

    async def close(self) -> None:
        """Closes the WebSocket connection cleanly."""
        self._connected = False
        if self._listener_task:
            self._listener_task.cancel()
        if self.ws:
            await self.ws.close()
            self.ws = None
        # Cancel any pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()
