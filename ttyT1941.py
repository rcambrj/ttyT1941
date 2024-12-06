#!/usr/bin/python3

# ===========================================================================================
# Demonstrator to show the serial communication betwenn a host and the Tacx T1941 motor brake
# T1941 wants 19200 baud, 8N1, 3.3V TTL (no RS232 voltage levels)
# ===========================================================================================
#
# Python preconditions:
#
# Linux (Debian/Ubuntu):
#   sudo apt install python3
#   python3 -m pip install pyserial
#
# ---------------
# Standard USB2TTL
# ---------------
#
# Set permissions for '/dev/ttyUSBx' where 'x' is YOUR serial USB->serial adatper
# => typically /dev/ttyUSB0 if you have only one adapter connected to your PC
#
# 1. solution: every time after you plugged in the adapter (here: /dev/ttyUSB0)
#   sudo chmod 666 /dev/ttyUSB0
#
# 2. solution: add your user to the group, that 'owns' the ttyUSB device (typically 'dialout')
#   sudo adduser $USER dialout
#
# 3a. solution: add a rule (here for everyone!) to /etc/udev/rules.d/ i.e. '99-myttyusb.rules' with
#   KERNEL=="ttyUSB[0-9]*",MODE="0666"
#
# 3b. only for a specific adapter (here: 1a86:7523 QinHeng Electronics HL-340 USB-Serial adapter)
#   ACTION=="add", KERNEL=="ttyUSB[0-9]*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666"
#
# -------------
# Raspberry Pi:
# -------------
#
# If you connect the brake directly to Raspi's GPIO 14 and GPIO 15 (that is Pin 8 (Tx) and Pin 10 (Rx))
# do no forget to make the UART accessable via /dev/ttyAMA0 by adding:
#     enable_uart=1
#
# on Raspi 3 B (or B+) or Raspi Zero W use /dev/ttyS0 (not /dev/ttyUSB0). Be warned: the Mini-UART on the
# Raspi W Zero is limited and the error rate increase with a high command rate.
# So, if you do not need on-board Bluetooth switch it off with
#     dtoverlay=pi3-disable-bt
# to enable the standard UART under /dev/ttyAMA0.
# If you need Bluetooth on the Raspi, I recommend to use an additional USB2TTL adapter instead of the
# Mini-UART.
#
# to your /boot/config.txt. I recommend to first test the serial with a simple loopback test before
# you connect the brake just to make sure the you talk to the serial via /dev/ttyAMA0.
# Calling "./ttyT1941.py -d /dev/ttyAMA0" (in loopback) should print something like
#   Using /dev/ttyAMA0
#   bytearray(b'\x02\x00\x00\x00')
#   bytearray(b'\x02\x00\x00\x00')
#   ......
#
# --------------
# The Connection
# --------------
#
# socket (female side) how you see it, when looking on the brake-power-back (same for head unit)
#
#      __|^^^|__
#    _|         |_  original|
#    |           |  cable   | T1941: motor brake                   (T1901 eddy current brake)
#    |           |  color   |
#    |6 5 4 3 2 1|  ----------------------------------------------------------------------------
#     | | | | | |__ white   | T1941: not used                   (T1901: CAD sensor)
#     | | | | |____ black   | T1941  GND                        (T1901: also GND)
#     | | | |______ red     | T1941: Brake-Rx, Host-Tx (3.3V !) (T1901: magnetic field 'PWM' switch)
#     | | |________ green   | T1941: not used                   (T1901: powerline sinus +/- 20V)
#     | |__________ yellow  | T1941: ~6V                        (T1901: >12V) (maybe to power stand-alone head units?)
#     |____________ blue    | T1941: Brake-Tx, Host-Rx (3.3v !) (T1901: wheel signal)
#
# tested with a "1$" CH341 USB to TTL adapter
#
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# !!!                                               !!!
# !!! It is HIGHLY recommend to use 3.3V TTL logic, !!!
# !!! because the brake may not be 5V tolerant      !!!
# !!!                                               !!!
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#
# Just wire USB/TTL-GND to RJ12-Pin 2 (black, GND), USB/TTL-Tx to RJ12-Pin 3 (Red, Host-Tx, Brake Rx) and USB/TTL-Rx to RJ12-Pin 6 (blue, Host-Rx, Brake Tx).
# On Raspi GND is Pin 6, Tx is Pin 8 and Rx is Pin 10.
#
# Because I did not want to cut my original cable, I bought a new 6p6c RJ12 cable (1$) a CH341 USB to TTL adapter (1$).
# You can solder the pins or connected 'Dupont' sockets to the cable (< 1$) if you have a crimp tool.
#
# From 'Makeblock' there is a cable with a RJ12/RJ25 (6p6c) socket on one side an Dupont sockets on the other side.
# Price is about 2$-3$ for a bundle with two cables.
# The cable is only 20cm long, but with a full connected female-female 6p6c adapter, you can use the original
# cable in addition. The Makeblock part no. is MB14230. They even use the same wire colors as the original cable.

#
# The command- and answer-frames all look like: "4-bytes-header" | Message-Data | "2-bytes-checksum"
# the length of the msg is coded in the second byte of the header (header[1])
# Before sending to the serial line, the whole frame is converted into 'readable' Hex-Values (ascii 0-9,A-F).
#
# Motorbrake "version" command: (cmd=0x02, no message date)
# 02 00 00 00
#    => T1941 brake sends a short version message. i.e.:
#
#     T1941[16+2]: 03 0c 00 00 65 09 00 00 ba c4 77 18 08 0c 00 00 [c4 70]
#                  |--part1--| |--part2--| |--part3--| |--part4--|
#
# part1: Header 03=respose, 0xc size of paket (here 12 bytes of part2,part3,part4)
# part2: Firmware version, little endian, here "0.0.9.65"
# part3: Serial of YOUR motorbrake (not the head unit), little endian, here 0x1877c4ba = 41.05.02330
#        =>  41 (brake type=1941) 05 (year) 02330 (MY motorbrake serial)
# part4: unknown additional version
#
# Note: If you send 0x02,0x00,0x00,0x00 as first command or while switching on the brake,
#       the brake initialize not all parts in the buffer and sends the following answers
#   while switching on 1-2 times (raw):
#    01 46 46 30 32 30 30 30 30 43 44 46 46 39 44 38 31 17
#       => ff 02 00 00 cd ff [checksum: 9d 81] (decoded)
#   and then (raw):
#
#     [01] 30 33 30 43 30 30 30 30 36 35 30 39 30 30 30 30
#          41 42 43 34 37 37 31 38 30 38 30 43 00 00 00 00
#     [Checksum: 44 46 36 42] [17]             ^^^^^^^^^^^
#                                              |||||||||||
#   Înstead of 30 30 30 30 the brake sends probably uninitialized "00 00 00 00"
#   The checksum is calculated based on "00 00 00 00"
# After sending a 'normal' command with a 'longer' answer this part of the answer contains
# 'valid' ascii-hex values (probably the unchanged values of the previous 'longer' command)
#
#
# standard Motorbrake command:
#  0  1  2  3    4        5      6  7      8              9       10            11
# 01 08 01 00 LOAD_LSB LOAD_MSB 00 00 CAD_BOUNCE(0x01) WEIGHT CALIBRATE_LSB CALIBRATE_MSB
#    => with LOAD ie 0x0680 and CALIBRATE = 0x0410
#    => long answer from brake
#     T1941[23+1]: 03 13 02 00 00 00 00 00 00 00 f0 61 00 00 00 00 80 06 00 00 00 00 02 [cc cc]
#
# illegal message (a possible testmessage to detect motorbrake):
# 01
#    => the middle part and the checksum can vary
#     T1941[6+2] : ff 02 14 00 ce ff [48 4d]    -> little endian is 02FF, 0014, FFCE [cksm]
#
# Command Modes
#  Off-Mode
#     mode="0"  LOAD=0, weight does not matter, calibrate does not matter
#
#  Ergo-Mode: you give target power, brake controls resistance
#     mode="2"  LOAD ~= targetPower (in watts) * 128866 / raw_speed, weight = 0x0a, calibrate as necessary (0x410 = 8.0*130 is default)
#
#  Slope-Mode: you give the "slope", brake simulates a force (power = force * distance)
#     mode="2"  LOAD ~= (slope (in %) - 0.4) * 650, weight = total weight of rider and bike, calibrate as necessary (0x410 = 8.0*130 is default)
#
#  "3" Calibrate Mode: you give a speed, the brake turns the wheel and measures the power -> calibration depends on the necessary power to turn the wheel
#     LOAD = speed(in kmh) * 290, weight = 0 (does not matter), calibrate=0 (does not matter)


import serial, glob
import argparse
#import time
from time import sleep
from datetime import datetime, time, timedelta

startOfFrame = 0x01
endOfFrame   = 0x17

class HexValueError(Exception):
    pass

# bithack: parity
def parity16(b):
    b ^= b >> 8
    b ^= b >> 4
    b &= 0xf
    return (0x6996 >> b) & 1

# nibble => ascii: 0x0..0x9 => '0'..'9' and 0xa..0xf => 'A'..'F'
def bin2hex(b):
    if b >= 0 and b < 10:
        return b + 0x30      # '0'
    elif b >= 10 and b < 16:
        return b - 10 + 0x41 # 'A'
    else:
        raise NameError("only 4bit nibbles allowed")

def hex2bin(b):
    if b >= 0x30 and b <= 0x39:
        # '0'..'9'
        return b - 0x30
    elif b >= 0x41 and b <= 0x46:
        # 'A'..'F'
        return b + 10 - 0x41
    elif b >= 0x61 and b <= 0x66:
        # 'a'..'f'
        return b + 10 - 0x61
    # "special" fallback to handle case with wrong initialized brake
    elif b == 0x0:
        return 0

    raise HexValueError("only Ascii Hex chars allowed")

# checksum1() is checksum() with "pre-decoded" '0x01' start-of-frame byte (based on shiftreg 0x0000)
def checksum1(buffer):
    shiftreg = 0xc0c1
    # shiftreg = 0x0000
    poly = 0xc001
    for a in buffer:
        tmp = a ^ (shiftreg & 0xff)
        shiftreg >>= 8
        if parity16(tmp):
            shiftreg ^= poly
        tmp ^= tmp<<1
        shiftreg ^= tmp << 6
    return shiftreg


def marshal(buffer):
    buf = bytearray()
    for b in buffer:
        buf.append(bin2hex((b>>4)&0xf))
        buf.append(bin2hex((b>>0)&0xf))
    chk = checksum1(buf)
    buf.append(bin2hex((chk>>4)&0xf))
    buf.append(bin2hex((chk>>0)&0xf))
    chk >>= 8
    buf.append(bin2hex((chk>>4)&0xf))
    buf.append(bin2hex((chk>>0)&0xf))
    buf.insert(0, startOfFrame)
    buf.append(endOfFrame)
    return buf

def unmarshal(buffer):
    buf = bytearray()
    if len(buffer) < 6:
        print('frame too short')
        return buf

    if buffer[0] != startOfFrame or buffer[-1] != endOfFrame:
        print('no valid frame')
        return buf

    chk = checksum1(buffer[1:-5])
    try:
        chkBuf  = hex2bin(buffer[-5])<<4
        chkBuf += hex2bin(buffer[-4])<<0
        chkBuf += hex2bin(buffer[-3])<<12
        chkBuf += hex2bin(buffer[-2])<<8

        print('checksum  calc:{:4x} and buf:{:4x}'.format(chk, chkBuf))
        if chk != chkBuf:
            print('checksum error {:4x} != {:4x}'.format(chk, chkBuf))
            return buf

        for i in range(1,len(buffer)-5,2):
            buf.append( (hex2bin(buffer[i])<<4)+hex2bin(buffer[i+1]) )

    except HexValueError as err:
        print(err)
        # typically caused by a transfer error of received data - probably
        # in the 4 byte checksum. The other case (a corrupted frame with
        # a valid checksum) is unlikely (but can happen, too)
        return bytearray()

    return buf


def main():
    parser = argparse.ArgumentParser(description='Demonstrator to show the serial communication between a host and the Tacx T1941 motor brake')
    parser.add_argument('-d','--device', help='The serial device to use for communication.', required=False, default="/dev/ttyUSB0")

    parser.add_argument('-c','--calibrate', help='Switch to calibration mode', action='store_true', default=False)
    parser.add_argument('-ct','--calibrateTime', help='duration of calibration run', required=False, default=50)
    #parser.add_argument('-e','--ergo',      help='Switch to ergo (Power) mode', action='store_true', default=True)
    parser.add_argument('-s','--slope',     help='Switch to simulation (Slope) mode', action='store_true', default=False)
    args = parser.parse_args()

    if len(glob.glob('/dev/ttyUSB*')) > 1:
        print("INFO: Multiple /dev/ttyUSB device found.")
    print("Using "+args.device+" \n")

    if args.calibrate and args.slope:
        print("'Calibrate'- and 'Slope'-mode mutually exclude each other." )
        exit(1)

    port = serial.Serial(args.device, baudrate=19200, timeout=0.1, parity = serial.PARITY_NONE , bytesize = serial.EIGHTBITS, stopbits = serial.STOPBITS_ONE, xonxoff = False , rtscts = False, dsrdtr = False )
    # port = serial.Serial(args.device, baudrate=19200, timeout=0.1)
    port.read_all()   # just in case - to delete remaining data in input buffers

    selectedWatt     = 150.0
    selectedSlope    =  0.0
    selectedSpeed    = 20.0  # calibrate mode with 20 km/h

    weight_ergo = 0x0a             # weight=0x0a together with mode=2 switchs to ERGO mode.
    weight_slope_default = 0x52    # total weight (rider+bike) for simulation/slope mode

    slopeOffset      = -0.4
    slopeScale       = 2*5*130   # 13 * 5 * 10 * 5 = 3250
    speedScale       = 289.75  # convert km/h to "raw_speed"

    scale_calibrate = 130
    calibrate_value =  0.0         # calibrate_value range -8.0 ... 8.0
    calibrate = int(scale_calibrate * (calibrate_value + 8.0)) # default x0410 = 8*130 = 1040

    # The 'magic' scale factor: Raw_Load = Target_Power * 128866 / Raw_Speed
    power2load_magic   = 128866

    waitForSerial = True
    cadSensor = 0
    wheel = 0
    mode = 0
    calibrate_timer = 0
    calibrate_total = int(args.calibrateTime)   # default 50 seconds

    cmds_per_second = 1   # max is < 20 with 50ms timeout

    # Standard brake commands have 30 symbols and standard brake
    # answers have 52 symbols. One symbol needs 10 bits (with 8N1)
    # With 19200 baud, sending and receiving takes about 40ms, but
    # with values less then 70ms, brake sometimes loses a frame
    port.timeout = 0.070

    try:
        while True:

            nextCMD = None

            timeStart = datetime.now()

            if waitForSerial:
                print('=> sending version request')
                #triggerErrorCMD = bytes([0x01])
                nextCMD  = bytes([0x02,0x00,0x00,0x00])

            elif args.calibrate:
                print('=> sending calibration')
                if calibrate_timer == 0 and mode == 0:
                    print(
                        "\u001b[31;1mWatch out: Brake accelerates the wheel to 20 km/h.\n\n"
                        "\u001b[33;1mThe calibration process runs for about 50 seconds to warm up the\n"
                        "wheel and the brake. Rerun calibration if values are not stable at the end.\u001b[0m\n\n"
                        "\u001b[31;1mIf - for some reason - the program crashes while calibrating, the brake\n"
                        "continues wheeling. Start the programm again in non-calibrating mode to stop.\u001b[0m\n\n"
                        "\u001b[33;1mBrake is 'armed' for calibration - now turn the wheel with at least 5 km/h to\n"
                        "start the calibration (then stop pedalling).\u001b[0m\n\n"
                        )
                    mode = 3
                    load     = int( selectedSpeed * speedScale )

                if wheel > 10*speedScale or calibrate_timer > 0:
                    calibrate_timer += 1

                if calibrate_timer == calibrate_total*cmds_per_second:
                    mode = 0
                    load = 0
                    print("Stopping brake")

                if calibrate_timer > calibrate_total*cmds_per_second and wheel == 0:
                    exit(1)

                nextCMD   = bytes([0x01,0x08,0x01,0x00, load & 0xff, load >> 8, 0, 0x00, mode, 0x52, 0, 0 ])

            elif args.slope:
                print('=> sending slope')
                load     = int( (selectedSlope + slopeOffset)*slopeScale )
                if load > 32500:
                    load = 32500
                if load < -0x4000:
                    load = -0x4000
                if load < 0:
                    load += 0x10000
                cadecho  = cadSensor & 0x1
                mode = 2
                weight = weight_slope_default
                nextCMD   = bytes([0x01,0x08,0x01,0x00, load & 0xff, load >> 8, cadecho, 0x00, mode, weight, calibrate & 0xff, calibrate >> 8 ])

            else:
                print('=> sending status')
                load = 0
                if wheel > 0:
                    load     = int(selectedWatt * power2load_magic / wheel)
                cadecho  = cadSensor & 0x1
                mode = 2
                weight = weight_ergo
                nextCMD   = bytes([0x01,0x08,0x01,0x00, load & 0xff, load >> 8, cadecho, 0x00, mode, weight, calibrate & 0xff, calibrate >> 8 ])

            if nextCMD:
                cmd = marshal(nextCMD)
                print('=> D: '+' '.join(format(x, '02x') for x in nextCMD))
                print('=> R: '+' '.join(format(x, '02x') for x in cmd))
                port.write(cmd)

            answerRaw     = port.read(64)
            answerDecoded = unmarshal(answerRaw)
            print("R: "+' '.join(format(x, '02x') for x in answerRaw))
            print("D: "+' '.join(format(x, '02x') for x in answerDecoded))


            if len(answerDecoded) >= 23 and answerDecoded[24-24] == 0x03 and answerDecoded[25-24] == 19 and answerDecoded[26-24] == 2 and answerDecoded[27-24] == 0:
                print("<= received status")
                wheel                   = answerDecoded[32-24] | (answerDecoded[33-24]<<8)
                cadence                 = answerDecoded[44-24]
                cadSensor               = answerDecoded[42-24]
                distance                = answerDecoded[28-24] | (answerDecoded[29-24]<<8) | (answerDecoded[30-24]<<16) | (answerDecoded[31-24]<<24)
                unknown34_35            = answerDecoded[34-24] | (answerDecoded[35-24]<<8)
                currentResistance       = answerDecoded[38-24] | (answerDecoded[39-24]<<8)
                currentResistanceAvg    = answerDecoded[36-24] | (answerDecoded[37-24]<<8)
                desiredLoad             = answerDecoded[40-24] | (answerDecoded[41-24]<<8)

                speed       = wheel / speedScale

                if mode == 3:
                    useCalibration = 65536-currentResistance
                    if speed >= 19.8 and speed < 20.3:
                        print('    Calibrate: Wheel={:4d}, Speed={:4.1f} Resistance={:5d}: CalibrateTo={:5d} =0x{:04x}'.format(
                            wheel, speed, currentResistance, useCalibration, useCalibration))
                    elif speed > 3:
                        print('    Calibrate: Wheel={:4d}, Speed={:4.1f} Resistance={:5d}: CalibrateTo={:5d} =0x{:04x} \u001b[31;1m[Speed not between 19.8 and 20.2]\u001b[0m'.format(
                            wheel, speed, currentResistance, useCalibration, useCalibration))
                    else:
                        print('.', end='', flush=True)

                else:
                    currentWatt = int(currentResistance * wheel / power2load_magic)
                    currentWattAvg = int(currentResistanceAvg * wheel / power2load_magic)
                    print('DST={:5d}, '
                        'PWR=\u001b[31;1m{:4d}\u001b[0m, PWRAvg={:4d}, '
                        'Wheel={:4d}, SPD=\u001b[33;1m{:4.1f}\u001b[0m, '
                        'CAD=\u001b[32;1m{:3d}\u001b[0m, CadSensor={:1d}, '
                        'U3435={:5d} ForceAvg={:5d}, Force={:5d}, '
                        'LoadEcho={:5d} Load={:5d}'.format(
                        distance, currentWatt, currentWattAvg, wheel, speed, cadence, cadSensor,
                        unknown34_35, currentResistanceAvg, currentResistance, desiredLoad, load ))

            elif (len(answerDecoded) >= 16
                    and answerDecoded[24-24] == 0x03
                    and answerDecoded[25-24] == 12
                    and answerDecoded[26-24] == 0
                    and answerDecoded[27-24] == 0):

                print("<= received version")

                serialNr    = answerDecoded[32-24] | (answerDecoded[33-24] << 8) | (answerDecoded[34-24] << 16) | (answerDecoded[35-24] << 24)
                year        = serialNr // 100000 % 100
                serialSmall = serialNr  % 100000
                deviceNo    = serialNr // 10000000

                print("\u001b[32;1mPowerback\n"
                        "  firmwareVersion= {:02x}.{:02x}.{:02x}.{:02x}\n"
                        "  serial= {:d} (Tacx T19{:02d} Year 20{:02d} #{:05d})\n"
                        "  Date= {:02x}.{:02x} Unknown= {:02x}.{:02x}\u001b[0m\n".format(
                    answerDecoded[31-24],answerDecoded[30-24],answerDecoded[29-24],answerDecoded[28-24],
                    serialNr, deviceNo, year, serialSmall,
                    answerDecoded[37-24],answerDecoded[36-24],
                    answerDecoded[39-24],answerDecoded[38-24]))

                waitForSerial = False
            else:
                print("<= received unknown")


            delta = timeStart + timedelta(seconds=1/cmds_per_second) - datetime.now()
            if delta.total_seconds() >= 0:
                sleep(delta.microseconds / 1000000)
            else:
                print("OVERRUN: reduce commands per second!")

    except KeyboardInterrupt:
        if mode != 0:
            print("\nOoops - sending Stop command.")
            port.write(marshal(bytes([0x01,0x08,0x01,0x00, 0, 0, 0, 0, 0, 0, 0, 0 ])))


if __name__ == "__main__":
  main()
