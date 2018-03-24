#include <stdint.h>

#include <SPI.h>

#define DATAOUT 11 // MOSI
#define DATAIN  12 // MISO
#define SPICLOCK  13 //SCK
#define SLAVESELECT 10 // SS

// opcodes
#define WREN  6
#define WRDI  4
#define RDSR  5
#define WRSR  1
#define READ  3
#define WRITE 2
#define SECTOR_ERASE 0x20
#define CHIP_ERASE 0xC7

void erase_all(void);
void read_page(uint8_t adr1, uint8_t adr2);
void write_page(uint8_t adr1, uint8_t adr2);
void dump_buffer(void);
void dump_buffer_crc(void);
void load_buffer(void);
void erase_sector(uint8_t addr1, uint8_t addr2);
void wait_for_write(void);

uint32_t crc_buffer(void);

uint8_t buffer [256];

SPISettings settingsA(100000, MSBFIRST, SPI_MODE0);

void setup()
{
  Serial.begin(115200);

  pinMode(DATAOUT, OUTPUT);
  pinMode(DATAIN, INPUT);
  pinMode(SPICLOCK,OUTPUT);
  pinMode(SLAVESELECT,OUTPUT);

  digitalWrite(SLAVESELECT, HIGH); // disable device

  // SPCR = 01010000
  // interrupt disabled, spi enabled, msb 1st, master,
  // clk low when idle, sample on leading edge of clk,
  // system clock/2 rate (fastest)
  // SPCR = (1<<SPE) | (1<<MSTR);
  // SPSR = (1<<SPI2X);
  SPI.begin();

  delay(10);

  buffer[0] = 0xca;
  buffer[1] = 0xfe;
}

void loop()
{
  uint8_t addr1, addr2;

  // Wait for command
  while(Serial.available() == 0)
  {
  }

  int cmd = Serial.read();
  switch(cmd) {
  case '>':
    Serial.print('>');
    break;

  case 'e':
    erase_all();
    break;

  case 'r':
    addr1 = read_hex();
    addr2 = read_hex();
    read_page(addr1, addr2);
    break;

  case 'w':
    addr1 = read_hex();
    addr2 = read_hex();
    write_page(addr1, addr2);
    break;

  case 'd':
    dump_buffer();
    break;

  case 'c':
    dump_buffer_crc();
    break;

  case 'l':
    load_buffer();
    break;

  case 's':
    addr1 = read_hex();
    addr2 = read_nibble() << 4;
    erase_sector(addr1, addr2);
    break;

  case '?':
  case 'h':
    Serial.println();
    Serial.println("SPI Flash programmer");
    Serial.println("  e    : erase chip");
    Serial.println("  sXXX : erase 4k sector XXX (hex)");
    Serial.println("  c    : print buffer CRC-32");
    Serial.println("  rXXXX: read 256-uint8_t page XXXX (hex) to buffer");
    Serial.println("  wXXXX: write buffer to 256-uint8_t page XXXX (hex)");
    Serial.println("  d    : display the buffer (in hex)");
    Serial.println("  l<b> : load the buffer with <b>, where b is 256 uint8_ts of data");
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

void load_buffer()
{
  uint16_t counter;

  for(counter = 0; counter < 256; counter++) {
    buffer[counter] = read_hex();
  }
}

uint8_t read_nibble()
{
  uint8_t nibble;
  do {
    nibble = Serial.read();
  } while(nibble == -1);

  if(nibble >= 'A') {
    // works for lowercase as well (but no range checking of course)
    return 9 + (nibble & 0x0f);
  } else {
    return nibble & 0x0f;
  } 
}

uint8_t read_hex()
{
  uint8_t val;

  val = (read_nibble() & 0xf) << 4;
  val |= read_nibble();

  return val;
}

uint8_t spi_transfer(uint8_t data)
{
  return SPI.transfer(data);
}

void read_page(uint8_t adr1, uint8_t adr2)
{
  uint16_t counter;

  //READ EEPROM
  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(READ);
  spi_transfer(adr1); // bits 23 to 16
  spi_transfer(adr2); // bits 15 to 8
  spi_transfer(0);    // bits 7 to 0
  for(counter = 0; counter < 256; counter++) {
    buffer[counter] = spi_transfer(0xff);
  }
  digitalWrite(SLAVESELECT,HIGH); //release chip, signal end transfer
} 

void wait_for_write(void)
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

  for (counter = 0; counter < 256; counter++)
  {
    spi_transfer(buffer[counter]);
  }
  digitalWrite(SLAVESELECT,HIGH);
  delay(1);

  wait_for_write();
}

void erase_all()
{
  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WREN); //write enable
  digitalWrite(SLAVESELECT,HIGH);
  delay(10);

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(CHIP_ERASE);
  digitalWrite(SLAVESELECT,HIGH);
  delay(1);

  wait_for_write();
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

  wait_for_write();
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

  for(i = 0; i < 256; i++)
  {
    crc = crc_update(crc, buffer[i]);
  }

  crc = ~crc;

  return crc;
}
