# Unohana Visualizer

Standalone audio-reactive blood-drip overlay for the Unohana blood-sword
wallpaper: animated drips hang from the sword blade, growing and fading
with whatever audio is playing on the system. Designed for a computer with
one 1920x1080 screen on Linux (PulseAudio/PipeWire + X11/Qt).

## What it does

- `blood_visualizer.py` is a full-screen transparent overlay that renders
  audio-reactive "drip" bars hanging down from the blade. Quiet audio
  leaves a faint wet sheen along the blade; loud passages make the drips
  longer, brighter, and glowing. It is frameless, click-through, stays
  below every normal window, and never shows up in the taskbar/alt-tab —
  it just sits over the desktop like wallpaper.
- `audio_visualizer.py` taps the current output device's loopback
  "monitor" source (via `soundcard`), so the drips react to *whatever you
  are hearing* — music, games, video — with no microphone involved.
- `unohana.jpg` is the artwork. Set it as your own desktop background
  (e.g. `feh --bg-scale unohana.jpg`, or your desktop environment's
  wallpaper settings), then run this app on top of it.

## Setup

```sh
cd "Unohana Visualizer"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Audio capture additionally needs the system `libpulse` package, which is
already present on any PipeWire/PulseAudio desktop. If it is missing (or
there is no audio output device), the app still runs — the drips simply
stay at their quiet idle length.

## Run

```sh
.venv/bin/python main.py
```

Optionally pass an alternate config: `python main.py /path/to/config.json`.

Stop with `Ctrl+C`.

## Aiming the drips at the blade (`config.json`)

All keys are optional; the shown defaults are what ships in this repo.
Everything that positions the bars is a fraction of the screen, so it
adapts to any resolution once set:

- `baseline_fraction` — **the blade's height** as a fraction of screen
  height (0.0 = top, 1.0 = bottom). With `unohana.jpg` (1920x1600)
  cover-scaled onto a 1920x1080 desktop, the blade lands at about **0.60**.
  Nudge this up/down until the drips meet the blade exactly.
- `x_range` — `[left, right]` fractions of the screen width spanned by the
  drips (defaults to the full blade span, `[0.03, 0.97]`).
- `drip_count` — number of drip bars along the blade.
- `base_height_fraction` / `max_height_fraction` — idle and peak drip
  lengths, as fractions of screen height.
- `color_top` / `color_mid` / `color_tip` — drip gradient colors
  (blade end to tip).
- `screen_index` — which screen to draw on (0 for a single display).
- `fps` — redraw rate.

Audio-level tuning:

- `visualizer.source` — `"auto"` picks the default speaker's monitor
  source; you can also pass a specific mic/monitor name.
- `visualizer.db_min` / `db_max` — the dBFS range mapped onto 0..1 bar
  levels (lower `db_min` = more sensitive).
