# Changelog

Notable changes to PolyWollyWin are recorded here.
## v3.0.3

### Changed

- Prepared the repository for public users and contributors.
- Rebuilt the README with installation, build, troubleshooting, and hardware support information.
- Added hardware-porting and contribution documentation.
- Added bug, feature, and hardware-port issue templates.
- Made the Inno Setup build independent of local drive paths.
- Separated runtime, optional, and development dependencies.
- Cleaned the licence, acknowledgements, changelog, and repository contents.

## v3.0.2

### Fixed

- Added a forced shutdown path so the application exits even when audio, HID, or dependency cleanup becomes blocked.
- Added a two-second shutdown watchdog to prevent PolyWollyWin from remaining in Task Manager after exit.
- Restored TIFF support in the optimized packaged build.

### Changed

- Updated release packaging for the 3.0.2 build.

## v3.0.1

### Changed

- Rebuilt the PyInstaller configuration as an optimized ONEDIR package.
- Removed unused Qt modules, platform plugins, translations, and Pillow components from release builds.
- Kept the Windows platform plugin and the image formats used by PolyWollyWin.
- Reduced release size without changing the source-run dependency model.

## v3.0.0

### Fixed

- Repaired installer generation and release packaging.

## v2.9.0

### Added

- Added start-minimized behavior for tray-based startup.

## v2.8.5

### Fixed

- Corrected preview and paint column offsets.

## v2.7.0

### Added

- Added Knight Industries inspired effects and controls.

## v2.6.5

### Changed

- Updated and refined built-in effects.

## v2.6.3

### Added

- Added a one-click release workflow for building release artifacts from a single version prompt.
- Added automated portable ZIP packaging.
- Added automated Inno Setup generation for `PolyWollyWin-vX.X.X-Setup.exe`.
- Added release-output validation.
- Added repository hygiene and release archive auditing.

### Changed

- Updated installer architecture settings.
- Improved uninstall handling with a stable `RunOnceId`.

### Fixed

- Fixed version drift between `version.py` and `PolyWollyWin.iss`.
- Fixed release builds producing installers with stale filenames.
- Replaced fragile version replacement logic with safer line-based updating.
- Kept public `.spec` and `.iss` build files visible to Git.
- Cleaned up malformed and superseded release output handling.

## v2.5.0

### Added

- Added Fire, a demoscene-style cellular flame effect.
- Added Metaballs with animated Gaussian fields.
- Added Conway's Game of Life with fading trails and automatic reseeding.
- Rebuilt Matrix Rain V2 with independent streams and eight travel directions.
- Added live per-effect parameter controls.
- Added crossfade when changing effects or modes.
- Added the Sequencer tab for timed effect playlists.
- Added persistent per-effect parameter storage.
- Added live Layer A and Layer B blending.
- Added direction and flow metadata to applicable effects.
- Added rocket launch behavior and trail persistence to Fireworks.

### Changed

- Rebuilt Matrix Rain stream behavior.
- Improved Starfield into a forward-flight effect.
- Improved Fire seeding across the full logical width.
- Changed Lightning so branches build from top to bottom before fading.

### Fixed

- Fixed Layer B and mix persistence.
- Fixed Matrix Rain V2 direction labels.
- Fixed saved parameter restoration for primary and secondary effect instances.

## v2.1.21

### Changed

- Added internal preparation for later feature work.

## v2.1.2

### Fixed

- Fixed Layer B saved-state handling.

## v2.1.1

### Changed

- Replaced hidden right-click blend assignment with visible effect checkboxes.
- Added a Clear control for Layer B.
- Kept the active secondary effect visible in the blend panel.

## v2.1.0

### Added

- Added Snake.
- Added Clock.
- Added Typing Visualizer.
- Added effect speed persistence.
- Added GIF playback speed control.
- Added live effect blending.

## v2.0.35

### Added

- Added opt-in persistence for the active effect, brightness, contrast, GIF path, and positioning.

## v2.0.3

### Fixed

- Corrected speed scaling across several effects.
- Normalized project structure and file layout.

## v2.0.2

### Changed

- Switched release installation to Inno Setup.
- Improved ZIP and installer packaging.

## v2.0.1

### Added

- Added a Windows installer.
- Stabilized the public release structure.

## v2.0.0

### Added

- Added Matrix Rain.
- Added Starfield.
- Added Comet.
- Added Ripple.
- Added Helix.
- Added Fireworks.
- Added Bounce.
- Added Wave.
- Added Audio Visualizer.
- Added GIF positioning, scaling, auto-fit, and live preview.
- Added the paint editor and brightness palette.
- Added global brightness and contrast controls.
- Added quick controls and effect switching from the system tray.
- Added close-to-tray behavior.
- Added GitHub update checks.
- Added live status information for FPS, mode, and connection state.

### Protocol

- Confirmed the Flare II Animate HID frame format.
- Confirmed a single 1024 byte payload containing 312 LED brightness values.
- Moved contrast handling into the driver loop so it applies to every mode.

## v1.0.0

### Added

- Initial public release.
- Added direct HID control of the ROG Strix Flare II Animate matrix.
- Added basic effects, GIF playback, and static image playback.
