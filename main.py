import time
from secrets import WIFI_HOSTNAME, WIFI_PASSWORD, WIFI_SSID

import machine
import network
import ntptime

import ssd1306

NTP_SERVER = "time.diehlabs.lan"
GMT_OFFSET = (
    -6
)  # time zone adjustment here, need to replace with a function that determines if it's daylight savings time or not
TIME_ZONE = GMT_OFFSET * 60 * 60  # change timezone offset to seconds
OLED_WIDTH = 128
OLED_HEIGHT = 32


def init_i2c():
    from machine import I2C, Pin

    # Initialize I2C interface
    i2c = I2C(scl=Pin(22), sda=Pin(21))

    # Create an SSD1306 object
    display = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c)
    return display


def show_msg(display, lines: list[str]):
    # Clear the display
    display.fill(0)
    # display.rect(0, 0, OLED_WIDTH, OLED_HEIGHT, 1)
    line_number = 0
    for idx, line in lines:
        if idx > 0:
            line_number += 10
        display.text(line, 0, line_number, 1)

    # Update the display
    display.show()


def sync_ntp_to_rtc():
    """
    Get the time from NTP server and set it to RTC.
    Timezone is UTC.
    """
    try:
        ntptime.host = NTP_SERVER
        ntptime.settime()
        print("RTC synchronized with NTP server.")
    except Exception as e:
        print("Error synchronizing with NTP server:", e)


def init_wlan(display=None):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(dhcp_hostname=WIFI_HOSTNAME)
    # try:
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    while not wlan.isconnected():
        if display is not None:
            show_msg(display, [f"WiFi status: {wlan.status()}"])
        time.sleep(1)

    print("Connected to WiFi!")
    return wlan


def format_time(the_time, format=24, offset_seconds=0):
    the_time = time.localtime(time.time() + offset_seconds)
    the_hour = the_time[
        3
    ]  # store the current hour, so it can be converted to 12 hour time
    if format == 12 and the_hour > 12:  # converting to 12 hour clock; remove these 2 line if you want 24
        the_hour -= 12
    the_time = f"{the_hour}:{the_time[4]}"

    return the_time


display = init_i2c()

wlan = init_wlan()

sync_ntp_to_rtc()

rtc = machine.RTC()

while True:
    current_time = rtc.datetime()
    local_time = format_time(current_time, format=12, offset_seconds=TIME_ZONE)
    utc_time = format_time(current_time)
    display_lines = [
        (0, f"Local: {local_time}"),
        (1, f"UTC: {utc_time}"),
        (2, f"Wifi Signal {wlan.status('rssi')}"),
    ]
    try:
        show_msg(display, display_lines)
    except Exception as e:
        print(f"Error displaying message: {e}")

    time.sleep(0.5)
