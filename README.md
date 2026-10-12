# esp32-clock
Cheap Yellow Display (CYD) based clock code - Managed by CultClassik/iac-github-mgmt (Github)

A little CYD based Internet clock with RTC and a big full-screen time display, for fun.

# Hardware
* [Cheap Yellow Display](https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display) (ESP32-2432S028R, ILI9341 2.8" TFT + XPT2046 touch) -- see that repo for the board's full pinout/schematics
* [Tiny RTC I2C module 24C32 memory DS1307](https://lastminuteengineers.com/ds1307-rtc-arduino-tutorial/), wired to the CYD's CN1 header (SCL -> GPIO22, SDA -> GPIO27) -- optional, see below

# Pinout used by this code
The CYD hard-wires its display, touch and SD card to fixed GPIOs; the only
pins free for extra hardware are on the CN1 header. This project uses:

| Function              | GPIO |
|------------------------|------|
| Display SPI SCK        | 14   |
| Display SPI MOSI       | 13   |
| Display DC             | 2    |
| Display CS / RST       | 15   |
| Display backlight      | 21   |
| RTC I2C SCL (CN1)      | 22   |
| RTC I2C SDA (CN1)      | 27   |

# Usage
* Install dependencies with [uv](https://docs.astral.sh/uv/): `uv sync` (run `uv run ampy ...` / `uv run esptool ...` below, or `source .venv/bin/activate` first)
* Download MicroPython firmware https://micropython.org/download/ESP32_GENERIC/
* Download the display library and save as `ili9341.py`: https://github.com/rdagger/micropython-ili9341/blob/master/ili9341.py
* Download the font library and save as `xglcd_font.py`: https://github.com/rdagger/micropython-ili9341/blob/master/xglcd_font.py
* Download the touch library and save as `xpt2046.py`: https://github.com/rdagger/micropython-ili9341/blob/master/xpt2046.py
* Download the RTC driver and save as `ds1307.py`: https://github.com/mcauser/micropython-tinyrtc-i2c/blob/master/ds1307.py
* Write `secrets.py` with your WiFi credentials (`WIFI_SSID`, `WIFI_PASSWORD`, `WIFI_HOSTNAME`)
* The RTC module is optional -- `main.py` works without it (falls back to NTP-only time, or boots with an unset clock if WiFi is also unavailable).
* Plug ESP32 in. `make` auto-detects the serial port from `/dev/tty.usb*`, or pass `SERIAL_PORT=/dev/tty.usbXXXX` explicitly.
* Unplug, hold BOOT button on ESP32, then hit RST and let go to set boot mode

# Makefile
Common operations are wrapped in the `Makefile` (run `make help` for the full list):
* `make flash` -- erase the board and write the MicroPython firmware
* `make deploy` -- copy `main.py` and everything it needs onto the device
* `make setrtc` -- run `rtc.py` on the device to set the DS1307's clock (after editing `SET_TIME` in that file; requires `make deploy` first so `ds1307.py` is already on the device)
* `make monitor` -- open a serial monitor to watch the device's console output

# Display Items
1. Big local time (24-hour) and date
2. Weather
3. Wifi signal strength
