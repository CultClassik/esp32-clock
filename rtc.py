"""
One-time utility to set the DS1307 RTC module's time.

Run this manually (e.g. `ampy --port $SERIAL_PORT run rtc.py`) whenever the
RTC needs to be set or re-set, such as after first wiring it up or after its
backup battery dies. Do NOT import this from main.py or run it on every
boot -- it overwrites whatever time the RTC was keeping.

Wiring (CYD CN1 header): SCL -> GPIO22, SDA -> GPIO27
"""

import time

import machine

from ds1307 import DS1307

i2c = machine.I2C(0, scl=machine.Pin(22), sda=machine.Pin(27))
clock = DS1307(i2c)

# Enable the RTC oscillator
clock.halt(False)

# Set this to the current UTC time before running, then run once.
# Format: (year, month, day, weekday, hour, minute, second, subsecond)
# Weekday: 0=Monday, ..., 6=Sunday (per this driver's weekday_start=1 convention)
SET_TIME = (2025, 1, 1, 0, 0, 0, 0, 0)

if __name__ == "__main__":
    clock.datetime(SET_TIME)
    print("RTC set to:", clock.datetime())

    # Read back once a second to confirm it's ticking.
    for _ in range(5):
        print(clock.datetime())
        time.sleep(1)
