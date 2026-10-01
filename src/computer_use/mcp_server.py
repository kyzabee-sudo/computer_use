"""Newline-delimited JSON-RPC MCP server. It listens on stdin and opens no port."""

import base64
import json
import sys
import traceback

from computer_use import __version__
from computer_use.errors import ComputerUseError
from computer_use.parsing import as_int, runtime_id, window_id
from computer_use.service import ComputerUseService

_PROTOCOL = "2024-11-05"


def tool_specs() -> list[dict]:
    return [
        _tool(
            "health",
            "Report whether desktop control is enabled, whether the kill switch is present, and whether this process can see an interactive Windows desktop. This does not click or type.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _tool(
            "list_windows",
            "List visible top-level windows. Requires computer use to be enabled.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _tool(
            "screenshot",
            "Capture the desktop or one window as a PNG. The text result includes origin and scale. Convert an image pixel back to the screen with screen_x = origin_x + image_x / scale and screen_y = origin_y + image_y / scale.",
            {
                "type": "object",
                "properties": {
                    "window_id": {"type": "string", "description": "hwnd from list_windows. Omit for the whole desktop."},
                    "max_edge": {"type": "integer", "description": "Longest image edge in pixels. Default 1600."},
                },
                "additionalProperties": False,
            },
        ),
        _tool(
            "tree",
            "Read the UI Automation tree of one window, bounded by depth.",
            {
                "type": "object",
                "properties": {
                    "window_id": {"type": "string"},
                    "max_depth": {"type": "integer", "description": "Default 3, maximum 8."},
                },
                "required": ["window_id"],
                "additionalProperties": False,
            },
        ),
        _tool(
            "find_elements",
            "Find UI Automation elements in one window by name and optional control type.",
            {
                "type": "object",
                "properties": {
                    "window_id": {"type": "string"},
                    "name_contains": {"type": "string"},
                    "control_type": {"type": "string", "description": "For example Button, Edit, or MenuItem."},
                    "limit": {"type": "integer"},
                },
                "required": ["window_id"],
                "additionalProperties": False,
            },
        ),
        _tool(
            "focus",
            "Bring a window to the foreground. The Windows session must be unlocked.",
            {
                "type": "object",
                "properties": {"window_id": {"type": "string"}},
                "required": ["window_id"],
                "additionalProperties": False,
            },
        ),
        _tool(
            "click",
            "Click a screen point, or the center of a window when x and y are omitted. Coordinates are screen pixels, not scaled image pixels.",
            {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {"type": "integer", "enum": [1, 2]},
                    "window_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        _tool(
            "type_text",
            "Type Unicode text into the focused window, or into window_id after focusing it. Newlines become Enter.",
            {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "window_id": {"type": "string"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        ),
        _tool(
            "key",
            "Press a key chord such as [\"ctrl\", \"c\"] or [\"alt\", \"f4\"]. Names include enter, tab, esc, arrows, and f1 through f24.",
            {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}},
                    "window_id": {"type": "string"},
                },
                "required": ["keys"],
                "additionalProperties": False,
            },
        ),
        _tool(
            "invoke",
            "Invoke a UI Automation element by the runtime_id returned from tree or find_elements.",
            {
                "type": "object",
                "properties": {
                    "window_id": {"type": "string"},
                    "runtime_id": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["window_id", "runtime_id"],
                "additionalProperties": False,
            },
        ),
        _tool(
            "set_value",
            "Set the value of a UI Automation element that supports the Value pattern.",
            {
                "type": "object",
                "properties": {
                    "window_id": {"type": "string"},
                    "runtime_id": {"type": "array", "items": {"type": "integer"}},
                    "value": {"type": "string"},
                },
                "required": ["window_id", "runtime_id", "value"],
                "additionalProperties": False,
            },
        ),
    ]


def serve(service: ComputerUseService, reader, writer) -> None:
    while True:
        try:
            message = read_message(reader)
        except json.JSONDecodeError as exc:
            write_message(writer, _error(None, -32700, f"parse error: {exc}"))
            continue
        except ComputerUseError as exc:
            write_message(writer, _error(None, -32700, str(exc)))
            continue
        if message is None:
            return
        response = handle(service, message)
        if response is not None:
            write_message(writer, response)


def handle(service: ComputerUseService, message: dict) -> dict | None:
    if not isinstance(message, dict):
        return _error(None, -32600, "invalid request")
    method = message.get("method")
    msg_id = message.get("id")
    if "id" not in message:
        return None
    params = message.get("params") or {}
    try:
        if method == "initialize":
            client_protocol = params.get("protocolVersion") if isinstance(params, dict) else None
            protocol = client_protocol if isinstance(client_protocol, str) else _PROTOCOL
            return _result(
                msg_id,
                {
                    "protocolVersion": protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "computer-use", "version": __version__},
                    "instructions": (
                        "Desktop control is disabled until COMPUTER_USE_ENABLED=1 "
                        "or the enabled file exists. Remove actions by creating the STOP file."
                    ),
                },
            )
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": tool_specs()})
        if method == "tools/call":
            return _result(msg_id, _call_tool(service, params))
        return _error(msg_id, -32601, f"unknown method {method}")
    except ComputerUseError as exc:
        if method == "tools/call":
            return _result(msg_id, _tool_error(str(exc)))
        return _error(msg_id, -32000, str(exc))
    except Exception as exc:
        print(traceback.format_exc(), file=sys.stderr)
        if method == "tools/call":
            return _result(msg_id, _tool_error(str(exc)))
        return _error(msg_id, -32603, str(exc))


def read_message(reader) -> dict | None:
    while True:
        line = reader.readline()
        if line == b"":
            return None
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(b"{"):
            return json.loads(stripped.decode("utf-8"))
        if stripped.lower().startswith(b"content-length:"):
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                header = reader.readline()
                if header in (b"\n", b"\r\n", b""):
                    break
            payload = reader.read(length)
            return json.loads(payload.decode("utf-8"))
        raise ComputerUseError(f"unrecognized MCP frame: {stripped[:40]!r}")


def write_message(writer, message: dict) -> None:
    data = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    writer.write(data + b"\n")
    writer.flush()


def _call_tool(service: ComputerUseService, params: dict) -> dict:
    if not isinstance(params, dict):
        raise ComputerUseError("tools/call params must be an object")
    name = params.get("name")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise ComputerUseError("tool arguments must be an object")
    if name == "health":
        return _text(service.health())
    if name == "list_windows":
        return _text(service.list_windows())
    if name == "screenshot":
        result = service.screenshot(
            window_id=window_id(args.get("window_id")),
            max_edge=as_int(args.get("max_edge", 1600), "max_edge"),
        )
        encoded = base64.b64encode(result["png"]).decode("ascii")
        return {
            "content": [
                {"type": "text", "text": json.dumps(result["meta"])},
                {"type": "image", "data": encoded, "mimeType": "image/png"},
            ],
            "isError": False,
        }
    if name == "tree":
        return _text(
            service.tree(
                window_id(args.get("window_id")),
                as_int(args.get("max_depth", 3), "max_depth"),
            )
        )
    if name == "find_elements":
        return _text(
            service.find_elements(
                window_id(args.get("window_id")),
                str(args.get("name_contains") or ""),
                str(args.get("control_type") or ""),
                as_int(args.get("limit", 20), "limit"),
            )
        )
    if name == "focus":
        return _text(service.focus(window_id(args.get("window_id"))))
    if name == "click":
        x = args.get("x")
        y = args.get("y")
        return _text(
            service.click(
                None if x is None else as_int(x, "x"),
                None if y is None else as_int(y, "y"),
                str(args.get("button") or "left"),
                as_int(args.get("clicks", 1), "clicks"),
                window_id(args.get("window_id")),
            )
        )
    if name == "type_text":
        return _text(service.type_text(str(args.get("text") or ""), window_id(args.get("window_id"))))
    if name == "key":
        keys = args.get("keys")
        if not isinstance(keys, list):
            raise ComputerUseError("keys must be a list of key names")
        return _text(service.key(keys, window_id(args.get("window_id"))))
    if name == "invoke":
        return _text(service.invoke(window_id(args.get("window_id")), runtime_id(args.get("runtime_id"))))
    if name == "set_value":
        return _text(
            service.set_value(
                window_id(args.get("window_id")),
                runtime_id(args.get("runtime_id")),
                str(args.get("value") or ""),
            )
        )
    raise ComputerUseError(f"unknown tool {name}")


def _tool(name: str, description: str, schema: dict) -> dict:
    return {"name": name, "description": description, "inputSchema": schema}


def _text(payload: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": False,
    }


def _tool_error(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps({"ok": False, "error": message})}],
        "isError": True,
    }


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
