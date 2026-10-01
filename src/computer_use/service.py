"""Policy, audit, and coordinate mapping in front of a desktop backend."""

from datetime import datetime, timezone
import json
import sys

from computer_use import __version__
from computer_use.coords import fit_size
from computer_use.errors import ComputerUseError, PolicyError
from computer_use.keys import plan_chord, plan_text
from computer_use.models import ElementNode, Shot, WindowInfo
from computer_use.policy import Policy, policy_from_env

_MAX_TEXT = 4000
_DEFAULT_EDGE = 1600
_MIN_EDGE = 256
_MAX_EDGE = 4096
_DEFAULT_DEPTH = 3
_MAX_DEPTH = 8


class ComputerUseService:
    def __init__(self, backend, env: dict[str, str] | None = None):
        self.backend = backend
        self._env = env

    def health(self) -> dict:
        policy = self._policy()
        try:
            desktop = self.backend.describe()
        except Exception as exc:
            desktop = {"interactive": False, "detail": str(exc), "elevated": False, "dpi": "unknown"}
        return {
            "ok": True,
            "version": __version__,
            "enabled": policy.enabled,
            "kill_switch": policy.kill_switch_active(),
            "allow_processes": sorted(policy.allow_processes),
            "home": str(policy.home),
            "desktop": desktop,
        }

    def list_windows(self) -> dict:
        self._guard("list_windows", process=None, scope="any")
        windows = [window.to_dict() for window in self._visible_windows()]
        self._audit("list_windows", process=None, extra={"count": len(windows)})
        return {"ok": True, "windows": windows}

    def screenshot(self, window_id: int | None = None, max_edge: int = _DEFAULT_EDGE) -> dict:
        edge = _clamp_edge(max_edge)
        self._guard("screenshot", None, scope="any")
        window = self._window_if_any(window_id)
        scope = "process" if window is not None else "desktop"
        self._guard("screenshot", window.process if window else None, scope=scope)
        shot: Shot = self.backend.screenshot(None if window is None else window.window_id)
        png, image_w, image_h, scale = _downscale(shot, edge)
        payload = {
            "ok": True,
            "window_id": None if window is None else str(window.window_id),
            "origin_x": shot.origin_x,
            "origin_y": shot.origin_y,
            "screen_width": shot.screen_width,
            "screen_height": shot.screen_height,
            "image_width": image_w,
            "image_height": image_h,
            "scale": scale,
            "map": "screen_x = origin_x + image_x / scale; screen_y = origin_y + image_y / scale",
        }
        self._audit("screenshot", window.process if window else None, extra={"window_id": payload["window_id"]})
        return {"meta": payload, "png": png}

    def tree(self, window_id: int, max_depth: int = _DEFAULT_DEPTH) -> dict:
        self._guard("tree", None, scope="any")
        window = self._require_window(window_id)
        self._guard("tree", window.process)
        depth = max(0, min(int(max_depth), _MAX_DEPTH))
        node = self.backend.element_tree(window.window_id, depth)
        self._audit("tree", window.process, extra={"window_id": str(window.window_id), "max_depth": depth})
        return {"ok": True, "window": window.to_dict(), "tree": node.to_dict()}

    def find_elements(
        self,
        window_id: int,
        name_contains: str = "",
        control_type: str = "",
        limit: int = 20,
    ) -> dict:
        self._guard("find_elements", None, scope="any")
        window = self._require_window(window_id)
        self._guard("find_elements", window.process)
        capped = max(1, min(int(limit), 50))
        matches = self.backend.find_elements(window.window_id, name_contains, control_type, capped)
        self._audit(
            "find_elements",
            window.process,
            extra={"window_id": str(window.window_id), "count": len(matches)},
        )
        return {"ok": True, "matches": [_element_summary(item) for item in matches]}

    def focus(self, window_id: int) -> dict:
        self._guard("focus", None, scope="any")
        window = self._require_window(window_id)
        self._guard("focus", window.process)
        self._require_interactive()
        focused = self.backend.focus(window.window_id)
        self._audit("focus", focused.process, extra={"window_id": str(focused.window_id)})
        return {"ok": True, "window": focused.to_dict()}

    def click(
        self,
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        clicks: int = 1,
        window_id: int | None = None,
    ) -> dict:
        button_name = _button(button)
        repeat = _clicks(clicks)
        self._guard("click", None, scope="any")
        window = self._window_if_any(window_id)
        if window is not None and x is None and y is None:
            x, y = window.rect.center()
        if x is None or y is None:
            raise ComputerUseError("click requires x and y, or a window_id whose center can be used")
        if window is not None and not window.rect.contains(x, y):
            raise ComputerUseError("click point is outside the target window")
        process = window.process if window is not None else self.backend.process_at_point(x, y)
        self._guard("click", process)
        self._require_interactive()
        if window is not None:
            self.backend.focus(window.window_id)
        self.backend.click(x, y, button_name, repeat)
        self._audit(
            "click",
            process,
            extra={"x": x, "y": y, "button": button_name, "clicks": repeat, "window_id": _id(window)},
        )
        return {"ok": True, "x": x, "y": y, "button": button_name, "clicks": repeat, "process": process}

    def type_text(self, text: str, window_id: int | None = None) -> dict:
        if not isinstance(text, str) or text == "":
            raise ComputerUseError("text is required")
        if len(text) > _MAX_TEXT:
            raise ComputerUseError(f"text is limited to {_MAX_TEXT} characters")
        self._guard("type_text", None, scope="any")
        window = self._window_if_any(window_id)
        process = window.process if window is not None else self._foreground_process()
        self._guard("type_text", process)
        self._require_interactive()
        if window is not None:
            self.backend.focus(window.window_id)
        events = plan_text(text)
        self.backend.send_keys(events)
        self._audit("type_text", process, extra={"chars": len(text), "window_id": _id(window)})
        return {"ok": True, "chars": len(text), "process": process}

    def key(self, keys: list[str], window_id: int | None = None) -> dict:
        if not keys:
            raise ComputerUseError("keys are required")
        try:
            events = plan_chord([str(item) for item in keys])
        except ValueError as exc:
            raise ComputerUseError(str(exc)) from exc
        self._guard("key", None, scope="any")
        window = self._window_if_any(window_id)
        process = window.process if window is not None else self._foreground_process()
        self._guard("key", process)
        self._require_interactive()
        if window is not None:
            self.backend.focus(window.window_id)
        self.backend.send_keys(events)
        self._audit("key", process, extra={"keys": [str(item) for item in keys], "window_id": _id(window)})
        return {"ok": True, "keys": [str(item) for item in keys], "process": process}

    def invoke(self, window_id: int, runtime_id: list[int]) -> dict:
        self._guard("invoke", None, scope="any")
        window = self._require_window(window_id)
        identity = _runtime_id(runtime_id)
        self._guard("invoke", window.process)
        self._require_interactive()
        self.backend.invoke(window.window_id, identity)
        self._audit("invoke", window.process, extra={"window_id": str(window.window_id)})
        return {"ok": True, "window_id": str(window.window_id), "runtime_id": list(identity)}

    def set_value(self, window_id: int, runtime_id: list[int], value: str) -> dict:
        self._guard("set_value", None, scope="any")
        window = self._require_window(window_id)
        identity = _runtime_id(runtime_id)
        if not isinstance(value, str):
            raise ComputerUseError("value must be a string")
        if len(value) > _MAX_TEXT:
            raise ComputerUseError(f"value is limited to {_MAX_TEXT} characters")
        self._guard("set_value", window.process)
        self._require_interactive()
        self.backend.set_value(window.window_id, identity, value)
        self._audit("set_value", window.process, extra={"window_id": str(window.window_id), "chars": len(value)})
        return {"ok": True, "window_id": str(window.window_id), "chars": len(value)}

    def _policy(self) -> Policy:
        return policy_from_env(self._env)

    def _visible_windows(self) -> list[WindowInfo]:
        policy = self._policy()
        windows = self.backend.list_windows()
        if not policy.allow_processes:
            return windows
        return [window for window in windows if policy.allows_process(window.process)]

    def _window_if_any(self, window_id: int | None) -> WindowInfo | None:
        if window_id is None:
            return None
        return self._require_window(window_id)

    def _require_window(self, window_id: int) -> WindowInfo:
        return self.backend.window(int(window_id))

    def _foreground_process(self) -> str | None:
        window = self.backend.foreground_window()
        return None if window is None else window.process

    def _require_interactive(self) -> None:
        info = self.backend.describe()
        if not info.get("interactive"):
            detail = info.get("detail") or "This session has no interactive desktop."
            raise ComputerUseError(detail)

    def _guard(self, action: str, process: str | None, scope: str = "process") -> None:
        policy = self._policy()
        if policy.kill_switch_active():
            self._audit(action, process, denied="kill_switch")
            raise PolicyError(
                f"Kill switch is active at {policy.home / 'STOP'}. Remove that file to continue."
            )
        if not policy.enabled:
            self._audit(action, process, denied="disabled")
            raise PolicyError(
                "Computer use is disabled. Set COMPUTER_USE_ENABLED=1 or create "
                f"{policy.home / 'enabled'}."
            )
        if scope == "any":
            return
        if scope == "desktop" and policy.allow_processes:
            self._audit(action, process, denied="allowlist")
            raise PolicyError(
                "COMPUTER_USE_ALLOW_PROCESSES is set, so this action needs a window in that list."
            )
        if scope == "process" and not policy.allows_process(process):
            self._audit(action, process, denied="allowlist")
            name = process or "the target"
            raise PolicyError(f"{name} is outside COMPUTER_USE_ALLOW_PROCESSES.")

    def _audit(self, action: str, process: str | None, denied: str | None = None, extra: dict | None = None) -> None:
        policy = self._policy()
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "process": process,
            "denied": denied,
        }
        if extra:
            event.update(extra)
        try:
            policy.home.mkdir(parents=True, exist_ok=True)
            with (policy.home / "audit.log").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        except OSError as exc:
            print(f"computer-use audit log unavailable: {exc}", file=sys.stderr)


def _downscale(shot: Shot, max_edge: int) -> tuple[bytes, int, int, float]:
    image_w, image_h = fit_size(shot.screen_width, shot.screen_height, max_edge)
    if (image_w, image_h) == (shot.screen_width, shot.screen_height):
        return shot.png, image_w, image_h, 1.0
    try:
        from PIL import Image
    except ImportError:
        return shot.png, shot.screen_width, shot.screen_height, 1.0
    import io

    image = Image.open(io.BytesIO(shot.png))
    image = image.resize((image_w, image_h), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), image_w, image_h, image_w / shot.screen_width


def _element_summary(node: ElementNode) -> dict:
    data = node.to_dict()
    data.pop("children", None)
    return data


def _button(button: str) -> str:
    name = button.strip().lower()
    if name not in {"left", "right", "middle"}:
        raise ComputerUseError("button must be left, right, or middle")
    return name


def _clicks(clicks: int) -> int:
    if isinstance(clicks, bool) or not isinstance(clicks, int) or clicks < 1 or clicks > 2:
        raise ComputerUseError("clicks must be 1 or 2")
    return clicks


def _clamp_edge(max_edge: int) -> int:
    if isinstance(max_edge, bool) or not isinstance(max_edge, int):
        raise ComputerUseError("max_edge must be an integer")
    return max(_MIN_EDGE, min(max_edge, _MAX_EDGE))


def _runtime_id(values: list[int]) -> tuple[int, ...]:
    if not isinstance(values, list) or not values:
        raise ComputerUseError("runtime_id must be a non-empty list of integers")
    identity: list[int] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ComputerUseError("runtime_id must be a non-empty list of integers")
        identity.append(item)
    return tuple(identity)


def _id(window: WindowInfo | None) -> str | None:
    return None if window is None else str(window.window_id)
