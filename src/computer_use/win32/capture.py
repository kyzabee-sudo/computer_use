"""Screenshot the virtual desktop or one window."""

import sys

from computer_use.errors import ComputerUseError
from computer_use.models import Rect, Shot
from computer_use.win32 import desktop


def screenshot(window_id: int | None, rect: Rect | None) -> Shot:
    if sys.platform != "win32":
        raise ComputerUseError("Screenshots run on Windows.")
    try:
        import mss
    except ImportError as exc:
        raise ComputerUseError("Install the Windows extras with: pip install -e .") from exc
    with mss.mss() as sct:
        if window_id is None:
            monitor = sct.monitors[0]
            region = {
                "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
            }
        else:
            if rect is None or rect.width <= 0 or rect.height <= 0:
                raise ComputerUseError("That window has no visible bounds to capture.")
            if desktop.is_minimized(window_id):
                raise ComputerUseError("That window is minimized. Focus it before capturing.")
            region = {"left": rect.left, "top": rect.top, "width": rect.width, "height": rect.height}
        grabbed = sct.grab(region)
        png = mss.tools.to_png(grabbed.rgb, grabbed.size)
    return Shot(
        png=png,
        screen_width=int(region["width"]),
        screen_height=int(region["height"]),
        origin_x=int(region["left"]),
        origin_y=int(region["top"]),
    )
