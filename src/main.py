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

CLEINT_ID=ubinascii.hexlify('desk_esp32c3')

POSITION_FILE='position.txt'

class Driver:
    def __init__(self, motor: Motor):
        self.mqtt_client = self.init_mqtt() 
        self.direction = False
        self.target_speed = 0
        self.current_speed = 0
        self.sens_val = 0
        self.driving = False
        self.sensor = self.init_he_sensor()
        self.get_stored_pos()
        self.target_position = self.position
        self.motor = motor
        self.update_status()

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

    def set_position(self, position):
        self.position = position
        self.target_position = position
        self.store_position()


    async def position_drive(self):
        # Decides the target speed profile to assign to the motor
        while True:
            if self.driving:
                if self.position != self.target_position:
                    self.direction = True if self.target_position > self.position else False
                    diff = abs(self.target_position - self.position)
                    if diff > 2:
                        self.target_speed = settings['MOTION']['MAX_SPEED']
                    else:
                        self.target_speed = settings['MOTION']['CRAWL_SPEED'] 
                    print(
                        "Driving to position:",
                        self.target_position,
                        "current position:",
                        self.position,
                    )
                else:
                    print("reached target, stopping and storing position")
                    self.target_speed = 0
                    self.driving = False
                    self.store_position()
            else:
                self.target_speed = 0

            await asyncio.sleep_ms(200)

    async def speed_drive(self):
        # Accelerates/declerates the motor to the target speed
        while True:
            if self.current_speed < self.target_speed:
                self.current_speed = min(
                    min(settings["MOTION"]["MAX_SPEED"], self.target_speed),
                    self.current_speed + settings["MOTION"]["ACCEL"],
                )
            elif self.current_speed == self.target_speed:
                pass
            else:
                self.current_speed = max(
                    max(settings["MOTION"]["MIN_SPEED"], self.target_speed),
                    self.current_speed - settings["MOTION"]["DECEL"],
                )
            if self.target_speed == 0:
                self.motor.stop()
            elif self.direction:
                self.motor.drive_up(self.current_speed)
            else:
                self.motor.drive_down(self.current_speed)
            await asyncio.sleep_ms(100)

    def update_status(self):
        if self.position > 0:
            self.mqtt_client.publish(b'%s/status' % settings['MQTT']['BASE_TOPIC'], b'ON')
        else:
            self.mqtt_client.publish(b'%s/status' % settings['MQTT']['BASE_TOPIC'], b'OFF')

    def subscribe_cb(self, topic, msg):
        topic = topic.decode()
        msg = msg.decode()
        print('new msg', topic, msg)
        if topic == settings['MQTT']['BASE_TOPIC'] + '/position/set':
            try:
                target = int(msg)
            except ValueError:
                print('invalid payload for position')
                return
            if not settings['MOTION']['MIN_POS'] <= target <= settings['MOTION']['MAX_POS'] or target == self.position:
                return
            self.target_position = target
            self.driving = True
        elif topic == settings['MQTT']['BASE_TOPIC'] + '/position/override':
            try:
                override_pos = int(msg)
            except ValueError:
                print('invalid payload for override position')
                return
            old_pos = self.position
            print('Overriding position from %s to %s' % (old_pos, override_pos))
            self.set_position(override_pos)
            self.update_status()

        elif topic == settings['MQTT']['BASE_TOPIC'] + '/switch':
            if msg == 'ON':
                self.target_position = settings['MOTION']['ON_POS']
                self.driving = True
                print("Turning ON")
            elif msg == 'OFF':
                self.target_position = settings['MOTION']['MIN_POS']
                self.driving = True
                print("Turning OFF")

    def init_mqtt(self):
        print('Connecting to MQTT broker %s' % settings['MQTT']['SERVER'])
        mqtt_client = MQTTClient(CLEINT_ID, settings['MQTT']['SERVER'], settings['MQTT']['PORT'], keepalive=10)
        mqtt_client.set_callback(self.subscribe_cb)
        mqtt_client.connect()
        subtopics = ['position/set', 'position/override', 'switch'] 
        for topic in subtopics:
            mqtt_client.subscribe(b'%s/%s' % (settings['MQTT']['BASE_TOPIC'], topic))
        print('Connected to %s MQTT broker, subscribed to %s topic' % (settings['MQTT']['SERVER'], settings['MQTT']['BASE_TOPIC']))
        return mqtt_client

    async def monitor_sens(self):
        self.sens_val = self.sensor.value()
        while True:
            tmp_val = self.sensor.value()
            # monitor for a 'rising edge' on the sensor
            if tmp_val > self.sens_val:
                if self.direction:
                    self.position += 1
                    if self.position > 0:
                        self.mqtt_client.publish(b'%s/status' % settings['MQTT']['BASE_TOPIC'], b'ON')
                else:
                    self.position -= 1
                    if self.position <= 0:
                        self.mqtt_client.publish(b'%s/status' % settings['MQTT']['BASE_TOPIC'], b'OFF')
                print("Position:", self.position)
            self.mqtt_client.publish(b'%s/position' % settings['MQTT']['BASE_TOPIC'], b'%s' % self.position)
            self.sens_val = tmp_val
            await asyncio.sleep_ms(100)

    def init_he_sensor(self):
        return Pin(settings['PINS']['HE_PIN'], Pin.IN, Pin.PULL_UP)

    async def monitor_mqtt(self):
        while True:
            self.mqtt_client.check_msg()
            await asyncio.sleep(0)

    async def mqtt_keepalive(self):
        while True:
            self.mqtt_client.ping()
            await asyncio.sleep(10)


def connect_wifi():
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    ap = network.WLAN(network.AP_IF)
    ap.active(False)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect(settings['WIFI']['SSID'], settings['WIFI']['PASSWORD'])
        while not wlan.isconnected():
            print("waiting..")
            time.sleep(1)
    print('connected!')
    print('network config:', wlan.ifconfig())

async def main():
    connect_wifi()
    motor = Motor(settings['PINS']['UP_PIN'], settings['PINS']['DOWN_PIN'], settings['PINS']['EN_PIN'],)
    d = Driver(motor) 

    sens_task = asyncio.create_task(d.monitor_sens())
    speed_task = asyncio.create_task(d.speed_drive())
    position_task = asyncio.create_task(d.position_drive())
    keepalive_task = asyncio.create_task(d.mqtt_keepalive())
    mqtt_task = asyncio.create_task(d.monitor_mqtt())
    await asyncio.gather(position_task, speed_task, keepalive_task, mqtt_task, sens_task)

asyncio.run(main())
