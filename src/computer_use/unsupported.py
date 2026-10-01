"""Desktop backend used on anything other than Windows."""

from computer_use.errors import ComputerUseError


_DETAIL = (
    "Windows desktop control runs on Windows, in a signed-in interactive session. "
    "This process is not on Windows."
)


class UnsupportedBackend:
    def describe(self) -> dict:
        return {
            "interactive": False,
            "detail": _DETAIL,
            "elevated": False,
            "dpi": "unavailable",
            "platform": "unsupported",
        }

    def list_windows(self):
        raise ComputerUseError(_DETAIL)

    def window(self, window_id: int):
        raise ComputerUseError(_DETAIL)

    def foreground_window(self):
        return None

    def process_at_point(self, x: int, y: int) -> str:
        raise ComputerUseError(_DETAIL)

    def screenshot(self, window_id: int | None):
        raise ComputerUseError(_DETAIL)

    def element_tree(self, window_id: int, max_depth: int):
        raise ComputerUseError(_DETAIL)

    def find_elements(self, window_id: int, name_contains: str, control_type: str, limit: int):
        raise ComputerUseError(_DETAIL)

    def focus(self, window_id: int):
        raise ComputerUseError(_DETAIL)

    def click(self, x: int, y: int, button: str, clicks: int) -> None:
        raise ComputerUseError(_DETAIL)

    def send_keys(self, events) -> None:
        raise ComputerUseError(_DETAIL)

    def invoke(self, window_id: int, runtime_id: tuple[int, ...]) -> None:
        raise ComputerUseError(_DETAIL)

    def set_value(self, window_id: int, runtime_id: tuple[int, ...], value: str) -> None:
        raise ComputerUseError(_DETAIL)
