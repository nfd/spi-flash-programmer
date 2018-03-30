#!/bin/python3

import time
import serial
import argparse
import binascii

import serial.tools.list_ports as list_ports

from clint.textui import colored, puts, progress

COMMAND_HELLO = '>'

COMMAND_BUFFER_CRC = 'h'
COMMAND_BUFFER_LOAD = 'l'
COMMAND_BUFFER_STORE = 's'

COMMAND_FLASH_READ = 'r'
COMMAND_FLASH_WRITE = 'w'
COMMAND_FLASH_ERASE_SECTOR = 'k'

DEFAULT_FLASH_SIZE = 4096  # 4096 kbit = 16 MBit
DEFAULT_SECTOR_SIZE = 4096
DEFAULT_PAGE_SIZE = 256

ENCODING = 'iso-8859-1'


def logMessage(text):
    puts(colored.white(text))


def logOk(text):
    puts(colored.green(text))


def logError(text):
    puts(colored.red(text))


class SerialProgrammer:

    def __init__(self, port, baud_rate, sector_size=DEFAULT_SECTOR_SIZE, page_size=DEFAULT_PAGE_SIZE):
        self.sector_size = sector_size
        self.page_size = page_size
        self.pages_per_sector = self.sector_size // self.page_size

        self.sock = serial.Serial(port, baud_rate, timeout=1)
        time.sleep(2)  # Wait for the Arduino bootloader

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

            # Debug here
            # puts("Recv: \'%s\'" % new_data.decode(ENCODING))

            data = (data + new_data)[-length:]
            if check(data):
                return True

        return False

    def _getUntilMessage(self, text, tries=3, max_length=100):
        """Wait for the expected message and return the data received"""
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

            message = (message + new_data)[-length:]
            data += new_data
            if check(message):
                return data[:-len(message)]

        return None

    def _sendCommand(self, command):
        # Debug here
        # puts("Send: \'%s\'" % command)

        self.sock.write(command.encode(ENCODING))
        self.sock.flush()

    def _eraseSector(self, sector):
        self._sendCommand('%s%08x' % (COMMAND_FLASH_ERASE_SECTOR, sector * self.pages_per_sector))
        return self._waitForMessage(COMMAND_FLASH_ERASE_SECTOR)

    def _readCRC(self):
        # Write crc check
        self._sendCommand(COMMAND_BUFFER_CRC)

        # Wait for crc start
        if not self._waitForMessage(COMMAND_BUFFER_CRC):
            return None

        crc = self._readExactly(8).decode(ENCODING)
        if crc is None:
            return None

        try:
            return int(crc, 16)
        except ValueError:
            return None

    def _loadPageOnce(self, page, tries=3):
        """Read a page into the internal buffer"""
        # Reads page
        self._sendCommand('%s%08x' % (COMMAND_FLASH_READ, page))

        # Wait for read acknowledge
        if not self._waitForMessage(COMMAND_FLASH_READ):
            return None

        return self._readCRC()

    def _loadPageMultiple(self, page, tries=3):
        """Read a page into the internal buffer

        Keeps reading until we get two page reads the same checksum.
        """
        crc_list = []
        _try = 0

        while _try < tries:
            crc = self._loadPageOnce(page, tries)
            if crc is None:
                _try += 1
                continue

            if len(crc_list) > 1:
                if crc in crc_list:
                    return crc
                else:
                    _try += 1

            crc_list.append(crc)

        return None

    def _readPage(self, page, tries=3):
        """Read a page from the flash and receive it's contents"""
        # Load page into the buffer
        self._loadPageMultiple(page, tries)

        for _ in range(tries):
            # Dump the buffer
            self._sendCommand(COMMAND_BUFFER_LOAD)

            # Wait for data start
            if not self._waitForMessage(COMMAND_BUFFER_LOAD):
                continue

            # Load successful -> read sector with 2 nibbles per byte
            page_data = self._readExactly(self.page_size * 2)
            if page_data is None:
                continue

            try:
                return binascii.a2b_hex(page_data.decode(ENCODING))
            except TypeError:
                continue

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
            return False

        # This shouldn't fail if we're using a reliable connection.
        if self._readCRC() != expected_crc:
            return False

        # Write page
        self._sendCommand('%s%08x' % (COMMAND_FLASH_WRITE, page))
        time.sleep(.2)  # Sleep 200 ms

        if not self._waitForMessage(COMMAND_FLASH_WRITE):
            return False

        # Read back page
        # Fail if we can't read what we wrote
        read_crc = self._loadPageMultiple(page)
        if read_crc is None:
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

        with progress.Bar(expected_size=page_count) as bar:
            sector_write_attempt = 0
            sector = 0
            while sector < sector_count:
                sector_index = sectors_offset + sector

                bar.show(sector * self.pages_per_sector)

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
                        bar.show(page_data_index + 1)
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

        with progress.Bar(expected_size=sector_count) as bar:
            for sector in range(sector_count):
                sector_index = sectors_offset + sector

                bar.show(sector)

                # Erase sector up to 'tries' times
                for _ in range(tries):
                    if self._eraseSector(sector_index):
                        break
                else:  # No erase was successful
                    logError('Could not erase sector %08x' % sector_index)
                    return False

            bar.show(sector_count)

        return True

    def _hello(self):
        """Send a hello message and expect a version string"""
        # Write hello
        self._sendCommand(COMMAND_HELLO)

        # Wait for hello response start
        if not self._waitForMessage(COMMAND_HELLO):
            return None

        message = self._getUntilMessage(COMMAND_HELLO)
        if message is None:
            return None

        return message.decode(ENCODING)

    def hello(self):
        """Send a hello message and print the retrieved version string"""
        version = self._hello()
        if version is None:
            logError('Connected to unknown device')
            return False
        else:
            logMessage('Connected to \'%s\'' % version.strip())
            return True

    def writeFromFile(self, filename, flash_offset=0, file_offset=0, length=DEFAULT_SECTOR_SIZE):
        """Write the data in the file to the flash"""
        if length % self.sector_size != 0:
            logError("length must be a multiple of the sector size %d" % self.sector_size)
            return False

        if flash_offset % self.sector_size != 0:
            logError("flash_offset must be a multiple of the sector size %d" % self.sector_size)
            return False

        if file_offset < 0:
            logError("file_offset must be a positive value or 0")
            return False

        data = None
        try:
            with open(filename, 'rb') as file:
                file.seek(file_offset)
                data = file.read(length)
                if len(data) != length:
                    logError('File is not large enough to read %d bytes' % length)
                    return True
        except IOError:
            logError('Could not read from file \'%s\'' % filename)
            return True

        if not self._writeSectors(flash_offset, data):
            logError('Aborting')
        else:
            logOk('Done')

        return True

    def readToFile(self, filename, flash_offset=0, length=DEFAULT_FLASH_SIZE):
        """Read the data from the flash into the file"""
        if length % self.page_size != 0:
            logError("length must be a multiple of the page size %d" % self.page_size)
            return False

        if flash_offset % self.page_size != 0:
            logError("flash_offset must be a multiple of the page size %d" % self.page_size)
            return False

        page_count = length // self.page_size
        pages_offset = flash_offset // self.page_size

        try:
            with open(filename, 'wb') as file:
                with progress.Bar(expected_size=page_count) as bar:
                    for page in range(page_count):
                        bar.show(page)

                        page_index = pages_offset + page
                        data = self._readPage(page_index)
                        if data is not None:
                            file.write(data)
                            continue

                        # Invalid data
                        logError('Could not read page 0x%08x' % page_index)
                        return True

                    bar.show(page_count)

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
            logError("length must be a multiple of the page size %d" % self.page_size)
            return False

        if flash_offset % self.page_size != 0:
            logError("flash_offset must be a multiple of the page size %d" % self.page_size)
            return False

        page_count = length // self.page_size
        pages_offset = flash_offset // self.page_size

        try:
            with open(filename, 'rb') as file:
                file.seek(file_offset)

                with progress.Bar(expected_size=page_count) as bar:
                    for page in range(page_count):
                        bar.show(page)

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

                    bar.show(page_count)

            logOk('Done')
            return True
        except IOError:
            logError('Could not write to file \'%s\'' % filename)
            return True

    def erase(self, flash_offset=0, length=DEFAULT_FLASH_SIZE):
        """Write the data in the file to the flash"""
        if length % self.sector_size != 0:
            logError("length must be a multiple of the sector size %d" % self.sector_size)
            return False

        if flash_offset % self.sector_size != 0:
            logError("flash_offset must be a multiple of the sector size %d" % self.sector_size)
            return False

        if not self._eraseSectors(flash_offset, length):
            logError('Aborting')
        else:
            logOk('Done')

        return True


def printComPorts():
    logMessage('Available COM ports:')

    for i, port in enumerate(list_ports.comports()):
        logMessage('%d: %s' % (i+1, port.device))

    logOk('Done')


def main():
    parser = argparse.ArgumentParser(description="Interface with an Arduino-based SPI flash programmer")
    parser.add_argument('-d', dest='device', default='COM1',
                        help='serial port to communicate with')
    parser.add_argument('-f', dest='filename', default='flash.bin',
                        help='file to read from / write to')
    parser.add_argument('-l', type=int, dest='length', default=DEFAULT_FLASH_SIZE,
                        help='length to read/write in kibi bytes (factor 1024)')

    parser.add_argument('--rate', type=int, dest='baud_rate', default=115200,
                        help='baud-rate of serial connection')
    parser.add_argument('--flash-offset', type=int, dest='flash_offset', default=0,
                        help='offset for flash read/write in bytes')
    parser.add_argument('--file-offset', type=int, dest='file_offset', default=0,
                        help='offset for file read/write in bytes')

    parser.add_argument('command', choices=('ports', 'write', 'read', 'verify', 'erase'),
                        help='command to execute')

    args = parser.parse_args()
    if args.command == 'ports':
        printComPorts()
        return

    try:
        programmer = SerialProgrammer(args.device, args.baud_rate)
    except serial.SerialException:
        logError('Could not connect to serial port %s' % args.device)
        return

    def write(args, prog):
        return prog.writeFromFile(args.filename, args.flash_offset, args.file_offset, args.length * 1024)

    def read(args, prog):
        return prog.readToFile(args.filename, args.flash_offset, args.length * 1024)

    def verify(args, prog):
        return prog.verifyWithFile(args.filename, args.flash_offset, args.file_offset, args.length * 1024)

    def erase(args, prog):
        return prog.erase(args.flash_offset, args.length * 1024)

    commands = {
            'write': write,
            'read': read,
            'verify': verify,
            'erase': erase
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
