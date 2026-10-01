"""Desktop facts shared by the service and the Windows backend."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def center(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    def to_dict(self) -> dict:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class WindowInfo:
    window_id: int
    title: str
    process: str
    process_id: int
    rect: Rect
    class_name: str

    def to_dict(self) -> dict:
        return {
            "window_id": str(self.window_id),
            "title": self.title,
            "process": self.process,
            "process_id": self.process_id,
            "class_name": self.class_name,
            "rect": self.rect.to_dict(),
        }


@dataclass(frozen=True)
class Shot:
    png: bytes
    screen_width: int
    screen_height: int
    origin_x: int
    origin_y: int


@dataclass(frozen=True)
class ElementNode:
    name: str
    control_type: str
    runtime_id: tuple[int, ...]
    rect: Rect
    process: str
    process_id: int
    enabled: bool
    children: tuple["ElementNode", ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "control_type": self.control_type,
            "runtime_id": list(self.runtime_id),
            "rect": self.rect.to_dict(),
            "process": self.process,
            "process_id": self.process_id,
            "enabled": self.enabled,
            "children": [child.to_dict() for child in self.children],
        }
