# Hardware Porting Guide

PolyWollyWin currently supports one confirmed device:

```text
ASUS ROG Strix Flare II Animate
VID:        0x0B05
PID:        0x19FC
Usage page: 0xFF02
Interface:  normally MI_04
```

The application is not yet a formal device-plugin system. A port normally requires changes to `transport.py` and `renderer.py`, plus small integration changes when the new device has additional commands or capabilities.

The effect logic is already mostly hardware-independent. Effects render logical grayscale frames, and the renderer converts those frames into the physical LED order expected by the device.

## Architecture

```text
Effects and image tools
        |
        v
Logical matrix frame
        |
        v
renderer.py
  - dimensions
  - physical mask
  - LED ordering
        |
        v
transport.py
  - device discovery
  - report ID
  - packet header
  - payload size
  - HID write
        |
        v
Hardware
```

## Porting checklist

A usable hardware port needs answers to all of the following.

### USB identity

- Vendor ID
- Product ID
- Interface number
- Usage page
- Usage
- Report ID
- Whether the device uses feature reports, output reports, or both

### Frame format

- Total HID write size
- Command or packet header
- Number of LED values
- Bytes per LED
- Pixel format, such as grayscale, RGB, or packed bits
- Required padding
- Frame segmentation rules
- Required initialization or mode-switch commands
- Required acknowledgements or timing delays

### Geometry

- Logical width and height
- Physical LED count
- Missing-cell mask
- Physical LED order
- Rotation, mirroring, or serpentine row behavior
- Brightness range and gamma behavior

## Step 1: Capture known-good traffic

Use the vendor software to display controlled test patterns while capturing USB traffic.

Useful tools on Windows include:

- USBPcap
- Wireshark
- Device Manager
- USB Device Tree Viewer
- hidapitester or a small hidapi script

Start with simple patterns:

1. All LEDs off
2. All LEDs at low brightness
3. All LEDs at full brightness
4. One logical row
5. One logical column
6. One moving pixel
7. Two pixels with clearly different brightness values

Controlled patterns make packet boundaries and physical LED ordering easier to identify.

Do not commit raw captures containing unrelated USB traffic or personal paths. Reduce captures to the relevant device and document the packet bytes in text.

## Step 2: Identify the correct HID interface

A device can expose several HID interfaces under the same VID and PID.

The current transport selects the interface by usage page:

```python
VID = 0x0B05
PID = 0x19FC
USAGE_PAGE = 0xFF02
```

For a new device, enumerate every matching interface and record:

- path
- interface number
- usage page
- usage
- report lengths
- manufacturer and product strings

Do not assume that `MI_04` or usage page `0xFF02` applies to another ASUS device.

## Step 3: Reproduce one confirmed frame

Before integrating the full application, write a minimal script that:

1. Opens the exact HID interface.
2. Sends one known frame.
3. Waits briefly.
4. Sends a blank frame.
5. Closes the interface.

The current keyboard uses:

```text
0x00 report ID prefix

1024 byte payload:
[0x60, 0x81, 0x00, 0x00, <312 LED bytes>, <zero padding>]
```

That format is specific to the Flare II Animate and must not be assumed for another product.

## Step 4: Replace or generalize `transport.py`

The existing transport exposes a small public surface:

```python
connect()
disconnect()
connected
send_frame()
send_blank()
send_brightness()
enumerate_interfaces()
```

A new transport should preserve those behaviors where practical.

A minimal skeleton looks like:

```python
import hid


class MyTransport:
    def __init__(self):
        self._dev = None

    def connect(self) -> str:
        # Enumerate and open the confirmed interface.
        raise NotImplementedError

    def disconnect(self):
        if self._dev is not None:
            self._dev.close()
        self._dev = None

    @property
    def connected(self) -> bool:
        return self._dev is not None

    def send_frame(self, led_bytes):
        # Validate, encode, pad, and transmit one frame.
        raise NotImplementedError

    def send_blank(self):
        # Send a valid all-off frame.
        raise NotImplementedError

    def send_brightness(self, level: int):
        # Implement only after confirming the device command.
        raise NotImplementedError
```

Keep packet encoding in the transport. Do not scatter device command bytes through the UI or effect code.

## Step 5: Define geometry in `renderer.py`

The current renderer uses:

```python
ROWS = 12
COLS = 37
PHYSICAL_LED_COUNT = 312
```

It builds a mask where row `r` begins at column `r * 2`, then emits active cells in row-major order.

For a new device, replace:

- `ROWS`
- `COLS`
- `PHYSICAL_LED_COUNT`
- `MASK`
- `PHYSICAL_INDICES`
- any device-specific default scaling or offsets

Validate both directions:

```python
logical_to_physical()
physical_to_logical()
```

A one-pixel walking test should visit every physical LED exactly once and in the expected order.

## Step 6: Handle color depth

PolyWollyWin currently renders 8-bit grayscale values from 0 to 255.

A color device may require:

- three bytes per LED
- RGB, GRB, BGR, or another channel order
- packed 4-bit or 5-bit channels
- a global brightness byte
- gamma correction
- multiple packets per frame

Keep effects in a logical format that is easy to work with, then convert to the device wire format at the renderer or transport boundary.

Do not rewrite every effect around the packet format.

## Step 7: Confirm frame timing

Test:

- maximum reliable FPS
- behavior when packets are sent too quickly
- whether writes block
- whether the device drops frames
- whether an acknowledgement is required
- whether the device must periodically receive a keepalive

Start slowly, then increase the frame rate while checking for corruption, disconnects, and device resets.

## Step 8: Integrate safely

A hardware port should not silently claim support based only on matching branding.

Add a device only after confirming:

- the exact USB identity
- the correct interface
- a repeatable frame command
- the complete LED mapping
- a reliable blank or shutdown frame
- clean disconnect behavior

Document the exact tested model number and firmware version when available.

## Information to include with a port request

Open a hardware-port issue and include:

- Manufacturer and exact model
- Windows Device Manager hardware IDs
- VID and PID
- Interface and usage-page enumeration
- Matrix dimensions
- Physical LED count
- Vendor software name and version
- A short description of the capture process
- Relevant packet examples
- Photos or video of controlled test patterns
- Whether you can test experimental builds

Remove serial numbers, usernames, unrelated USB traffic, and private file paths before posting.

## Pull request expectations

A device-port pull request should include:

- transport implementation
- geometry and mapping implementation
- detection that cannot accidentally select unrelated interfaces
- a blank-frame path
- documented packet format
- tested model and firmware details
- updated README support table
- no raw private captures
- no vendor binaries
