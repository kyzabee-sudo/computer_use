"""Turn text and key chords into keyboard events. No OS calls."""

from dataclasses import dataclass

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_DELETE = 0x2E
VK_LWIN = 0x5B

_NAMED = {
    "backspace": VK_BACK,
    "bksp": VK_BACK,
    "tab": VK_TAB,
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "shift": VK_SHIFT,
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "alt": VK_MENU,
    "menu": VK_MENU,
    "esc": VK_ESCAPE,
    "escape": VK_ESCAPE,
    "space": VK_SPACE,
    "spacebar": VK_SPACE,
    "pageup": VK_PRIOR,
    "pgup": VK_PRIOR,
    "pagedown": VK_NEXT,
    "pgdn": VK_NEXT,
    "end": VK_END,
    "home": VK_HOME,
    "left": VK_LEFT,
    "up": VK_UP,
    "right": VK_RIGHT,
    "down": VK_DOWN,
    "delete": VK_DELETE,
    "del": VK_DELETE,
    "win": VK_LWIN,
    "meta": VK_LWIN,
    "super": VK_LWIN,
    "-": 0xBD,
    "=": 0xBB,
    ",": 0xBC,
    ".": 0xBE,
    ";": 0xBA,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    "'": 0xDE,
}


@dataclass(frozen=True)
class KeyEvent:
    kind: str
    value: int
    keyup: bool


def name_to_vk(name: str) -> int:
    key = name.strip().lower()
    if not key:
        raise ValueError("empty key name")
    if key in _NAMED:
        return _NAMED[key]
    if len(key) >= 2 and key[0] == "f" and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    if len(key) == 1 and "a" <= key <= "z":
        return ord(key.upper())
    if len(key) == 1 and "0" <= key <= "9":
        return ord(key)
    raise ValueError(f"unknown key {name!r}")


def plan_chord(keys: list[str]) -> list[KeyEvent]:
    if not keys:
        raise ValueError("key chord is empty")
    if len(keys) > 6:
        raise ValueError("key chord is limited to 6 keys")
    vks = [name_to_vk(key) for key in keys]
    down = [KeyEvent("vk", vk, False) for vk in vks]
    up = [KeyEvent("vk", vk, True) for vk in reversed(vks)]
    return down + up


def plan_text(text: str) -> list[KeyEvent]:
    events: list[KeyEvent] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
            events.extend(_tap(VK_RETURN))
            index += 2
            continue
        if char in "\r\n":
            events.extend(_tap(VK_RETURN))
        elif char == "\t":
            events.extend(_tap(VK_TAB))
        else:
            for unit in _utf16_units(char):
                events.append(KeyEvent("unicode", unit, False))
                events.append(KeyEvent("unicode", unit, True))
        index += 1
    return events


def _tap(vk: int) -> list[KeyEvent]:
    return [KeyEvent("vk", vk, False), KeyEvent("vk", vk, True)]


def _utf16_units(char: str) -> list[int]:
    raw = char.encode("utf-16-le")
    return [int.from_bytes(raw[offset : offset + 2], "little") for offset in range(0, len(raw), 2)]
