"""Screen and image coordinate helpers. These stay free of Windows APIs."""


def fit_size(width: int, height: int, max_edge: int) -> tuple[int, int]:
    """Return a size that keeps aspect ratio with neither edge above max_edge."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if max_edge <= 0:
        raise ValueError("max_edge must be positive")
    longest = max(width, height)
    if longest <= max_edge:
        return width, height
    scale = max_edge / longest
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def image_to_screen(image_x: float, image_y: float, origin_x: int, origin_y: int, scale: float) -> tuple[float, float]:
    """Map a pixel in a (possibly scaled) screenshot back to screen coordinates."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    return origin_x + (image_x / scale), origin_y + (image_y / scale)


def absolute_mouse(x: int, y: int, origin_x: int, origin_y: int, width: int, height: int) -> tuple[int, int]:
    """Map a screen point onto the 0..65535 range SendInput expects for the virtual desktop."""
    if width <= 0 or height <= 0:
        raise ValueError("virtual screen size must be positive")
    ax = round((x - origin_x) * 65535 / max(width - 1, 1))
    ay = round((y - origin_y) * 65535 / max(height - 1, 1))
    return _clamp(ax), _clamp(ay)


def _clamp(value: int) -> int:
    return max(0, min(65535, value))
