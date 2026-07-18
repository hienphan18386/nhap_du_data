"""Minimal Marionette client -- drives a real Firefox with only the stdlib.

Marionette is Mozilla's own automation protocol, built into every Firefox build and
enabled with the --marionette flag (it listens on 127.0.0.1:2828). Unlike Playwright,
which needs its own patched Firefox, this talks to the Firefox the user already has
installed, so nothing extra is downloaded.

The wire format is length-prefixed JSON: b"<byte_length>:<json>". A command is
[0, message_id, command_name, params] and the reply is [1, message_id, error, result].

Only the pieces this project needs are implemented: navigate and execute_script.
"""

import json
import socket
from typing import Any, Dict, List, Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 2828


class MarionetteError(RuntimeError):
    """Raised when Firefox returns an error packet for a command."""


class Marionette:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 180.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.session_id: Optional[str] = None
        self._buffer = b""
        self._message_id = 0

    # --- connection ---------------------------------------------------------

    def connect(self, accept_insecure_certs: bool = True) -> Dict[str, Any]:
        """Open the socket, read the server hello, and start a WebDriver session.

        accept_insecure_certs lets the session load a site whose certificate the
        profile does not trust yet, mirroring what a user clicking through would get.
        """
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)

        hello = self._read_packet()
        if hello.get("marionetteProtocol") != 3:
            raise MarionetteError(f"Unsupported Marionette protocol: {hello!r}")

        # Raw Marionette reads the requested capabilities straight from the params
        # object -- the WebDriver {"capabilities": {"alwaysMatch": {...}}} wrapper is
        # silently ignored here (it leaves acceptInsecureCerts stuck at False).
        params = {"acceptInsecureCerts": accept_insecure_certs}
        result = self.command("WebDriver:NewSession", params)
        self.session_id = result.get("sessionId")
        return result

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self.command("WebDriver:DeleteSession", {})
        except (MarionetteError, OSError):
            pass
        try:
            self.sock.close()
        finally:
            self.sock = None
            self.session_id = None

    def __enter__(self) -> "Marionette":
        self.connect()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- wire format --------------------------------------------------------

    def _read_exactly(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise MarionetteError("Firefox closed the Marionette connection")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def _read_packet(self) -> Any:
        """Read one b'<length>:<json>' packet."""
        length = b""
        while True:
            char = self._read_exactly(1)
            if char == b":":
                break
            if not char.isdigit():
                raise MarionetteError(f"Bad length prefix byte: {char!r}")
            length += char
        return json.loads(self._read_exactly(int(length)).decode("utf-8"))

    def _send_packet(self, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.sock.sendall(str(len(body)).encode("ascii") + b":" + body)

    def command(self, name: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send one command and return its result, raising on an error packet."""
        if self.sock is None:
            raise MarionetteError("Not connected -- call connect() first")

        self._message_id += 1
        message_id = self._message_id
        self._send_packet([0, message_id, name, params or {}])

        while True:
            packet = self._read_packet()
            # Ignore anything that is not the reply we are waiting for.
            if not isinstance(packet, list) or len(packet) != 4 or packet[0] != 1:
                continue
            if packet[1] != message_id:
                continue
            _, _, error, result = packet
            if error:
                raise MarionetteError(f"{name}: {error.get('error')}: {error.get('message')}")
            return result

    # --- the bits the importer uses -----------------------------------------

    def navigate(self, url: str) -> None:
        self.command("WebDriver:Navigate", {"url": url})

    def execute_script(self, script: str, args: Optional[List[Any]] = None) -> Any:
        """Run JS in the content page. The script must `return` its value."""
        result = self.command(
            "WebDriver:ExecuteScript",
            {"script": script, "args": args or [], "newSandbox": False},
        )
        # A WebDriver session wraps results as {"value": ...}; older paths return raw.
        if isinstance(result, dict) and "value" in result:
            return result["value"]
        return result

    def find_element(self, value: str, using: str = "xpath") -> Optional[str]:
        """Return an element reference id, or None if nothing matches."""
        try:
            result = self.command("WebDriver:FindElement", {"using": using, "value": value})
        except MarionetteError:
            return None
        element = result.get("value", result) if isinstance(result, dict) else result
        if not isinstance(element, dict):
            return None
        for key, ref in element.items():
            if key.startswith("element-") or key == "ELEMENT":
                return ref
        return None

    def element_click(self, element_id: str) -> None:
        """Click via the browser's own input synthesis -- a real, trusted event.

        DevExtreme ignores JS-dispatched clicks on some widgets, so this is not
        interchangeable with dispatching events from execute_script().
        """
        self.command("WebDriver:ElementClick", {"id": element_id})

    def element_clear(self, element_id: str) -> None:
        """Clear a field the way a user would, so masked inputs reset their state."""
        self.command("WebDriver:ElementClear", {"id": element_id})

    def element_send_keys(self, element_id: str, text: str) -> None:
        self.command("WebDriver:ElementSendKeys", {"id": element_id, "text": text})

    def current_url(self) -> str:
        result = self.command("WebDriver:GetCurrentURL", {})
        if isinstance(result, dict) and "value" in result:
            return result["value"]
        return result

    def set_script_timeout(self, milliseconds: int) -> None:
        self.command("WebDriver:SetTimeouts", {"script": milliseconds})
