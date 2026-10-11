"""
WebOS.ai — Real Session Extension Bridge
Runs a WebSocket server on 127.0.0.1:9223 for the WebOS Chrome Extension.
Enables 100% native control over the user's running Chrome window without isolated profiles.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable, List
import websockets

logger = logging.getLogger(__name__)

_GLOBAL_BRIDGE: Optional[ExtensionBridge] = None


class ExtensionBridge:
    """Bridges WebOS CDP commands to the user's active Chrome via WebOS Extension."""

    def __init__(self, port: int = 9223) -> None:
        self.port = port
        self.ws: Optional[websockets.WebSocketServerProtocol] = None
        self._server = None
        self._msg_id: int = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._event_listeners: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.active_tab: Optional[Dict[str, Any]] = None
        self.target_id: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self.ws is not None and not getattr(self.ws, "closed", False)

    async def start(self) -> None:
        """Starts WebSocket server on 127.0.0.1:9223."""
        if self._server is not None:
            return

        async def handler(websocket):
            self.ws = websocket
            logger.info("WebOS Chrome Extension connected on port %s", self.port)
            try:
                async for raw in websocket:
                    try:
                        msg = json.loads(raw)
                        # Handshake
                        if msg.get("type") == "handshake":
                            self.active_tab = msg.get("activeTab")
                            if self.active_tab:
                                self.target_id = self.active_tab.get("id")
                            logger.info("Extension active tab: %s", self.active_tab)
                            continue

                        # Events
                        if msg.get("type") == "event":
                            method = msg.get("method")
                            params = msg.get("params", {})
                            for listener in self._event_listeners.get(method, []):
                                try:
                                    listener(params)
                                except Exception as err:
                                    logger.warning("Event listener error: %s", err)
                            continue

                        # Response matching
                        req_id = msg.get("id")
                        if req_id is not None and req_id in self._pending:
                            fut = self._pending.pop(req_id)
                            if not fut.done():
                                if "error" in msg and msg["error"]:
                                    fut.set_exception(RuntimeError(msg["error"].get("message", "CDP Error")))
                                else:
                                    fut.set_result(msg.get("result", {}))
                    except Exception as e:
                        logger.warning("Error processing extension message: %s", e)
            except Exception as e:
                logger.debug("Extension connection closed: %s", e)
            finally:
                if self.ws == websocket:
                    self.ws = None
                logger.info("WebOS Chrome Extension disconnected.")

        self._server = await websockets.serve(handler, "127.0.0.1", self.port, max_size=50 * 1024 * 1024)
        logger.info("WebOS Extension Bridge listening on ws://127.0.0.1:%s", self.port)

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 20.0) -> Dict[str, Any]:
        """Sends CDP command to extension and awaits result."""
        if not self.is_connected:
            raise RuntimeError("WebOS Chrome Extension is not currently connected. Please load or enable the extension in Chrome.")

        self._msg_id += 1
        msg_id = self._msg_id
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[msg_id] = future

        payload = {
            "id": msg_id,
            "method": method,
            "params": params or {},
            "targetId": self.target_id
        }

        try:
            await self.ws.send(json.dumps(payload))
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"Extension command {method} timed out after {timeout}s")
        except Exception:
            self._pending.pop(msg_id, None)
            raise

    async def call(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 20.0) -> Dict[str, Any]:
        return await self.send(method, params, timeout=timeout)

    async def evaluate(self, expression: str, timeout: float = 15.0) -> Any:
        res = await self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True}, timeout=timeout)
        val = res.get("result", {})
        return val.get("value")

    async def get_all_page_targets(self, host: str = "127.0.0.1", port: int = 9222) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            res = await self.send("Target.getTargets")
            return res.get("targets", res.get("targetInfos", []))
        except Exception:
            return []

    async def create_new_tab(self, url: str, host: str = "127.0.0.1", port: int = 9222) -> Dict[str, Any]:
        res = await self.send("Target.createTarget", {"url": url})
        self.target_id = res.get("targetId") or res.get("id")
        return res

    async def activate_tab(self, target_id: str, host: str = "127.0.0.1", port: int = 9222) -> None:
        self.target_id = target_id
        await self.send("Target.activateTarget", {"targetId": target_id})

    async def bring_to_front(self) -> None:
        await self.send("Page.bringToFront")

    def on(self, event_name: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        if event_name not in self._event_listeners:
            self._event_listeners[event_name] = []
        self._event_listeners[event_name].append(callback)

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


def get_global_bridge() -> ExtensionBridge:
    global _GLOBAL_BRIDGE
    if _GLOBAL_BRIDGE is None:
        _GLOBAL_BRIDGE = ExtensionBridge()
    return _GLOBAL_BRIDGE
