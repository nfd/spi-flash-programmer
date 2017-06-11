#include <SPI.h>
#include <avr/pgmspace.h>

#define DATAOUT 11//MOSI
#define DATAIN  12//MISO 
#define SPICLOCK  13//sck
#define SLAVESELECT 10//ss

//opcodes
#define WREN  6
#define WRDI  4
#define RDSR  5
#define WRSR  1
#define READ  3
#define WRITE 2 
#define SECTOR_ERASE 0x20
#define CHIP_ERASE 0xC7

SPISettings settingsA(100000, MSBFIRST, SPI_MODE0);

void erase_all();
void read_page(byte adr1, byte adr2);
void write_page(byte adr1, byte adr2);

byte buffer [256];

// Via http://excamera.com/sphinx/article-crc.html
static const PROGMEM uint32_t crc_table[16] = {
    0x00000000, 0x1db71064, 0x3b6e20c8, 0x26d930ac,
    0x76dc4190, 0x6b6b51f4, 0x4db26158, 0x5005713c,
    0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c,
    0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c
};

unsigned long crc_update(unsigned long crc, byte data)
{
    byte tbl_idx;
    tbl_idx = crc ^ (data >> (0 * 4));
    crc = pgm_read_dword_near(crc_table + (tbl_idx & 0x0f)) ^ (crc >> 4);
    tbl_idx = crc ^ (data >> (1 * 4));
    crc = pgm_read_dword_near(crc_table + (tbl_idx & 0x0f)) ^ (crc >> 4);
    return crc;
}

unsigned long crc_buffer(void)
{
  unsigned long crc = ~0L;
  for(int i=0; i < 256; i++)
    crc = crc_update(crc, buffer[i]);
  crc = ~crc;
  return crc;
}

void setup()
{
  Serial.begin(115200);

  pinMode(DATAOUT, OUTPUT);
  pinMode(DATAIN, INPUT);
  pinMode(SPICLOCK,OUTPUT);
  pinMode(SLAVESELECT,OUTPUT);
    
  digitalWrite(SLAVESELECT,HIGH); //disable device 
  // SPCR = 01010000
  //interrupt disabled,spi enabled,msb 1st,master,clk low when idle,
  //sample on leading edge of clk,system clock/4 rate (fastest)
  //SPCR = (1<<SPE)|(1<<MSTR);
  //SPCR = (1<<SPE)|(1<<MSTR)|(1<<SPI2X);
  SPI.begin();
  
  //byte clr;
  //clr=SPSR;
  //clr=SPDR;
  
  delay(10);
 
  buffer[0] = 0xca;
  buffer[1] = 0xfe;   
}

void loop()
{
  byte addr1, addr2;
  
  while(Serial.available() == 0)
    ;

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
    addr2 = read_nybble() << 4;
    erase_sector(addr1, addr2);
    break;
  case '?':
  case 'h':
    Serial.println("\nSPI Flash programmer");
    Serial.println(" e    : erase chip");
    Serial.println(" sXXX : erase 4k sector XXX (hex)");
    Serial.println(" c    : print buffer CRC-32");
    Serial.println(" rXXXX: read 256-byte page XXXX (hex) to buffer");
    Serial.println(" wXXXX: write buffer to 256-byte page XXXX (hex)");
    Serial.println(" d    : display the buffer (in hex)");
    Serial.println(" l<b> : load the buffer with <b>, where b is 256 bytes of data");
    Serial.println();
    Serial.println("Ex: r3700 - read 256 bytes from page 0x3700");
    Serial.println("Ex: lcafe[...]3737 - load the buffer with 256 bytes, first byte 0xca...");
  }
  
  Serial.flush();
} 

void dump_buffer()
{
  int counter;
  
  for(counter = 0; counter < 256; counter++) {
    Serial.print(buffer[counter] >> 4, HEX);
    Serial.print(buffer[counter] & 0xF, HEX);
  }
  Serial.println();
}

void dump_buffer_crc()
{
  unsigned long crc = crc_buffer();
  Serial.print(crc_buffer(), HEX);
  Serial.println();
}

void load_buffer()
{
  int counter;
  for(counter = 0; counter < 256; counter++) {
    buffer[counter] = read_hex();
  }
}

byte read_nybble()
{
  int nybble;
  while((nybble = Serial.read()) == -1)
    ;
  
  if(nybble >= 'A') {
    // works for lowercase as well (but no range checking of course)
    return 9 + (nybble & 0x0f);
  } else {
    return nybble & 0x0f;
  } 
}

byte read_hex()
{
  byte val;
  
  val = (read_nybble() & 0xf) << 4;
  val |= read_nybble();
  
  return val;
}

byte spi_transfer(volatile char data)
{
  char ret;
  //SPI.beginTransaction(settingsA);
  ret = SPI.transfer(data);
  //SPI.endTransaction();
  return ret;
  /*SPDR = data;                    // Start the transmission
  while (!(SPSR & (1<<SPIF)))     // Wait for the end of the transmission
  {
  };
  return SPDR;                    // return the received byte*/
}

void
read_page(byte adr1, byte adr2)
{
  //READ EEPROM
  int counter;
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

void wait_for_write()
{
  byte statreg = 0x1;
  
  while((statreg & 0x1) == 0x1) {
    // Wait for the chip.
    digitalWrite(SLAVESELECT, LOW);
    spi_transfer(RDSR);
    statreg = spi_transfer(RDSR);
    digitalWrite(SLAVESELECT, HIGH);
  }  
}

void write_page(byte adr1, byte adr2)
{
  int counter;
  
  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WREN); //write enable
  digitalWrite(SLAVESELECT,HIGH);
  delay(10);

  digitalWrite(SLAVESELECT,LOW);
  spi_transfer(WRITE); //write instruction
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
  int counter;
  
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

void erase_sector(byte addr1, byte addr2)
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
