SPI Flash programmer
====================

This is a very simple Arduino sketch and Python client to program SPI flash chips. It's probably not very nice or tolerant, but it does at least have error correction and fast verification (and needs both!)

It requires [pySerial](http://pyserial.sourceforge.net).

To use it, write the Arduino program, connect your chip, and run the Python client.

Reading
-------

    python3 spi_flash_programmer_client.py -d /dev/cu.usbserial --flash-offset 0 -s 4096 -f dump.bin read

Writing
-------

    python3 spi_flash_programmer_client.py -d /dev/cu.usbserial --flash-offset 0 -s 4096 -f dump.bin write

Verifying
---------

    python3 spi_flash_programmer_client.py -d /dev/cu.usbserial --flash-offset 0 -s 4096 -f dump.bin verify

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

