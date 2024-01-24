from machine import Pin, PWM

class Motor:
    def __init__(self, up_pin_num, down_pin_num, en_pin_num):
        self.up_pin = PWM(Pin(up_pin_num), freq=500, duty=0)
        self.down_pin = PWM(Pin(down_pin_num), freq=500, duty=0)
        self.en_pin = Pin(en_pin_num, Pin.OUT)
        self.stop()
    
    def drive_up(self, speed):
        self.en_pin.on()
        self.up_pin.duty(int(speed * 1023 / 100))
        self.down_pin.duty(0)
    
    def drive_down(self, speed):
        self.en_pin.on()
        self.down_pin.duty(int(speed * 1023 / 100))
        self.up_pin.duty(0)
    
    def stop(self):
        self.up_pin.duty(0)
        self.down_pin.duty(0)
        self.en_pin.off()