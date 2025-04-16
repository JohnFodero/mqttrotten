# Adopted from https://wokwi.com/projects/395705310735654913

# Constants for AS5600
AS5600_I2C_ADDR = 0x36
RAW_ANGLE_REGISTER_MSB = 0x0C
RAW_ANGLE_REGISTER_LSB = 0x0D
ANGLE_REGISTER_MSB = 0x0E
ANGLE_REGISTER_LSB = 0x0F
STATUS_REGISTER = 0x0B
AGC_REGISTER = 0x1A
MAGNITUDE_REGISTER_MSB = 0x1B
MAGNITUDE_REGISTER_LSB = 0x1C

class AS5600:
    def __init__(self, i2c):
        self.i2c = i2c

    def read_register(self, register):
        try:
            return self.i2c.readfrom_mem(AS5600_I2C_ADDR, register, 1)[0]
        except OSError as e:
            print("I2C read error:", e)
            return None

    def read_registers(self, reg_msb, reg_lsb):
        try:
            msb = self.i2c.readfrom_mem(AS5600_I2C_ADDR, reg_msb, 1)[0]
            lsb = self.i2c.readfrom_mem(AS5600_I2C_ADDR, reg_lsb, 1)[0]
            return (msb << 8) | lsb
        except OSError as e:
            print("I2C read error:", e)
            return None

    def write_register(self, register, value):
        try:
            self.i2c.writeto_mem(AS5600_I2C_ADDR, register, bytearray([value]))
        except OSError as e:
            print("I2C write error:", e)

    def read_position_raw(self):
        return self.read_registers(RAW_ANGLE_REGISTER_MSB, RAW_ANGLE_REGISTER_LSB)

    def read_position(self):
        raw_angle = self.read_position_raw()
        if raw_angle is None:
            print("Failed to read raw angle")
            return None
        return int(raw_angle / 4096 * 360)

    def read_scaled_angle(self):
        return self.read_registers(ANGLE_REGISTER_MSB, ANGLE_REGISTER_LSB)

    def get_status(self):
        status = self.read_register(STATUS_REGISTER)
        if status is None:
            print("Failed to read status register")
            return {
                "magnet_too_strong": False,
                "magnet_too_weak": False,
                "magnet_detected": False,
            }
        return {
            "magnet_too_strong": bool(status & 0x08),
            "magnet_too_weak": bool(status & 0x10),
            "magnet_detected": bool(status & 0x20),
        }

    def get_magnitude(self):
        return self.read_registers(MAGNITUDE_REGISTER_MSB, MAGNITUDE_REGISTER_LSB)
