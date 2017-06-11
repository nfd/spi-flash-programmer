import time
import serial
import argparse
import binascii
import sys

MAX_SIZE = 16 * 1024 * 1024
SECTOR_SIZE = 4096

class NoResponse(Exception):
	pass

def decodeHex(hexBytes):
	return binascii.unhexlify(hexBytes)

def encodeHex(data):
	return binascii.hexlify(data)

class SerialChatChat:
	def __init__(self, filename):
		self.sock = serial.Serial(filename, 115200, timeout=1)
		# Wait for the Arduino bootloader
		time.sleep(2)
	
	def _readCRC(self):
		crc = b''
		self.sock.flushInput()
		self.sock.write(b'c')
		while not crc.endswith(b'\r\n'):
			crc += self.sock.read(1)

		return int(crc, 16)

	def _printBuffer(self):
		crc = b''
		self.sock.flushInput()
		self.sock.write(b'd')
		while not crc.endswith(b'\r\n'):
			crc += self.sock.read(1)

		print ("BUFFER", crc)
		
	def _readPageOnce(self, page):
		# Reads page, returns CRC
		
		cmd = 'r%02x%02x' % ((page & 0xff00) >> 8, (page & 0xff))
		self.sock.write(cmd.encode('iso-8859-1'))
		self.sock.flush()
		return self._readCRC()

	def _readPageMultiple(self, page):
		# Keep reading until we get two pages reads the same.
		crc = [self._readPageOnce(page), self._readPageOnce(page)]
		count = 0
		while crc[0] != crc[1] and count < 3:
			print("Retrying read of page %d" % (page))
			crc.pop(0)
			crc.append(self._readPageOnce(page))
			count += 1

		if crc[0] != crc[1]:
			raise Exception()
		return crc[1]

	def readPage(self, page):
		self._readPageMultiple(page)
	
		# Dump the buffer.
		self.sock.write(b'd')

		result = []
		amt_read = 0
		while amt_read < 512:
			fromChip = self.sock.read(512 - amt_read)
			amt_read += len(fromChip)
			result.append(fromChip)

		result = b''.join(result)
		assert len(result) == 512, len(result)
		return decodeHex(result)

	def writePage(self, page, data):
		# Write the page and verify that it was written correctly.
		expectedCRC = binascii.crc32(data)

		data = encodeHex(data)
		assert len(data) == 512, (len(data), data)

		self.sock.write(b'l' + data)
		self.waitReady()

		# This shouldn't fail if we're using a reliable connection.
		if self._readCRC() != expectedCRC:
			raise Exception()

		# Write it, read it back, fail if we can't read what we wrote.
		cmd = 'w%02x%02x' % ((page & 0xff00) >> 8, (page & 0xff))
		
		#self._printBuffer()
		
		self.sock.write(cmd.encode('iso-8859-1'))
		self.sock.flush()
		self.waitReady()

		writtenCRC = self._readPageMultiple(page)
		#self._printBuffer()

		#print("written CRC", hex(writtenCRC), "expected CRC", hex(expectedCRC), page, data)
		return writtenCRC == expectedCRC

	def waitReady(self, seconds_to_wait=5):
		self.sock.flushInput()
		self.sock.write(b'>')
		self.sock.flush()

		for retry in range(seconds_to_wait):
			data = self.sock.read(1)
			if data == b'>':
				break
			elif data:
				print('unexpected', data)
		else:
			raise NoResponse()
	
	def verify(self, filename, flashStartByte=0, fileStartByte=0):
		assert flashStartByte % 256 == 0
		assert fileStartByte % 256 == 0
		idx = flashStartByte
		print("Verifying %s with flash start %d and file start %d" % (filename, flashStartByte, fileStartByte))
		with open(filename, 'rb') as h:
			h.seek(fileStartByte)
			while True:
				sys.stdout.write('\r%d' % (idx))
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

	def eraseSector(self, sectorNumber):
		cmd = 's%03x' % (sectorNumber)
		self.sock.write(cmd.encode('iso-8859-1'))
		self.waitReady()

	def _writeSectorOnce(self, byteOffset, sectorData):
		assert byteOffset % SECTOR_SIZE == 0
		assert len(sectorData) == SECTOR_SIZE
		pageData = []
		for idx in range(0, SECTOR_SIZE, 256):
			pageData.append(sectorData[idx:idx+256])

		pageOffset = byteOffset // 256
		
		expectedCRCs = [binascii.crc32(page) for page in pageData]
		actualCRCs   = [self._readPageMultiple(pageOffset + idx) for idx in range(SECTOR_SIZE // 256)]

		#print ("CRCS:", [hex(i) for i in expectedCRCs])
		#print ("CRCS2:", [hex(i) for i in actualCRCs])
		
		
		if expectedCRCs != actualCRCs:
			print("APAGANDO")
			self.eraseSector(byteOffset // SECTOR_SIZE)

		for idx, page in enumerate(pageData):
			#print("VAI GRAVAR", pageOffset + idx)
			if not self.writePage(pageOffset + idx, page):
				return False

		return True

	def writeFile(self, filename, offset=0):
		with open(filename, 'rb') as h:
			data = h.read(MAX_SIZE)

		print('Writing', filename, 'at', offset)

		for idx in range(0, len(data), SECTOR_SIZE):
			sys.stdout.write('\r%d of %d' % (idx, len(data)))
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
				sys.stdout.write('\r%d of %d' % (idx, size))
				sys.stdout.flush()

				page = idx // 256

				pageData = self.readPage(page + flashStartPage)
				handle.write(pageData)
	
def main():
	parser = argparse.ArgumentParser(description="Interface with an Arduino-based SPI flash programmer")
	parser.add_argument('-f', dest='filename')
	parser.add_argument('-d', dest='device', default='COM28')
	parser.add_argument('-s', dest='size', default='4096', help="size in KB")
	parser.add_argument('--flash-offset', dest='flash_offset', default='0', help='offset for flash read/write in bytes')
	parser.add_argument('--file-offset', dest='file_offset', default='0', help='offset for file read/write in bytes')
	parser.add_argument('command', choices=('write', 'read', 'verify'))
	args = parser.parse_args()

	chat = SerialChatChat(args.device)
	if args.command=='write':
		chat.writeFile(args.filename, int(args.flash_offset))
	elif args.command=='read':
		chat.readToFile(args.filename, int(args.size) * 1024, int(args.flash_offset))
	elif args.command=='verify':
		chat.verify(args.filename, int(args.flash_offset), int(args.file_offset))
	else:
		raise NotImplementedError()

if __name__ == '__main__':
	main()
