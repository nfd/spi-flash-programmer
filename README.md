
SPI Flash programmer
====================

This is a very simple Arduino sketch and Python 3 client to program SPI flash chips. It's probably not very nice or tolerant, but it does at least have error correction and fast verification.

The requirements are [pySerial](https://github.com/pyserial/pyserial) and [clint](https://github.com/kennethreitz/clint). Both modules can be installed with [pip](https://pip.pypa.io/en/stable/installing/):

```bash
python3 -m pip install pyserial clint
```

Usage
-----

  - Program the Arduino with sketch
  - Connect the SPI flash chip as described
  - Run python client on PC to talk to programmer

Connecting a chip
-----------------

Connect the chip as follows, assuming you have an 3.3V 8-pin SSOP Flash chip.
<b>You will need an Arduino running at 3.3V logic.</b> See [3.3V Conversion](https://learn.adafruit.com/arduino-tips-tricks-and-techniques/3-3v-conversion) to convert your Arduino to 3.3V.

Or use one of the following devices running at 3.3V:

  - [Arduino 101 / Genuino 101](https://store.arduino.cc/genuino-101)
  - [Arduino Zero / Genuino Zero](https://store.arduino.cc/genuino-zero)
  - [Arduino Due](https://store.arduino.cc/arduino-due)
  - [Arduino M0](https://store.arduino.cc/arduino-m0)
  - [Arduino M0 Pro](https://store.arduino.cc/arduino-m0-pro)

<table>
<tr><td>Chip pin</td><td>Arduino pin</td> </tr>
<tr><td>1 /SS</td><td>10</td></tr>
<tr><td>2 MISO</td><td>12</td></tr>
<tr><td>3 /WP</td><td>+3.3V</td></tr>
<tr><td>4 GND</td><td>GND</td></tr>
<tr><td>5 MOSI</td><td>11</td></tr>
<tr><td>6 SCK</td><td>13</td></tr>
<tr><td>7 /HOLD</td><td>+3.3V</td></tr>
<tr><td>8 VDD</td><td>+3.3V</td></tr>
</table>

Commands
-------

```bash
# Listing serial ports
> python3 spi_flash_programmer_client.py ports
0: COM15
1: /dev/ttyS1
2: /dev/cu.usbserial
Done

# Read flash
> python3 spi_flash_programmer_client.py \
>   -d COM1 -l 4096 -f dump.bin read
Connected to 'SPI Flash programmer v1.0'
....

# Write flash (sectors are erased automatically)
> python3 spi_flash_programmer_client.py \
>   -d /dev/ttyS1 -l 4096 -f dump.bin write
Connected to 'SPI Flash programmer v1.0'
....

# Verify flash
> python3 spi_flash_programmer_client.py \
>   -d /dev/cu.usbserial -l 4096 -f dump.bin verify
Connected to 'SPI Flash programmer v1.0'
....

# Erase flash
> python3 spi_flash_programmer_client.py \
>   -d COM1 -l 4096 erase
Connected to 'SPI Flash programmer v1.0'
[###########                     ] 383/1024 - 00:01:13

# Help text
> python3 spi_flash_programmer_client.py -h
usage: spi_flash_programmer_client.py [-h] [-d DEVICE] [-f FILENAME]
                                      [-l LENGTH] [--rate BAUD_RATE]
                                      [--flash-offset FLASH_OFFSET]
                                      [--file-offset FILE_OFFSET]
                                      {ports,write,read,verify,erase}

Interface with an Arduino-based SPI flash programmer

positional arguments:
  {ports,write,read,verify,erase}
                        command to execute

optional arguments:
  -h, --help            show this help message and exit
  -d DEVICE             serial port to communicate with
  -f FILENAME           file to read from / write to
  -l LENGTH             length to read/write in kibi bytes (factor 1024)
  --rate BAUD_RATE      baud-rate of serial connection
  --flash-offset FLASH_OFFSET
                        offset for flash read/write in bytes
  --file-offset FILE_OFFSET
                        offset for file read/write in bytes
```

Troubleshooting
---------------

* Try reducing the serial speed from 115200 to 57600. You'll have to edit the value in both the .ino and the .py.
* Play with the SPCR setting in the .ino according to the datasheet.

License [CC0][http://creativecommons.org/publicdomain/zero/1.0/]
----------------------------------------------------------------

To the extent possible under law, the authors below have waived all copyright and related or neighboring rights to spi-flash-programmer.

  - Leonardo Goncalves
  - Nicholas FitzRoy-Dale, United Kingdom
  - Tobias Faller, Germany


Flashing a 16MB wr703n Flash chip
=================================
I used this to write a 16MB flash chip for the wr703n router running OpenWRT. Recent versions of OpenWRT detect the larger Flash and automatically use it, so you don't need to do any patching. U-Boot still thinks the chip is 4MB large, but Linux doesn't seem to care. So all you need to do is copy the image and write the ART (wireless firmware) partition to the right spot, which is right at the end of Flash.

I guess if you do a system upgrade which puts the kernel image somewhere after the first 4MB you might be in trouble, so upgrade u-boot before doing that.

1. Connect the original chip and dump it:

    python3 spi_flash_programmer_client.py -s 4096 -f wr703n.orig.bin read

2. Connect the new chip and write it:

    python3 spi_flash_programmer_client.py -s 4096 -f wr703n.orig.bin write

3. Verify the write.

    python3 spi_flash_programmer_client.py -s 4096 -f wr703n.orig.bin verify

3. Write the ART partition to the final 64k of the chip (the magic numbers are 16M-64K and 4M-64K respectively).

    python3 spi_flash_programmer_client.py -f wr703n.orig.bin --flash-offset 16711680 --file-offset 4128768 write

4. Verify the ART partition.

    python3 spi_flash_programmer_client.py -f wr703n.orig.bin --flash-offset 16711680 --file-offset 4128768 verify

5. Solder the new chip in.

If you try this, let me know!

