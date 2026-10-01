"""Command line entry for one-shot actions and the MCP server."""

import argparse
import json
import sys

from computer_use.errors import ComputerUseError, PolicyError
from computer_use.mcp_server import serve
from computer_use.parsing import runtime_id
from computer_use.service import ComputerUseService


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    service = ComputerUseService(_backend(), env)
    try:
        if args.command == "mcp":
            print("computer-use MCP server on stdin. No port is opened.", file=sys.stderr)
            serve(service, sys.stdin.buffer, sys.stdout.buffer)
            return 0
        payload = _run(service, args)
    except (PolicyError, ComputerUseError) as exc:
        return _fail(str(exc), 2 if isinstance(exc, PolicyError) else 1)
    except KeyboardInterrupt:
        return _fail("interrupted", 1)
    if args.command == "screenshot" and args.output:
        args.output.write_bytes(payload.pop("png"))
        payload["meta"]["saved"] = str(args.output)
        _emit(payload["meta"])
        return 0
    if args.command == "screenshot":
        _emit(payload["meta"])
        return 0
    _emit(payload)
    return 0


def _run(service: ComputerUseService, args) -> dict:
    if args.command == "health":
        return service.health()
    if args.command == "windows":
        return service.list_windows()
    if args.command == "screenshot":
        return service.screenshot(args.window, args.max_edge)
    if args.command == "tree":
        return service.tree(args.window, args.max_depth)
    if args.command == "find":
        return service.find_elements(args.window, args.name or "", args.control_type or "", args.limit)
    if args.command == "focus":
        return service.focus(args.window)
    if args.command == "click":
        return service.click(args.x, args.y, args.button, args.clicks, args.window)
    if args.command == "type":
        return service.type_text(args.text, args.window)
    if args.command == "key":
        return service.key(args.keys, args.window)
    if args.command == "invoke":
        return service.invoke(args.window, runtime_id(args.runtime_id))
    if args.command == "set-value":
        return service.set_value(args.window, runtime_id(args.runtime_id), args.value)
    raise ComputerUseError(f"unknown command {args.command}")


def _backend():
    if sys.platform == "win32":
        from computer_use.win32.backend import WindowsBackend

        return WindowsBackend()
    from computer_use.unsupported import UnsupportedBackend

    return UnsupportedBackend()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="computer-use",
        description="Opt-in Windows desktop control for an always-on agent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="Show enablement, the kill switch, and desktop status")
    sub.add_parser("windows", help="List visible windows")
    sub.add_parser("mcp", help="Serve MCP tools on stdin")

    shot = sub.add_parser("screenshot", help="Capture the desktop or one window")
    _window(shot, required=False)
    shot.add_argument("--max-edge", type=int, default=1600)
    shot.add_argument("--output", type=_path)

    tree = sub.add_parser("tree", help="Read a window's UI Automation tree")
    _window(tree, required=True)
    tree.add_argument("--max-depth", type=int, default=3)

    find = sub.add_parser("find", help="Find elements by name")
    _window(find, required=True)
    find.add_argument("--name", default="")
    find.add_argument("--control-type", default="")
    find.add_argument("--limit", type=int, default=20)

    focus = sub.add_parser("focus", help="Bring a window to the foreground")
    _window(focus, required=True)

    click = sub.add_parser("click", help="Click a screen point or a window center")
    _window(click, required=False)
    click.add_argument("--x", type=int)
    click.add_argument("--y", type=int)
    click.add_argument("--button", default="left", choices=("left", "right", "middle"))
    click.add_argument("--clicks", type=int, default=1, choices=(1, 2))

    typed = sub.add_parser("type", help="Type text")
    _window(typed, required=False)
    typed.add_argument("--text", required=True)

    key = sub.add_parser("key", help="Press a key chord")
    _window(key, required=False)
    key.add_argument("keys", nargs="+")

    invoke = sub.add_parser("invoke", help="Invoke a UI Automation element")
    _window(invoke, required=True)
    invoke.add_argument("--runtime-id", required=True)

    value = sub.add_parser("set-value", help="Set a UI Automation value")
    _window(value, required=True)
    value.add_argument("--runtime-id", required=True)
    value.add_argument("--value", required=True)
    return parser


def _window(parser: argparse.ArgumentParser, required: bool) -> None:
    parser.add_argument("--window", type=int, required=required, help="Window hwnd")


def _path(value: str):
    from pathlib import Path

    return Path(value)


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def _fail(message: str, code: int) -> int:
    sys.stdout.write(json.dumps({"ok": False, "error": message}) + "\n")
    return code
