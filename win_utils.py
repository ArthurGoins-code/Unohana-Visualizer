"""Win32 helper: keep the Qt overlay behaving like wallpaper on Windows.

Windows has no equivalent of the EWMH "sticky" state that `x11_utils.py`
sets on Linux, and the `IVirtualDesktopManager` COM interface that could
pin a window to all virtual desktops has an IID that Microsoft changes
between builds (it is not part of the stable public API). What *is* stable
is the window-style/Z-order behavior we need:

- `WS_EX_TOOLWINDOW`  -- no taskbar entry, not in Alt+Tab.
- `WS_EX_NOACTIVATE`  -- never steals focus when it is shown.
- `WS_EX_TRANSPARENT` -- clicks fall through to whatever is underneath.
- `WS_EX_LAYERED`     -- required for the per-pixel alpha Qt uses for the
  translucent background.
- `SetWindowPos(..., HWND_BOTTOM, ...)` -- pushes the overlay to the bottom
  of the Z-order so every normal window sits above it.

Qt already requests most of this via its window flags, but some styles get
dropped when the native window is recreated (screen changes, DPI changes,
show/hide), so `main.py` re-applies this periodically -- exactly like the
X11 sticky hint.

Everything is done through `ctypes` against `user32`, so there are no extra
dependencies (no pywin32 needed).
"""

import ctypes
import os
from ctypes import wintypes

GWL_EXSTYLE = -20

WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

HWND_BOTTOM = 1

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200

_OVERLAY_EX_STYLES = (
    WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE
)


# `make_window_wallpaper_like()` is called every few seconds for the life of
# the process (see main.py), so the DLL handle and bound function pointers
# are cached here instead of being reloaded/re-bound on every single call.
_user32_cache = None


def _user32():
    global _user32_cache
    if _user32_cache is not None:
        return _user32_cache

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    # 64-bit Windows uses the ...Ptr variants; the plain ones truncate to
    # 32 bits and would silently mangle the style word.
    if hasattr(user32, "GetWindowLongPtrW"):
        get_long, set_long = user32.GetWindowLongPtrW, user32.SetWindowLongPtrW
    else:
        get_long, set_long = user32.GetWindowLongW, user32.SetWindowLongW

    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    get_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_long.restype = ctypes.c_ssize_t

    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    _user32_cache = (user32, get_long, set_long)
    return _user32_cache


def make_window_wallpaper_like(window_id: int) -> bool:
    """Apply the click-through / no-taskbar / bottom-most treatment to the
    native window *window_id* (a Qt `winId()`).

    Returns True on success, False if the Win32 call failed or the handle is
    not (or no longer) a window -- never raises. Set UNOHANA_DEBUG=1 to print
    the underlying error.
    """
    try:
        hwnd = wintypes.HWND(int(window_id))
        user32, get_long, set_long = _user32()

        if not user32.IsWindow(hwnd):
            return False

        style = get_long(hwnd, GWL_EXSTYLE)
        wanted = style | _OVERLAY_EX_STYLES
        if wanted != style:
            ctypes.set_last_error(0)
            if set_long(hwnd, GWL_EXSTYLE, wanted) == 0 and ctypes.get_last_error():
                raise ctypes.WinError(ctypes.get_last_error())

        # Re-assert bottom-most Z-order. Without this the overlay can float
        # above other windows again after the desktop is refreshed.
        ok = user32.SetWindowPos(
            hwnd, wintypes.HWND(HWND_BOTTOM), 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
        return bool(ok)
    except Exception as exc:  # noqa: BLE001 - report, then fail soft
        if os.environ.get("UNOHANA_DEBUG"):
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        return False
