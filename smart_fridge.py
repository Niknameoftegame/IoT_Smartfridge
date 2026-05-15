import board
import adafruit_bmp280
import paho.mqtt.client as mqtt
import threading
import busio
from busio import SPI
import time
import digitalio
import requests
import datetime
from datetime import date
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import cv2
import json

# =====================================================
# PRODUCT CLASS
# =====================================================

class Product():
    expiration_date: date
    name: str
    warned: bool
    expired: bool

# =====================================================
# PIN DEFINITIE
# =====================================================

LED_GPIO      = board.D22
MOTOR_GPIO    = board.D21
OLED_DC_GPIO  = board.D24
OLED_RESET_GPIO = board.D25
OLED_CS_GPIO  = board.D5
TRIG_GPIO     = board.D16
ECHO_GPIO     = board.D20

BTN_IN_GPIO   = board.D19   # knop voor "IN"
BTN_OUT_GPIO  = board.D26   # knop voor "OUT"

# =====================================================
# CONSTANTEN
# =====================================================

CLOSED_DISTANCE    = 15
MAX_TIME_OPEN      = 30
PICO_IP            = "192.168.1.171"
BROKER             = "broker.hivemq.com"
PORT               = 1883
TOPIC_COMMAND      = "smart_fridge/door"
api                = "https://iot-api.vercel.app/"
days_before_warning = 3
cooldown           = 5
distance_cooldown  = 0.5
TOPIC_DOOR_STATUS = "smart_fridge/door_status"
# =====================================================
# GLOBALE VARIABELEN
# =====================================================

program  = True
temp     = 0
distance = 0
products = []
oled_busy = False   # True als QR-scan scherm actief is

# =====================================================
# MQTT SETUP
# =====================================================

def on_connect(client, userdata, flags, rc, properties):
    print("Connected to MQTT")
    client.subscribe(TOPIC_COMMAND)

def on_message(client, userdata, msg):
    command = msg.payload.decode()
    if command == "close":
        close_door()

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)

# =====================================================
# HARDWARE SETUP
# =====================================================

# BMP280
i2c   = busio.I2C(board.SCL, board.SDA)
bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=0x77)

# LED
led = digitalio.DigitalInOut(LED_GPIO)
led.direction = digitalio.Direction.OUTPUT

# Motor
Motor = digitalio.DigitalInOut(MOTOR_GPIO)
Motor.direction = digitalio.Direction.OUTPUT

# Ultrasoon
trig = digitalio.DigitalInOut(TRIG_GPIO)
trig.direction = digitalio.Direction.OUTPUT
trig.value = False

echo = digitalio.DigitalInOut(ECHO_GPIO)
echo.direction = digitalio.Direction.INPUT

# Knoppen
btn_in = digitalio.DigitalInOut(BTN_IN_GPIO)
btn_in.direction = digitalio.Direction.INPUT
btn_in.pull = digitalio.Pull.UP

btn_out = digitalio.DigitalInOut(BTN_OUT_GPIO)
btn_out.direction = digitalio.Direction.INPUT
btn_out.pull = digitalio.Pull.UP

# OLED
spi   = SPI(clock=board.SCK, MOSI=board.MOSI)
dc    = digitalio.DigitalInOut(OLED_DC_GPIO)
reset = digitalio.DigitalInOut(OLED_RESET_GPIO)
cs    = digitalio.DigitalInOut(OLED_CS_GPIO)
oled  = adafruit_ssd1306.SSD1306_SPI(128, 64, spi, dc, reset, cs)

image = Image.new("1", (128, 64))
draw  = ImageDraw.Draw(image)
font  = ImageFont.load_default()

# Camera + QR
cap      = cv2.VideoCapture(0)
detector = cv2.QRCodeDetector()

# =====================================================
# OLED FUNCTIES
# =====================================================

def oled_show(l1="", l2="", l3=""):
    """Toon 3 regels tekst op het OLED scherm."""
    draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
    draw.text((0,  0), l1, font=font, fill=255)
    draw.text((0, 20), l2, font=font, fill=255)
    draw.text((0, 40), l3, font=font, fill=255)
    oled.image(image)
    oled.show()

def oled_show_temperature():
    """Toon temperatuur — alleen als OLED niet bezet is door QR-scan."""
    if not oled_busy:
        draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
        draw.text((10, 20), f"{round(temp, 2)}°C", font=font, fill=255)
        oled.image(image)
        oled.show()

# =====================================================
# DEUR / MOTOR FUNCTIES
# =====================================================

def close_door():
    while distance > CLOSED_DISTANCE:
        Motor.value = True
    Motor.value = False

def publish_door_status(open: bool):
    client.publish(TOPIC_DOOR_STATUS, "open" if open else "closed")

# =====================================================
# PRODUCT / API FUNCTIES
# =====================================================

def get_content():
    response = requests.get(api + "get_content")
    for p in response.json():
        product = Product()
        product.expiration_date = p[2]
        product.name = p[1]
        product.warned = p[3]
        product.expired = p[4]
        products.append(product)

def insert_content(expiration_date, name, warned):
    product = Product()
    product.expiration_date = expiration_date
    product.name = name
    product.warned = warned

    products.append(product)
    requests.post(api + "insert_content", json={
        "expiration_date": expiration_date,
        "name": name,
        "warned": warned
    })

def remove_product(product):
    products.remove(product)
    requests.post(api + "remove_content", json={
        "name": product.name,
        "expiration_date": product.expiration_date
    })

def send_warning(product):
    days_left = (datetime.date.fromisoformat(product.expiration_date) - datetime.date.today()).days
    message = f"{product.name} expires in {days_left} days"
    requests.post(f"https://ntfy.sh/smart_fridge", data=message.encode('utf-8'))
    product.warned = True
    requests.post(api + "warned_true", json={
        "name": product.name,
        "expiration_date": product.expiration_date
    })

def product_expire(product):
    message = f"ALERT: {product.name} has expired!"
    requests.post(f"https://ntfy.sh/smart_fridge", data=message.encode('utf-8'))
    product.expired = True
    requests.post(api + "expired_true", json={
        "name": product.name,
        "expiration_date": product.expiration_date
    })

def send_to_api(product_data, action):
    payload = {
        "name": product_data["product"],
        "expiration_date": product_data["expiry"]
    }
    endpoint = "/insert_content" if action == "IN" else "/remove_content"
    r = requests.post(api + endpoint, json=payload, timeout=5)
    return r.status_code == 200

# =====================================================
# QR KNOP FUNCTIE
# =====================================================

def wait_button():
    oled_show("IN or OUT?", "D19 = IN", "D26 = OUT")
    while True:
        if not btn_in.value:
            time.sleep(0.2)
            return "IN"
        if not btn_out.value:
            time.sleep(0.2)
            return "OUT"

# =====================================================
# THREADS
# =====================================================

def task_read_temp():
    while program:
        global temp
        temp = bmp280.temperature
        time.sleep(cooldown)

def task_measure_distance():
    global distance
    while program:
        trig.value = False
        time.sleep(0.1)
        trig.value = True
        time.sleep(0.00001)
        trig.value = False

        while not echo.value:
            pulse_start = time.time()
        while echo.value:
            pulse_end = time.time()


        distance = (pulse_end - pulse_start) * 17000
        print(f"Distance: {distance:.1f} cm")
        time.sleep(distance_cooldown)

def task_door_status():
    '''Waits for hardcoded time to have passed beforer closing the door (if not already closed)'''
    seconds = 0
    while seconds < MAX_TIME_OPEN and distance > CLOSED_DISTANCE:
        time.sleep(1)
        seconds += 1
    if distance > CLOSED_DISTANCE:
        close_door()

#Old code below for debugging if function doesn't work
#    while program:
#        if distance > CLOSED_DISTANCE:
#            Motor.value = False
#        else:
#            Motor.value = True
#        time.sleep(distance_cooldown)


def task_send_temperature():
    while program:
        url = f"http://{PICO_IP}/?temp={temp}"
        requests.get(url, timeout=5)
        time.sleep(cooldown)

def task_door_statusMQTT():
    while program:
        if distance > CLOSED_DISTANCE:
            publish_door_status(True)
        else:
            publish_door_status(False)
        time.sleep(1)

def task_qr_scan():
    """Scant continu op QR-codes en verwerkt ze."""
    global oled_busy
    last_qr  = None
    qr_locked = False

    while program:
        ret, frame = cap.read()
        if not ret:
            continue

        data, _, _ = detector.detectAndDecode(frame)

        if not data:
            qr_locked = False
            last_qr   = None
            continue

        if qr_locked and data == last_qr:
            continue

        qr_locked = True
        last_qr   = data

        try:
            product_data = json.loads(data)

            oled_busy = True  # blokkeer temperatuur op scherm

            action = wait_button()  # toont "IN or OUT?" op OLED

            oled_show("Processing...", product_data["product"], action)
            success = send_to_api(product_data, action)

            if success:
                oled_show("SUCCESS", product_data["product"], action)
            else:
                oled_show("API ERROR")

            time.sleep(2)

        except Exception as e:
            oled_show("Invalid QR")
            print(e)
            time.sleep(2)

        finally:
            oled_busy = False  # geef scherm terug aan temperatuur
        

# =====================================================
# START THREADS
# =====================================================

t_read_temp       = threading.Thread(target=task_read_temp,       daemon=True)
t_measure_distance = threading.Thread(target=task_measure_distance, daemon=True)
t_door_status     = threading.Thread(target=task_door_status,     daemon=True)
t_qr_scan         = threading.Thread(target=task_qr_scan,         daemon=True)
t_send_temperature = threading.Thread(target=task_send_temperature, daemon=True)
t_door_statusMQTT = threading.Thread(target=task_door_statusMQTT, daemon=True)

t_read_temp.start()
t_measure_distance.start()
t_door_status.start()
t_send_temperature.start()
t_qr_scan.start()
client.loop_start()
t_door_statusMQTT.start()

# =====================================================
# MAIN LOOP
# =====================================================
get_content()
try:
    while program:
        for product in products:
            if (datetime.date.fromisoformat(product.expiration_date) - datetime.date.today()) <= datetime.timedelta(days=days_before_warning) and not product.warned:
                send_warning(product)
            elif datetime.date.fromisoformat(product.expiration_date) < datetime.date.today() and not product.expired:
                product_expire(product)

        oled_show_temperature()
        time.sleep(cooldown)

except KeyboardInterrupt:
    program = False
    Motor.value = False
    led.value = False
    t_read_temp.join()
    t_measure_distance.join()
    t_door_status.join()
    t_qr_scan.join()
    t_send_temperature.join()
    t_door_statusMQTT.join()
    cap.release()
    oled_show("Goodbye!")