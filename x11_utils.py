"""X11 helper: make a Qt window visible on *all* workspaces/desktops.

Qt has no API for the EWMH "sticky" window state, so without this the
overlay only appears on the workspace it was created on (e.g. workspace 1
of a multi-workspace setup), while the wallpaper it decorates is shared
across every workspace. We set the property directly through `libxcb` --
the same shared library the Qt X11 platform plugin links against, so no
extra packages are needed.

Set on the window:
- EWMH `_NET_WM_STATE`: `STICKY` (show on every workspace), plus
  `BELOW` / `SKIP_TASKBAR` / `SKIP_PAGER` so the overlay keeps its
  wallpaper-like behavior even on WMs that only honor EWMH state hints.
- Legacy Motif `WM_STATE` sticky bit, for older WMs that predate EWMH.
"""

import ctypes
import ctypes.util
import struct


class _InternAtomCookie(ctypes.Structure):
    _fields_ = [("sequence", ctypes.c_uint32), ("length", ctypes.c_uint16)]


class _InternAtomReply(ctypes.Structure):
    _fields_ = [
        ("response_type", ctypes.c_uint8),
        ("only_if_exists", ctypes.c_uint8),
        ("pad0", ctypes.c_uint16),
        ("pad1", ctypes.c_uint32),
        ("atom", ctypes.c_uint32),
    ]


class _RootsIterator(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("read", ctypes.c_size_t),
        ("end", ctypes.c_void_p),
    ]


def _load_xcb():
    lib = ctypes.CDLL("libxcb.so.1")
    lib.xcb_connect.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    lib.xcb_connect.restype = ctypes.c_void_p
    lib.xcb_disconnect.argtypes = [ctypes.c_void_p]
    lib.xcb_get_setup.argtypes = [ctypes.c_void_p]
    lib.xcb_get_setup.restype = ctypes.c_void_p
    lib.xcb_setup_roots_iterator.argtypes = [ctypes.c_void_p]
    lib.xcb_setup_roots_iterator.restype = _RootsIterator
    lib.xcb_intern_atom.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_char_p]
    lib.xcb_intern_atom.restype = _InternAtomCookie
    lib.xcb_intern_atom_reply.argtypes = [
        ctypes.c_void_p, _InternAtomCookie, ctypes.c_void_p]
    lib.xcb_intern_atom_reply.restype = ctypes.c_void_p
    lib.xcb_change_property.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_void_p]
    lib.xcb_send_event.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_char_p]
    lib.xcb_flush.argtypes = [ctypes.c_void_p]
    return lib


def make_window_sticky(window_id: int) -> bool:
    """Best-effort: ask the window manager to show *window_id* on every
    workspace. Returns True on success, False if X11/libxcb is unavailable
    (e.g. headless/offscreen) -- never raises. Set UNOHANA_DEBUG=1 to print
    the underlying error when it fails."""
    window_id = int(window_id)  # winId() may be a sip.voidptr, not a plain int
    import os as _os

    def _debug(exc: BaseException) -> None:
        if _os.environ.get("UNOHANA_DEBUG"):
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)

    try:
        lib = _load_xcb()
        screen = ctypes.c_int()
        conn = lib.xcb_connect(None, ctypes.byref(screen))
    except OSError:
        return False
    if not conn:
        return False
    try:
        def atom(name: str) -> int:
            cookie = lib.xcb_intern_atom(conn, 0, len(name), name.encode("ascii"))
            ptr = lib.xcb_intern_atom_reply(conn, cookie, None)
            if not ptr:
                return 0
            return ctypes.cast(ptr, ctypes.POINTER(_InternAtomReply)).contents.atom

        def set_property(property_atom: int, value: bytes) -> None:
            buf = ctypes.create_string_buffer(value, len(value))
            lib.xcb_change_property(
                conn, 0, window_id, property_atom, property_atom, 32,
                len(value) // 4, buf)

        # EWMH: sticky + stays-below + no taskbar/pager entries.
        net_wm_state = atom("_NET_WM_STATE")
        states = [atom(n) for n in
                  ("STICKY", "BELOW", "SKIP_TASKBAR", "SKIP_PAGER")]
        set_property(net_wm_state, struct.pack(f"<{len(states)}I", *states))

        # Proper EWMH way of asking the WM to *apply* the states above:
        # a _NET_WM_STATE_CHANGE ClientMessage to the root window (EWMH
        # section 5.2.2). Just changing the property isn't seen by some
        # WMs -- e.g. Kwin rewrites the window's _NET_WM_STATE itself and
        # drops STICKY unless it is told via the ClientMessage.
        setup = lib.xcb_get_setup(conn)
        root_ptr = lib.xcb_setup_roots_iterator(setup).data
        root = ctypes.cast(root_ptr, ctypes.POINTER(ctypes.c_uint32)).contents.value
        event = (
            bytes([1]) + b"\x00" * 3                      # response_type
            + struct.pack("<I", net_wm_state)             # type
            + struct.pack("<I", window_id)                # window
            + struct.pack("<I", net_wm_state)             # message_type
            + bytes([32]) + b"\x00" * 3                   # format
            + struct.pack("<5I", 1, *states[:2], 0, 0)  # add STICKY, BELOW
        )
        mask = (0x800   # StructureChangeMask
                | 0x2000  # SubstructureRedirectMask
                | 0x4000)  # SubstructureNotifyMask
        lib.xcb_send_event(
            conn, 0, root, mask,
            ctypes.create_string_buffer(event, len(event)))

        # Legacy Motif sticky bit (WM_STATE = [ClientMessage, 0, 1, root]).
        wm_state = atom("WM_STATE")
        set_property(wm_state, struct.pack("<5I", 1, 0, 1, root, 0))

        lib.xcb_flush(conn)
        return True
    except Exception as exc:  # noqa: BLE001 - report, then fail soft
        _debug(exc)
        return False
    finally:
        lib.xcb_disconnect(conn)