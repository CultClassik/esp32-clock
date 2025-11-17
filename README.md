# esp32-clock
ESP32 based clock code - Managed by CultClassik/iac-github-mgmt (Github)

A little ESP32 based Internet clock with RTC and a small display for fun.

# Hardware
* ESP32 dev board
* [Tiny RTC I2C module 24C32 memory DS1307](https://lastminuteengineers.com/ds1307-rtc-arduino-tutorial/)
* Display

# Usage
* Download MicroPython firmware https://micropython.org/download/ESP32_GENERIC/
* Download the display library https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/display/ssd1306/ssd1306.py
* Plug ESP32 in and get the serial port with `SERIAL_PORT=$(ls /dev/tty.usb*)`
* Unplug, hold BOOT button on ESP32, then hit RST and let go to set boot modeand 

`esptool --chip esp32 --port $SERIAL_PORT erase-flash`

`python -m esptool --chip esp32 --port "$SERIAL_PORT" write_flash -z 0x1000 ESP32_GENERIC-20250911-v1.26.1.bin`


ampy --port "$SERIAL_PORT" put main.py

# Display Items
1. Current time and date, local time from WiFi and UTC
2. Weather
3. Wifi signal strength
