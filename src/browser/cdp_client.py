"""
Chrome DevTools Protocol (CDP) WebSocket client for real browser automation.
"""

import asyncio
import json
import logging
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

    async def send(
        self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0
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
