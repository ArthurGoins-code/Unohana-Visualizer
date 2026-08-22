"""Transparent overlay that grows audio-reactive "blood" bars down from the
sword blade in the Unohana wallpaper.

Bars extend *down* from a glowing horizontal line (the blade), with the
gradient fading to transparent where they meet the blade and paling to a
solid drip tip at the loose end. Drawn as plain rounded-rect bars. Frameless,
click-through, stays below every normal window, and never appears in the
taskbar/alt-tab, so it just sits over the desktop behind everything else
(the wallpaper itself is set by the user; see `README.md`). Where the drips
hang from and how far they span is purely a matter of `config.json`, so it
can be aimed at the blade wherever the wallpaper places it.
"""

import math

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget


def parse_color(value: str) -> QColor:
    """Parse '#rrggbb' or 'rgba(r,g,b,a)' strings into a QColor."""
    value = value.strip()
    if value.startswith("#"):
        return QColor(value)
    if value.startswith("rgba"):
        nums = value[value.index("(") + 1 : value.index(")")].split(",")
        r, g, b = (int(n) for n in nums[0:3])
        a = float(nums[3])
        color = QColor(r, g, b)
        color.setAlphaF(a)
        return color
    return QColor(value)


class BloodVisualizerWindow(QWidget):
    """Screen-sized, see-through overlay drawing audio-reactive bars hanging
    from the Unohana wallpaper's sword blade, in sync with system audio."""

    def __init__(self, config: dict, audio_reader=None, parent=None):
        super().__init__(parent)
        self._cfg = config.get("blood_visualizer", {})
        self._audio_reader = audio_reader
        self._n_bands = max(2, int(self._cfg.get("drip_count", 24)))
        # Distinct from any key the other visualizers use, so none of them
        # stomp on each other's smoothing state when sharing one reader.
        self._client_key = "blood_visualizer"

        self._setup_window()
        self._build_geometry()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        fps = max(5, int(self._cfg.get("fps", 30)))
        self._timer.start(int(1000 / fps))

    # -- setup ---------------------------------------------------------------

    def _setup_window(self):
        screens = QGuiApplication.screens()
        idx = int(self._cfg.get("screen_index", 0))
        geo = screens[idx].geometry() if 0 <= idx < len(screens) else QGuiApplication.primaryScreen().geometry()
        self.setGeometry(geo)

        # Frameless + translucent so only the painted drips are visible;
        # StaysOnBottom + transparent-for-input + Tool keeps it out of the
        # way entirely -- it never steals clicks, focus, or a taskbar entry,
        # and normal windows always sit above it.
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnBottomHint
            | Qt.WindowTransparentForInput
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

    def _build_geometry(self):
        w, h = self.width(), self.height()
        self._baseline_y = h * float(self._cfg.get("baseline_fraction", 0.589))
        self._max_extra = h * float(self._cfg.get("max_height_fraction", 0.30))
        self._base_height = h * float(self._cfg.get("base_height_fraction", 0.010))

        x_range = self._cfg.get("x_range", [0.061, 0.97])
        self._x0, self._x1 = x_range[0] * w, x_range[1] * w

        # Parsed once here rather than on every paintEvent -- these never
        # change after startup, so re-parsing the config strings ~30x/sec
        # would be pure waste.
        self._top_c = parse_color(self._cfg.get("color_top", "#ff4d3d"))
        self._mid_c = parse_color(self._cfg.get("color_mid", "#c40e0e"))
        self._tip_c = parse_color(self._cfg.get("color_tip", "#5c0000"))

        # Deterministic per-drip jitter (x offset / width / satellite drips)
        # so they look organically irregular but never "jump" between
        # frames -- only their length reacts to audio.
        self._jitter = []
        for i in range(self._n_bands):
            frac = math.sin(i * 12.9898) * 43758.5453
            self._jitter.append(frac - math.floor(frac))

    # -- audio -----------------------------------------------------------

    def _levels(self):
        if self._audio_reader is None:
            return [0.0] * self._n_bands
        try:
            return self._audio_reader.get_levels(self._n_bands, client_key=self._client_key)
        except TypeError:
            # Older AudioLevelReader without client_key support.
            return self._audio_reader.get_levels(self._n_bands)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        levels = self._levels()
        self._draw_drips(painter, levels)

        painter.end()

    def _draw_drips(self, painter, levels):
        n = len(levels)
        width = self._x1 - self._x0
        if width <= 0 or n <= 0:
            return
        slot = width / n

        top_c, mid_c, tip_c = self._top_c, self._mid_c, self._tip_c

        for i, level in enumerate(levels):
            jitter = self._jitter[i]
            cx = self._x0 + (i + 0.5 + (jitter - 0.5) * 0.4) * slot
            bar_w = slot * (0.16 + 0.16 * jitter)
            length = self._base_height + self._max_extra * level
            self._draw_bar(painter, cx, bar_w, length, level, top_c, mid_c, tip_c)

            # Occasional smaller satellite bar beside the main one, like the
            # clustered thin streaks in the source artwork.
            if jitter > 0.55:
                sat_len = length * (0.35 + 0.25 * jitter)
                sat_x = cx + bar_w * (1.1 if jitter > 0.75 else -1.1)
                self._draw_bar(painter, sat_x, bar_w * 0.5, sat_len, level, top_c, mid_c, tip_c)

    def _draw_bar(self, painter, cx, width, length, level, top_c, mid_c, tip_c):
        # Plain rounded-rect bar extending straight down from the blade
        # (same visual language as the hardware-monitor bars, but standing
        # entirely on its own here) instead of a tapered drip shape.
        top_y = self._baseline_y
        radius = width / 2.0
        rect = QRectF(cx - width / 2.0, top_y, width, length)

        # Idle bars (no/quiet audio) stay faint and thin so they read as a
        # subtle wet sheen along the blade rather than a row of solid teeth;
        # louder audio both lengthens *and* opacifies them so the reactive
        # ones pop out clearly against that quiet baseline.
        intensity = 0.12 + 0.88 * level

        def _scaled(color, extra=1.0):
            c = QColor(color)
            c.setAlphaF(max(0.0, min(1.0, color.alphaF() * intensity * extra)))
            return c

        # Soft glow behind the bar, widening/brightening with level so louder
        # passages bloom like the wallpaper's own blade glow.
        if level > 0.03:
            glow = _scaled(mid_c, 0.4)
            painter.setBrush(glow)
            painter.drawRoundedRect(rect.adjusted(-2, -1, 2, 1), radius + 2, radius + 2)

        # Gradient: fully transparent where it meets the blade, becoming
        # bright/opaque toward the loose end -- so the bar's top blends into
        # the blade's own glow with no hard color edge, while the bottom
        # reads as a solid drip tip. The transparent stretch is held out
        # further (to 0.7) so the upper portion of the bar stays especially
        # faint before the color ramps in.
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, _scaled(top_c, 0.0))
        grad.setColorAt(0.7, _scaled(mid_c, 0.5))
        grad.setColorAt(1.0, _scaled(tip_c))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(rect, radius, radius)
