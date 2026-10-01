"""Top-level windows, process names, and the interactive-session check."""

import ctypes
from ctypes import wintypes
import sys

from computer_use.errors import ComputerUseError
from computer_use.models import Rect, WindowInfo

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
GW_OWNER = 4
GA_ROOT = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DESKTOP_READOBJECTS = 0x0001


class POINT(ctypes.Structure):
    _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))


def describe() -> dict:
    _require_windows()
    interactive, detail = _interactive_desktop()
    return {
        "interactive": interactive,
        "detail": detail,
        "elevated": _is_elevated(),
        "dpi": _enable_dpi_awareness(),
        "platform": "win32",
    }


def list_windows() -> list[WindowInfo]:
    _require_windows()
    user32, _kernel32 = _bind()
    found: list[WindowInfo] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _lparam):
        if _is_listed_window(hwnd):
            try:
                found.append(window_info(int(hwnd)))
            except ComputerUseError:
                pass
        return True

    callback = enum_proc(visit)
    user32.EnumWindows.argtypes = (enum_proc, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    if not user32.EnumWindows(callback, 0):
        err = ctypes.windll.kernel32.GetLastError()
        if not found:
            raise ComputerUseError(f"EnumWindows failed (winerror {err}).")
    return found


def window_info(hwnd: int) -> WindowInfo:
    _require_windows()
    user32, _kernel32 = _bind()
    if not user32.IsWindow(hwnd):
        raise ComputerUseError(f"window {hwnd} is not open")
    title = _text(user32.GetWindowTextW, user32.GetWindowTextLengthW, hwnd)
    class_name = _class_name(hwnd)
    pid = _pid(hwnd)
    return WindowInfo(
        window_id=int(hwnd),
        title=title or class_name,
        process=process_name(pid),
        process_id=pid,
        rect=_rect(hwnd),
        class_name=class_name,
    )


def foreground_window() -> WindowInfo | None:
    _require_windows()
    user32, _kernel32 = _bind()
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    try:
        return window_info(int(hwnd))
    except ComputerUseError:
        return None


def process_at_point(x: int, y: int) -> str:
    _require_windows()
    user32, _kernel32 = _bind()
    hwnd = user32.WindowFromPoint(POINT(x, y))
    if hwnd:
        root = user32.GetAncestor(hwnd, GA_ROOT)
        hwnd = root or hwnd
    if not hwnd:
        raise ComputerUseError(f"no window at {x}, {y}")
    return process_name(_pid(int(hwnd)))


def set_foreground(hwnd: int) -> WindowInfo:
    _require_windows()
    user32, kernel32 = _bind()
    info = window_info(hwnd)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    current = user32.GetForegroundWindow()
    attached = False
    foreground_thread = 0
    if current and int(current) != int(hwnd):
        ignored = wintypes.DWORD()
        foreground_thread = int(user32.GetWindowThreadProcessId(current, ctypes.byref(ignored)))
        this_thread = int(kernel32.GetCurrentThreadId())
        attached = bool(user32.AttachThreadInput(this_thread, foreground_thread, True))
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if attached:
        user32.AttachThreadInput(int(kernel32.GetCurrentThreadId()), foreground_thread, False)
    return info


def is_minimized(hwnd: int) -> bool:
    _require_windows()
    user32, _kernel32 = _bind()
    return bool(user32.IsIconic(hwnd))


def process_name(pid: int) -> str:
    _require_windows()
    if pid <= 0:
        return ""
    _user32, kernel32 = _bind()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        path = buffer.value
        name = path.rsplit("\\", 1)[-1]
        return name
    finally:
        kernel32.CloseHandle(handle)


def _is_listed_window(hwnd: int) -> bool:
    user32, _kernel32 = _bind()
    if not user32.IsWindowVisible(hwnd):
        return False
    if _cloaked(hwnd):
        return False
    style = _ex_style(hwnd)
    if style & WS_EX_TOOLWINDOW and not style & WS_EX_APPWINDOW:
        return False
    title = _text(user32.GetWindowTextW, user32.GetWindowTextLengthW, hwnd)
    owner = user32.GetWindow(hwnd, GW_OWNER)
    if owner and not (style & WS_EX_APPWINDOW):
        return False
    return bool(title)


def _rect(hwnd: int) -> Rect:
    user32, _kernel32 = _bind()
    bounds = wintypes.RECT()
    dwmapi = _dwmapi()
    if dwmapi is not None:
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(bounds),
            ctypes.sizeof(bounds),
        )
        if hr == 0 and (bounds.right > bounds.left) and (bounds.bottom > bounds.top):
            return Rect(int(bounds.left), int(bounds.top), int(bounds.right), int(bounds.bottom))
    if not user32.GetWindowRect(hwnd, ctypes.byref(bounds)):
        raise ComputerUseError(f"could not read the bounds of window {hwnd}")
    return Rect(int(bounds.left), int(bounds.top), int(bounds.right), int(bounds.bottom))


def _interactive_desktop() -> tuple[bool, str]:
    user32, kernel32 = _bind()
    session = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session)):
        return False, "Could not read the Windows session id."
    if session.value == 0:
        return False, "This process is in Session 0, which has no interactive desktop. Run it in the signed-in user session."
    desktop = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not desktop:
        err = kernel32.GetLastError()
        return False, f"The input desktop is unavailable. Unlock the session and try again (winerror {err})."
    user32.CloseDesktop(desktop)
    return True, "Interactive desktop is available."


def _is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


_DPI: str | None = None


def _enable_dpi_awareness() -> str:
    global _DPI
    if _DPI:
        return _DPI
    user32, _kernel32 = _bind()
    mode = "system"
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            mode = "per-monitor-v2"
    except Exception:
        mode = "system"
    if mode == "system":
        try:
            shcore = ctypes.windll.shcore
            shcore.SetProcessDpiAwareness.argtypes = (ctypes.c_int,)
            shcore.SetProcessDpiAwareness.restype = ctypes.c_int
            if shcore.SetProcessDpiAwareness(2) == 0:
                mode = "per-monitor"
        except Exception:
            pass
    if mode == "system":
        try:
            user32.SetProcessDPIAware()
        except Exception:
            mode = "unknown"
    _DPI = mode
    return mode


def _cloaked(hwnd: int) -> bool:
    dwmapi = _dwmapi()
    if dwmapi is None:
        return False
    cloaked = wintypes.DWORD()
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return hr == 0 and cloaked.value != 0


def _ex_style(hwnd: int) -> int:
    user32, _kernel32 = _bind()
    try:
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        return int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) or 0)
    except Exception:
        user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetWindowLongW.restype = wintypes.LONG
        return int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) or 0)


def _pid(hwnd: int) -> int:
    user32, _kernel32 = _bind()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _class_name(hwnd: int) -> str:
    user32, _kernel32 = _bind()
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _text(getter, length_getter, hwnd: int) -> str:
    length = int(length_getter(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    getter(hwnd, buffer, length + 1)
    return buffer.value


_BOUND = False
_DWMAPI = None
_DWMAPI_LOOKED = False


def _bind():
    global _BOUND
    _require_windows()
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if _BOUND:
        return user32, kernel32
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = (POINT,)
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
    user32.CloseDesktop.restype = wintypes.BOOL
    kernel32.GetCurrentProcessId.argtypes = ()
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    kernel32.GetCurrentThreadId.argtypes = ()
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.ProcessIdToSessionId.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.GetLastError.argtypes = ()
    kernel32.GetLastError.restype = wintypes.DWORD
    _BOUND = True
    return user32, kernel32


def _dwmapi():
    global _DWMAPI, _DWMAPI_LOOKED
    if _DWMAPI_LOOKED:
        return _DWMAPI
    _DWMAPI_LOOKED = True
    try:
        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmGetWindowAttribute.argtypes = (
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
        _DWMAPI = dwmapi
    except Exception:
        _DWMAPI = None
    return _DWMAPI


def _require_windows() -> None:
    if sys.platform != "win32":
        raise ComputerUseError("Window listing runs on Windows.")
