# Contributing to PolyWollyWin

Contributions are welcome, including bug fixes, effects, documentation, packaging improvements, and verified hardware ports.

## Before starting

- Search existing issues first.
- Use the bug-report template for reproducible defects.
- Use the hardware-port template for new devices.
- Keep changes focused. Separate unrelated cleanup from feature work.
- Do not commit generated builds, packet captures, logs, virtual environments, or private release scripts.

## Development setup

PolyWollyWin requires Windows and Python 3.10 or newer.

```powershell
git clone https://github.com/MikeOpitz99/PolyWollyWin.git
cd PolyWollyWin

py -m venv .venv
.venv\Scripts\Activate.ps1

py -m pip install --upgrade pip
py -m pip install -r requirements-dev.txt
python app.py
```

## Code expectations

- Preserve direct HID access in `transport.py`.
- Keep logical rendering and physical LED mapping in `renderer.py`.
- Keep effect code independent from USB packet formatting.
- Validate frame lengths before sending them to hardware.
- Handle missing optional audio and keyboard-capture dependencies gracefully.
- Avoid blocking the Qt UI thread.
- Clean up HID, audio, keyboard hooks, timers, and worker threads on exit.
- Use descriptive names and short comments for non-obvious protocol behavior.
- Do not add a device ID based on an assumption or a similar model name.

## Adding an effect

1. Subclass `BaseEffect` in `effects.py`.
2. Render into the logical matrix.
3. Return the result through the existing emit path.
4. Add the class to `ALL_EFFECTS`.
5. Add a `PARAMS` definition when live controls are useful.
6. Test at low and high speed.
7. Test with Layer B blending and crossfade enabled.

## Hardware ports

Read [HARDWARE_PORTING.md](HARDWARE_PORTING.md) before modifying USB detection or packet encoding.

A hardware port must include evidence for:

- exact VID and PID
- correct interface selection
- confirmed report ID and packet format
- verified LED count and physical order
- blank-frame behavior
- brightness behavior, when implemented
- tested model and firmware details

Do not commit raw USB captures unless they are reduced, scrubbed, necessary, and explicitly approved.

## Testing

At minimum, test:

- application launch
- keyboard connection and reconnection
- effect switching
- Layer B blending
- crossfade
- GIF or image playback
- settings save and clear
- close-to-tray behavior
- full application exit
- installer or portable build when packaging changes are involved

For a release build:

```powershell
pyinstaller PolyWollyWin.spec
ISCC PolyWollyWin.iss
```

Run the built application from `dist\PolyWollyWin`, not only from source.

## Pull requests

A useful pull request includes:

- a clear title
- the problem being solved
- a concise description of the implementation
- testing performed
- screenshots or video for visible UI or effect changes
- exact hardware details for device-specific changes
- documentation updates when behavior changes

Do not include drive-specific paths, local directory listings, usernames, logs, build output, or unrelated formatting changes.

## Licence

By submitting a contribution, you agree that it may be distributed under the project's MIT License.
