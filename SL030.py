# StrongLink SL030 card reader python module

# The MIT License
#
# Copyright (C) 2013 Gabor Molnar <gabor@molnar.es>
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# 'Software'), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# The protocol is not compatible with SMBus so we can't use the python-smb
# module. Instead, we use the standard /dev interface exposed by the i2c-dev
# kernel module.
# Documentation: https://www.kernel.org/doc/Documentation/i2c/dev-interface
#
# Furthermore, standard file IO is not low level enough: we can't control the
# size of the buffer size when issuing a read syscall, and the i2c dev interface
# does not work with large read buffers. The io module let's us specify the
# exact buffer size, so we use that instead of standard IO.

import fcntl
import io
import time
import select

# I2C_SLAVE constant from i2c-tools-3.1.0/include/linux/i2c-dev.h
I2C_SLAVE = 0x0703


class SL030:
    COMMAND_SELECT = 0x01
    COMMAND_SLEEP = 0x50

    STATUS_SUCCESS = 0x00

    def __init__(self, i2c_bus, i2c_address, gpio_detect=None, gpio_wake=None):
        # Opening the I2C device file
        self.bus = io.FileIO('/dev/i2c-%d' % i2c_bus, 'r+')

        # Specifying the address of the I2C slave with the I2C_SLAVE ioctl.
        error = fcntl.ioctl(self.bus, I2C_SLAVE, i2c_address)
        if error:
            raise Exception('Couldn\'t set the slave address on the bus', error)

        # Preparing the tag detect GPIO pin
        self.pin_detect = None
        if gpio_detect is not None:
            try:
                export = open('/sys/class/gpio/export', 'w')
                export.write(str(gpio_detect))
                export.close()
            except:
                print 1
            gpio_root = '/sys/class/gpio/gpio%d' % gpio_detect
            open(gpio_root + '/direction', 'w').write('in')
            open(gpio_root + '/edge', 'w').write('falling')
            self.pin_detect = open(gpio_root + '/value', 'r')

        # Preparing the wake up GPIO pin
        self.pin_wake = None
        if gpio_wake is not None:
            try:
                export = open('/sys/class/gpio/export', 'w')
                export.write(str(gpio_wake))
                export.close()
            except:
                print 1
            gpio_root = '/sys/class/gpio/gpio%d' % gpio_wake
            open(gpio_root + '/direction', 'w').write('out')
            self.pin_wake = open(gpio_root + '/value', 'w')
            self.pin_wake.write('1')

    def write(self, command, data=''):
        length = 1 + len(data)
        if length > 255:
            raise Exception('Too large data (max size: 254)')

        if not (0 <= command <= 255):
            raise Exception('Invalid command')

        self.bus.write(chr(length) + chr(command) + data)

    def read(self):
        response = self.bus.read(256)

        # Length prefix
        length = ord(response[0])

        # Raspberry Pi bug? MSB of every payload byte is always 1.
        response = ''.join(map(chr, map(lambda c: c & 127, map(ord, response))))

        # Payload
        command = ord(response[1])
        status = ord(response[2])
        data = response[3:length+1]

        return command, status, data

    def transaction(self, command, data=''):
        self.write(command, data)

        time.sleep(0.1)

        response_command, status, data = self.read()
        if response_command != command:
            raise Exception('Transaction response contains wrong command (%d)' %
                            response_command)

        return status, data

    def sleep(self):
        self.write(SL030.COMMAND_SLEEP)

    def wake(self):
        self.pin_wake.write('1')
        time.sleep(0.1)
        self.pin_wake.write('0')

    def select(self):
        status, data = self.transaction(SL030.COMMAND_SELECT)

        if status is not SL030.STATUS_SUCCESS:
            return None

        length = len(data)
        card_type = ord(data[length - 1])
        uid = data[:length - 1]

        return card_type, uid

    def poll(self):
        self.pin_detect.read()
        poll = select.epoll()
        poll.register(self.pin_detect, select.EPOLLPRI)

        poll.poll()
        return self.select()

reader = SL030(1, 0x50, 4, None)

while True:
    print map(ord, reader.poll()[1])
