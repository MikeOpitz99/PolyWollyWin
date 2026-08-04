# PolyWollyWin

[![Windows build check](https://github.com/MikeOpitz99/PolyWollyWin/actions/workflows/windows-build-check.yml/badge.svg)](https://github.com/MikeOpitz99/PolyWollyWin/actions/workflows/windows-build-check.yml)

An open-source Windows controller for the **ASUS ROG Strix Flare II Animate** AniMe Matrix display.

PolyWollyWin talks directly to the keyboard over USB HID, so the matrix can run effects, images, GIFs, drawing tools, text, sequences, and audio-reactive visuals without Armoury Crate controlling the display.

<p align="center">
  <img src="assets/pwwAnim.gif" alt="PolyWollyWin running on the ROG Strix Flare II Animate" width="640">
</p>

## Download

Get the installer or portable build from the [GitHub Releases page](https://github.com/MikeOpitz99/PolyWollyWin/releases).

**Current version:** 3.0.3

PolyWollyWin is currently tested only with:

| Device | USB ID | Interface |
|---|---|---|
| ASUS ROG Strix Flare II Animate | `VID 0x0B05`, `PID 0x19FC` | `usage_page 0xFF02`, normally `MI_04` |

Other ASUS AniMe Matrix products are not automatically compatible. Developers interested in adapting the project should read [HARDWARE_PORTING.md](HARDWARE_PORTING.md).

## Why this exists

The Flare II Animate has a useful 312 LED matrix, but the stock software does not expose the display as a general-purpose canvas. PolyWollyWin provides a lightweight controller with direct hardware access and a reusable effect and rendering layer.

Typical live effects use very little CPU and memory. Actual usage depends on the selected effect, GIF size, audio capture, and Windows runtime state.

## Features

- Direct USB HID control
- No Armoury Crate required for matrix control
- 37 x 12 logical renderer with 312 active physical LEDs
- Built-in live effects with adjustable parameters
- Static image and animated GIF playback
- Position, scale, speed, brightness, and contrast controls
- Paint editor with fill, invert, erase, and brightness tools
- Layer A and Layer B effect blending
- Crossfade when switching modes or effects
- Timed effect sequencer
- Audio-reactive visualization
- Typing and keyboard-reactive effects
- Saved presets and optional settings persistence
- System tray controls
- Startup and start-minimized options
- Automatic GitHub release update checks

## Built-in effects

PolyWollyWin includes:

- Pulse
- Matrix Rain
- Matrix Rain V2
- Rain
- Wipe
- Plasma
- Noise
- Scan
- Starfield
- Comet
- Ripple
- Helix
- Fireworks
- Lightning
- Bounce
- Wave
- Snake
- Clock
- Scroll Text
- Keyboard React
- Audio
- Fire
- Metaballs
- Game of Life
- Chase

Most effects expose live parameters in the Effects tab. Changes are applied while the effect is running.

## Installation

### Recommended: installer

1. Open the [Releases page](https://github.com/MikeOpitz99/PolyWollyWin/releases).
2. Download `PolyWollyWin-v3.0.3-Setup.exe`.
3. Run the installer.
4. Close Armoury Crate if it is holding the keyboard interface.
5. Start PolyWollyWin.

### Portable build

Download the release ZIP, extract the entire folder, and run `PolyWollyWin.exe`.

Do not move only the executable out of the portable folder. The optimized build uses a PyInstaller ONEDIR layout and requires its `_internal` directory.

## Run from source

PolyWollyWin requires Windows and Python 3.10 or newer.

```powershell
git clone https://github.com/MikeOpitz99/PolyWollyWin.git
cd PolyWollyWin

py -m venv .venv
.venv\Scripts\Activate.ps1

py -m pip install --upgrade pip
py -m pip install -r requirements.txt
python app.py
```

Install the optional live-audio and keyboard-capture features with:

```powershell
py -m pip install -r requirements-optional.txt
```

Without the optional packages:

- Audio visualization falls back gracefully when audio capture is unavailable.
- Typing visualization falls back to demo behavior when keyboard capture is unavailable.

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Main window, driver loop, settings, tray controls, sequencer, and application entry point |
| `transport.py` | Device discovery and HID packet transmission |
| `renderer.py` | Logical matrix geometry, physical LED mapping, image rendering, and GIF playback |
| `effects.py` | Built-in matrix effects |
| `paint.py` | Interactive paint editor |
| `preview.py` | Matrix preview widget |
| `version.py` | Application version |
| `PolyWollyWin.spec` | Optimized PyInstaller ONEDIR build |
| `PolyWollyWin.iss` | Inno Setup installer definition |
| `HARDWARE_PORTING.md` | Guide for adapting the transport and geometry to other hardware |
| `tools/flare2_matrix_test.py` | Standalone HID protocol and matrix diagnostic |

## Confirmed HID protocol

The currently supported keyboard uses a 1025 byte HID write:

```text
Report ID prefix:
0x00

1024 byte payload:
[0x60, 0x81, 0x00, 0x00, <312 LED bytes>, <zero padding>]
```

The 312 LED values are sent in row-major order across the active physical cells.

Current logical geometry:

```text
37 columns x 12 rows
444 logical cells
312 active LEDs

Row 0 starts at column 0
Row 1 starts at column 2
Row 2 starts at column 4
...
Row 11 starts at column 22
```

Brightness uses a separate confirmed command in `transport.py`.

## Adding an effect

Create a subclass of `BaseEffect` in `effects.py`:

```python
class MyEffect(BaseEffect):
    name = "My Effect"

    def tick(self, dt: float) -> list[int]:
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        # Render into frame here.
        return self._emit(frame)
```

Add the class to `ALL_EFFECTS`. It will then appear in the Effects tab.

Follow the existing `PARAMS` pattern to expose live sliders.

## Adapting PolyWollyWin to other hardware

The current code is device-specific, but the renderer and effect logic are separate from the HID transport.

A hardware port normally requires changes to:

1. USB VID, PID, interface, and usage-page detection
2. Report ID, packet size, and command bytes
3. Matrix width, height, mask, and LED ordering
4. Brightness and initialization commands
5. Any device-specific frame timing or acknowledgement behavior

See [HARDWARE_PORTING.md](HARDWARE_PORTING.md) for a practical porting checklist.

## Building a release

Install all runtime, optional, and build dependencies:

```powershell
py -m pip install -r requirements-dev.txt
```

Build the portable ONEDIR application:

```powershell
pyinstaller PolyWollyWin.spec
```

The output is created under:

```text
dist\PolyWollyWin\
```

Build the Windows installer with Inno Setup:

```powershell
ISCC PolyWollyWin.iss
```

The installer is created under:

```text
releases\
```

The installer script uses paths relative to the repository, so the project does not need to live on a specific drive or directory.

Before publishing a release, update:

- `version.py`
- `PolyWollyWin.iss`
- `CHANGELOG.md`
- Git tag
- GitHub release title and assets

Recommended release asset names:

```text
PolyWollyWin-vX.X.X.zip
PolyWollyWin-vX.X.X-Setup.exe
```

## Troubleshooting

### Keyboard is not detected

- Confirm the keyboard is connected directly to Windows.
- Close Armoury Crate and other software that may be using the same HID interface.
- Disconnect and reconnect the keyboard.
- Confirm Device Manager reports `VID_0B05&PID_19FC`.
- Run from source and use the interface enumeration helper in `transport.py` when debugging a port.

### The app closes but remains in Task Manager

Version 3.0.3 includes a shutdown watchdog so blocked audio or HID cleanup cannot leave the process running indefinitely.

### Windows warns about the installer

Unsigned independent Windows applications can trigger SmartScreen reputation warnings. Verify that the file came from this repository's Releases page.

## Contributing

Bug fixes, effects, documentation, hardware research, and device ports are welcome.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Use the issue templates for reproducible bugs and hardware-port requests.

## Licence

PolyWollyWin is released under the [MIT License](LICENSE).

See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) for related projects and research that informed this work.

## Disclaimer

PolyWollyWin is an independent community project. It is not affiliated with, endorsed by, or supported by ASUS.
