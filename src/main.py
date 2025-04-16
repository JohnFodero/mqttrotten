from machine import Pin, SoftI2C
import uasyncio as asyncio
import time
from umqtt.simple import MQTTClient
import ubinascii
import json
from motor import Motor
from as5600 import AS5600


settings = json.load(open("settings.json", "r"))


def update_settings(settings):
    with open("settings.json", "w") as f:
        json.dump(settings, f)


CLEINT_ID = ubinascii.hexlify("desk_esp32c3")

POSITION_FILE = "position.txt"

SENSOR_READ_INTERVAL_MS = 25
SLOW_INTERVAL_MS = 1000
BUFFER_DEG = 20

class Driver:
    def __init__(self, motor: Motor):
        self.mqtt_client = self.init_mqtt()
        self.direction = False  # True = up, False = down
        self.target_speed = 0
        self.current_speed = 0
        self.driving = False
        self.encoder = self.init_encoder()
        self.read_buffer = []
        self.read_buffer_size = 5
        start_val = self.encoder.read_position()
        self.ms_since_last_update = 0
        self.ticks_since_last_move = 0
        if start_val is None:
            print("Failed to read initial position")
            raise Exception
        self.last_sens_val = start_val
        self.get_stored_pos()
        self.target_position = self.position
        self.motor = motor
        self.update_status()

    def get_stored_pos(self):
        try:
            with open(POSITION_FILE, "r") as f:
                self.position = int(f.read())
        except OSError:
            self.position = 0

    def store_position(self):
        self.position = max(settings["MOTION"]["MIN_POS"], self.position)
        with open(POSITION_FILE, "w") as f:
            f.write(str(self.position))

    def set_position(self, position):
        self.position = position
        self.target_position = position
        self.store_position()

    def get_position_pct(self, pos):
        return int((pos / settings["MOTION"]["MAX_POS"]) * 100)

    def get_position_ct(self, pct):
        return int((pct / 100) * settings["MOTION"]["MAX_POS"])

    async def position_drive(self):
        # Decides the target speed profile to assign to the motor
        while True:
            if not self.driving:
                self.target_speed = 0
                print("Current Position:", self.position, "Target Position:", self.target_position)
                await asyncio.sleep_ms(SLOW_INTERVAL_MS)
            else:
                if not (self.target_position - BUFFER_DEG <= self.position <= self.target_position + BUFFER_DEG):
                    diff = abs(self.target_position - self.position)
                    if diff > 400:
                        self.target_speed = settings["MOTION"]["MAX_SPEED"]
                    else:
                        self.target_speed = settings["MOTION"]["CRAWL_SPEED"]
                else:
                    # Reached the target
                    self.target_speed = 0
                    self.driving = False
                    self.ticks_since_last_move = 0
                    self.store_position()
                await asyncio.sleep_ms(10)

    async def speed_drive(self):
        # Accelerates/declerates the motor to the target speed
        while True:
            if not self.driving and self.current_speed == 0:
                await asyncio.sleep_ms(SLOW_INTERVAL_MS)
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
            await asyncio.sleep_ms(50)

    def update_status(self):
        if self.get_position_pct(self.position) > 0:
            self.mqtt_client.publish(
                b"%s/status" % settings["MQTT"]["BASE_TOPIC"], b"ON"
            )
        else:
            self.mqtt_client.publish(
                b"%s/status" % settings["MQTT"]["BASE_TOPIC"], b"OFF"
            )
    def update_position(self):
        self.mqtt_client.publish(
            b"%s/position" % settings["MQTT"]["BASE_TOPIC"], b"%s" % self.get_position_pct(self.position)
        )
        self.mqtt_client.publish(
            b"%s/raw_position" % settings["MQTT"]["BASE_TOPIC"], b"%s" % self.position
        )

    def subscribe_cb(self, topic, msg):
        topic = topic.decode()
        msg = msg.decode()
        print("new msg", topic, msg)
        if topic == settings["MQTT"]["BASE_TOPIC"] + "/position/set":
            try:
                target = int(msg)
            except ValueError:
                print("invalid payload for position")
                return
            if (
                not 0
                <= target
                <= 100
                or target == self.position
            ):
                return
            self.target_position = self.get_position_ct(target) + BUFFER_DEG + 10 # Add buffer so it always ends on the target pct
            self.direction = (
                True if self.target_position > self.position else False
            )
            self.driving = True
        elif topic == settings["MQTT"]["BASE_TOPIC"] + "/position/override":
            try:
                override_pos = int(msg)
            except ValueError:
                print("invalid payload for override position")
                return
            old_pos = self.position
            print("Overriding position from %s to %s" % (old_pos, override_pos))
            self.set_position(override_pos)
            self.update_status()
            self.update_position()

        elif topic == settings["MQTT"]["BASE_TOPIC"] + "/switch":
            if msg == "ON":
                self.target_position = self.get_position_ct(settings["MOTION"]["ON_POS"]) + BUFFER_DEG + 10
                self.driving = True
                print("Turning ON")
            elif msg == "OFF":
                self.target_position = self.get_position_ct(settings["MOTION"]["MIN_POS"]) + BUFFER_DEG + 10
                self.driving = True
                print("Turning OFF")

    def init_mqtt(self):
        print("Connecting to MQTT broker %s" % settings["MQTT"]["SERVER"])
        mqtt_client = MQTTClient(
            CLEINT_ID,
            settings["MQTT"]["SERVER"],
            settings["MQTT"]["PORT"],
            keepalive=10,
        )
        mqtt_client.set_callback(self.subscribe_cb)
        mqtt_client.connect()
        subtopics = ["position/set", "position/override", "switch"]
        for topic in subtopics:
            mqtt_client.subscribe(b"%s/%s" % (settings["MQTT"]["BASE_TOPIC"], topic))
        print(
            "Connected to %s MQTT broker, subscribed to %s topic"
            % (settings["MQTT"]["SERVER"], settings["MQTT"]["BASE_TOPIC"])
        )
        return mqtt_client

    async def monitor_sens(self):
        while True:
            last_pos = self.position
            if self.driving:
                sens_val = self.encoder.read_position()
                if sens_val is None:
                    print("Failed to read sensor value")
                    continue 
                if len(self.read_buffer) < self.read_buffer_size:
                    self.read_buffer.append(sens_val)
                else:
                    new_sens_val = sorted(self.read_buffer)[self.read_buffer_size // 2 + 1]
                    sens_delta = new_sens_val - self.last_sens_val  
                    if abs(sens_delta) < 5:
                        self.ticks_since_last_move += 1
                    if self.ticks_since_last_move > 8:
                        print("No movement detected, stopping motor")
                        self.motor.stop()
                        self.driving = False
                        self.target_speed = 0
                        self.ticks_since_last_move = 0
                        self.position = 0
                        self.update_status()
                        self.update_position()
                        self.store_position()
                    self.direction = (
                        True if self.target_position > self.position else False
                    )
                    if self.direction:  # driving up
                        if sens_delta > 0:  # moving up, didnt rollover
                            self.position += sens_delta
                        elif sens_delta < 0:  # rollover
                            self.position += new_sens_val + (360 - self.last_sens_val)
                    else:  # driving down
                        if sens_delta < 0:  # moving down, didnt rollover
                            self.position += sens_delta
                        elif sens_delta > 0:  # rollover
                            self.position -= self.last_sens_val + (360 - new_sens_val)
                    print("Current Position:", self.position, "Target Position:", self.target_position, "Last Pos", last_pos, "Current Sensor Value:", new_sens_val, "Last Sensor Value:", self.last_sens_val, "Buffer", self.read_buffer)
                    self.last_sens_val = new_sens_val
                    if self.get_position_pct(self.position) != self.get_position_pct(last_pos):
                        print("updating!!!!!!!!")
                        self.ms_since_last_update = 0
                        self.update_status()
                        self.update_position()
                    self.read_buffer = []

                await asyncio.sleep_ms(SENSOR_READ_INTERVAL_MS)
                self.ms_since_last_update += SENSOR_READ_INTERVAL_MS
            else:
                await asyncio.sleep_ms(SLOW_INTERVAL_MS)
                self.last_sens_val = self.encoder.read_position()
                self.ms_since_last_update += SLOW_INTERVAL_MS
            if self.ms_since_last_update >= 1000*settings.get("STATUS_INTERVAL_SEC", 300):
                """Only send status update and """
                self.ms_since_last_update = 0
                self.update_status()
                self.update_position()

    def init_encoder(self):
        # i2c = SoftI2C(scl=Pin(5), sda=Pin(4), freq=400000)
        i2c = SoftI2C(scl=Pin(settings['PINS']['SCL_PIN']), sda=Pin(settings['PINS']['SDA_PIN']), freq=400000)
        devices = i2c.scan()
        print("I2C devices found:", devices)
        while len(i2c.scan()) == 0:
            print("No I2C devices found. Retrying...")
            time.sleep(1)
        return AS5600(i2c)

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
        print("connecting to network...")
        wlan.connect(settings["WIFI"]["SSID"], settings["WIFI"]["PASSWORD"])
        while not wlan.isconnected():
            print("waiting..")
            time.sleep(1)
    print("connected!")
    print("network config:", wlan.ifconfig())


async def main():
    connect_wifi()
    motor = Motor(
        settings["PINS"]["UP_PIN"],
        settings["PINS"]["DOWN_PIN"],
        settings["PINS"]["EN_PIN"],
    )
    d = Driver(motor)
    d.update_status()
    d.update_position()
    sens_task = asyncio.create_task(d.monitor_sens())
    speed_task = asyncio.create_task(d.speed_drive())
    position_task = asyncio.create_task(d.position_drive())
    keepalive_task = asyncio.create_task(d.mqtt_keepalive())
    mqtt_task = asyncio.create_task(d.monitor_mqtt())
    await asyncio.gather(
        position_task, speed_task, keepalive_task, mqtt_task, sens_task
    )


asyncio.run(main())
