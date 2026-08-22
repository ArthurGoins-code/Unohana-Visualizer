# Unohana Visualizer

Standalone audio-reactive blood-drip overlay for the Unohana blood-sword
wallpaper: animated drips hang from the sword blade, growing and fading
with whatever audio is playing on the system. Designed for a single
1920x1080 screen, and runs on **Windows 10/11** as well as **Linux**
(PulseAudio/PipeWire + X11/Qt).

## What it does

- `blood_visualizer.py` is a full-screen transparent overlay that renders
  audio-reactive "drip" bars hanging down from the blade. Quiet audio
  leaves a faint wet sheen along the blade; loud passages make the drips
  longer, brighter, and glowing. It is frameless, click-through, stays
  below every normal window, and never shows up in the taskbar/alt-tab —
  it just sits over the desktop like wallpaper. `desktop_utils.py` keeps
  that behavior on every workspace/virtual desktop: on X11 via the EWMH
  `_NET_WM_STATE_STICKY` hint (`x11_utils.py`), on Windows via the Win32
  tool-window/click-through styles and bottom-most Z-order
  (`win_utils.py`).
- `audio_visualizer.py` taps the current output device's loopback source
  (via `soundcard` — WASAPI loopback on Windows, the PulseAudio/PipeWire
  "monitor" source on Linux), so the drips react to *whatever you are
  hearing* — music, games, video — with no microphone involved.
- `unohana.jpg` is the artwork. Set it as your own desktop background
  (Windows: right-click the image → *Set as desktop background*; Linux:
  e.g. `feh --bg-scale unohana.jpg` or your desktop environment's
  wallpaper settings), then run this app on top of it.

## Setup

### Windows

Set unohana.jpg as desktop background and set fit to center.

Double-click **`install.bat`**, or run it from a command prompt:

```bat
cd Unohana-Visualizer
install.bat
```

This creates `.venv`, installs the requirements, and adds a
`unohana-visualizer` command to your PATH. If Python is not installed yet,
the script installs it for you (via `winget`, falling back to the official
python.org installer) — per-user, so no administrator rights are needed.
Use `install.bat --force` to rebuild the virtualenv and
`install.bat --uninstall` to remove the launcher.

> **Why a `.bat` and not the `.ps1` directly?** A stock Windows install
> refuses to run `.ps1` scripts ("running scripts is disabled on this
> system"). `install.bat` is just a thin wrapper that starts
> `install.ps1` with `-ExecutionPolicy Bypass`, which applies to that one
> PowerShell process only — it does not change your machine's policy and
> needs no admin rights. If you'd rather invoke it yourself, this is the
> equivalent one-liner:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\install.ps1
> ```

To set things up by hand instead (with Python 3.8+ already installed):

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Audio capture uses WASAPI loopback, which is built into Windows — nothing
extra to install.

### Linux

```sh
cd Unohana-Visualizer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Audio capture additionally needs the system `libpulse` package, which is
already present on any PipeWire/PulseAudio desktop. If it is missing (or
there is no audio output device), the app still runs — the drips simply
stay at their quiet idle length.

## Run

Windows:

```powershell
unohana-visualizer
# or, to keep a console for Ctrl+C:
.venv\Scripts\python main.py
```

Linux:

```sh
.venv/bin/python main.py
```

Optionally pass an alternate config: `python main.py path\to\config.json`.

Stop with `Ctrl+C` (or, if it was started windowless by the launcher, end
the `pythonw` task from Task Manager).

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

- `visualizer.source` — `"auto"` picks the default speaker's loopback
  source; you can also pass a specific device name (on Windows, the
  playback device's own name; on Linux, a `...monitor` source name).
- `visualizer.db_min` / `db_max` — the dBFS range mapped onto 0..1 bar
  levels (lower `db_min` = more sensitive).
