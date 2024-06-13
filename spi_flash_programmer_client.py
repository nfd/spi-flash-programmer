#!/bin/python3

import time
import serial
import argparse
import binascii

import serial.tools.list_ports as list_ports

COMMAND_HELLO = '>'

COMMAND_BUFFER_CRC = 'h'
COMMAND_BUFFER_LOAD = 'l'
COMMAND_BUFFER_STORE = 's'

COMMAND_FLASH_READ = 'r'
COMMAND_FLASH_WRITE = 'w'
COMMAND_FLASH_ERASE_SECTOR = 'k'

COMMAND_WRITE_PROTECTION_ENABLE = 'p'
COMMAND_WRITE_PROTECTION_DISABLE = 'u'
COMMAND_WRITE_PROTECTION_CHECK = 'x'
COMMAND_STATUS_REGISTER_READ = 'y'
COMMAND_ID_REGISTER_READ = 'i'

COMMAND_SET_CS_IO = '*'
COMMAND_SET_OUTPUT = 'o'

WRITE_PROTECTION_NONE = 0x00
WRITE_PROTECTION_PARTIAL = 0x01
WRITE_PROTECTION_FULL = 0x02
WRITE_PROTECTION_UNKNOWN = 0x03

WRITE_PROTECTION_CONFIGURATION_NONE = 0x00
WRITE_PROTECTION_CONFIGURATION_PARTIAL = 0x01
WRITE_PROTECTION_CONFIGURATION_LOCKED = 0x02
WRITE_PROTECTION_CONFIGURATION_UNKNOWN = 0x03

DEFAULT_FLASH_SIZE = 4096 * 1024
DEFAULT_SECTOR_SIZE = 4096
DEFAULT_PAGE_SIZE = 256

ENCODING = 'iso-8859-1'

DEBUG_NORMAL = 1
DEBUG_VERBOSE = 2


class bcolors:
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def decorademsg(s: str, color):
    print(color + s + bcolors.ENDC)


def logMessage(text):
    print(text)


def logOk(text):
    decorademsg(text, bcolors.GREEN)


def logError(text):
    decorademsg(text, bcolors.RED)


def logDebug(text, type):
    if type == DEBUG_NORMAL:

        decorademsg(text, bcolors.CYAN)
    else:  # DEBUG_VERBOSE
        decorademsg(text, bcolors.MAGENTA)


class progress():
    def __init__(self, max) -> None:
        self.max = max
        self.act = 0
        print("\r\n")

    def show(self, cnt):
        self.print_delete_line()
        self.act = cnt
        print(str(self.act) + " of " + str(self.max))

    def show_bar(self, cnt):
        self.cnt = cnt
        percent = int(round(100.0 * self.cnt / self.max))
        barlen = 40
        bar = "["
        for i in range(barlen):
            if (i < (percent / (100 / barlen))):
                bar = bar + "#"
            else:
                bar = bar + " "
        bar = bar + "] " + str(self.cnt) + " of " + str(self.max)
        self.print_delete_line()
        print(bar)

    def print_delete_line(self):
        print("\033[A\033[A")  # to clear the previous print


class SerialProgrammer:

    def __init__(self, port, baud_rate, debug='off', sector_size=DEFAULT_SECTOR_SIZE, page_size=DEFAULT_PAGE_SIZE):
        self.sector_size = sector_size
        self.page_size = page_size
        self.pages_per_sector = self.sector_size // self.page_size

        if debug == 'normal':
            self.debug = DEBUG_NORMAL
        elif debug == 'verbose':
            self.debug = DEBUG_VERBOSE
        else:  # off
            self.debug = 0

        self._debug('Opening serial connection')
        self.sock = serial.Serial(port, baud_rate, timeout=1)
        self._debug('Serial connection opened successfully')

        time.sleep(2)  # Wait for the Arduino bootloader

    def _debug(self, message, level=DEBUG_NORMAL):
        if self.debug >= level:
            logDebug(message, level)

    def _readExactly(self, length, tries=3):
        """Read exactly n bytes or return None"""
        data = b''
        _try = 0
        while len(data) < length and _try < tries:
            new_data = self.sock.read(length - len(data))
            if new_data == b'':
                _try += 1

            data += new_data

        if len(data) != length:
            return None

        return data

    def _waitForMessage(self, text, tries=3, max_length=100):
        """Wait for the expected message and return True or return False"""
        self._debug('Waiting for \'%s\'' % text, DEBUG_VERBOSE)

        data = text.encode(ENCODING)
        return self._waitFor(len(data), lambda _data: data == _data, tries, max_length)

    def _waitFor(self, length, check, tries=3, max_length=100):
        """Wait for the expected message and return True or return False"""
        data = b''

        _try = 0
        while _try < tries:
            new_data = self.sock.read(max(length - len(data), 1))
            if new_data == b'':
                _try += 1

            max_length -= len(new_data)
            if max_length < 0:
                return False

            self._debug('Recv: \'%s\'' % new_data.decode(ENCODING), DEBUG_VERBOSE)

            data = (data + new_data)[-length:]
            if check(data):
                return True

        return False

    def _getUntilMessage(self, text, tries=3, max_length=100):
        """Wait for the expected message and return the data received"""
        self._debug('Reading until \'%s\'' % text, DEBUG_VERBOSE)

        data = text.encode(ENCODING)
        return self._getUntil(len(data), lambda _data: data == _data, tries, max_length)

    def _getUntil(self, length, check, tries=3, max_length=1000):
        """Wait for the expected message and return the data received"""
        data = b''
        message = b''

        _try = 0
        while _try < tries:
            new_data = self.sock.read(max(length - len(message), 1))
            if new_data == b'':
                _try += 1

            max_length -= len(new_data)
            if max_length < 0:
                return None

            self._debug('Recv: \'%s\'' % new_data.decode(ENCODING), DEBUG_VERBOSE)

            message = (message + new_data)[-length:]
            data += new_data
            if check(message):
                return data[:-len(message)]

        return None

    def _dump(self, data_str):
        for offset, data_row in [(i, data_str[i:i+16]) for i in range(0, len(data_str), 16)]:
            logMessage('%08x: %s' % (offset, ' '.join([data_row[i:i+2] for i in range(0, 16, 2)])))
        return

    def _sendCommand(self, command):
        self._debug('Send: \'%s\'' % command, DEBUG_VERBOSE)

        self.sock.write(command.encode(ENCODING))
        self.sock.flush()

    def _eraseSector(self, sector):
        self._debug('Command: ERASE_SECTOR %d' % sector)

        self._sendCommand('%s%08x' % (COMMAND_FLASH_ERASE_SECTOR, sector))
        return self._waitForMessage(COMMAND_FLASH_ERASE_SECTOR)

    def _readCRC(self):
        self._debug('Command: BUFFER_CRC')

        # Write crc check
        self._sendCommand(COMMAND_BUFFER_CRC)

        # Wait for crc start
        if not self._waitForMessage(COMMAND_BUFFER_CRC):
            self._debug('Invalid / no response for BUFFER_CRC command')
            return None

        crc = self._readExactly(8).decode(ENCODING)
        if crc is None:
            self._debug('Invalid / no CRC response')
            return None

        try:
            return int(crc, 16)
        except ValueError:
            self._debug('Could not decode CRC')
            return None

    def _loadPageOnce(self, page, tries=3):
        """Read a page into the internal buffer"""
        self._debug('Command: FLASH_READ %d' % page)

        # Reads page
        self._sendCommand('%s%08x' % (COMMAND_FLASH_READ, page))

        # Wait for read acknowledge
        if not self._waitForMessage(COMMAND_FLASH_READ):
            self._debug('Invalid / no response for FLASH_READ command')
            return None

        crc = self._readExactly(8).decode(ENCODING)
        if crc is None:
            self._debug('Invalid / no CRC response')
            return None

        try:
            return int(crc, 16)
        except ValueError:
            self._debug('Could not decode CRC')
            return None

    def _loadPageMultiple(self, page, tries=3):
        """Read a page into the internal buffer

        Keeps reading until we get two page reads the same checksum.
        """
        self._debug('Command: FLASH_READ_MULTIPLE %d' % page)

        crc_list = []
        _try = 0

        while _try < tries:
            crc = self._loadPageOnce(page, tries)
            if crc is None:
                _try += 1
                continue

            if len(crc_list) >= 1:
                if crc in crc_list:
                    self._debug('CRC is valid')
                    return crc
                else:
                    _try += 1

            crc_list.append(crc)

        self._debug('CRC reads did not match once')
        return None

    def _readPage(self, page, tries=3):
        """Read a page from the flash and receive it's contents"""
        self._debug('Command: FLASH_READ_PAGE %d' % page)

        # Load page into the buffer
        crc = self._loadPageMultiple(page, tries)

        for _ in range(tries):
            # Dump the buffer
            self._sendCommand(COMMAND_BUFFER_LOAD)

            # Wait for data start
            if not self._waitForMessage(COMMAND_BUFFER_LOAD):
                self._debug('Invalid / no response for BUFFER_LOAD command')
                continue

            # Load successful -> read sector with 2 nibbles per byte
            page_data = self._readExactly(self.page_size * 2)
            if page_data is None:
                self._debug('Invalid / no response for page data')
                continue

            try:
                data = binascii.a2b_hex(page_data.decode(ENCODING))
                if crc == binascii.crc32(data):
                    self._debug('CRC did match with read data')
                    return data
                else:
                    self._debug('CRC did not match with read data')
                    continue

            except TypeError:
                self._debug('CRC could not be parsed')
                continue

        self._debug('Page read tries exceeded')
        return None

    def _writePage(self, page, data):
        """Write a page into the buffer and instruct a page write operation

        This operation checks the written data with a generated checksum.
        """
        assert len(data) == self.page_size, (len(data), data)

        # Write the page and verify that it was written correctly.
        expected_crc = binascii.crc32(data)
        encoded_data = binascii.b2a_hex(data)

        self._sendCommand(COMMAND_BUFFER_STORE + encoded_data.decode(ENCODING))
        if not self._waitForMessage(COMMAND_BUFFER_STORE):
            self._debug('Invalid / no response for BUFFER_STORE command')
            return False

        # This shouldn't fail if we're using a reliable connection.
        crc = self._readExactly(8).decode(ENCODING)
        if crc is None:
            self._debug('Invalid / no CRC response for buffer write')
            return None

        try:
            if int(crc, 16) != expected_crc:
                return None
        except ValueError:
            self._debug('Could not decode CRC')
            return None

        # Write page
        self._sendCommand('%s%08x' % (COMMAND_FLASH_WRITE, page))
        time.sleep(.2)  # Sleep 200 ms

        if not self._waitForMessage(COMMAND_FLASH_WRITE):
            self._debug('Invalid / no response for FLASH_WRITE command')
            return False

        # Read back page
        # Fail if we can't read what we wrote
        read_crc = self._loadPageMultiple(page)
        if read_crc is None:
            self._debug('Invalid / no CRC response for flash write')
            return False

        return (read_crc == expected_crc)

    def _writeSectors(self, offset, data, tries=3):
        """Write one or more sectors with data

        This method clears the sectors before writing to them and checks
        for valid data via reading each page and comparing the checksum.
        """
        assert offset % self.sector_size == 0
        pages_offset = offset // self.page_size
        sectors_offset = offset // self.sector_size

        assert len(data) % self.sector_size == 0
        page_count = len(data) // self.page_size
        sector_count = len(data) // self.sector_size

        sector_write_attempt = 0
        sector = 0

        p = progress(page_count)

        while sector < sector_count:
            sector_index = sectors_offset + sector

            p.show_bar(sector * self.pages_per_sector)

            # Erase sector up to 'tries' times
            for _ in range(tries):
                if self._eraseSector(sector_index):
                    break
            else:  # No erase was successful
                logError('Could not erase sector 0x%08x' % sector_index)
                return False

            for page in range(self.pages_per_sector):
                page_data_index = sector * self.pages_per_sector + page
                data_index = page_data_index * self.page_size
                page_index = pages_offset + page_data_index

                if self._writePage(page_index, data[data_index: data_index + self.page_size]):
                    p.show_bar(page_data_index + 1)
                    continue

                sector_write_attempt += 1
                if sector_write_attempt < tries:
                    break  # Retry sector

                logError('Could not write page 0x%08x' % page_index)
                return False

            else:  # All pages written normally -> next sector
                sector += 1

        return True

    def _eraseSectors(self, offset, length, tries=3):
        """Clears one or more sectors"""
        assert offset % self.sector_size == 0
        sectors_offset = offset // self.sector_size

        assert length % self.sector_size == 0
        sector_count = length // self.sector_size

        p = progress(sector_count)
        for sector in range(sector_count):
            sector_index = sectors_offset + sector

            p.show(sector)

            # Erase sector up to 'tries' times
            for _ in range(tries):
                if self._eraseSector(sector_index):
                    break
            else:  # No erase was successful
                logError('Could not erase sector %08x' % sector_index)
                return False

            p.show(sector_count)

        return True

    def _hello(self):
        """Send a hello message and expect a version string"""
        self._debug('Command: HELLO')

        # Write hello
        self._sendCommand(COMMAND_HELLO)

        # Wait for hello response start
        if not self._waitForMessage(COMMAND_HELLO):
            self._debug('Invalid / no response for HELLO command')
            return None

        message = self._getUntilMessage(COMMAND_HELLO)
        if message is None:
            self._debug('No termination for HELLO command')
            return None

        return message.decode(ENCODING)

    def _read_register(self, cmd, name):
        """Generic read register function, send cmd and read a <CMD><LEN><DATA> response"""
        self._sendCommand(cmd)
        if not self._waitForMessage(cmd):
            self._debug('Invalid / no response for %s command' % (name,))
            logError('Invalid response')
            return None

        length_str = self._readExactly(2).decode(ENCODING)
        if length_str is None:
            self._debug('Invalid / no response for %s length' % (name,))
            logError('Invalid response')
            return None

        try:
            length = int(length_str, 16)
        except ValueError:
            self._debug('Could not decode %s length' % (name,))
            logError('Invalid register length')
            return None

        data_str = self._readExactly(length * 2).decode(ENCODING)
        if data_str is None:
            self._debug('Invalid / no response for %s check' % (name,))
            logError('Invalid response')
            return None

        try:  # Check if valid data
            decoded_data = binascii.a2b_hex(data_str)
        except TypeError:
            self._debug('Could not decode %s content' % (name))
            logError('Invalid response')
            return None

        return data_str

    def hello(self):
        """Send a hello message and print the retrieved version string"""
        version = self._hello()
        if version is None:
            logError('Connected to unknown device')
            return False
        else:
            logMessage('Connected to \'%s\'' % version.strip())
            return True

    def writeFromFile(self, filename, flash_offset=0, file_offset=0, length=DEFAULT_SECTOR_SIZE, pad=None):
        """Write the data from file to the flash"""
        if pad == None:
            if (length != -1) and (length % self.sector_size != 0):
                logError('length must be a multiple of the sector size %d' % self.sector_size)
                return False

            if flash_offset % self.sector_size != 0:
                logError('flash_offset must be a multiple of the sector size %d' % self.sector_size)
                return False
        elif not ((0x0 <= pad) and (pad <= 0xff)):
            logError('pad must be in range 0x00--0xff')
            return False

        if file_offset < 0:
            logError('file_offset must be a positive value or 0')
            return False

        data = None
        try:
            with open(filename, 'rb') as file:
                file.seek(file_offset)
                data = file.read(length)
        except IOError:
            logError('Could not read from file \'%s\'' % filename)
            return True

        if (length != -1) and (len(data) != length):
            logError('File is not large enough to read %d bytes' % length)
            return True

        if pad != None:
            pad_value = b'%c' % (pad&0xff)
            self._debug("Length of data before padding 0x%x" % (len(data),))

            pad_pre = flash_offset % self.sector_size
            self._debug("Pad 0x%x bytes before data" % (pad_pre,))
            data = pad_value*(flash_offset % self.sector_size) + data

            post_pad = self.sector_size - (len(data) % self.sector_size)
            if post_pad == self.sector_size:
                post_pad = 0x0
            self._debug("Pad 0x%x bytes after data" % (post_pad,))
            data = data + pad_value*(post_pad)

            flash_offset = flash_offset & (self.sector_size-0x1)
        elif (length == -1) and (len(data) % self.sector_size != 0):
            logError('file size must be a multiple of the sector size %d, use --pad' % self.sector_size)
            return False

        if not self._writeSectors(flash_offset, data):
            logError('Aborting')
        else:
            logOk('Done')

        return True

    def readToFile(self, filename, flash_offset=0, length=DEFAULT_FLASH_SIZE):
        """Read the data from the flash into the file"""
        if length % self.page_size != 0:
            logError('length must be a multiple of the page size %d' % self.page_size)
            return False

        if flash_offset % self.page_size != 0:
            logError('flash_offset must be a multiple of the page size %d' % self.page_size)
            return False

        page_count = length // self.page_size
        pages_offset = flash_offset // self.page_size

        try:
            with open(filename, 'wb') as file:

                p = progress(page_count)
                for page in range(page_count):

                    p.show(page)

                    page_index = pages_offset + page
                    data = self._readPage(page_index)
                    if data is not None:
                        file.write(data)
                        continue

                    # Invalid data
                    logError('Could not read page 0x%08x' % page_index)
                    return True

                p.show(page_count)

            logOk('Done')
            return True
        except IOError:
            logError('Could not write to file \'%s\'' % filename)
            return True

    def verifyWithFile(self, filename, flash_offset=0, file_offset=0, length=DEFAULT_FLASH_SIZE):
        """Verify the flash content by checking against the file

        This method only uses checksums to verify the data integrity.
        """
        if length % self.page_size != 0:
            logError('length must be a multiple of the page size %d' % self.page_size)
            return False

        if flash_offset % self.page_size != 0:
            logError('flash_offset must be a multiple of the page size %d' % self.page_size)
            return False

        page_count = length // self.page_size
        pages_offset = flash_offset // self.page_size

        try:
            with open(filename, 'rb') as file:
                file.seek(file_offset)

                p = progress(page_count)
                for page in range(page_count):

                    p.show(page)

                    data = file.read(self.page_size)

                    page_index = pages_offset + page
                    crc = self._loadPageMultiple(page_index)
                    if crc is None:
                        logError('Could not read page 0x%08x' % page_index)
                        return True

                    if crc == binascii.crc32(data):
                        logOk('Page 0x%08x OK' % page_index)
                    else:
                        logError('Page 0x%08x invalid' % page_index)

                p.show(page_count)

            logOk('Done')
            return True
        except IOError:
            logError('Could not write to file \'%s\'' % filename)
            return True

    def erase(self, flash_offset=0, length=DEFAULT_FLASH_SIZE):
        """Write the data in the file to the flash"""
        if length % self.sector_size != 0:
            logError('length must be a multiple of the sector size %d' % self.sector_size)
            return False

        if flash_offset % self.sector_size != 0:
            logError('flash_offset must be a multiple of the sector size %d' % self.sector_size)
            return False

        if not self._eraseSectors(flash_offset, length):
            logError('Aborting')
        else:
            logOk('Done')

        return True

    def set_write_protection(self, enable=False):
        """Set or clear the write protection of the flash"""
        self._debug('Command: WITE_PROTECTION %s' % enable)

        # Write command
        if enable:  # Enable
            self._sendCommand(COMMAND_WRITE_PROTECTION_ENABLE)
            if not self._waitForMessage(COMMAND_WRITE_PROTECTION_ENABLE):
                self._debug('Invalid / no response for WITE_PROTECTION command')
                logError('Invalid response')
                return True
        else:  # Disable
            self._sendCommand(COMMAND_WRITE_PROTECTION_DISABLE)
            if not self._waitForMessage(COMMAND_WRITE_PROTECTION_DISABLE):
                self._debug('Invalid / no response for WITE_PROTECTION command')
                logError('Invalid response')
                return True

        logOk('Done')
        return True

    def check_write_protection(self):
        """Check the write protection of the flash"""
        self._debug('Command: WITE_PROTECTION_CHECK')

        self._sendCommand(COMMAND_WRITE_PROTECTION_CHECK)
        if not self._waitForMessage(COMMAND_WRITE_PROTECTION_CHECK):
            self._debug('Invalid / no response for WRITE_PROTECTION_CHECK command')
            logError('Invalid response')
            return True

        protection = self._readExactly(4).decode(ENCODING)
        if protection is None:
            self._debug('Invalid / no response for protection check')
            logError('Invalid response')
            return True

        try:
            configuration_protection = int(protection[0:2], 16)
            write_protection = int(protection[2:4], 16)

            if configuration_protection == WRITE_PROTECTION_CONFIGURATION_NONE:
                logMessage('Configuration is unprotected')
            elif configuration_protection == WRITE_PROTECTION_CONFIGURATION_PARTIAL:
                logMessage('Configuration is partially protected')
            elif configuration_protection == WRITE_PROTECTION_CONFIGURATION_FULL:
                logMessage('Configuration is fully protected')
            elif configuration_protection == WRITE_PROTECTION_CONFIGURATION_UNKNOWN:
                logMessage('Configuration protection is unknown')
            else:
                logError('Unknown configuration protection status')

            if write_protection == WRITE_PROTECTION_NONE:
                logMessage('Flash content is unprotected')
            elif write_protection == WRITE_PROTECTION_PARTIAL:
                logMessage('Flash content is partially protected')
            elif write_protection == WRITE_PROTECTION_FULL:
                logMessage('Flash content is fully protected')
            elif write_protection == WRITE_PROTECTION_UNKNOWN:
                logMessage('Flash content protection is UNKNOWN')
            else:
                logError('Unknown flash protection status')

        except ValueError:
            self._debug('Could not decode protection status')
            logError('Invalid protection status')
            return True

        logOk('Done')
        return True

    def read_status_register(self):
        """Reads the status register contents"""
        self._debug('Command: STATUS_REGISTER')
        data = self._read_register(COMMAND_STATUS_REGISTER_READ, 'STATUS_REGISTER')
        if data==None:
            return True

        self._dump(data)
        return True

    def read_id_register(self):
        """Reads the id register contents"""
        self._debug('Command: ID_REGISTER')
        data = self._read_register(COMMAND_ID_REGISTER_READ, 'ID_REGISTER')
        if data==None:
            return True

        self._dump(data)
        return True

    def set_cs_io(self, io):
        """Overrides the CS/SS IO of Arduino"""
        self._debug('Command: SET_CS_IO')

        self._sendCommand('%s%02x' % (COMMAND_SET_CS_IO, io))
        if not self._waitForMessage(COMMAND_SET_CS_IO):
          self._debug('Invalid / no response for SET_CS_IO command')
          logError('Invalid response')
          return True

        return True

    def set_output(self, io, value):
        """Set IO pin to OUTPUT"""
        self._debug('Command: SET_OUTPUT')

        if value==None:
          value=0x00
        else:
          value=value&0xf
          if value&0xf!=0x0:
            value=0x1
          value=value|0x10

        self._sendCommand('%s%02x%02x' % (COMMAND_SET_OUTPUT, io, value))
        if not self._waitForMessage(COMMAND_SET_OUTPUT):
          self._debug('Invalid / no response for SET_OUTPUT command')
          logError('Invalid response')
          return True

        return True


def printComPorts():
    logMessage('Available COM ports:')

    for i, port in enumerate(list_ports.comports()):
        logMessage('%d: %s' % (i+1, port.device))

    logOk('Done')


def main():
    def hex_dec(x):
        # use auto detect mode, supports 0bYYYY=binary, 0xYYYY=hex, YYYY=decimal
        return int(x,0)

    parser = argparse.ArgumentParser(description='Interface with an Arduino-based SPI flash programmer')
    parser.add_argument('-d', dest='device', default='COM1',
                        help='serial port to communicate with')
    parser.add_argument('-f', dest='filename', default='flash.bin',
                        help='file to read from / write to')
    parser.add_argument('-l', type=hex_dec, dest='length', default=DEFAULT_FLASH_SIZE,
                        help='length to read/write in bytes, use -1 to write entire file')

    parser.add_argument('--rate', type=int, dest='baud_rate', default=115200,
                        help='baud-rate of serial connection')
    parser.add_argument('--flash-offset', type=hex_dec, dest='flash_offset', default=0,
                        help='offset for flash read/write in bytes')
    parser.add_argument('--file-offset', type=hex_dec, dest='file_offset', default=0,
                        help='offset for file read/write in bytes')
    parser.add_argument('--pad', type=hex_dec, default=None,
                        help='pad value if file is not algined with SECTOR_SIZE')
    parser.add_argument('--debug', choices=('off', 'normal', 'verbose'), default='off',
                        help='enable debug output')
    parser.add_argument('--io', type=hex_dec, default=None,
                        help="IO pin used for set-cs-io and set-output")
    parser.add_argument('--value', type=hex_dec, default=None,
                        help="value used for set-output")

    parser.add_argument('command', choices=('ports', 'write', 'read', 'verify', 'erase',
                                            'enable-protection', 'disable-protection', 'check-protection',
                                            'status-register', 'id-register', 'set-cs-io', 'set-output'),
                        help='command to execute')

    args = parser.parse_args()
    if args.command == 'ports':
        printComPorts()
        return

    try:
        programmer = SerialProgrammer(args.device, args.baud_rate, args.debug)
    except serial.SerialException:
        logError('Could not connect to serial port %s' % args.device)
        return

    def write(args, prog):
        return prog.writeFromFile(args.filename, args.flash_offset, args.file_offset, args.length, args.pad)

    def read(args, prog):
        return prog.readToFile(args.filename, args.flash_offset, args.length)

    def verify(args, prog):
        return prog.verifyWithFile(args.filename, args.flash_offset, args.file_offset, args.length)

    def erase(args, prog):
        return prog.erase(args.flash_offset, args.length)

    def enable_protection(args, prog):
        return prog.set_write_protection(True)

    def disable_protection(args, prog):
        return prog.set_write_protection(False)

    def check_protection(args, prog):
        return prog.check_write_protection()

    def read_status_register(args, prog):
        return prog.read_status_register()

    def read_id_register(args, prog):
        return prog.read_id_register()

    def set_cs_io(args, prog):
        return prog.set_cs_io(args.io)

    def set_output(args, prog):
        return prog.set_output(args.io, args.value)

    commands = {
            'write': write,
            'read': read,
            'verify': verify,
            'erase': erase,
            'enable-protection': enable_protection,
            'disable-protection': disable_protection,
            'check-protection': check_protection,
            'status-register': read_status_register,
            'id-register': read_id_register,
            'set-cs-io': set_cs_io,
            'set-output': set_output
        }

    if args.command not in commands:
        logError('Invalid command \'%d\'' % args.command)
        parser.print_help()
        return

    if not programmer.hello():
        # Unrecognized device
        parser.print_help()
        return

    if not commands[args.command](args, programmer):
        # Command got invalid arguments
        parser.print_help()


if __name__ == '__main__':
    main()