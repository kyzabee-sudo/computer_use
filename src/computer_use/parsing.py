"""Argument parsing shared by the CLI and the MCP tools."""

from computer_use.errors import ComputerUseError


def window_id(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ComputerUseError("window_id must be an integer hwnd")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    raise ComputerUseError("window_id must be an integer hwnd")


def runtime_id(value) -> list[int]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        try:
            return [int(part) for part in parts]
        except ValueError as exc:
            raise ComputerUseError("runtime_id must be a list of integers") from exc
    if isinstance(value, list):
        return value
    raise ComputerUseError("runtime_id must be a list of integers")


def as_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        raise ComputerUseError(f"{name} must be an integer")
    return value
