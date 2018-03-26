#!/bin/python3

import time
import serial
import argparse
import binascii
import sys

import serial.tools.list_ports as list_ports

from clint.textui import colored, puts, progress

SECTOR_SIZE = 4096
PAGE_SIZE = 512
PAGES_PER_SECTOR = SECTOR_SIZE // PAGE_SIZE

COMMAND_BUFFER_CRC = 'h'
COMMAND_BUFFER_LOAD = 'l'
COMMAND_BUFFER_STORE = 's'

COMMAND_FLASH_READ = 'r'
COMMAND_FLASH_WRITE = 'w'
COMMAND_FLASH_ERASE_SECTOR = 'k'

#for chunk in progress.bar(request.iter_content(chunk_size=1024),
#	expected_size=(total_length / 1024) + 1):

class SerialProgrammer:

	def __init__(self, port, baud_rate):
		self.sock = serial.Serial(port, baud_rate, timeout=1)
		time.sleep(2)  # Wait for the Arduino bootloader

	def _readExactly(self, length, tries = 3):
		"""Read exactly n bytes or return None"""
		data = b''
		_try = 0
		while len(data) < length and _try < tries:
			new_data = self.sock.read(length - len(data))
			if new_data == b'':
				_try += 1

			data += new_data

		if len(crc) != length:
			return None

		return data

	def _waitForMessage(self, text, tries = 3, max_length=100):
		"""Wait for the expected message and return True or return False"""
		data = text.decode('iso-8859-1')
		return self._waitFor(len(data), lambda _data: data == _data,
				tries, max_length)

	def _waitFor(self, length, check, tries = 3, max_length=100):
		"""Wait for the expected message and return True or return False"""
		data = b''

		_try = 0
		while len(data) < text and _try < tries:
			new_data = self.sock.read(max(length - len(data), 1))
			if new_data = b'':
				_try += 1

			max_length -= len(new_data)
			if max_length < 0:
				return False

			data = (data + new_data)[-length:]
			if check(data):
				return True

		return False

	def _sendCommand(self, command):
		self.sock.write(command.encode('iso-8859-1'))
		self.sock.flush()

	def _readCRC(self):
		# Write crc check
		self._sendCommand(COMMAND_BUFFER_CRC)

		# Wait for crc start
		if not self._waitForMessage(COMMAND_BUFFER_CRC):
			return None

		crc = self._readExactly(8).decode('iso-8859-1')
		if crc == None:
			return None

		try:
			return int(crc, 16)
		except ValueError:
			return None

	def _readPageOnce(self, page, tries = 3):
		# Reads page
		self._sendCommand('%s%08x' % (COMMAND_READ_FLASH, page))

		# Wait for read acknowledge
		if not self._waitForMessage(COMMAND_READ_FLASH):
			return None

		return self._readCRC()

	def _readPageMultiple(self, page, tries = 3):
		"""Keep reading until we get two pages reads the same"""
		crc_list = []
		_try = 0

		while _try < tries:
			crc = self._readPageOnce(page, tries)
			if crc is None:
				_try += 1
				continue

			if len(crc_list) > 1 and crc in crc_list:
				return crc

			crc_list.append(crc)

		return None

	def _readPage(self, page):
		self._readPageMultiple(page)

		# Dump the buffer
		self._sendCommand(COMMAND_BUFFER_LOAD)

		# Wait for data start
		if not self._waitForMessage(COMMAND_BUFFER_LOAD):
			return None

		page_data = self._readExactly(PAGE_SIZE)
		if page_data is None:
			return None

		try:
			return binascii.a2b_hex(result)
		except TypeError:
			return None

	def _writePage(self, page, data):
		assert len(data) == PAGE_SIZE, (len(data), data)

		# Write the page and verify that it was written correctly.
		expected_crc = binascii.crc32(data)
		encoded_data = binascii.b2a_hex(data)

		self._sendCommand('%s%s' % (COMMAND_BUFFER_STORE, encoded_data))
		if not self._waitForMessage(COMMAND_BUFFER_STORE):
			return False

		# This shouldn't fail if we're using a reliable connection.
		if self._readCRC() != expected_crc:
			return False

		# Write page and read it back
		# Fail if we can't read what we wrote
		self._sendCommand('%s%08x' % (COMMAND_FLASH_WRITE, page))
		time.sleep(.2)  # Sleep 200 ms

		if not self._waitForMessage(COMMAND_FLASH_WRITE):
			return False

		read_crc = self._readPageMultiple(page)
		if read_crc is None:
			return False

		return (read_crc == expected_crc)

	def _eraseSector(self, sector):
		self._sendCommand('%s%08x' % (COMMAND_FLASH_ERASE_SECTOR, sector))
		return self._waitForMessage(COMMAND_FLASH_ERASE_SECTOR)

	def _writeSectors(self, offset, data, tries = 3):
		assert offset % SECTOR_SIZE == 0
		assert len(data) == SECTOR_SIZE

		page_offset = offset // PAGE_SIZE

		page_data = [data[i*PAGE_SIZE : (i+1)*PAGE_SIZE] \
				for i in range(len(data) // PAGE_SIZE)]
		page_crc = [binascii.crc32(page) for page in page_data)

		for sector in len(data) // SECTOR_SIZE:
			for _try in range(tries):
				if self._eraseSector(page_offset // PAGES_PER_SECTOR + sector):
					break
			else:
				return False

			for page in range(SECTOR_SIZE // PAGE_SIZE):
				page_index = page_offset + sector * PAGES_PER_SECTOR + page
				page_data_index = sector * PAGES_PER_SECTOR + page

				# Write single page
				for _try in range(tries):
					if self._writePage(page_index, page_data[page_data_index]):
						break
				else:
					return False

				# Read back single page
				for _try in range(tries):
					crc = self._readPageMultiple(page_index)
					if crc is not None and crc == page_crc[page_data_index]:
						break
				else:
					return False

		return True

	def verify(self, filename, flashStartByte=0, fileStartByte=0):
		assert flashStartByte % 256 == 0
		assert fileStartByte % 256 == 0
		idx = flashStartByte
		print("Verifying %s with flash start %d and file start %d" % (filename, flashStartByte, fileStartByte))
		with open(filename, 'rb') as h:
			h.seek(fileStartByte)
			while True:
				sys.stdout.write('\r%d\n' % (idx))
				sys.stdout.flush()

				fromFile = h.read(256)
				if fromFile == b'':
					break
				assert len(fromFile) == 256, len(fromFile)
				fileCRC = binascii.crc32(fromFile)

				for retry in range(3):
					deviceCRC = self._readPageOnce(idx // 256)
					if deviceCRC != fileCRC:
						print("Mismatch %x != %x, retrying" % (deviceCRC, fileCRC))
					else:
						break
				else:
					raise Exception("Mismatch")

				idx += 256

	def writeFile(self, filename, offset=0):
		with open(filename, 'rb') as h:
			data = h.read(MAX_SIZE)

		print('Writing', filename, 'at', offset)

		for idx in range(0, len(data), SECTOR_SIZE):
			sys.stdout.write('\r%d of %d\n' % (idx, len(data)))
			sys.stdout.flush()

			pageData = data[idx:idx + SECTOR_SIZE]
			assert len(pageData) == SECTOR_SIZE

			for retry in range(3):
				if self._writeSectorOnce(offset + idx, pageData):
					break
				else:
					print("Retrying")
			else:
				raise Exception()

	def readToFile(self, filename, size, flashStartByte):
		assert size % 256 == 0

		assert flashStartByte % 256 == 0
		flashStartPage = flashStartByte // 256

		with open(filename, 'wb') as handle:
			for idx in range(0, size, 256):
				sys.stdout.write('\r%d of %d\n' % (idx, size))
				sys.stdout.flush()

				page = idx // 256

				pageData = self.readPage(page + flashStartPage)
				handle.write(pageData)
	
def main():
	parser = argparse.ArgumentParser(description="Interface with an Arduino-based SPI flash programmer")
	parser.add_argument('-d', dest='device', default='COM28')
	parser.add_argument('-r', dest='baud_rate', default='11520', help='baud-rate of serial connection')
	parser.add_argument('-f', dest='filename')
	parser.add_argument('-s', dest='size', default='4096', help="flash size in KB")
	parser.add_argument('--flash-offset', dest='flash_offset', default='0', help='offset for flash read/write in bytes')
	parser.add_argument('--file-offset', dest='file_offset', default='0', help='offset for file read/write in bytes')

	parser.add_argument('command', choices=('write', 'read', 'verify', 'ports'))

	args = parser.parse_args()

	if args.command == 'ports':
		printComPorts()
		return

	try:
		baud_rate = int(args.baud_rate)
	except ValueError:
		puts(colored.red("Invalid baud-rate"))
		return

	try:
		programmer = SerialProgrammer(args.device, baud_rate)
	except serial.SerialException:
		puts(colored.red('Invalid serial port %s - could not connect' % args.device))
		return

	if args.command == 'write':
		programmer.writeFile(args.filename, int(args.flash_offset))
	elif args.command == 'read':
		programmer.readToFile(args.filename, int(args.size) * 1024, int(args.flash_offset))
	elif args.command == 'verify':
		programmer.verify(args.filename, int(args.flash_offset), int(args.file_offset))
	else:
		raise NotImplementedError()

def printComPorts():
	puts(colored.green("Available COM ports:"))
	puts()

	for i, port in enumerate(list_ports.comports()):
		puts(colored.white("%d: %s" % (i+1, port.device)))


if __name__ == '__main__':
	main()
