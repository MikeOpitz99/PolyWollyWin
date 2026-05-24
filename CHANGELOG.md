# Changelog

## v2.0.0
### New Features
- 9 new effects: The Matrix, Starfield, Comet, Ripple, Helix, Fireworks, Bounce, Wave, Audio Visualizer
- GIF positioning controls: Offset X/Y and Scale sliders with live matrix preview
- Auto-fit button calculates correct scale from GIF dimensions
- Extended scale range (0.1×–50×) to support both zooming in and shrinking large images
- Paint editor: 9-swatch brightness palette with amber-orange LED colour accuracy
- Paint editor: contrast slider with Apply button
- Global brightness + contrast bar visible on all tabs
- Quick Controls popup from system tray (brightness, contrast, all effects)
- Effects submenu in tray right-click menu — switch modes without opening the window
- Close-to-tray checkbox (window X button behaviour toggleable)
- GitHub button and Check for Updates (polls GitHub releases API, silent on launch)
- Debug footer: live FPS, mode, and connection status
- Version string in window title and tray tooltip

### Improvements
- All effect buttons uniform width with centred text
- Tray menu styled to match app dark theme
- BCBar shared widget — brightness/contrast consistent across main window and Quick Controls
- GIF preview updates live as sliders move (no need to hit Play to see changes)
- MatrixPreview widget reusable across tabs

### Protocol
- Confirmed HID wire format for ROG Strix Flare II Animate (VID=0x0B05 PID=0x19FC)
- Single 1024-byte packet per frame: `[0x60, 0x81, 0x00, 0x00, <312 LED bytes>]`
- Contrast applied in driver tick (not in renderer), affects all modes uniformly

## v1.0.0
Initial public release. 
## v2.0.1 
- added an installer 
 
## v2.0.1 
- Updating release version 2.0.1 
 
## v2.0.1 
- Updating for Release and install 
 
## v2.0.1 
- Updating for release and proper installation 
 
## v2.0.1 
- Testing for final public consumption 
 
## v2.02 
- Updating release plan and installer 
 
## v2.02 
- Fixing zips 
 
## v2.02 
- Incluing inno as install creation tool 
 
## v2.02 
- fixing release scripts 
 
## v2.02 
- ready 
