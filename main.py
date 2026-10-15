import json
import socket
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
# Only used if the network time zone lookup (fetch_utc_offset_seconds, called
# from sync_time) fails -- e.g. no internet, or ip-api.com is down.
FALLBACK_GMT_OFFSET = -6
TIME_ZONE = FALLBACK_GMT_OFFSET * 60 * 60  # seconds; sync_time() may replace this

WIFI_CONNECT_TIMEOUT = 15  # seconds to wait for WiFi before falling back to the RTC
RESYNC_INTERVAL = 24 * 60 * 60  # re-check NTP time and time zone this often

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


# This board's MADCTL row/column-exchange bit doesn't actually rotate the
# panel into landscape -- confirmed on hardware that both rotation=90 and
# rotation=270 stayed portrait (just mirrored top/bottom). So the panel is
# left in its native, definitely-working portrait orientation, and the
# clock is laid out in a 320x240 "logical landscape" coordinate system
# that's rotated into physical portrait coordinates in software (see
# fill_rect/put_text below). All the layout constants above (DIGITS_X,
# DATE_Y, etc.) are in this logical space and don't need to change.
LOGICAL_W = 320
LOGICAL_H = 240


def _to_physical_rect(lx, ly, lw, lh):
    """Rotate a logical-landscape rect into physical native coords.

    A plain swap (raw_x=ly, raw_y=lx) matches the 4-corner test, but a plain
    axis swap is a mirror, not a rotation -- confirmed on hardware: digit
    shapes (drawn with this function) came out mirrored, while text (drawn
    with put_text, whose "py" already runs the opposite sense) did not. So
    raw_y needs to run opposite lx, same sense as put_text's py.
    """
    return ly, LOGICAL_W - lw - lx, lh, lw


def fill_rect(display, lx, ly, lw, lh, color):
    px, py, pw, ph = _to_physical_rect(lx, ly, lw, lh)
    display.fill_rectangle(px, py, pw, ph, color)


def put_text(display, lx, ly, text, font, color, background):
    """Draw text whose logical top-left is (lx, ly), reading left to right,
    rotated the same way as fill_rect (see its docstring).

    py starts near the high end of the native height and runs DOWN as more
    characters are drawn (the underlying landscape mode's own mechanism) --
    starting too close to 0 (as an earlier version did) meant the row
    position went negative after only a few characters, which silently
    aborts the rest of the string instead of wrapping or clipping it."""
    px = ly
    py = LOGICAL_W - 1 - lx
    display.draw_text(px, py, text, font, color, background=background, landscape=True)


def init_display():
    # Function to set up SPI for TFT display
    # Lowered from 40MHz -- the big full-area fills the clock does are much
    # more SPI traffic than the old small-text version, and 40MHz over the
    # CYD's wiring can be marginal; 20MHz is still plenty fast for a clock.
    display_spi = SPI(1, baudrate=20000000, sck=Pin(14), mosi=Pin(13))

    # Set up display
    # rst=Pin(0): a harmless unused pin, NOT tied to cs as previously assumed
    # -- toggling cs during the driver's reset pulse was corrupting init.
    # rotation=270 (with this driver's default bgr=True) produces
    # MADCTL=0x28, confirmed correct for this exact board via the HenrysCat
    # CYD diagnostic tool's working default config.
    # width/height stay NATIVE (240x320) -- block()/is_off_grid() use these
    # directly as SET_COLUMN/SET_PAGE bounds with no rotation-awareness, so
    # they must match the chip's real addressable range regardless of
    # MADCTL. The *visual* landscape remap is a pure diagonal transpose
    # (confirmed empirically: visual_x=raw_y, visual_y=raw_x, no inversion)
    # handled in software by fill_rect/put_text below.
    return Display(
        display_spi,
        dc=Pin(2),
        cs=Pin(15),
        rst=Pin(0),
        width=240,
        height=320,
        rotation=270,
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


def fetch_utc_offset_seconds():
    """
    Look up the current UTC offset (including DST) for this device's public
    IP, via a free geolocation API -- no API key, no fixed timezone needed,
    and it stays correct across DST transitions automatically. Returns None
    on any failure (no internet, API down, etc.) so callers can fall back
    to a fixed offset.

    Uses ip-api.com's plain-HTTP endpoint (worldtimeapi.org, used
    previously, has been decommissioned -- it now resets the connection on
    both HTTP and HTTPS).
    """
    try:
        addr = socket.getaddrinfo("ip-api.com", 80)[0][-1]
        s = socket.socket()
        s.settimeout(5)
        s.connect(addr)
        s.send(b"GET /json?fields=status,offset HTTP/1.0\r\nHost: ip-api.com\r\n\r\n")
        response = b""
        while True:
            chunk = s.recv(512)
            if not chunk:
                break
            response += chunk
        s.close()
        body = response.split(b"\r\n\r\n", 1)[1]
        data = json.loads(body)
        if data.get("status") != "success":
            raise ValueError("API returned status=" + str(data.get("status")))
        return data["offset"]
    except Exception as e:  # noqa: BLE001 -- network lookup is best-effort
        print("Could not fetch time zone from network:", e)
        return None


def sync_time(ds1307):
    """
    Bring the system clock (and the DS1307, if present) up to date.

    If WiFi/NTP works, sync the system clock from NTP (UTC) and mirror that
    time onto the DS1307 so it keeps ticking correctly on the next boot
    without WiFi. If WiFi/NTP isn't available, seed the system clock from
    the DS1307 instead. If neither is available, the system clock just
    keeps whatever it booted with.

    Also updates TIME_ZONE from the network when possible (see
    fetch_utc_offset_seconds) so DST doesn't need to be tracked by hand.
    """
    global TIME_ZONE

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

        offset = fetch_utc_offset_seconds()
        if offset is not None:
            TIME_ZONE = offset
            print("Time zone offset from network:", TIME_ZONE, "seconds")
        else:
            print("Using fallback fixed time zone offset:", TIME_ZONE, "seconds")
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


def fill_hbar(display, x, y, w, h, color):
    """Horizontal segment bar with pointed (mitered) ends, like a real
    7-segment LED, instead of a plain blunt-ended rectangle."""
    tip = min(h // 2, w // 2)
    if tip <= 0:
        fill_rect(display, x, y, w, h, color)
        return
    fill_rect(display, x + tip, y, w - 2 * tip, h, color)
    half = (h - 1) / 2
    for r in range(h):
        inset = min(tip, round(abs(r - half) * tip / half)) if half > 0 else 0
        row_w = tip - inset
        if row_w > 0:
            fill_rect(display, x + tip - row_w, y + r, row_w, 1, color)
            fill_rect(display, x + w - tip, y + r, row_w, 1, color)


def fill_vbar(display, x, y, w, h, color):
    """Vertical segment bar with pointed (mitered) ends -- see fill_hbar."""
    tip = min(w // 2, h // 2)
    if tip <= 0:
        fill_rect(display, x, y, w, h, color)
        return
    fill_rect(display, x, y + tip, w, h - 2 * tip, color)
    half = (w - 1) / 2
    for c in range(w):
        inset = min(tip, round(abs(c - half) * tip / half)) if half > 0 else 0
        col_h = tip - inset
        if col_h > 0:
            fill_rect(display, x + c, y + tip - col_h, 1, col_h, color)
            fill_rect(display, x + c, y + h - tip, 1, col_h, color)


def draw_digit(display, x, y, value, color, background):
    """Draw a single big digit (0-9) as a block 7-segment readout."""
    fill_rect(display, x, y, DIGIT_W, DIGIT_H, background)
    segs = SEGMENTS[value]
    t = DIGIT_T
    half = DIGIT_H // 2
    seg_w = DIGIT_W - 2 * t
    vert_h = half - t - t // 2

    if "a" in segs:
        fill_hbar(display, x + t, y, seg_w, t, color)
    if "g" in segs:
        fill_hbar(display, x + t, y + half - t // 2, seg_w, t, color)
    if "d" in segs:
        fill_hbar(display, x + t, y + DIGIT_H - t, seg_w, t, color)
    if "f" in segs:
        fill_vbar(display, x, y + t, t, vert_h, color)
    if "b" in segs:
        fill_vbar(display, x + DIGIT_W - t, y + t, t, vert_h, color)
    if "e" in segs:
        fill_vbar(display, x, y + half + t // 2, t, vert_h, color)
    if "c" in segs:
        fill_vbar(display, x + DIGIT_W - t, y + half + t // 2, t, vert_h, color)


def draw_colon(display, x, color):
    dot = DIGIT_T
    cx = x + (COLON_W - dot) // 2
    fill_rect(display, cx, DIGITS_Y + DIGIT_H // 3 - dot // 2, dot, dot, color)
    fill_rect(display, cx, DIGITS_Y + 2 * DIGIT_H // 3 - dot // 2, dot, dot, color)


display = init_display()
ds1307 = init_ds1307()

# Turn on display backlight
backlight = Pin(21, Pin.OUT)
backlight.on()
display.clear(BLACK_COLOR)

wlan = sync_time(ds1307)
_last_sync = time.time()

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


# Last-drawn state, so draw_screen() only erases+redraws what actually
# changed -- redrawing unchanged digits/text every tick is what caused the
# visible flash, since each redraw blanks the area black before drawing the
# new content over it.
_last_digits = [None, None, None, None]
_last_date = None
_last_status = None
_status_tick = 0
STATUS_REFRESH_TICKS = 15  # rssi fluctuates almost every reading; only check it this often


def draw_screen():
    global _last_date, _last_status, _status_tick

    _year, month, day, hour, minute, weekday = get_local_time()

    h_tens, h_ones = divmod(hour, 10)
    m_tens, m_ones = divmod(minute, 10)
    new_digits = [h_tens, h_ones, m_tens, m_ones]
    for i, value in enumerate(new_digits):
        if value != _last_digits[i]:
            draw_digit(display, cell_x[i], DIGITS_Y, value, GREEN_COLOR, BLACK_COLOR)
            _last_digits[i] = value

    date_str = f"{WEEKDAYS[weekday]}, {MONTHS[month - 1]} {day}"
    if date_str != _last_date:
        fill_rect(display, 0, DATE_Y, 320, 24, BLACK_COLOR)
        text_x = (320 - len(date_str) * (unispace_font.width + 1)) // 2
        put_text(
            display,
            max(text_x, 0),
            DATE_Y,
            date_str,
            unispace_font,
            GREEN_COLOR,
            BLACK_COLOR,
        )
        _last_date = date_str

    _status_tick += 1
    if _status_tick >= STATUS_REFRESH_TICKS:
        _status_tick = 0
        if wlan is not None:
            status = f"WiFi signal {wlan.status('rssi')}"
        elif ds1307 is not None:
            status = "WiFi offline (RTC time)"
        else:
            status = "WiFi offline, no RTC"
        if status != _last_status:
            fill_rect(display, 0, STATUS_Y, 320, 24, BLACK_COLOR)
            put_text(display, 1, STATUS_Y, status, unispace_font, GREEN_COLOR, BLACK_COLOR)
            _last_status = status


while True:
    try:
        draw_screen()
    except Exception as e:  # noqa: BLE001 -- must not crash the display loop
        print("Error occurred:", e)

    # Re-sync time and time zone periodically rather than only at boot, so
    # a device that stays powered on through a DST transition still picks
    # up the new offset (DST changes at 2am local time in the US, not
    # midnight, and the exact time/date varies by country -- rather than
    # hardcoding any of that, just check regularly; ip-api.com always
    # returns whatever's correct right now).
    if time.time() - _last_sync >= RESYNC_INTERVAL:
        wlan = sync_time(ds1307)
        _last_sync = time.time()

    # Digits only change once a minute; this just needs to be frequent
    # enough to catch that promptly without redrawing needlessly.
    time.sleep(2)
