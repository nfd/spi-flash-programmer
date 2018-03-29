#include <stdint.h>
#include <stdio.h>

#include <SPI.h>

// SPI pins
#define DATAOUT 11 // MOSI
#define DATAIN  12 // MISO
#define SPICLOCK  13 // SCK
#define SLAVESELECT 10 // SS

// SPI opcodes
#define WREN  6
#define WRDI  4
#define RDSR  5
#define WRSR  1
#define READ  3
#define WRITE 2
#define SECTOR_ERASE 0x20
#define CHIP_ERASE 0xC7

// Command
#define COMMAND_HELLO '>'
#define COMMAND_HELP '?'
#define COMMAND_BUFFER_CRC 'h'
#define COMMAND_BUFFER_LOAD 'l'
#define COMMAND_BUFFER_STORE 's'
#define COMMAND_FLASH_READ 'r'
#define COMMAND_FLASH_WRITE 'w'
#define COMMAND_FLASH_ERASE_SECTOR 'k'
#define COMMAND_FLASH_ERASE_ALL 'n'
#define COMMAND_ERROR '!'

#define VERSION "SPI Flash programmer v1.0"

void dump_buffer(void);
void dump_buffer_crc(void);
int8_t read_into_buffer(void);

void erase_all(void);
void erase_sector(uint32_t address);
void read_page(uint32_t address);
void write_page(uint32_t address);

uint32_t crc_buffer(void);
void wait_for_write_enable(void);

int8_t read_nibble(void);
int16_t read_hex_u8(void);
int32_t read_hex_u16(void);
int8_t read_hex_u32(uint32_t *value);
void write_hex_u8(uint8_t value);
void write_hex_u16(uint16_t value);

uint8_t buffer [256];

SPISettings settingsA(100000, MSBFIRST, SPI_MODE0);

void setup()
{
  uint16_t i;

  for (i = 0; i < 256; i += 4)
  { // Initialize buffer with 0xDEADBEEF
    buffer[i + 0] = 0xDE;
    buffer[i + 1] = 0xAD;
    buffer[i + 2] = 0xBE;
    buffer[i + 3] = 0xEF;
  }

  Serial.begin(115200);

  pinMode(DATAOUT, OUTPUT);
  pinMode(DATAIN, INPUT);
  pinMode(SPICLOCK, OUTPUT);
  pinMode(SLAVESELECT, OUTPUT);

  digitalWrite(SLAVESELECT, HIGH); // disable flash device

  SPI.begin();

  delay(10);
}

void loop()
{
  uint32_t address;

  // Wait for command
  while(Serial.available() == 0) {
    ; // Do nothing
  }

  int cmd = Serial.read();
  switch(cmd) {
  case COMMAND_HELLO:
    Serial.print(COMMAND_HELLO); // Echo OK
    Serial.println(VERSION);
    Serial.print(COMMAND_HELLO); // Echo 2nd OK
    break;

  case COMMAND_FLASH_ERASE_ALL:
    erase_all();
    Serial.print(COMMAND_FLASH_ERASE_ALL); // Echo OK
    break;

  case COMMAND_FLASH_ERASE_SECTOR:
    if (!read_hex_u32(&address)) {
      Serial.print(COMMAND_ERROR); // Echo Error
      break;
    }

    erase_sector(address);
    Serial.print(COMMAND_FLASH_ERASE_SECTOR); // Echo OK
    break;

  case COMMAND_FLASH_READ:
    if (!read_hex_u32(&address)) {
      Serial.print(COMMAND_ERROR); // Echo Error
      break;
    }

    read_page(address);
    Serial.print(COMMAND_FLASH_READ); // Echo OK
    break;

  case COMMAND_FLASH_WRITE:
    if (!read_hex_u32(&address)) {
      Serial.print(COMMAND_ERROR); // Echo Error
      break;
    }

    write_page(address);
    Serial.print(COMMAND_FLASH_WRITE); // Echo OK
    break;

  case COMMAND_BUFFER_LOAD:
    Serial.print(COMMAND_BUFFER_LOAD); // Echo OK
    dump_buffer();
    Serial.println();
    break;

  case COMMAND_BUFFER_CRC:
    Serial.print(COMMAND_BUFFER_CRC); // Echo OK
    dump_buffer_crc();
    Serial.println();
    break;

  case COMMAND_BUFFER_STORE:
    if (!read_into_buffer()) {
      Serial.print(COMMAND_ERROR); // Echo Error
      break;
    }

    Serial.print(COMMAND_BUFFER_STORE); // Echo OK
    break;

  case COMMAND_HELP:
    Serial.println(VERSION);
    Serial.println("  n         : erase chip");
    Serial.println("  kXXXXXXXX : erase 4k sector XXXXXXXX (hex)");
    Serial.println();
    Serial.println("  rXXXXXXXX : read 256b page XXXXXXXX (hex) to buffer");
    Serial.println("  wXXXXXXXX : write buffer to 256b page XXXXXXXX (hex)");
    Serial.println();
    Serial.println("  h         : print buffer CRC-32");
    Serial.println("  l         : display the buffer (in hex)");
    Serial.println("  sBBBBBBBB : load the buffer with 256b of data BBBBBBBB...");
    Serial.println();
    Serial.println("Examples:");
    Serial.println("  r00003700      read 256 bytes from page 0x3700 into buffer");
    Serial.println("  scafe...3737   load the buffer with 256 bytes, first byte is 0xca ...");
    break;
  }

  Serial.flush();
} 

uint8_t spi_transfer(uint8_t data)
{
  return SPI.transfer(data);
}

void read_page(uint32_t address)
{
  uint16_t counter;

  // Send read command
  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(READ);                  // read instruction
  spi_transfer((address >> 8) & 0xFF); // bits 23 to 16
  spi_transfer(address & 0xFF);        // bits 15 to 8
  spi_transfer(0);                     // bits 7 to 0

  // Transfer a dummy sector to read data
  for(counter = 0; counter < 256; counter++) {
    buffer[counter] = spi_transfer(0xff);
  }

  // Release chip, signal end transfer
  digitalWrite(SLAVESELECT, HIGH);
} 

void wait_for_write_enable(void)
{
  uint8_t statreg = 0x1;

  while((statreg & 0x1) == 0x1) {
    // Wait for the chip
    digitalWrite(SLAVESELECT, LOW);
    spi_transfer(RDSR);
    statreg = spi_transfer(RDSR);
    digitalWrite(SLAVESELECT, HIGH);
  }
}

void write_page(uint32_t address)
{
  uint16_t counter;

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WREN); // write enable
  digitalWrite(SLAVESELECT,HIGH);
  delay(10);

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WRITE);                 // write instruction
  spi_transfer((address >> 8) & 0xFF); // bits 23 to 16
  spi_transfer(address & 0xFF);        // bits 15 to 8
  spi_transfer(0);                     // bits 7 to 0

  for (counter = 0; counter < 256; counter++) {
    spi_transfer(buffer[counter]);
  }

  digitalWrite(SLAVESELECT, HIGH);
  delay(1); // Wait for 1 ms

  wait_for_write_enable();
}

void erase_all()
{
  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WREN); // write enable
  digitalWrite(SLAVESELECT,HIGH);
  delay(10); // Wait for 10 ms

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(CHIP_ERASE);
  digitalWrite(SLAVESELECT,HIGH);
  delay(1); // Wait for 1 ms

  wait_for_write_enable();
}

void erase_sector(uint32_t address)
{
  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WREN);
  digitalWrite(SLAVESELECT,HIGH);
  delay(10);

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(SECTOR_ERASE);          // sector erase instruction
  spi_transfer((address >> 8) & 0xFF); // bits 23 to 16
  spi_transfer(address & 0xFF);        // bits 15 to 8
  spi_transfer(0);                     // bits 7 to 0
  digitalWrite(SLAVESELECT,HIGH);

  wait_for_write_enable();
}

void dump_buffer(void)
{
  uint16_t counter;

  for(counter = 0; counter < 256; counter++) {
    write_hex_u8(buffer[counter]);
  }
}

void dump_buffer_crc(void)
{
  uint32_t crc = crc_buffer();
  write_hex_u16((crc >> 16) & 0xFFFF);
  write_hex_u16(crc & 0xFFFF);
}

int8_t read_into_buffer(void)
{
  uint16_t counter;
  int16_t tmp;

  for(counter = 0; counter < 256; counter++) {
    tmp = read_hex_u8();
    if (tmp == -1) {
      return 0;
    }

    buffer[counter] = (uint8_t) tmp;
  }

  return 1;
}

int8_t read_nibble(void)
{
  int16_t c;

  do {
    c = Serial.read();
  } while(c == -1);

  if (c >= '0' && c <= '9') {
    return (c - '0') + 0;
  } else if (c >= 'a' && c <= 'f') {
    return (c - 'a') + 10;
  } else if (c >= 'A' && c <= 'F') {
    return (c - 'A') + 10;
  } else {
    return -1;
  }
}

int32_t read_hex_u16(void)
{
  int8_t i, tmp;
  uint16_t value = 0;

  for (i = 0; i < 4; i++) {
    tmp = read_nibble();
    if (tmp == -1) {
      return -1;
    }

    value <<= 4;
    value |= ((uint8_t) tmp) & 0x0F;
  }

  return value;
}

int16_t read_hex_u8(void)
{
  int8_t i, tmp;
  uint8_t value = 0;

  for (i = 0; i < 2; i++) {
    tmp = read_nibble();
    if (tmp == -1) {
      return -1;
    }

    value <<= 4;
    value |= ((uint8_t) tmp) & 0x0F;
  }

  return value;
}

int8_t read_hex_u32(uint32_t *value)
{
  int8_t i, tmp;
  uint32_t result = 0;

  for (i = 0; i < 8; i++) {
    tmp = read_nibble();
    if (tmp == -1) {
      return -1;
    }

    result <<= 4;
    result |= ((uint32_t) tmp) & 0x0F;
  }

  (*value) = result;

  return 1;
}

void write_nibble(uint8_t value)
{
  if (value < 10) {
    Serial.write(value + '0' - 0);
  } else {
    Serial.write(value + 'A' - 10);
  }
}

void write_hex_u8(uint8_t value)
{
    uint8_t i;

    for (i = 0; i < 2; i++) {
      write_nibble((uint8_t) ((value >> 4) & 0x0F));
      value <<= 4;
    }
}

void write_hex_u16(uint16_t value)
{
    uint8_t i;

    for (i = 0; i < 4; i++) {
      write_nibble((uint8_t) ((value >> 12) & 0x0F));
      value <<= 4;
    }
}

// Via http://excamera.com/sphinx/article-crc.html
static const uint32_t crc_table[16] = {
  0x00000000, 0x1db71064, 0x3b6e20c8, 0x26d930ac,
  0x76dc4190, 0x6b6b51f4, 0x4db26158, 0x5005713c,
  0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c,
  0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c
};

uint32_t crc_update(uint32_t crc, uint8_t data)
{
  uint8_t tbl_idx;

  tbl_idx = crc ^ (data >> (0 * 4));
  crc = crc_table[tbl_idx & 0x0f] ^ (crc >> 4);

  tbl_idx = crc ^ (data >> (1 * 4));
  crc = crc_table[tbl_idx & 0x0f] ^ (crc >> 4);

  return crc;
}

uint32_t crc_buffer(void)
{
  uint16_t i;
  uint32_t crc = ~0L;

  for(i = 0; i < 256; i++) {
    crc = crc_update(crc, buffer[i]);
  }

  crc = ~crc;

  return crc;
}
