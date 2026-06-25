## v3.0.0
- fixing installer

## v2.9
- adding minimize to tray function on boot

## v2.8.5
- Fix preview and paint column offset

## v2.7.0
- Knight Industries additions.

## v2.6.5
- updating some effects

## v2.6.3 - 2026-06-08

### Added
- Added a one-click release workflow for building PolyWollyWin release artifacts from a single version prompt.
- Added automated ZIP packaging for portable releases.
- Added automated Inno Setup installer generation for `PolyWollyWin-vX.X.X-Setup.exe`.
- Added release-output validation so the build stops when the expected installer file is not created.
- Added release artifact cleanup rules to separate public release assets from local build outputs.
- Added repository hygiene rules for keeping generated build folders out of source control.
- Added release ZIP auditing support to check archive contents before pushing artifacts to GitHub.

### Changed
- Updated installer script settings to use the newer architecture identifier instead of the deprecated `x64` value.
- Updated uninstall handling so the taskkill uninstall step includes a `RunOnceId`.

### Fixed
- Fixed installer version drift where `version.py` could update but `PolyWollyWin.iss` stayed on an older version.
- Fixed release builds producing an installer with the wrong filename, such as creating a `v2.5.0` installer when the requested release was `v2.6.0`.
- Replaced fragile PowerShell regex version replacement with safer line-based installer version updating.
- Fixed accidental hiding of public build configuration by ensuring `.spec` and `.iss` files are not ignored.
- Cleaned up release-version handling after several failed installer attempts and malformed artifact names.


v2.5.0
New Effects

- Fire — demoscene cellular-automaton flame; heat seeds the bottom virtual rows each tick and propagates upward through an averaging + random-cooling step. Parameters: Intensity, Cooling, Speed
- Metaballs — lava-lamp blobs following sinusoidal Lissajous paths; each pixel's brightness is the sum of Gaussian field contributions from every blob, creating natural hot-spots where blobs converge. Parameters: Blobs, Radius, Speed
- Game of Life — Conway's Game of Life on the LED mask with a glow trail; dead cells fade gradually rather than snapping to black. Auto-reseeds on extinction or stagnation (identical generation for 3+ consecutive steps). Parameters: Density, Speed, Trail
- Matrix Rain V2 — rebuilt Matrix rain with true per-column independent streams, each with its own speed and a random gap delay between drops. Parameters: Speed, Density, Direction
-     8-direction travel — Direction slider (0–7) selects: ↓ ↙ ← ↖ ↑ ↗ → ↘. Cardinal modes use column/row streams; diagonal modes generate COLS + ROWS − 1 diagonal streams covering the full grid. Switching direction live wipes the buffer and rebuilds geometry instantly.
 
New Features
 
- Per-effect parameter UI — a dynamic slider panel in the Effects tab rebuilds itself whenever an effect is selected. Each slider maps directly to a live attribute on the running effect instance, so changes take effect immediately without restarting. All effects expose a PARAMS dict; effects with no meaningful parameters show a placeholder.
- Crossfade on switch — when changing effects or modes, the driver snapshots the last rendered frame and blends from it to the new effect over 0.5 s. Toggle via the "Crossfade on switch" checkbox in the Effects tab. Both the Effects tab and the Sequencer tab share the same toggle.
- Sequencer tab — new tab for building an effect playlist. Add any effect with a configurable dwell time (1 s – 1 hr), reorder with ▲▼, remove entries, and hit Play to auto-cycle. Supports loop and crossfade toggles. The param panel updates to reflect whichever effect is currently playing. A countdown label shows time until the next step.
- Lightning now builds from top to bottom over time before echo/fade pulses.
- Added persistent per-effect PARAMS storage in app.py via effect_params JSON.
- Primary effect sliders restore saved values instead of defaults.
- Layer B uses the saved parameters when assigned as secondary.
- If Layer A and Layer B are the same effect, slider changes sync both instances.
- Fire, Wave, Wipe, and Scan include LRUD direction/flow metadata.
- Fireworks includes rocket-launch burst behaviour and trail persistence parameter. 
Improvements
 
- Matrix Rain — restored proper per-column stream behaviour with independent speeds and gap delays; the previous scroll-and-seed approach that lost individual stream character is replaced
- Fire seeding — heat source now seeds all 37 columns uniformly instead of only columns valid at the bottom mask row; fixes fire appearing skewed to one side due to the diagonal-cut LED mask
 
 Bug Fixes
 
-  Fixed blend persistence so Layer B effect and mix percentage are saved and restored when Remember settings is enabled.
- Fixed Matrix Rain V2 direction control to display arrows instead of numeric direction values.
- Rebuilt Starfield into a proper forward-flight starfield effect instead of random drift.
- Added Trail parameter to Starfield.
- Fixed blend persistence so Layer B and mix percentage restore after restart.
v2.1.21
 
- Releasing some updates for future changes
 
v2.1.2
 
- Fixed save state for Layer B
 
v2.1.1
 
- Each effect now has a small checkbox to its right in the grid. Checking one sets it as Blend Layer B — checking a different one automatically unchecks the previous one (only one Layer B at a time)
- The ✕ Clear button in the Blend group unchecks all boxes and resets the mix slider
- Right-click behaviour completely removed — no more hidden gestures needed
- The Blend group box label still shows the active Layer B name so it's always visible even when the checkbox is off-screen

v2.1.0
New Effects
 
- Snake — auto-playing AI snake navigates the 37×12 matrix, eats food, avoids walls and itself; flashes on death and restarts
- Clock — displays current local time as HH:MM in a 3×5 pixel font; colon blinks every half-second
- Typing Visualizer — fires a column brightness burst on each keypress, spread by character; falls back to randomised demo mode if pynput is unavailable
 
New Features
 
- Effect speed persistence — speed slider value is now saved and restored on startup alongside brightness and contrast
- GIF playback speed — new speed slider (0.1× – 10.0×) in the GIF tab; divides frame duration in the driver tick so any GIF can be slowed down or sped up without re-encoding
- Effect blend / crossfade — left-click an effect button to set it as Layer A (primary); right-click any effect button to assign it as Layer B; Mix slider (0–100%) crossfades both layers in real time; Clear button removes Layer B
 
Dependencies
 
- Added pynput>=1.7 (optional — Typing Visualizer degrades gracefully without it)
 
v2.0.35
 
- Added persistent save/restore of last active effect, brightness, contrast, GIF path, and position settings (opt-in via "Remember settings" checkbox)
 
v2.0.3
 
- Fixed several built-in effects that had incorrect or missing speed scaling
- Normalised project structure and file layout
 
v2.02
 
- Switched to Inno Setup for Windows installer creation
- Fixed release scripts and zip packaging
 
v2.0.1
 
- Added Windows installer (.exe setup package)
- Stabilised release pipeline and project structure
 
v2.0.0
New Effects
 
- The Matrix — digital rain with per-drop speed variance and fading trails
- Starfield — perspective-projected stars flying toward the viewer
- Comet — multi-comet streaks with randomised velocity and brightness tails
- Ripple — expanding ring bursts from random grid positions
- Helix — two-strand DNA helix scrolling across the matrix
- Fireworks — particle burst explosions with gravity and decay
- Bounce — glowing ball bouncing around the grid with a trail buffer
- Wave — sine wave sweeping horizontally across the display
- Audio Visualizer — FFT bar graph from system audio; falls back to plasma if no audio device is available
 
New Features
 
- GIF positioning controls: Offset X/Y and Scale sliders with live matrix preview
- Auto-fit button calculates correct scale from GIF dimensions
- Extended scale range (0.1× – 50×) to support both zoomed-in and shrunk large images
- Paint editor: 9-swatch brightness palette with accurate LED brightness steps
- Paint editor: contrast slider with Apply button
- Global brightness + contrast bar visible on all tabs
- Quick Controls popup from system tray (brightness, contrast, all effects)
- Effects submenu in tray right-click menu — switch modes without opening the main window
- Close-to-tray checkbox (window X button behaviour toggleable)
- GitHub button and automatic update check (polls GitHub releases API, silent on launch)
- Debug footer: live FPS, mode, and connection status
- Version string displayed in window title and tray tooltip
 
Improvements

- All effect buttons uniform width with centred text
- Tray menu styled to match app dark theme
- BCBar shared widget — brightness/contrast consistent between main window and Quick Controls
- GIF preview updates live as sliders move; no need to hit Play to see changes
- MatrixPreview widget made reusable across tabs
 
Protocol
 
- Confirmed HID wire format for ROG Strix Flare II Animate (VID=0x0B05, PID=0x19FC, MI_04)
- Single 1024-byte packet per frame: [0x60, 0x81, 0x00, 0x00, <312 LED bytes>, <padding>]
- Contrast applied in driver tick (not renderer), so it affects all modes uniformly
 
v1.0.0
 
- Initial public release — direct HID control of the ROG Strix Flare II Animate matrix display. Basic effects: Pulse, Rain, Wipe, Plasma, Noise, Scan. GIF and static image playback. No Armoury Crate required. 
## v2.5.0 
- Major updates 
 
## v2.5.0 
- Huge updates 
 
## v2.5.1 
- fixing release version 
 
## v2.5.5 
-  
 
## v2.5.5 
-  
 
## v2.5.2 
-  
