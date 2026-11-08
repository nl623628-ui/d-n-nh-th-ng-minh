# ESP32 SMART HOME - MicroPython
# Copy this file to ESP32 as main.py.
# Install/copy the required MicroPython libraries listed in README.md.

import network
import time
import ujson
import urequests
from machine import Pin, ADC, PWM, SPI, I2C
import dht
import ssd1306
from mfrc522 import MFRC522

# ====== CONFIGURATION: EDIT THESE VALUES ======
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
SERVER_URL = "http://192.168.1.100:8000"  # Replace with your PC IPv4 address
# ==============================================

# GPIO assignments taken from the supplied project document
SOIL_PIN = 34
PUMP_RELAY_PIN = 26
RFID_SS_PIN = 5
RFID_RST_PIN = 22
DOOR_SERVO_PIN = 13
MQ2_PIN = 35
BUZZER_PIN = 25
DHT_PIN = 32
FAN_RELAY_PIN = 33
OLED_SDA = 14
OLED_SCL = 17
PIR_PIN = 36
LED_PIN = 16
RAIN_DO_PIN = 27
RAIN_SERVO_PIN = 4

TEMP_ON = 35.0
TEMP_OFF = 33.0
RELAY_ON = 1
RELAY_OFF = 0
BUZZER_ON = 0
BUZZER_OFF = 1
DRY_VALUE = 3857
WET_VALUE = 1667
MOISTURE_STANDARD = 30
GAS_THRESHOLD = 1800
LED_TIME = 3000
DOOR_OPEN_TIME = 3000
AUTHORIZED_UID = [0xE4, 0x9E, 0x26, 0x06]

# Hardware setup
soil_adc = ADC(Pin(SOIL_PIN)); soil_adc.atten(ADC.ATTN_11DB)
gas_adc = ADC(Pin(MQ2_PIN)); gas_adc.atten(ADC.ATTN_11DB)
pump_relay = Pin(PUMP_RELAY_PIN, Pin.OUT)
fan_relay = Pin(FAN_RELAY_PIN, Pin.OUT)
buzzer = Pin(BUZZER_PIN, Pin.OUT)
pir = Pin(PIR_PIN, Pin.IN)
led = Pin(LED_PIN, Pin.OUT)
rain_sensor = Pin(RAIN_DO_PIN, Pin.IN)
dht_sensor = dht.DHT22(Pin(DHT_PIN))
i2c = I2C(0, scl=Pin(OLED_SCL), sda=Pin(OLED_SDA), freq=400000)
display = ssd1306.SSD1306_I2C(128, 64, i2c)
spi = SPI(2, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(18), mosi=Pin(23), miso=Pin(19))
rfid = MFRC522(sck=18, mosi=23, miso=19, rst=RFID_RST_PIN, cs=RFID_SS_PIN)

door_servo = PWM(Pin(DOOR_SERVO_PIN), freq=50)
rain_servo = PWM(Pin(RAIN_SERVO_PIN), freq=50)

def servo_write(servo, angle):
    angle = max(0, min(180, int(angle)))
    pulse_us = 500 + angle * 2000 / 180
    servo.duty_u16(int(pulse_us * 65535 / 20000))

def adc12(sensor, count):
    total = 0
    for _ in range(count):
        # read_u16() is 0..65535; scale to 12-bit to match 3857/1667/1800
        total += sensor.read_u16() >> 4
        time.sleep_ms(10)
    return total // count

def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        timeout = time.ticks_add(time.ticks_ms(), 20000)
        while not wlan.isconnected() and time.ticks_diff(timeout, time.ticks_ms()) > 0:
            time.sleep_ms(300)
    if wlan.isconnected():
        print("Wi-Fi:", wlan.ifconfig())
    else:
        print("Wi-Fi connection failed")
    return wlan

# State
mode = "AUTO"
temperature = None
humidity = None
soil_raw = 0
soil_moisture = 0
gas_value = 0
gas_alarm = False
is_raining = False
motion = False
fan_state = False
pump_state = False
led_state = False
buzzer_state = False
door_angle = 0
door_state = "CLOSED"
door_timer = 0
door_step_timer = 0
rain_angle = 0
last_motion_time = 0
last_sensor_time = 0
last_gas_time = 0
last_dht_time = 0
last_oled_time = 0
last_post_time = 0
last_command_time = 0

def control_pump(on):
    global pump_state
    pump_state = bool(on)
    pump_relay.value(RELAY_ON if pump_state else RELAY_OFF)

def control_fan(on):
    global fan_state
    fan_state = bool(on)
    fan_relay.value(RELAY_ON if fan_state else RELAY_OFF)

def check_card():
    status, tag_type = rfid.request(rfid.REQIDL)
    if status != rfid.OK:
        return False
    status, uid = rfid.anticoll()
    if status != rfid.OK:
        return False
    return list(uid[:4]) == AUTHORIZED_UID

def request_door_open():
    global door_state
    if door_state == "CLOSED":
        door_state = "OPENING"

def update_door():
    global door_angle, door_state, door_timer, door_step_timer
    now = time.ticks_ms()
    if mode == "AUTO" and door_state == "CLOSED":
        if check_card():
            request_door_open()
    if time.ticks_diff(now, door_step_timer) < 20:
        return
    door_step_timer = now
    if door_state == "OPENING":
        if door_angle < 90:
            door_angle += 1
            servo_write(door_servo, door_angle)
        else:
            door_timer = now
            door_state = "WAITING"
    elif door_state == "WAITING":
        if time.ticks_diff(now, door_timer) >= DOOR_OPEN_TIME:
            door_state = "CLOSING"
    elif door_state == "CLOSING":
        if door_angle > 0:
            door_angle -= 1
            servo_write(door_servo, door_angle)
        else:
            door_state = "CLOSED"

def read_sensors():
    global soil_raw, soil_moisture, gas_value, gas_alarm
    global temperature, humidity, is_raining, motion, last_motion_time
    soil_raw = adc12(soil_adc, 20)
    soil_moisture = int((soil_raw - DRY_VALUE) * 100 / (WET_VALUE - DRY_VALUE))
    soil_moisture = max(0, min(100, soil_moisture))
    gas_value = adc12(gas_adc, 10)
    gas_alarm = gas_value >= GAS_THRESHOLD
    rain_now = (rain_sensor.value() == 0)
    is_raining = rain_now
    now = time.ticks_ms()
    if pir.value():
        last_motion_time = now
    motion = last_motion_time != 0 and time.ticks_diff(now, last_motion_time) < LED_TIME
    try:
        dht_sensor.measure()
        temperature = dht_sensor.temperature()
        humidity = dht_sensor.humidity()
    except Exception as e:
        temperature = None
        humidity = None
        print("DHT22 error:", e)

def apply_automatic():
    if soil_moisture < MOISTURE_STANDARD:
        control_pump(True)
    else:
        control_pump(False)
    if temperature is not None:
        if temperature >= TEMP_ON:
            control_fan(True)
        elif temperature <= TEMP_OFF:
            control_fan(False)
    # PIR light: 3 seconds after last motion
    led.value(1 if motion else 0)
    global led_state
    led_state = bool(motion)
    # Rain protection: rain => servo 180, dry => 0
    global rain_angle
    target = 180 if is_raining else 0
    if rain_angle < target:
        rain_angle += 1
    elif rain_angle > target:
        rain_angle -= 1
    servo_write(rain_servo, rain_angle)

def apply_manual(cmd):
    global led_state, rain_angle
    if cmd.get("pump") is not None:
        control_pump(cmd["pump"])
    if cmd.get("fan") is not None:
        control_fan(cmd["fan"])
    if cmd.get("led") is not None:
        led_state = bool(cmd["led"])
        led.value(1 if led_state else 0)
    if cmd.get("rain_servo_angle") is not None:
        rain_angle = max(0, min(180, int(cmd["rain_servo_angle"])))
        servo_write(rain_servo, rain_angle)
    if cmd.get("door_open"):
        request_door_open()

def update_oled():
    display.fill(0)
    display.text("SMART HOME ESP32", 0, 0)
    if temperature is None:
        display.text("DHT22: ERROR", 0, 14)
    else:
        display.text("T:{:.1f}C H:{:.1f}%".format(temperature, humidity), 0, 14)
    display.text("SOIL:{}% P:{}".format(soil_moisture, "ON" if pump_state else "OFF"), 0, 27)
    display.text("FAN:{} GAS:{}".format("ON" if fan_state else "OFF", gas_value), 0, 40)
    display.text("MODE:" + mode, 0, 53)
    display.show()

def post_telemetry():
    data = {
        "temperature": temperature, "humidity": humidity,
        "soil_moisture": soil_moisture, "soil_raw": soil_raw,
        "gas_value": gas_value, "gas_alarm": gas_alarm,
        "rain": is_raining, "motion": motion,
        "fan": fan_state, "pump": pump_state,
        "buzzer": buzzer_state, "led": led_state,
        "door": "OPEN" if door_state in ("OPENING", "WAITING") else "CLOSED",
        "rain_servo_angle": rain_angle
    }
    try:
        response = urequests.post(SERVER_URL + "/api/telemetry",
                                  data=ujson.dumps(data),
                                  headers={"Content-Type": "application/json"})
        response.close()
    except Exception as e:
        print("Telemetry error:", e)

def get_commands():
    global mode
    try:
        response = urequests.get(SERVER_URL + "/api/commands")
        cmd = response.json()
        response.close()
        new_mode = cmd.get("mode", mode)
        if new_mode in ("AUTO", "MANUAL"):
            mode = new_mode
        if mode == "MANUAL":
            apply_manual(cmd)
    except Exception as e:
        print("Command error:", e)

def setup():
    global buzzer_state
    control_pump(False)
    control_fan(False)
    buzzer.value(BUZZER_OFF)
    led.value(0)
    servo_write(door_servo, 0)
    servo_write(rain_servo, 0)
    display.fill(0)
    display.text("SMART HOME", 0, 0)
    display.text("Starting...", 0, 20)
    display.show()
    wifi_connect()

def main():
    global buzzer_state, last_sensor_time
    setup()
    while True:
        now = time.ticks_ms()

        # Read sensors about once per second
        if time.ticks_diff(now, last_sensor_time) >= 1000:
            last_sensor_time = now
            read_sensors()
            if mode == "AUTO":
                apply_automatic()
            # Gas safety has priority in both modes
            buzzer_state = bool(gas_alarm)
            buzzer.value(BUZZER_ON if gas_alarm else BUZZER_OFF)

        # Check web commands frequently; HTTP polling interval 0.5 s
        if time.ticks_diff(now, last_command_time) >= 500:
            last_command_time = now
            get_commands()

        update_door()

        if time.ticks_diff(now, last_oled_time) >= 1000:
            update_oled()
            last_oled_time = now

        if time.ticks_diff(now, last_post_time) >= 1000:
            post_telemetry()
            last_post_time = now

        time.sleep_ms(10)

main()
