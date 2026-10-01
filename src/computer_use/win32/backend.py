"""Windows implementation of the desktop backend used by the service."""

from computer_use.keys import KeyEvent
from computer_use.models import ElementNode, Shot, WindowInfo
from computer_use.win32 import capture, desktop, input as wininput
from computer_use.win32 import uia


class WindowsBackend:
    def describe(self) -> dict:
        return desktop.describe()

    def list_windows(self) -> list[WindowInfo]:
        return desktop.list_windows()

    def window(self, window_id: int) -> WindowInfo:
        return desktop.window_info(window_id)

    def foreground_window(self) -> WindowInfo | None:
        return desktop.foreground_window()

    def process_at_point(self, x: int, y: int) -> str:
        return desktop.process_at_point(x, y)

    def screenshot(self, window_id: int | None) -> Shot:
        rect = None if window_id is None else desktop.window_info(window_id).rect
        return capture.screenshot(window_id, rect)

    def element_tree(self, window_id: int, max_depth: int) -> ElementNode:
        return uia.element_tree(window_id, max_depth)

    def find_elements(self, window_id: int, name_contains: str, control_type: str, limit: int) -> list[ElementNode]:
        return uia.find_elements(window_id, name_contains, control_type, limit)

    def focus(self, window_id: int) -> WindowInfo:
        return desktop.set_foreground(window_id)

    def click(self, x: int, y: int, button: str, clicks: int) -> None:
        wininput.click_at(x, y, button, clicks)

    def send_keys(self, events: list[KeyEvent]) -> None:
        wininput.send_events(events)

    def invoke(self, window_id: int, runtime_id: tuple[int, ...]) -> None:
        uia.invoke(window_id, runtime_id)

    def set_value(self, window_id: int, runtime_id: tuple[int, ...], value: str) -> None:
        uia.set_value(window_id, runtime_id, value)
