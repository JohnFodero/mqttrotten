from machine import Pin
import uasyncio as asyncio
import time
from umqtt.simple import MQTTClient
import ubinascii
import json
from motor import Motor

settings = json.load(open('settings.json', 'r'))

def update_settings(settings):
    with open('settings.json', 'w') as f:
        json.dump(settings, f)

TOPIC=b'jj_desk/time'
CLEINT_ID=ubinascii.hexlify('desk_esp32c3')

POSITION_FILE='position.txt'

class Driver:
    def __init__(self, motor: Motor):
        self.direction = False
        self.target_speed = 0
        self.current_speed = 0
        self.sens_val = 0
        self.driving = False
        self.get_stored_pos()
        self.target_position = self.position
        self.motor = motor

    def get_stored_pos(self):
        try:
            with open(POSITION_FILE, 'r') as f:
                self.position = int(f.read())
        except OSError:
            self.position = 0

    def store_position(self):
        self.position = max(settings['MOTION']['MIN_POS'], self.position)
        with open(POSITION_FILE, 'w') as f:
            f.write(str(self.position))

def subscribe_cb(topic, msg):
    topic = topic.decode()
    msg = msg.decode()
    print('new msg', topic, msg)
    if topic == 'jj_desk/position/set':
        try:
            target = int(msg)
        except ValueError:
            print('invalid payload for position')
            return
        if not settings['MOTION']['MIN_POS'] <= target <= settings['MOTION']['MAX_POS'] or target == d.position:
            return
        d.target_position = target
        d.driving = True
    elif topic == 'jj_desk/settings/set':
        pass

def init_mqtt():
    print('Connecting to MQTT broker %s' % settings['MQTT']['SERVER'])
    mqtt_client = MQTTClient(CLEINT_ID, settings['MQTT']['SERVER'], settings['MQTT']['PORT'], keepalive=10)
    mqtt_client.set_callback(subscribe_cb)
    mqtt_client.connect()
    subtopics = ['position/set', 'settings/set']
    for topic in subtopics:
        mqtt_client.subscribe(b'%s/%s' % (settings['MQTT']['BASE_TOPIC'], topic))
    print('Connected to %s MQTT broker, subscribed to %s topic' % (settings['MQTT']['SERVER'], settings['MQTT']['BASE_TOPIC']))
    return mqtt_client

motor = Motor(settings['PINS']['UP_PIN'], settings['PINS']['DOWN_PIN'], settings['PINS']['EN_PIN'],)
d = Driver(motor)
mqtt = init_mqtt()


def init_he_sensor():
    he_sensor = Pin(settings['PINS']['HE_PIN'], Pin.IN, Pin.PULL_UP)
    return he_sensor

def init_buttons():
    up_pin = Pin(settings['PINS']['UP_BUTTON_PIN'], Pin.IN, Pin.PULL_UP)
    dn_pin = Pin(settings['PINS']['DOWN_BUTTON_PIN'], Pin.IN, Pin.PULL_UP)
    return up_pin, dn_pin

async def monitor_buttons(up_pin, dn_pin, driver):
    while True:
        if not up_pin.value() and dn_pin.value():
            driver.target_speed = 10
            driver.direction = True
        elif not dn_pin.value() and up_pin.value():
            driver.target_speed = 10
            driver.direction = False
        elif not dn_pin.value() and not up_pin.value():
            print('Setting position at 0')
            driver.target_speed = 0
            driver.position = 0
        await asyncio.sleep_ms(100)

async def position_drive(driver):
    # Decides the target speed profile to assign to the motor
    while True:
        if driver.driving:
            if driver.position != driver.target_position:
                d.direction = True if d.target_position > d.position else False
                diff = abs(d.target_position - d.position)
                if diff > 5:
                    d.target_speed = settings['MOTION']['MAX_SPEED']
                elif diff > 2:
                    d.target_speed = 5
                else:
                    d.target_speed = 2
                print("Driving to position:", d.target_position, "current position:", d.position)
            else:
                print("reached target, stopping and storing position")
                driver.target_speed = 0
                driver.driving = False
                driver.store_position()
        else:
            driver.target_speed = 0

        await asyncio.sleep_ms(200)

async def speed_drive(driver):
    # Accelerates/declerates the motor to the target speed
    while True:
        # print("Current speed:", driver.current_speed, "Target speed:", driver.target_speed, "Direction:", driver.direction)
        if driver.current_speed < driver.target_speed:
            driver.current_speed = min(min(settings['MOTION']['MAX_SPEED'], driver.target_speed), driver.current_speed + settings['MOTION']['ACCEL'])
        elif driver.current_speed == driver.target_speed:
            pass
        else:
            driver.current_speed = max(max(settings['MOTION']['MIN_SPEED'], driver.target_speed), driver.current_speed - settings['MOTION']['DECEL'])
        if driver.target_speed == 0:
            driver.motor.stop()
        elif driver.direction:
            driver.motor.drive_up(driver.current_speed)
        else:
            driver.motor.drive_down(driver.current_speed)
        await asyncio.sleep_ms(100)

async def monitor_mqtt(mqtt_client):
    while True:
        mqtt_client.check_msg()
        await asyncio.sleep(0)

async def mqtt_keepalive(mqtt_client):
    while True:
        mqtt_client.ping()
        await asyncio.sleep(10)

async def monitor_sens(sens, driver):
    driver.sens_val = sens.value()
    while True:
        tmp_val = sens.value()
        # monitor for a 'rising edge' on the sensor
        if tmp_val > driver.sens_val:
            if driver.direction:
                driver.position += 1
            else:
                driver.position -= 1
            print("Position:", driver.position)
            mqtt.publish(b'%s/position/get' % settings['MQTT']['BASE_TOPIC'], b'%s' % d.position)
        driver.sens_val = tmp_val
        await asyncio.sleep_ms(100)

def do_connect():
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    ap = network.WLAN(network.AP_IF)
    ap.active(False)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect(settings['WIFI']['SSID'], settings['WIFI']['PASSWORD'])
        while not wlan.isconnected():
            pass
    print('network config:', wlan.ifconfig())

async def main():
    do_connect()

    up_pin, dn_pin = init_buttons()
    sens = init_he_sensor()

    sens_task = asyncio.create_task(monitor_sens(sens, d))
    speed_task = asyncio.create_task(speed_drive(d))
    position_task = asyncio.create_task(position_drive(d))
    button_task = asyncio.create_task(monitor_buttons(up_pin, dn_pin, d))
    keepalive_task = asyncio.create_task(mqtt_keepalive(mqtt))
    mqtt_task = asyncio.create_task(monitor_mqtt(mqtt))
    await asyncio.gather(position_task, speed_task, button_task, 
                         keepalive_task, mqtt_task, sens_task)

asyncio.run(main())