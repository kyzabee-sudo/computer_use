import base64

from computer_use.errors import ComputerUseError
from computer_use.models import ElementNode, Rect, Shot, WindowInfo

MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeDesktop:
    def __init__(self):
        self.clicks = []
        self.keys = []
        self.focused = []
        self.shots = []
        self.interactive = True
        self.foreground = WindowInfo(1, "Notes", "notepad.exe", 10, Rect(0, 0, 100, 80), "Notepad")
        self.windows = [
            self.foreground,
            WindowInfo(2, "Browser", "chrome.exe", 11, Rect(200, 0, 400, 300), "Chrome"),
        ]
        self.shot = Shot(png=MIN_PNG, screen_width=2, screen_height=2, origin_x=0, origin_y=0)

    def describe(self) -> dict:
        return {"interactive": self.interactive, "detail": "fake", "elevated": False, "dpi": "test"}

    def list_windows(self):
        return list(self.windows)

    def window(self, window_id: int) -> WindowInfo:
        for item in self.windows:
            if item.window_id == window_id:
                return item
        raise ComputerUseError(f"window {window_id} is not open")

    def foreground_window(self):
        return self.foreground

    def process_at_point(self, x: int, y: int) -> str:
        return self.foreground.process

    def screenshot(self, window_id: int | None) -> Shot:
        self.shots.append(window_id)
        return self.shot

    def element_tree(self, window_id: int, max_depth: int) -> ElementNode:
        return ElementNode("Notes", "Window", (1, 2), Rect(0, 0, 10, 10), "notepad.exe", 10, True)

    def find_elements(self, window_id: int, name_contains: str, control_type: str, limit: int):
        return [ElementNode("Save", "Button", (1, 2, 3), Rect(1, 1, 9, 9), "notepad.exe", 10, True)]

    def focus(self, window_id: int) -> WindowInfo:
        self.focused.append(window_id)
        return self.window(window_id)

    def click(self, x: int, y: int, button: str, clicks: int) -> None:
        self.clicks.append((x, y, button, clicks))

    def send_keys(self, events) -> None:
        self.keys.append(list(events))

    def invoke(self, window_id: int, runtime_id: tuple[int, ...]) -> None:
        self.invoked = (window_id, runtime_id)

    def set_value(self, window_id: int, runtime_id: tuple[int, ...], value: str) -> None:
        self.value = (window_id, runtime_id, value)
