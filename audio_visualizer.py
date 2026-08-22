"""
Audio level reader for the window's music-visualization bars.

Taps the *current output device* (the default PulseAudio/PipeWire sink)
through its loopback "monitor" source, so the levels always track what the
user is actually hearing -- whatever application is playing, on whichever
speaker is active. Built on `soundcard` (PulseAudio backend), which only
needs the system `libpulse` that any PipeWire/PulseAudio desktop already has.

Design
------
* A single daemon thread keeps one `soundcard` recorder open and appends
  incoming float32 samples into a bounded rolling buffer (mixing channels to
  mono).
* `get_levels(n_bands)` (called from the GUI thread at ~30 fps) computes a
  log-spaced FFT spectrum over the most recent samples, applies a fast-attack
  / slow-release envelope, and returns ``n_bands`` values in ``0..1``.

Everything degrades gracefully: if `soundcard`/`libpulse` are missing, there
is no monitor source, or the audio stack is down, `get_levels()` simply
returns zeros and the bars stay flat instead of crashing the monitor.
"""

import threading
from collections import deque

import numpy as np

try:
    import soundcard as _sc
    _SC_AVAILABLE = True
except Exception:  # depends on the host audio stack
    _sc = None
    _SC_AVAILABLE = False


_SAMPLE_RATE = 44100      # Hz -- fine for visualisation (covers ~22 kHz)
_RECORD_FRAMES = 1024     # frames per blocking read (~23 ms) -> smooth updates
_FFT_SIZE = 4096          # analysis window (~93 ms, ~10.5 Hz resolution)
_MAX_BUFFER = 16384       # ~0.37 s of audio retained for analysis
_F_MIN = 50.0             # Hz, lowest band edge
_F_MAX = 16000.0          # Hz, highest band edge


def _is_loopback(mic) -> bool:
    """True if `mic` records a speaker's output rather than a real input."""
    try:
        return bool(mic.isloopback)
    except Exception:
        try:
            return "monitor" in (mic.name or "").lower()
        except Exception:
            return False


def _find_named(source: str):
    """Resolve a user-supplied microphone name to a soundcard mic, or None."""
    if not _SC_AVAILABLE:
        return None
    try:
        return _sc.get_microphone(source, include_loopback=True)
    except Exception:
        return None


def _find_monitor():
    """Pick the loopback monitor that backs the *default* speaker.

    Falls back to the first available monitor, so "whatever the user is
    hearing" is captured even if the default-speaker name match fails.
    """
    if not _SC_AVAILABLE:
        return None
    try:
        mics = _sc.all_microphones(include_loopback=True)
    except Exception:
        return None

    loopbacks = [m for m in mics if _is_loopback(m)]
    if not loopbacks:
        return None

    default_name = ""
    try:
        default_name = _sc.default_speaker().name or ""
    except Exception:
        default_name = ""

    if default_name:
        for m in loopbacks:
            name = m.name or ""
            if name and (default_name in name or name in default_name):
                return m
    return loopbacks[0]


class AudioLevelReader:
    """Background audio tap that turns live output into per-band levels."""

    def __init__(self, source: str = "auto", sample_rate: int = _SAMPLE_RATE,
                 db_min: float = -58.0, db_max: float = -4.0):
        self.sample_rate = sample_rate
        self.source = source
        self.db_min = float(db_min)
        self.db_max = float(db_max)
        if self.db_max <= self.db_min:
            self.db_min, self.db_max = -58.0, -4.0
        self.source_name = None
        self.available = False
        self.error = None

        self._lock = threading.Lock()
        self._buf = deque()
        self._smooth_states = {}
        self._stop = threading.Event()
        self._thread = None

        mic = _find_named(source) if (source and source != "auto") else None
        if mic is None:
            mic = _find_monitor()
        if mic is None:
            self.error = ("soundcard unavailable" if not _SC_AVAILABLE
                          else "no loopback/monitor source found")
            return

        self._mic = mic
        try:
            self.source_name = mic.name
        except Exception:
            self.source_name = None

        self._thread = threading.Thread(
            target=self._run, name="audio-level-reader", daemon=True)
        self._thread.start()

    # -- background capture -------------------------------------------------

    def _run(self):
        try:
            # IMPORTANT: soundcard's PulseAudio backend only sets a small
            # server-side fragment/target length (`fragsize`/`tlength`) when
            # a `blocksize` is given; otherwise it tells PulseAudio/PipeWire
            # it can buffer up to ~4 GB before delivering samples to us. That
            # unbounded server-side buffer is what caused the visualizer to
            # trail the actual audio by ~2 seconds -- our own rolling buffer
            # was fine, it was just processing genuinely stale samples. This
            # blocksize forces the server to hand over each ~23ms fragment
            # (_RECORD_FRAMES) as soon as it's ready instead.
            with self._mic.recorder(self.sample_rate, blocksize=_RECORD_FRAMES) as rec:
                self.available = True
                while not self._stop.is_set():
                    try:
                        chunk = rec.record(_RECORD_FRAMES)
                    except Exception:
                        break
                    if chunk is None:
                        continue
                    arr = np.asarray(chunk, dtype=np.float32)
                    if arr.ndim == 2:          # mixdown stereo -> mono
                        arr = arr.mean(axis=1)
                    arr = arr.reshape(-1)
                    if arr.size == 0:
                        continue
                    with self._lock:
                        self._buf.append(arr)
                        total = sum(len(b) for b in self._buf)
                        while total > _MAX_BUFFER and self._buf:
                            total -= len(self._buf.popleft())
        except Exception as e:
            self.error = repr(e)
            self.available = False

    def stop(self):
        """Stop the capture thread and release the recorder (idempotent)."""
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=1.0)


    # -- level query (called from the GUI thread) ---------------------------

    def get_levels(self, n_bands: int, client_key=None):
        """Return ``n_bands`` smoothed band levels, each a float in 0..1.

        Multiple independent visualizers can share one `AudioLevelReader`
        (one loopback capture thread) and still each get their own
        attack/release envelope by passing a distinct ``client_key`` --
        otherwise two callers using a different ``n_bands`` would keep
        resetting each other's smoothing state every frame. Callers that
        don't care (the common single-visualizer case) can omit it, since
        ``n_bands`` alone is used as the key.
        """
        key = client_key if client_key is not None else n_bands
        with self._lock:
            if not self._buf:
                data = np.zeros(0, dtype=np.float32)
            else:
                data = np.concatenate(list(self._buf))

        if data.size < 512:
            return self._smoothed([0.0] * n_bands, n_bands, key)

        data = data[-_FFT_SIZE:]
        if data.size < _FFT_SIZE:
            data = np.pad(data, (_FFT_SIZE - data.size, 0), mode="constant")

        window = np.hanning(data.size)
        spectrum = np.abs(np.fft.rfft(data * window))
        freqs = np.fft.rfftfreq(data.size, d=1.0 / self.sample_rate)

        # Log-spaced band edges -> assign every FFT bin to a band, take the
        # peak amplitude per band (classic spectrum-visualiser look).
        f_max = min(_F_MAX, self.sample_rate / 2.0)
        edges = np.logspace(np.log10(_F_MIN), np.log10(f_max), n_bands + 1)
        idx = np.clip(np.searchsorted(edges, freqs, side="right") - 1, 0, n_bands - 1)
        peak = np.zeros(n_bands, dtype=np.float32)
        np.maximum.at(peak, idx, spectrum)

        # Map each band's peak to a level on a dBFS scale (0 dB = full scale)
        # and stretch [db_min, db_max] onto 0..1.  This tracks loudness
        # dynamically: quiet passages give short bars, loud ones nearly fill
        # the bar, and only real peaks reach the top -- instead of every band
        # saturating the moment there's any signal.
        ref = 0.5 * float(window.sum())          # full-scale single-bin amplitude
        amp = peak / ref                          # ~amplitude of the loudest partial
        db = 20.0 * np.log10(amp + 1e-7)          # dBFS, 0 = full scale
        levels = (db - self.db_min) / (self.db_max - self.db_min)
        levels = np.clip(levels, 0.0, 1.0)
        return self._smoothed(list(levels), n_bands, key)

    def _smoothed(self, levels, n_bands, key):
        """Fast-attack / slow-release envelope so bars pop up but linger down."""
        attack, release = 0.55, 0.25
        state = self._smooth_states.get(key)
        if state is None or len(state) != n_bands:
            state = [0.0] * n_bands
        for i in range(n_bands):
            target = levels[i]
            cur = state[i]
            coeff = attack if target > cur else release
            state[i] = cur + (target - cur) * coeff
        self._smooth_states[key] = state
        return list(state)


