"""UI Automation tree, invoke, and value. pywinauto is imported when a call needs it."""

import sys

from computer_use.errors import ComputerUseError
from computer_use.models import ElementNode, Rect
from computer_use.win32 import desktop

_MAX_NODES = 300
_MAX_CHILDREN = 40
_SEARCH_NODES = 800


def element_tree(window_id: int, max_depth: int) -> ElementNode:
    root = _wrapper(window_id)
    budget = {"nodes": _MAX_NODES}
    names = _names()
    return _node(root, max_depth, budget, names)


def find_elements(window_id: int, name_contains: str, control_type: str, limit: int) -> list[ElementNode]:
    root = _wrapper(window_id)
    needle = name_contains.strip().lower()
    kind = control_type.strip().lower()
    found: list[ElementNode] = []
    budget = {"nodes": _SEARCH_NODES}
    names = _names()

    def visit(wrapper, depth: int) -> None:
        if len(found) >= limit or budget["nodes"] <= 0:
            return
        budget["nodes"] -= 1
        node = _summary(wrapper, names)
        name_ok = not needle or needle in node.name.lower()
        type_ok = not kind or node.control_type.lower() == kind
        if name_ok and type_ok:
            found.append(node)
        if depth <= 0:
            return
        for child in _children(wrapper):
            visit(child, depth - 1)

    visit(root, 12)
    return found


def invoke(window_id: int, runtime_id: tuple[int, ...]) -> None:
    target = _find(window_id, runtime_id)
    try:
        target.iface_invoke.Invoke()
    except Exception as exc:
        raise ComputerUseError(f"That element has no Invoke pattern ({exc}).") from exc


def set_value(window_id: int, runtime_id: tuple[int, ...], value: str) -> None:
    target = _find(window_id, runtime_id)
    try:
        target.iface_value.SetValue(value)
    except Exception as exc:
        raise ComputerUseError(f"That element has no Value pattern ({exc}).") from exc


def _find(window_id: int, runtime_id: tuple[int, ...]):
    root = _wrapper(window_id)
    budget = {"nodes": _SEARCH_NODES}

    def visit(wrapper):
        if budget["nodes"] <= 0:
            return None
        budget["nodes"] -= 1
        if _runtime_id(wrapper) == runtime_id:
            return wrapper
        for child in _children(wrapper):
            found = visit(child)
            if found is not None:
                return found
        return None

    found = visit(root)
    if found is None:
        raise ComputerUseError("No element with that runtime_id is visible in the window.")
    return found


def _node(wrapper, depth: int, budget: dict, names: dict[int, str]) -> ElementNode:
    budget["nodes"] -= 1
    summary = _summary(wrapper, names)
    children: list[ElementNode] = []
    if depth > 0 and budget["nodes"] > 0:
        for child in _children(wrapper)[:_MAX_CHILDREN]:
            if budget["nodes"] <= 0:
                break
            children.append(_node(child, depth - 1, budget, names))
    return ElementNode(
        name=summary.name,
        control_type=summary.control_type,
        runtime_id=summary.runtime_id,
        rect=summary.rect,
        process=summary.process,
        process_id=summary.process_id,
        enabled=summary.enabled,
        children=tuple(children),
    )


def _summary(wrapper, names: dict[int, str]) -> ElementNode:
    info = wrapper.element_info
    pid = _int(getattr(info, "process_id", 0))
    if pid not in names:
        try:
            names[pid] = desktop.process_name(pid)
        except Exception:
            names[pid] = ""
    return ElementNode(
        name=_str(getattr(info, "name", "")),
        control_type=_str(getattr(info, "control_type", "")),
        runtime_id=_runtime_id(wrapper),
        rect=_rect(wrapper),
        process=names.get(pid, ""),
        process_id=pid,
        enabled=_enabled(wrapper),
    )


def _wrapper(window_id: int):
    if sys.platform != "win32":
        raise ComputerUseError("UI Automation runs on Windows.")
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise ComputerUseError("Install the Windows extras with: pip install -e .") from exc
    try:
        return Desktop(backend="uia").window(handle=window_id).wrapper_object()
    except Exception as exc:
        raise ComputerUseError(f"Could not read UI Automation for window {window_id} ({exc}).") from exc


def _children(wrapper) -> list:
    try:
        return list(wrapper.children())
    except Exception:
        return []


def _runtime_id(wrapper) -> tuple[int, ...]:
    try:
        raw = wrapper.element_info.runtime_id
    except Exception:
        return ()
    if not raw:
        return ()
    try:
        return tuple(int(part) for part in raw)
    except (TypeError, ValueError):
        return ()


def _rect(wrapper) -> Rect:
    try:
        rect = wrapper.rectangle()
        return Rect(int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception:
        return Rect(0, 0, 0, 0)


def _enabled(wrapper) -> bool:
    try:
        return bool(wrapper.is_enabled())
    except Exception:
        return True


def _names() -> dict[int, str]:
    return {}


def _str(value) -> str:
    return "" if value is None else str(value)


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
