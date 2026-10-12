"""
One-off diagnostic: draws distinct markers so we can empirically determine
how this specific panel maps (x, y) to physical pixels, instead of guessing
from driver source code (which has been wrong twice on this board already).

Run with: uv run ampy --port $SERIAL_PORT run rotation_test.py
Does not touch main.py.
"""

from machine import SPI, Pin

from ili9341 import Display, color565

BLACK = color565(0, 0, 0)
RED = color565(255, 0, 0)
GREEN = color565(0, 255, 0)
BLUE = color565(0, 0, 255)
YELLOW = color565(255, 255, 0)
WHITE = color565(255, 255, 255)

display_spi = SPI(1, baudrate=20000000, sck=Pin(14), mosi=Pin(13))
# Settings confirmed via the HenrysCat CYD diagnostic tool's default
# (working) config for this exact board: ILI9341, BGR, MADCTL=0x28, which
# decodes to mirror=False, rotation=270 with this driver's default bgr=True.
# rst=Pin(0): harmless unused pin, not tied to cs (toggling cs during the
# driver's reset pulse likely corrupted earlier init attempts).
# width/height stay NATIVE (240x320) -- block()/is_off_grid() use these
# directly as SET_COLUMN/SET_PAGE bounds with no rotation-awareness, so they
# must match the chip's real addressable range regardless of MADCTL; the
# *visual* landscape remap comes entirely from the rotation= MADCTL bits.
display = Display(
    display_spi, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=240, height=320, rotation=270
)

backlight = Pin(21, Pin.OUT)
backlight.on()

display.clear(BLACK)

W, H = 240, 320
S = 40  # marker square size

# One distinct color per corner, by (x, y) = (0,0) / (W-S,0) / (0,H-S) / (W-S,H-S)
display.fill_rectangle(0, 0, S, S, RED)  # (x=0, y=0)
display.fill_rectangle(W - S, 0, S, S, GREEN)  # (x=W-S, y=0)
display.fill_rectangle(0, H - S, S, S, BLUE)  # (x=0, y=H-S)
display.fill_rectangle(W - S, H - S, S, S, YELLOW)  # (x=W-S, y=H-S)

# Thin white bar along the full top edge (y=0..9, all x) to mark which edge
# the driver considers y=0.
display.fill_rectangle(0, 0, W, 10, WHITE)

print("Done. Corners: (0,0)=RED (W-S,0)=GREEN (0,H-S)=BLUE (W-S,H-S)=YELLOW")
print("Top edge (y=0..9, full width) = WHITE bar")
