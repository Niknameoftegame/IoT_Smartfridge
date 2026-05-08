import time
import board
import digitalio
import busio
import adafruit_bmp280
import smbus
from gpiozero import MCP3008

# ── Ultrasonic sensor ─────────────────────────────────────────────
trig = digitalio.DigitalInOut(board.D26)
trig.direction = digitalio.Direction.OUTPUT
trig.value = False

echo = digitalio.DigitalInOut(board.D19)
echo.direction = digitalio.Direction.INPUT

time.sleep(0.5)

# ── Stepper coils ─────────────────────────────────────────────────
coil1 = digitalio.DigitalInOut(board.D23)
coil1.direction = digitalio.Direction.OUTPUT
coil2 = digitalio.DigitalInOut(board.D18)
coil2.direction = digitalio.Direction.OUTPUT
coil3 = digitalio.DigitalInOut(board.D24)
coil3.direction = digitalio.Direction.OUTPUT
coil4 = digitalio.DigitalInOut(board.D25)
coil4.direction = digitalio.Direction.OUTPUT

# ── Status lights ─────────────────────────────────────────────────
green_light = digitalio.DigitalInOut(board.D22)
green_light.direction = digitalio.Direction.OUTPUT
green_light.value = False

red_light = digitalio.DigitalInOut(board.D12)
red_light.direction = digitalio.Direction.OUTPUT
red_light.value = False

# ── Potentiometer via MCP3008 ─────────────────────────────────────
potentiometer = MCP3008(channel=0)

# ── I2C and BMP280 ────────────────────────────────────────────────
i2c = busio.I2C(board.D3, board.D2)
bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=0x77)

# ── Buttons ───────────────────────────────────────────────────────
btn_close = digitalio.DigitalInOut(board.D13)
btn_close.direction = digitalio.Direction.INPUT
btn_close.pull = digitalio.Pull.UP

btn_open = digitalio.DigitalInOut(board.D6)
btn_open.direction = digitalio.Direction.INPUT
btn_open.pull = digitalio.Pull.UP

# ── Settings ──────────────────────────────────────────────────────
DOOR_OPEN_THRESHOLD_CM = 15
STEP_DELAY = 0.01
TEMP_PRINT_INTERVAL = 15.0
DISTANCE_PRINT_INTERVAL = 5.0


# ── Helpers ───────────────────────────────────────────────────────
def deenergise():
    coil1.value = False
    coil2.value = False
    coil3.value = False
    coil4.value = False


def update_lights(distance):
    """Update status lights based on door distance"""
    if distance is None:
        return

    if distance > DOOR_OPEN_THRESHOLD_CM:
        green_light.value = True
        red_light.value = False
    else:
        green_light.value = False
        red_light.value = True


def measure_distance_cm():
    trig.value = True
    time.sleep(0.00001)
    trig.value = False

    timeout = time.monotonic() + 0.04
    while not echo.value:
        if time.monotonic() > timeout:
            return None
    pulse_start = time.monotonic()

    timeout = time.monotonic() + 0.04
    while echo.value:
        if time.monotonic() > timeout:
            return None

    return (time.monotonic() - pulse_start) * 17150


def rotate(a, b):
    a.value = True
    b.value = True
    time.sleep(STEP_DELAY)
    a.value = False
    b.value = False


def printTemp(temp):
    print(f"Temperature: {temp:.1f} °C")


# ── Main loop ─────────────────────────────────────────────────────
print("Smart fridge ready.")
print("Hold GPIO13 = close  |  Hold GPIO6 = open  |  Ctrl+C = quit\n")

last_print = 0
last_temp_print = 0
last_distance_print = 0
motor_running = False
motor_mode = None

try:
    while True:
        pressing_close = btn_close.value == False
        pressing_open = btn_open.value == False
        now = time.monotonic()

        if pressing_close and not motor_running:
            motor_running = True
            motor_mode = "close"
        elif pressing_open and not motor_running:
            motor_running = True
            motor_mode = "open"

        if motor_running:
            if motor_mode == "close":
                rotate(coil1, coil2)
                rotate(coil2, coil3)
                rotate(coil3, coil4)
                rotate(coil4, coil1)

                dist = measure_distance_cm()
                update_lights(dist)

                if dist is not None and dist <= DOOR_OPEN_THRESHOLD_CM:
                    motor_running = False
                    deenergise()

            elif motor_mode == "open":
                rotate(coil4, coil1)
                rotate(coil3, coil4)
                rotate(coil2, coil3)
                rotate(coil1, coil2)

                dist = measure_distance_cm()
                update_lights(dist)

                if dist is not None and dist >= DOOR_OPEN_THRESHOLD_CM:
                    motor_running = False
                    deenergise()

            if now - last_distance_print >= DISTANCE_PRINT_INTERVAL:
                if dist is not None:
                    status = "OPEN" if dist > DOOR_OPEN_THRESHOLD_CM else "CLOSED"
                    print(f"Distance: {dist:5.1f} cm  [{status}]")
                last_distance_print = now

        else:
            deenergise()
            if now - last_print >= DISTANCE_PRINT_INTERVAL:
                dist = measure_distance_cm()
                update_lights(dist)
                if dist is not None:
                    status = "OPEN" if dist > DOOR_OPEN_THRESHOLD_CM else "CLOSED"
                    print(f"Distance: {dist:5.1f} cm  [{status}]")
                last_print = now

        if now - last_temp_print >= TEMP_PRINT_INTERVAL:
            temp = bmp280.temperature
            printTemp(temp)
            last_temp_print = now

        time.sleep(0.01)

except KeyboardInterrupt:
    deenergise()
    green_light.value = False
    red_light.value = False
    print("\nGPIO cleaned up.")