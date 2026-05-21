import board
import adafruit_bmp280
import paho.mqtt.client as mqtt
import threading
import busio
from busio import SPI
import time
import digitalio
from gpiozero import OutputDevice
import requests
import datetime
from datetime import date
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import cv2
import json

# CLASSES

class Product():
    expiration_date: date
    name: str
    warned: bool
    expired: bool

# PIN DEFINITIONS

LED_GPIO        = board.D6
MOTOR_GPIO      = board.D21
OLED_DC_GPIO    = board.D24
OLED_RESET_GPIO = board.D25
OLED_CS_GPIO    = board.D5
TRIG_GPIO       = board.D16
ECHO_GPIO       = board.D20

BTN_IN_GPIO     = board.D19   # button for "IN"
BTN_OUT_GPIO    = board.D26   # button for "OUT"

# CONSTANTS

CLOSED_DISTANCE     = 14
MAX_TIME_OPEN       = 30

days_before_warning = 3
cooldown            = 5
distance_cooldown   = 0.5
QR_COOLDOWN_SECS    = 10   # seconds a scanned code stays blocked

BROKER              = "broker.hivemq.com" # MQTT Credentials
PORT                = 1883
TOPIC_COMMAND       = "smart_fridge/door"
TOPIC_DOOR_STATUS   = "smart_fridge/door_status"
TOPIC_TEMPERATURE = "smart_fridge_2026/senne_lode_xander_matteo/temperatuur"

PICO_IP = "192.168.1.171" #IP for PICO

api                 = "https://iot-api.vercel.app/" #API Link

# GLOBAL VARIABLES

program   = True
temp      = 0
distance  = 0
products  = []
oled_busy = False   # True when QR Screen is activate
closing   = False   # True while close_door() is actively running
door_lock = threading.Lock()  # prevents simultaneous close_door() calls

# MQTT SETUP

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

# HARDWARE SETUP

# BMP280
i2c    = busio.I2C(board.SCL, board.SDA)
bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=0x77)

# LED
led = digitalio.DigitalInOut(LED_GPIO)
led.direction = digitalio.Direction.OUTPUT

# Motor — active_high=False: LOW = motor on, initial_value=False = off at boot
Motor = OutputDevice(21, active_high=False, initial_value=False)

# Ultrasonic sensor
trig = digitalio.DigitalInOut(TRIG_GPIO)
trig.direction = digitalio.Direction.OUTPUT
trig.value = False

echo = digitalio.DigitalInOut(ECHO_GPIO)
echo.direction = digitalio.Direction.INPUT

# Buttons
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

# OLED FUNCTIONS

def oled_show(l1="", l2="", l3=""):
    """Display 3 lines on OLED"""
    draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
    draw.text((0,  0), l1, font=font, fill=255)
    draw.text((0, 20), l2, font=font, fill=255)
    draw.text((0, 40), l3, font=font, fill=255)
    oled.image(image)
    oled.show()

def oled_show_temperature():
    """Show temperature when OLED is not busy with QR."""
    if not oled_busy:
        draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
        draw.text((10, 20), f"{round(temp, 2)}°C", font=font, fill=255)
        oled.image(image)
        oled.show()

# DOOR / MOTOR FUNCTIONS

def close_door():
    """
    Activate motor until the door is closed (distance <= CLOSED_DISTANCE).
    Lock prevents two threads (MQTT + timer) from running this simultaneously.
    """
    global closing
    if not door_lock.acquire(blocking=False):
        return   # already closing — ignore duplicate call
    try:
        closing = True
        Motor.on()
        while distance > CLOSED_DISTANCE and program:
            time.sleep(0.05)
        Motor.off()
    finally:
        closing = False
        door_lock.release()

def publish_door_status(open: bool):
    client.publish(TOPIC_DOOR_STATUS, "open" if open else "closed")

# PRODUCT / API FUNCTIONS

def get_content():
    response = requests.get(api + "get_content")
    # Create an object of every returned product and add it to the list of products.
    for p in response.json():
        product = Product()
        product.expiration_date = p[2]
        product.name = p[1]
        product.warned = p[3]
        product.expired = p[4]
        products.append(product)

def insert_content(expiration_date, name, warned):
    #Create an object with the given values and post it to the API
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
    #Remove a product from the database based on the name and expiration date.
    requests.post(api + "remove_content", json={
        "name": product.name,
        "expiration_date": product.expiration_date
    })

def send_warning(product):
    #If there are a certain amount of days left, send a warning via an API request to ntfy.
    days_left = (datetime.date.fromisoformat(product.expiration_date) - datetime.date.today()).days
    message = f"{product.name} expires in {days_left} days"
    requests.post(f"https://ntfy.sh/smart_fridge", data=message.encode('utf-8'))
    product.warned = True
    #Set warned true in the database for this product.
    requests.post(api + "warned_true", json={
        "name": product.name,
        "expiration_date": product.expiration_date
    })

def product_expire(product):
    #When a product expires send a message via an API request and remove the product from the database.
    message = f"ALERT: {product.name} has expired!"
    requests.post(f"https://ntfy.sh/smart_fridge", data=message.encode('utf-8'))
    product.expired = True
    products.remove(product)
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

# QR KNOP FUNCTION

def wait_button():
    #ASK FOR IN OR OUT ON THE OLED
    #RETURN CHOSEN VALUE FOR FURTHER ACITONS
    oled_show("IN or OUT?", "LEFT = IN", "RIGHT = OUT")
    while True:
        if not btn_in.value:
            time.sleep(0.2)
            return "IN"
        if not btn_out.value:
            time.sleep(0.2)
            return "OUT"

# THREADS

def task_read_temp():
    #Read the temperature with the bmp280 sensor.
    while program:
        global temp
        temp = bmp280.temperature
        time.sleep(cooldown)

def task_measure_distance():
    #Send a pulse and calculate the distance.
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
    #Checks if door is open for too long, and closes if it is.
    was_open   = False
    open_since = None

    while program:
        if closing:
            was_open   = False
            open_since = None
            led.value  = False
            time.sleep(0.5)
            continue

        door_open = distance > CLOSED_DISTANCE
        led.value = door_open

        if door_open and not was_open:
            was_open   = True
            open_since = time.time()

        elif door_open and was_open:
            if time.time() - open_since >= MAX_TIME_OPEN:
                close_door()
                was_open   = False
                open_since = None

        elif not door_open and was_open:
            was_open   = False
            open_since = None

        time.sleep(0.5)

def task_send_temperature():
    #Send the temperature to the PICO
   while program:
       url = f"http://{PICO_IP}/?temp={temp}"
       requests.get(url, timeout=5)
       time.sleep(cooldown)

def task_door_statusMQTT():
    #Publish the status of the door to MQTT.
    while program:
        publish_door_status(distance > CLOSED_DISTANCE)
        time.sleep(1)

def task_qr_scan():
    """
    Scans for QR codes continuously

    A code is blocked from re-scanning until these conditions are true:
      1. QR_COOLDOWN_SECS have passed since the last scan.
      2. The code has left the camera frame at least once.
    This prevents scanning the same product twice.
    """
    global oled_busy

    last_processed_qr   = None
    last_processed_time = 0
    code_left_frame     = True

    while program:
        ret, frame = cap.read()
        if not ret:
            continue

        try:
            data, _, _ = detector.detectAndDecode(frame)
        except cv2.error:
            continue

        # No QR in view
        if not data:
            code_left_frame = True
            continue

        # Same code as last scan: apply cooldown + must-leave-frame block
        if data == last_processed_qr:
            cooldown_done = (time.time() - last_processed_time) >= QR_COOLDOWN_SECS
            if not (cooldown_done and code_left_frame):
                continue
            last_processed_qr = None

        #  New valid scan
        code_left_frame     = False
        last_processed_time = time.time()

        try:
            product_data = json.loads(data)
            oled_busy = True

            action = wait_button()

            oled_show("Processing...", product_data["product"], action)
            success = send_to_api(product_data, action)

            if success:
                oled_show("SUCCESS", product_data["product"], action)
                last_processed_qr = data
            else:
                oled_show("API ERROR")
                last_processed_qr = None  # allow retry on API error

        except Exception as e:
            oled_show("Invalid QR")
            print(e)
            time.sleep(2)

        finally:
            oled_busy = False

# START THREADS

t_read_temp        = threading.Thread(target=task_read_temp,        daemon=True)
t_measure_distance = threading.Thread(target=task_measure_distance,  daemon=True)
t_door_status      = threading.Thread(target=task_door_status,       daemon=True)
t_qr_scan          = threading.Thread(target=task_qr_scan,           daemon=True)
t_send_temperature = threading.Thread(target=task_send_temperature,  daemon=True)
t_door_statusMQTT  = threading.Thread(target=task_door_statusMQTT,   daemon=True)

t_read_temp.start()
t_measure_distance.start()
t_door_status.start()
t_send_temperature.start()
t_qr_scan.start()
client.loop_start()
t_door_statusMQTT.start()

# MAIN LOOP

get_content() # Load all products from the database

try:
    while program: #While program is running
        for product in products: #For every product check if it is expiring soon or has expired and do actions based on that.
            if (datetime.date.fromisoformat(product.expiration_date) - datetime.date.today()) <= datetime.timedelta(days=days_before_warning) and not product.warned:
                send_warning(product)
            elif datetime.date.fromisoformat(product.expiration_date) < datetime.date.today() and not product.expired:
                product_expire(product)
        oled_show_temperature() #Update temperature on OLED
        time.sleep(cooldown)

except KeyboardInterrupt:
    pass

finally:
    try:
        #Shut down program and do cleanup
        program = False

        Motor.off()
        Motor.close()
        led.value = False

        cap.release()

        client.loop_stop()
        client.disconnect()

        t_read_temp.join(timeout=3)
        t_measure_distance.join(timeout=3)
        t_door_status.join(timeout=3)
        t_qr_scan.join(timeout=3)
        t_send_temperature.join(timeout=3)
        t_door_statusMQTT.join(timeout=3)

        oled_show("Goodbye!")
    except KeyboardInterrupt:
        # Second Ctrl+C during cleanup — hardware already safe, just exit
        pass