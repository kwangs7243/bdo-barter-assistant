from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageGrab


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DEFAULT_GAME_TITLE_TERMS = ("검은사막", "black desert")
DEFAULT_GAME_PROCESS_TERMS = ("blackdesert", "black desert")


class WindowCaptureError(RuntimeError):
    pass


class WindowSelectionError(WindowCaptureError):
    def __init__(self, message: str, candidates: Iterable["WindowInfo"] = ()) -> None:
        super().__init__(message)
        self.candidates = tuple(candidates)


class _NativeRect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _NativePoint(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


@dataclass(frozen=True)
class ScreenRect:
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

    def as_list(self) -> list[int]:
        return [self.left, self.top, self.right, self.bottom]


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    process: str | None
    process_path: str | None
    pid: int
    window_rect: ScreenRect
    client_rect_screen: ScreenRect
    dpi: int
    visible: bool
    minimized: bool

    @property
    def client_size(self) -> tuple[int, int]:
        return (self.client_rect_screen.width, self.client_rect_screen.height)

    @property
    def scale_factor(self) -> float:
        return self.dpi / 96.0

    def to_dict(self) -> dict[str, object]:
        return {
            "hwnd": self.hwnd,
            "hwnd_hex": hex(self.hwnd),
            "title": self.title,
            "process": self.process,
            "process_path": self.process_path,
            "pid": self.pid,
            "window_rect": self.window_rect.as_list(),
            "client_rect_screen": self.client_rect_screen.as_list(),
            "client_size": list(self.client_size),
            "dpi": self.dpi,
            "scale_factor": round(self.scale_factor, 4),
            "visible": self.visible,
            "minimized": self.minimized,
        }


@dataclass(frozen=True)
class CapturedWindow:
    window: WindowInfo
    image: Image.Image


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowCaptureError("Windows window capture is only available on Windows")


def _load_user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_NativeRect)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(_NativeRect)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(_NativePoint)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    if hasattr(user32, "GetDpiForWindow"):
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT
    return user32


def configure_process_dpi_awareness() -> str:
    """Request process-local DPI-aware coordinates without changing OS settings."""
    _require_windows()
    user32 = _load_user32()
    if hasattr(user32, "SetProcessDpiAwarenessContext"):
        user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per_monitor_v2"
        # ERROR_ACCESS_DENIED means another library already fixed awareness.
        if ctypes.get_last_error() == 5:
            return "already_configured"
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.c_long
        result = shcore.SetProcessDpiAwareness(2)
        if result in (0, -2147024891):
            return "per_monitor" if result == 0 else "already_configured"
    except (AttributeError, OSError):
        pass
    if hasattr(user32, "SetProcessDPIAware") and user32.SetProcessDPIAware():
        return "system"
    return "unchanged"


def _window_title(user32: ctypes.WinDLL, hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _process_path(pid: int) -> str | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def get_window_info(hwnd: int) -> WindowInfo:
    """Read outer and client rectangles using physical screen coordinates."""
    _require_windows()
    user32 = _load_user32()
    if not user32.IsWindow(hwnd):
        raise WindowCaptureError(f"window does not exist: {hwnd}")

    window_rect = _NativeRect()
    client_rect = _NativeRect()
    if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
        raise WindowCaptureError(f"GetWindowRect failed for hwnd {hwnd}")
    if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
        raise WindowCaptureError(f"GetClientRect failed for hwnd {hwnd}")
    client_top_left = _NativePoint(client_rect.left, client_rect.top)
    client_bottom_right = _NativePoint(client_rect.right, client_rect.bottom)
    if not user32.ClientToScreen(hwnd, ctypes.byref(client_top_left)):
        raise WindowCaptureError(f"ClientToScreen failed for hwnd {hwnd}")
    if not user32.ClientToScreen(hwnd, ctypes.byref(client_bottom_right)):
        raise WindowCaptureError(f"ClientToScreen failed for hwnd {hwnd}")

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_path = _process_path(pid.value)
    dpi = 96
    if hasattr(user32, "GetDpiForWindow"):
        measured_dpi = int(user32.GetDpiForWindow(hwnd))
        if measured_dpi > 0:
            dpi = measured_dpi
    return WindowInfo(
        hwnd=int(hwnd),
        title=_window_title(user32, hwnd),
        process=Path(process_path).name if process_path else None,
        process_path=process_path,
        pid=int(pid.value),
        window_rect=ScreenRect(
            window_rect.left, window_rect.top, window_rect.right, window_rect.bottom
        ),
        client_rect_screen=ScreenRect(
            client_top_left.x,
            client_top_left.y,
            client_bottom_right.x,
            client_bottom_right.y,
        ),
        dpi=dpi,
        visible=bool(user32.IsWindowVisible(hwnd)),
        minimized=bool(user32.IsIconic(hwnd)),
    )


def enumerate_top_level_windows() -> list[WindowInfo]:
    """Enumerate visible, titled, non-empty top-level client windows."""
    _require_windows()
    configure_process_dpi_awareness()
    user32 = _load_user32()
    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            handles.append(int(hwnd))
        return True

    ctypes.set_last_error(0)
    if not user32.EnumWindows(callback, 0):
        error_code = ctypes.get_last_error()
        # An isolated Windows desktop can expose no HWNDs and return zero
        # without setting an API error. Treat that as an empty enumeration.
        if error_code:
            raise WindowCaptureError(f"EnumWindows failed with error {error_code}")
    windows: list[WindowInfo] = []
    for hwnd in handles:
        try:
            info = get_window_info(hwnd)
        except WindowCaptureError:
            continue
        if info.client_rect_screen.width > 0 and info.client_rect_screen.height > 0:
            windows.append(info)
    return windows


def filter_windows(
    windows: Iterable[WindowInfo],
    *,
    title: str | None = None,
    process: str | None = None,
    game_only: bool = False,
) -> list[WindowInfo]:
    title_query = title.casefold() if title else None
    process_query = process.casefold() if process else None
    result: list[WindowInfo] = []
    for window in windows:
        folded_title = window.title.casefold()
        folded_process = (window.process or "").casefold()
        if title_query and title_query not in folded_title:
            continue
        if process_query and process_query not in folded_process:
            continue
        if game_only and not (
            any(term in folded_title for term in DEFAULT_GAME_TITLE_TERMS)
            or any(term in folded_process for term in DEFAULT_GAME_PROCESS_TERMS)
        ):
            continue
        result.append(window)
    return result


def select_window(
    windows: Iterable[WindowInfo],
    *,
    hwnd: int | None = None,
    title: str | None = None,
    process: str | None = None,
) -> WindowInfo:
    available = list(windows)
    if hwnd is not None:
        matches = [window for window in available if window.hwnd == hwnd]
    else:
        matches = filter_windows(
            available,
            title=title,
            process=process,
            game_only=title is None and process is None,
        )
    if not matches:
        raise WindowSelectionError("no matching game window was found", available)
    if len(matches) > 1:
        raise WindowSelectionError(
            "multiple matching windows found; select one with --hwnd", matches
        )
    return matches[0]


def capture_client_area(
    window: WindowInfo,
    *,
    grabber: Callable[[tuple[int, int, int, int]], Image.Image] | None = None,
) -> CapturedWindow:
    """Capture the currently visible desktop pixels for a window client area."""
    if window.minimized:
        raise WindowCaptureError("cannot capture a minimized window")
    rect = window.client_rect_screen
    if rect.width <= 0 or rect.height <= 0:
        raise WindowCaptureError("window client area is empty")
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    if grabber is None:
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
    else:
        image = grabber(bbox)
    image = image.convert("RGB")
    if image.size != (rect.width, rect.height):
        raise WindowCaptureError(
            f"capture size {image.size} does not match client size "
            f"{(rect.width, rect.height)}"
        )
    return CapturedWindow(window=window, image=image)
