"""Entry point for the Unohana Visualizer.

Layers the audio-reactive blood-drip overlay on top of the Unohana
blood-sword wallpaper, which the user installs as their own desktop
background (see `unohana.jpg`). The overlay is a full-screen, transparent,
click-through window, so it just sits over the desktop behind everything
else.

Usage:
    python main.py [path/to/config.json]
"""

import json
import os
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from blood_visualizer import BloodVisualizerWindow
from x11_utils import make_window_sticky


def _load_config(config_path: str) -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    full_path = config_path if os.path.isabs(config_path) else os.path.join(here, config_path)
    with open(full_path, "r") as f:
        return json.load(f)


def main():
    app = QApplication(sys.argv)

    # Qt's C++ event loop never hands control back to Python, so Python's
    # default SIGINT handler (which needs to run in the main thread) never
    # gets a chance to fire and Ctrl+C appears to do nothing. Install a
    # handler that asks Qt to quit gracefully, and use a short-interval timer
    # just to keep the interpreter "awake" so the signal can be delivered
    # promptly instead of only once the window emits some other Qt event.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    wakeup = QTimer()
    wakeup.timeout.connect(lambda: None)
    wakeup.start(200)

    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    config = _load_config(config_path)

    blood_cfg = config.get("blood_visualizer", {})
    viz_cfg = config.get("visualizer", {})

    audio_reader = None
    if blood_cfg.get("enabled", True):
        try:
            from audio_visualizer import AudioLevelReader
            audio_reader = AudioLevelReader(
                source=viz_cfg.get("source", "auto"),
                db_min=float(viz_cfg.get("db_min", -58.0)),
                db_max=float(viz_cfg.get("db_max", -4.0)))
        except Exception:
            audio_reader = None

    if blood_cfg.get("enabled", True):
        blood = BloodVisualizerWindow(config, audio_reader)
        blood.show()

        # The overlay must be visible on *every* workspace, not just the one
        # it was created on (the wallpaper it decorates is shared across all
        # of them). Qt has no API for the EWMH "sticky" state, so we set it
        # straight through libxcb (see `x11_utils.py`). Re-assert every few
        # seconds in case the WM resets window states when it relayouts.
        sticky_failed = False

        def _apply_sticky():
            nonlocal sticky_failed
            if not make_window_sticky(blood.winId()) and not sticky_failed:
                sticky_failed = True
                print(
                    "warning: could not set the sticky hint "
                    "(no X11/libxcb?) -- the overlay may only appear on "
                    "the workspace it was started on", file=sys.stderr)

        _apply_sticky()
        sticky_timer = QTimer()
        sticky_timer.timeout.connect(_apply_sticky)
        sticky_timer.start(5000)

    # Optional headless smoke-test: UNOHANA_AUTOSTOP_MS=2000 makes the app
    # quit by itself after 2000 ms (useful for verifying startup offscreen).
    auto_stop_ms = os.environ.get("UNOHANA_AUTOSTOP_MS", "").strip()
    if auto_stop_ms.isdigit() and int(auto_stop_ms) > 0:
        QTimer.singleShot(int(auto_stop_ms), app.quit)

    exit_code = app.exec()
    if audio_reader is not None:
        audio_reader.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
