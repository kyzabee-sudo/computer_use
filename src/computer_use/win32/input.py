"""SendInput wrappers. Struct layouts are checked on any 64-bit Python."""

import ctypes
import sys

from computer_use.coords import absolute_mouse
from computer_use.errors import ComputerUseError
from computer_use.keys import KeyEvent

# Windows is LLP64: LONG and DWORD stay 32-bit on 64-bit Windows.
# ctypes.wintypes uses the host C ABI, which is LP64 on Linux, so these
# aliases keep the SendInput layout correct on the machine that runs it.
LONG = ctypes.c_int32
DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
UINT = ctypes.c_uint32
ULONG_PTR = ctypes.c_void_p

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", DWORD),
        ("wParamL", WORD),
        ("wParamH", WORD),
    )


class INPUTUNION(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", DWORD),
        ("union", INPUTUNION),
    )


def click_at(x: int, y: int, button: str, clicks: int) -> None:
    _require_windows()
    down, up = _BUTTONS[button]
    origin_x, origin_y, width, height = _virtual_screen()
    ax, ay = absolute_mouse(x, y, origin_x, origin_y, width, height)
    placed = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    events = [_mouse(ax, ay, MOUSEEVENTF_MOVE | placed)]
    for _ in range(clicks):
        events.append(_mouse(ax, ay, down | placed))
        events.append(_mouse(ax, ay, up | placed))
    _send(events)


def send_events(events: list[KeyEvent]) -> None:
    _require_windows()
    inputs: list[INPUT] = []
    for event in events:
        if event.kind == "unicode":
            flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if event.keyup else 0)
            inputs.append(_key(0, event.value, flags))
        elif event.kind == "vk":
            flags = KEYEVENTF_KEYUP if event.keyup else 0
            inputs.append(_key(event.value, 0, flags))
        else:
            raise ComputerUseError(f"unknown key event {event.kind}")
    _send(inputs)


def _mouse(x: int, y: int, flags: int) -> INPUT:
    event = INPUT(type=INPUT_MOUSE)
    event.union.mi = MOUSEINPUT(dx=x, dy=y, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None)
    return event


def _key(vk: int, scan: int, flags: int) -> INPUT:
    event = INPUT(type=INPUT_KEYBOARD)
    event.union.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    return event


def _send(events: list[INPUT]) -> None:
    if not events:
        return
    user32 = ctypes.windll.user32
    user32.SendInput.argtypes = (UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = UINT
    batch = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), batch, ctypes.sizeof(INPUT))
    if sent != len(events):
        err = ctypes.windll.kernel32.GetLastError()
        raise ComputerUseError(f"SendInput delivered {sent} of {len(events)} events (winerror {err}).")


def _virtual_screen() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
    user32.GetSystemMetrics.restype = ctypes.c_int
    return (
        int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)),
    )


def _require_windows() -> None:
    if sys.platform != "win32":
        raise ComputerUseError("Mouse and keyboard input run on Windows.")
