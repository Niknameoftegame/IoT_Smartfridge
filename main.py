import board
import adafruit_bmp280
import paho.mqtt.client as mqtt
import threading
import busio
from busio import SPI
import time
import digitalio
import requests
import RPi.GPIO as GPIO
import datetime
import date
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont

class Product():
    expiration_date: date
    name: str
    warned: bool

def rotate(coil1,coil2):
    coil1.value = True
    coil2.value = True
    time.sleep(0.002)
    coil1.value = False
    coil2.value = False

def rotate(coil1, coil2, coil3, coil4):
    rotate(coil1,coil2)
    rotate(coil2,coil3)
    rotate(coil3,coil4)
    rotate(coil4,coil1)

def get_content():
    products = requests.get(api + "get_content")
    for product in products:
        product = Product(product["expiration_date"], product["name"], product["warned"])
        products.append(product)

def insert_content(date, type, warned):
    product = Product(date, type, warned)

    product_dict = {
        "expiration_date": date,
        "name": type,
        "warned": warned
    }

    products.append(product) # ADD TO PROGRAM MEMORY
    requests.post(api + "insert_content", json=product_dict) # ADD TO DB USING API

def remove_product(product):
    products.remove(product)
    requests.post(api + "remove_content", product) # REMOVE FROM DB

def close_door():
    while distance > CLOSED_DISTANCE:
        rotate()

def send_warning(product):
    topic = "smart_fridge"
    message = f"{product.type} expires in {(product.date - datetime.date.now()).days}"
    requests.post(f"https://ntfy.sh/{topic}", data=message.encode('utf-8'))
    product.warned = True

def product_expire(product):
    topic = "smart_fridge"
    message = f"ALERT: {product.type} has expired!"
    requests.post(f"https://ntfy.sh/{topic}", data=message.encode('utf-8'))

def OLED_Reset():
    oled.fill(0)
    oled.show()

def OLED_ShowTemperature():
    draw.text((10, 20), f"{temp}°C", font=font, fill=255)

def OLED_Update():
    oled.image(image)
    oled.show()

LED_GPIO = board.D22
COIL1_GPIO = board.D17
COIL2_GPIO = board.D17
COIL3_GPIO = board.D17
COIL4_GPIO = board.D1

OLED_DC_GPIO = board.D24
OLED_RESET_GPIO = board.D25
OLED_CS_GPIO = board.D16

CLOSED_DISTANCE = 0;

program = True

temp = 0;
distance = 0;

days_before_warning = 3;
cooldown = 5;

products = []

#API URL
api = "https://iot-api.vercel.app/"

# MQTT data
CHANNEL_ID = "3289179"
MQTT_CLIENT_ID = "ByEtHxUfJhIhFzgEGiEDEBM"
MQTT_USERNAME = "ByEtHxUfJhIhFzgEGiEDEBM"
MQTT_PASSWORD = "eqo1ov1BaFHWSAcDg7HRmpmW"
MQTT_BROKER = "mqtt3.thingspeak.com"
MQTT_PORT = 1883
TOPIC = f"channels/{CHANNEL_ID}/publish"

# MQTT Setup
client = mqtt.Client(client_id=MQTT_CLIENT_ID)
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.connect(MQTT_BROKER, MQTT_PORT, 60)

#BMP280 Setup

i2c = busio.I2C(board.SCL, board.SDA)
bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=0x77)

#LED Setup
led = digitalio.DigitalInOut(LED_GPIO)
led.direction = digitalio.Direction.OUTPUT

# Motor coil setup

coil1 = digitalio.DigitalInOut(COIL1_GPIO)
coil1.direction = digitalio.Direction.OUTPUT

coil2 = digitalio.DigitalInOut(COIL2_GPIO)
coil2.direction = digitalio.Direction.OUTPUT

coil3 = digitalio.DigitalInOut(COIL3_GPIO)
coil3.direction = digitalio.Direction.OUTPUT

coil4 = digitalio.DigitalInOut(COIL4_GPIO)
coil4.direction = digitalio.Direction.OUTPUT

# Ultrasonic sensor setup
TRIG = 16  # GPIO pin connected to TRIG
ECHO = 20  # GPIO pin connected to ECHO

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

#OLED Setup

spi = SPI(clock=board.SCK, MOSI=board.MOSI)

dc = digitalio.DigitalInOut(OLED_DC_GPIO)
reset = digitalio.DigitalInOut(OLED_RESET_GPIO)

cs = digitalio.DigitalInOut(OLED_CS_GPIO)  # dummy CS

oled = adafruit_ssd1306.SSD1306_SPI(128, 64, spi, dc, reset, cs)

# Afbeelding canvas maken
image = Image.new("1", (128, 64))
draw = ImageDraw.Draw(image)

# Font (standaard)
font = ImageFont.load_default()

#MCP 3008 Setup

#TODO

def task_read_temp():
    global target_temp
    target_temp = round(bmp280.temperature)
    while program:
        global temp
        temp = bmp280.temperature
        time.sleep(cooldown)

def task_measure_distance():
    global distance
    while program:
        """Measures the distance in cm using the HC-SR04 sensor."""
        # Ensure TRIG is low
        GPIO.output(TRIG, False)
        time.sleep(0.1)
        # Send 10us pulse to TRIG
        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)

        # Wait for ECHO start
        while GPIO.input(ECHO) == 0:
           pulse_start = time.time()

        # Wait for ECHO end
        while GPIO.input(ECHO) == 1:
            pulse_end = time.time()

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17000  # Convert to cm
        time.sleep(cooldown)

def task_send_temperature():
    while program:
        PICO_IP = "192.168.1.171" 
        url = f"http://{PICO_IP}/?temp={temp}"
        requests.get(url, timeout=5)
        time.sleep(cooldown)

#Initialize threads
t_read_temp = threading.Thread(target=task_read_temp, daemon=True)
t_measure_distance = threading.Thread(target=task_measure_distance, daemon=True)
t_send_temperature = threading.Thread(target=task_send_temperature, daemon=True)

#Start threads
t_read_temp.start()
t_measure_distance.start()
t_send_temperature.start()

#Main program
try:
    while program:
        for product in products:
            if product.date < datetime.date.today():
                product_expire()
            elif abs(product.date - datetime.date.today()) <= (datetime.timedelta(days=days_before_warning)) and product.warned is False:
                send_warning(product)
        OLED_Reset()
        OLED_ShowTemperature()
        OLED_Update()
        time.sleep(cooldown)
except KeyboardInterrupt:
    t_read_temp.join()
    t_measure_distance.join()
    t_send_temperature.join()
    led.value = False;

