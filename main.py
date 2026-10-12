import time
from secrets import WIFI_HOSTNAME, WIFI_PASSWORD, WIFI_SSID

import machine
import network
import ntptime
from machine import I2C, SPI, Pin

# Save this file as ds1307.py https://github.com/mcauser/micropython-tinyrtc-i2c/blob/master/ds1307.py
from ds1307 import DS1307

# Save this file as ili9341.py https://github.com/rdagger/micropython-ili9341/blob/master/ili9341.py
from ili9341 import Display, color565

# Save this file as xglcd_font.py https://github.com/rdagger/micropython-ili9341/blob/master/xglcd_font.py
from xglcd_font import XglcdFont

WHITE_COLOR = color565(255, 255, 255)
BLACK_COLOR = color565(0, 0, 0)
GREEN_COLOR = color565(0, 255, 0)

NTP_SERVER = "time.diehlabs.lan"
GMT_OFFSET = -6  # time zone adjustment here, need to replace with a function that determines if it's daylight savings time or not
TIME_ZONE = GMT_OFFSET * 60 * 60  # change timezone offset to seconds

WIFI_CONNECT_TIMEOUT = 15  # seconds to wait for WiFi before falling back to the RTC

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

# Big-digit clock layout (320x240 landscape)
DIGIT_W = 60
DIGIT_H = 140
DIGIT_T = 14  # segment thickness
COLON_W = 20
GAP = 10
DIGITS_TOTAL_W = 4 * DIGIT_W + COLON_W + 4 * GAP
DIGITS_X = (320 - DIGITS_TOTAL_W) // 2
DIGITS_Y = 15
DATE_Y = DIGITS_Y + DIGIT_H + 15
STATUS_Y = DATE_Y + 30

# Segments lit per digit, in the order a (top), b (upper-right), c (lower-right),
# d (bottom), e (lower-left), f (upper-left), g (middle)
SEGMENTS = {
    0: "abcdef",
    1: "bc",
    2: "abged",
    3: "abgcd",
    4: "fgbc",
    5: "afgcd",
    6: "afgecd",
    7: "abc",
    8: "abcdefg",
    9: "abcdfg",
}


def init_display():
    # Function to set up SPI for TFT display
    display_spi = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13))

    # Set up display
    # rst is tied to cs here: the CYD doesn't break out a separate reset pin
    # rotation=90 makes the panel's actual pixel addressing match width/height
    # below -- without it, writes past column 240 wrap/corrupt since the
    # panel is natively 240 wide in portrait.
    return Display(
        display_spi,
        dc=Pin(2),
        cs=Pin(15),
        rst=Pin(15),
        width=320,
        height=240,
        rotation=90,
    )


def init_ds1307():
    """Set up the DS1307 RTC. Returns None if it's not wired up / not responding."""
    try:
        # CYD CN1 header: SCL -> GPIO22, SDA -> GPIO27
        i2c = I2C(0, scl=Pin(22), sda=Pin(27))
        clock = DS1307(i2c)
        clock.halt(False)
        return clock
    except OSError as e:
        print("DS1307 not found, continuing without it:", e)
        return None


def init_wlan():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(dhcp_hostname=WIFI_HOSTNAME)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > WIFI_CONNECT_TIMEOUT:
            print("WiFi connect timed out, falling back to RTC time.")
            wlan.active(False)
            return None
        print(f"WiFi status: {wlan.status()}")
        time.sleep(1)

    print("Connected to WiFi!")
    return wlan


def sync_time(ds1307):
    """
    Bring the system clock (and the DS1307, if present) up to date.

    If WiFi/NTP works, sync the system clock from NTP (UTC) and mirror that
    time onto the DS1307 so it keeps ticking correctly on the next boot
    without WiFi. If WiFi/NTP isn't available, seed the system clock from
    the DS1307 instead. If neither is available, the system clock just
    keeps whatever it booted with.
    """
    wlan = init_wlan()

    if wlan is not None:
        try:
            ntptime.host = NTP_SERVER
            ntptime.settime()
            print("System clock synchronized with NTP server.")
            if ds1307 is not None:
                ds1307.datetime(machine.RTC().datetime())
        except Exception as e:  # noqa: BLE001 -- must not crash the boot sequence
            print("Error synchronizing with NTP server:", e)
    elif ds1307 is not None:
        rtc_time = ds1307.datetime()
        machine.RTC().datetime(rtc_time)
        print("System clock seeded from DS1307:", rtc_time)
    else:
        print("No WiFi and no DS1307 -- clock will be wrong until one is available.")

    return wlan


def get_local_time():
    year, month, day, hour, minute, _second, weekday, _yearday = time.localtime(
        time.time() + TIME_ZONE
    )
    return year, month, day, hour, minute, weekday


def draw_digit(display, x, y, value, color, background):
    """Draw a single big digit (0-9) as a block 7-segment readout."""
    display.fill_rectangle(x, y, DIGIT_W, DIGIT_H, background)
    segs = SEGMENTS[value]
    t = DIGIT_T
    half = DIGIT_H // 2
    seg_w = DIGIT_W - 2 * t
    vert_h = half - t - t // 2

    if "a" in segs:
        display.fill_rectangle(x + t, y, seg_w, t, color)
    if "g" in segs:
        display.fill_rectangle(x + t, y + half - t // 2, seg_w, t, color)
    if "d" in segs:
        display.fill_rectangle(x + t, y + DIGIT_H - t, seg_w, t, color)
    if "f" in segs:
        display.fill_rectangle(x, y + t, t, vert_h, color)
    if "b" in segs:
        display.fill_rectangle(x + DIGIT_W - t, y + t, t, vert_h, color)
    if "e" in segs:
        display.fill_rectangle(x, y + half + t // 2, t, vert_h, color)
    if "c" in segs:
        display.fill_rectangle(x + DIGIT_W - t, y + half + t // 2, t, vert_h, color)


def draw_colon(display, x, color):
    dot = DIGIT_T
    cx = x + (COLON_W - dot) // 2
    display.fill_rectangle(cx, DIGITS_Y + DIGIT_H // 3 - dot // 2, dot, dot, color)
    display.fill_rectangle(cx, DIGITS_Y + 2 * DIGIT_H // 3 - dot // 2, dot, dot, color)


display = init_display()
ds1307 = init_ds1307()

# Turn on display backlight
backlight = Pin(21, Pin.OUT)
backlight.on()
display.clear(BLACK_COLOR)

wlan = sync_time(ds1307)

print("Loading Unispace font...")
unispace_font = XglcdFont("fonts/Unispace12x24.c", 12, 24)

# Lay out, left to right: digit, digit, colon, digit, digit -- each
# followed by a gap, computed with a running cursor so spacing can't drift.
_cursor = DIGITS_X
cell_x = []
for _i in range(2):
    cell_x.append(_cursor)
    _cursor += DIGIT_W + GAP
colon_x = _cursor
_cursor += COLON_W + GAP
for _i in range(2):
    cell_x.append(_cursor)
    _cursor += DIGIT_W + GAP

draw_colon(display, colon_x, GREEN_COLOR)


def draw_screen():
    _year, month, day, hour, minute, weekday = get_local_time()

    h_tens, h_ones = divmod(hour, 10)
    m_tens, m_ones = divmod(minute, 10)
    draw_digit(display, cell_x[0], DIGITS_Y, h_tens, GREEN_COLOR, BLACK_COLOR)
    draw_digit(display, cell_x[1], DIGITS_Y, h_ones, GREEN_COLOR, BLACK_COLOR)
    draw_digit(display, cell_x[2], DIGITS_Y, m_tens, GREEN_COLOR, BLACK_COLOR)
    draw_digit(display, cell_x[3], DIGITS_Y, m_ones, GREEN_COLOR, BLACK_COLOR)

    date_str = f"{WEEKDAYS[weekday]}, {MONTHS[month - 1]} {day}"
    display.fill_rectangle(0, DATE_Y, 320, 24, BLACK_COLOR)
    text_x = (320 - len(date_str) * (unispace_font.width + 1)) // 2
    display.draw_text(
        x=max(text_x, 0),
        y=DATE_Y,
        text=date_str,
        font=unispace_font,
        color=GREEN_COLOR,
        background=BLACK_COLOR,
    )

    if wlan is not None:
        status = f"WiFi signal {wlan.status('rssi')}"
    elif ds1307 is not None:
        status = "WiFi offline (RTC time)"
    else:
        status = "WiFi offline, no RTC"
    display.fill_rectangle(0, STATUS_Y, 320, 24, BLACK_COLOR)
    display.draw_text(
        x=1,
        y=STATUS_Y,
        text=status,
        font=unispace_font,
        color=GREEN_COLOR,
        background=BLACK_COLOR,
    )


while True:
    try:
        draw_screen()
    except Exception as e:  # noqa: BLE001 -- must not crash the display loop
        print("Error occurred:", e)
    time.sleep(0.5)
