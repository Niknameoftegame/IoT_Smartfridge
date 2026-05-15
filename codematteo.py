import cv2
import json
import time
import requests
import board
import digitalio
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import busio
from busio import SPI


# =====================================================
# API
# =====================================================

API = "https://iot-api.vercel.app"


# =====================================================
# OLED SETUP (UIT JE CODE)
# =====================================================

spi = SPI(clock=board.SCK, MOSI=board.MOSI)
dc = digitalio.DigitalInOut(board.D24)
reset = digitalio.DigitalInOut(board.D25)
cs = digitalio.DigitalInOut(board.D16)

oled = adafruit_ssd1306.SSD1306_SPI(128, 64, spi, dc, reset, cs)

image = Image.new("1", (128, 64))
draw = ImageDraw.Draw(image)
font = ImageFont.load_default()


def oled_show(l1="", l2="", l3=""):
    oled.fill(0)
    draw.rectangle((0, 0, 128, 64), outline=0, fill=0)

    draw.text((0, 0), l1, font=font, fill=255)
    draw.text((0, 20), l2, font=font, fill=255)
    draw.text((0, 40), l3, font=font, fill=255)

    oled.image(image)
    oled.show()


# =====================================================
# BUTTONS (UIT 2e CODE)
# =====================================================

btn_close = digitalio.DigitalInOut(board.D19)
btn_close.direction = digitalio.Direction.INPUT
btn_close.pull = digitalio.Pull.UP

btn_open = digitalio.DigitalInOut(board.D26)
btn_open.direction = digitalio.Direction.INPUT
btn_open.pull = digitalio.Pull.UP


def wait_button():
    oled_show("IN or OUT?", "GPIO13 = IN", "GPIO6 = OUT")

    while True:
        if not btn_close.value:
            time.sleep(0.2)
            return "IN"

        if not btn_open.value:
            time.sleep(0.2)
            return "OUT"


# =====================================================
# API CALL
# =====================================================

def send_to_api(product, action):

    payload = {
        "name": product["product"],
        "expiration_date": product["expiry"]
    }

    endpoint = "/insert_content" if action == "IN" else "/remove_content"

    r = requests.post(API + endpoint, json=payload, timeout=5)

    return r.status_code == 200


# =====================================================
# CAMERA + QR
# =====================================================

cap = cv2.VideoCapture(0)
detector = cv2.QRCodeDetector()

last_qr = None
qr_locked = False

print("Smart Fridge", "Ready to scan")
oled_show("Smart Fridge", "Ready to scan")


# =====================================================
# MAIN LOOP
# =====================================================

# Verwijder deze regels overal:
# cv2.imshow("fridge", frame)
# if cv2.waitKey(1) & 0xFF == ord('q'): break

# En vervang de main loop door:
while True:
    ret, frame = cap.read()
    if not ret:
        continue

    data, bbox, _ = detector.detectAndDecode(frame)

    if not data:
        qr_locked = False
        last_qr = None
        continue

    if qr_locked and data == last_qr:
        continue

    qr_locked = True
    last_qr = data

    try:
        product = json.loads(data)
        print(product["product"], "Choose action", "")
        oled_show(product["product"], "Choose action", "")
        action = wait_button()
        print("Processing...", product["product"], action)
        oled_show("Processing...", product["product"], action)
        success = send_to_api(product, action)

        if success:
            print("SUCCESS", product["product"], action)
            oled_show("SUCCESS", product["product"], action)
        else:
            print("API ERROR")
            oled_show("API ERROR")

        time.sleep(2)
        oled_show("Ready to scan")

    except Exception as e:
        print("Invalid QR")
        oled_show("Invalid QR")
        print(e)


cap.release()
cv2.destroyAllWindows()