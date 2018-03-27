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

void dump_buffer(void);
void dump_buffer_crc(void);
void write_buffer(void);

void erase_all(void);
void erase_sector(uint32_t address);
void read_page(uint32_t address);
void write_page(uint32_t address);

uint32_t crc_buffer(void);
void wait_for_write_enable(void);

int8_t read_nibble(void);
int32_t read_hex_u16(void);
int8_t read_hex_u32(uint32_t *value);
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
  int32_t tmp;
  uint32_t address;

  // Wait for command
  while(Serial.available() == 0) {
    ; // Do nothing
  }

  int cmd = Serial.read();
  switch(cmd) {
  case COMMAND_HELLO:
    Serial.print(COMMAND_HELLO); // Echo OK
    Serial.print("SPI Flash programmer v1.0\r\n");
    Serial.print(COMMAND_HELLO); // Echo 2nd OK
    break;

  case COMMAND_FLASH_ERASE_ALL:
    erase_all();
    Serial.print(COMMAND_FLASH_ERASE_ALL); // Echo OK
    break;

  case COMMAND_FLASH_ERASE_SECTOR:
    if (!read_hex_u32(&address)) {
      Serial.print(COMMAND_ERROR); // Echo Error
    }

    erase_sector(address);
    Serial.print(COMMAND_FLASH_ERASE_SECTOR); // Echo OK
    break;

  case COMMAND_FLASH_READ:
    if (!read_hex_u32(&address)) {
      Serial.print(COMMAND_ERROR); // Echo Error
    }

    read_page(address);
    Serial.print(COMMAND_FLASH_READ); // Echo OK
    break;

  case COMMAND_FLASH_WRITE:
    if (!read_hex_u32(&address)) {
      Serial.print(COMMAND_ERROR); // Echo Error
    }

    write_page(address);
    Serial.print(COMMAND_FLASH_WRITE); // Echo OK
    break;

  case COMMAND_BUFFER_LOAD:
    Serial.print(COMMAND_BUFFER_LOAD); // Echo OK
    dump_buffer();
    break;

  case COMMAND_BUFFER_CRC:
    Serial.print(COMMAND_BUFFER_CRC); // Echo OK
    dump_buffer_crc();
    break;

  case COMMAND_BUFFER_STORE:
    Serial.print(COMMAND_BUFFER_STORE); // Echo OK
    write_buffer();
    break;

  case COMMAND_HELP:
    Serial.println();
    Serial.println("SPI Flash programmer");
    Serial.println("  e     : erase chip");
    Serial.println("  sXXX  : erase 4k sector XXX (hex)");
    Serial.println("  c     : print buffer CRC-32");
    Serial.println("  rXXXX : read 256-uint8_t page XXXX (hex) to buffer");
    Serial.println("  wXXXX : write buffer to 256-uint8_t page XXXX (hex)");
    Serial.println("  d     : display the buffer (in hex)");
    Serial.println("  l<b>  : load the buffer with <b>, where b is 256 uint8_ts of data");
    Serial.println();
    Serial.println("Ex: r3700 - read 256 uint8_ts from page 0x3700");
    Serial.println("Ex: lcafe[...]3737 - load the buffer with 256 uint8_ts, first uint8_t 0xca...");
    break;
  }

  Serial.flush();
} 

void dump_buffer(void)
{
  uint16_t counter;

  for(counter = 0; counter < 256; counter++) {
    Serial.print(buffer[counter] >> 4, HEX);
    Serial.print(buffer[counter] & 0xF, HEX);
  }

  Serial.println();
}

void dump_buffer_crc(void)
{
  Serial.print(crc_buffer(), HEX);
  Serial.println();
}

void load_buffer(void)
{
  uint16_t counter;

  for(counter = 0; counter < 256; counter++) {
    buffer[counter] = read_hex();
  }
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
  spi_transfer(READ);
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

void write_page(uint8_t adr1, uint8_t adr2)
{
  uint16_t counter;

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WREN); // write enable
  digitalWrite(SLAVESELECT,HIGH);
  delay(10);

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WRITE); // write instruction
  spi_transfer(adr1); // bits 23 to 16
  spi_transfer(adr2); // bits 15 to 8
  spi_transfer(0);    // bits 7 to 0

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

void erase_sector(uint8_t addr1, uint8_t addr2)
{
  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WREN);
  digitalWrite(SLAVESELECT,HIGH);
  delay(10);

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(SECTOR_ERASE);
  spi_transfer(addr1);
  spi_transfer(addr2);
  spi_transfer(0);
  digitalWrite(SLAVESELECT,HIGH);

  wait_for_write_enable();
}

int8_t read_nibble(void)
{
  int8_t c;

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
  uint16_t value;

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

int8_t read_hex_u32(uint32_t *value)
{
  uint32_t result;
  int16_t tmp;

  tmp = read_hex();
  if (tmp == -1) {
    return 0;
  }

  result = (uint16_t) tmp;
  result <<= 16;

  tmp = read_hex();
  if (tmp == -1) {
    return 0;
  }

  result |= (uint16_t) tmp;
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

void write_hex_u16(uint16_t value)
{
    uint8_t i;

    for (i = 0; i < 4; i++) {
      write_nibble((uint8_t) ((value >> 12) & 0x0F));
      value >>= 4;
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
