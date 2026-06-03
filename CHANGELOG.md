# Changelog

All notable changes to PolyWollyWin are documented here.

---
## V2.1.1
Each effect now has a small checkbox to its right in the grid. Checking one sets it as Blend Layer B — checking a different one automatically unchecks the previous one (only one Layer B at a time).
The ✕ Clear button in the Blend group unchecks all boxes and resets the mix slider.
The right-click behaviour is completely removed — no more hidden gestures needed.
The Blend group box label still shows the active Layer B name so it's always visible even when the checkbox is off-screen if you scroll.



## v2.1.0
### New Effects
- **Snake** — auto-playing AI snake navigates the 37×12 matrix, eats food, avoids walls and itself; flashes on death and restarts
- **Clock** — displays current local time as HH:MM in a 3×5 pixel font; colon blinks every half-second
- **Typing Visualizer** — fires a column brightness burst on each keypress, spread by character; falls back to randomised demo mode if pynput is unavailable

### New Features
- **Effect speed persistence** — speed slider value is now saved and restored on startup alongside brightness and contrast
- **GIF playback speed** — new speed slider (0.1× – 10.0×) in the GIF tab; divides frame duration in the driver tick so any GIF can be slowed down or sped up without re-encoding
- **Effect blend / crossfade** — left-click an effect button to set it as Layer A (primary); right-click any effect button to assign it as Layer B; Mix slider (0–100%) crossfades both layers in real time; Clear button removes Layer B

### Dependencies
- Added `pynput>=1.7` (optional — Typing Visualizer degrades gracefully without it)

---

## v2.0.35
- Added persistent save/restore of last active effect, brightness, contrast, GIF path, and position settings (opt-in via "Remember settings" checkbox)

## v2.0.3
- Fixed several built-in effects that had incorrect or missing speed scaling
- Normalised project structure and file layout

## v2.02
- Switched to Inno Setup for Windows installer creation
- Fixed release scripts and zip packaging

## v2.0.1
- Added Windows installer (`.exe` setup package)
- Stabilised release pipeline and project structure

---

## v2.0.0
### New Effects
- **The Matrix** — digital rain with per-drop speed variance and fading trails
- **Starfield** — perspective-projected stars flying toward the viewer
- **Comet** — multi-comet streaks with randomised velocity and brightness tails
- **Ripple** — expanding ring bursts from random grid positions
- **Helix** — two-strand DNA helix scrolling across the matrix
- **Fireworks** — particle burst explosions with gravity and decay
- **Bounce** — glowing ball bouncing around the grid with a trail buffer
- **Wave** — sine wave sweeping horizontally across the display
- **Audio Visualizer** — FFT bar graph from system audio; falls back to plasma if no audio device is available

### New Features
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

### Improvements
- All effect buttons uniform width with centred text
- Tray menu styled to match app dark theme
- BCBar shared widget — brightness/contrast consistent between main window and Quick Controls
- GIF preview updates live as sliders move; no need to hit Play to see changes
- MatrixPreview widget made reusable across tabs

### Protocol
- Confirmed HID wire format for ROG Strix Flare II Animate (VID=0x0B05, PID=0x19FC, MI_04)
- Single 1024-byte packet per frame: `[0x60, 0x81, 0x00, 0x00, <312 LED bytes>, <padding>]`
- Contrast applied in driver tick (not renderer), so it affects all modes uniformly

---

## v1.0.0
Initial public release — direct HID control of the ROG Strix Flare II Animate matrix display. Basic effects: Pulse, Rain, Wipe, Plasma, Noise, Scan. GIF and static image playback. No Armoury Crate required.
 
## v2.1.1 
-  
 
## v2.1.2 
- fixing the save for layer b - oof. 
