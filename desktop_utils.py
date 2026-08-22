"""Cross-platform helpers for keeping the overlay wallpaper-like.

The overlay has to behave the same on every platform: sit *below* every
normal window, never take focus or clicks, never show up in the taskbar,
and be visible on every workspace/virtual desktop (the wallpaper it
decorates is shared across all of them).

Qt covers most of that through window flags, but the "show on every
workspace" part needs platform-specific calls:

* **X11 / Linux** -- the EWMH `_NET_WM_STATE_STICKY` hint, set through
  `libxcb` (see `x11_utils.py`).
* **Windows** -- the shell has no "sticky" flag; instead a window is pinned
  to all virtual desktops through the `IVirtualDesktopManager` COM
  interface, whose IID changes between Windows builds. Rather than chase
  that, we use the documented and stable behavior that a *tool window*
  which is never activated stays put; additionally we re-assert
  bottom-most Z-order (`HWND_BOTTOM`) and the
  `WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT` extended
  styles, which is what actually keeps the overlay behaving like
  wallpaper.
* **Anything else (e.g. Wayland, macOS)** -- no-op; the Qt flags alone
  already give a frameless, click-through, always-on-bottom overlay.

Everything here is best-effort and never raises: `pin_overlay_window()`
returns False if the platform hook is unavailable, and the caller just
prints a warning.
"""

import sys

#: Human-readable hint shown when `pin_overlay_window()` fails, so the
#: warning can tell the user what is actually missing on their system.
if sys.platform.startswith("win"):
    UNSUPPORTED_HINT = "no Win32 user32 access?"
elif sys.platform.startswith("linux"):
    UNSUPPORTED_HINT = "no X11/libxcb?"
else:
    UNSUPPORTED_HINT = f"unsupported platform: {sys.platform}"


def pin_overlay_window(window_id) -> bool:
    """Best-effort: keep *window_id* wallpaper-like on every desktop.

    Returns True when the platform hook ran, False when it is unavailable
    (headless/offscreen, missing libxcb, unsupported platform). Never
    raises.
    """
    try:
        window_id = int(window_id)  # winId() is a sip.voidptr, not an int
    except (TypeError, ValueError):
        return False

    if sys.platform.startswith("win"):
        from win_utils import make_window_wallpaper_like
        return make_window_wallpaper_like(window_id)

    if sys.platform.startswith("linux"):
        from x11_utils import make_window_sticky
        return make_window_sticky(window_id)

    # Wayland/macOS/other: Qt's flags are all we can portably do, and they
    # are enough for a frameless click-through bottom-most overlay.
    return True
