#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
########################################################################
#
#   SMLlogger:  
#               7.2.2016 Dirk Clemens   iot@adcore.de
#               6.5.2017 Dirk Clemens   improvements, range check while converting hex to int
#               read data using a IR-USB-Head from a SML-counter (OBIS)
#               tested with "Zweirichtungszähler eHZ-IW8E2Axxx"
#       
#       based on 
#               http://wiki.volkszaehler.org/hardware/channels/meters/power/edl-ehz/edl21-ehz
#               http://wiki.volkszaehler.org/hardware/channels/meters/power/edl-ehz/emh-ehz-h1
#               http://volkszaehler.org/pipermail/volkszaehler-users/2012-September/000451.html
#               http://wiki.volkszaehler.org/software/sml
#               https://sharepoint.infra-fuerth.de/unbundling/obis_kennzahlen.pdf
#               https://www.mikrocontroller.net/attachment/89888/Q3Dx_D0_Spezifikation_v11.pdf
#               https://eclipse.org/paho/clients/python/ 
#
#       requirements:
#       sudo apt-get install python-dev python-pip python-serial python3-serial 
#       sudo pip install RPi.GPIO
#
########################################################################

import sys
import os
import serial
import time
import logging
from datetime import datetime
import math
import ssl
import urllib

########################################################################
import sys
import glob
import time
import serial
# http://stackoverflow.com/a/14224477

# logging
global logging
logging.basicConfig(level=logging.INFO, 
                                format='%(asctime)s %(levelname)s %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')

#logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)


# ------------- #
# settings      #
# ------------- #

# hex string to signed integer, inkl. range check http://stackoverflow.com/a/6727975 
def hexstr2signedint(hexval):
        uintval = int(hexval,16)
        if uintval > 0x7FFFFFFF:                # > 2147483647
                uintval -= 0x100000000          # -= 4294967296 
        return uintval

# parse hex string from USB serial stream and extract values for obis_id
def parseSML(data_hex, obis_string, pos, length):
        obis_value = 0
        # find position of OBIS-Kennzahl 
        position = data_hex.find(obis_string)
        
        # break, do not send mqtt message
        if position <= 0:
            logging.debug("%s int:%s raw:%s" % ("180",isk, data_hex))
            return 0

        # extract reading from position start: 34 length: 10 (for 1.8.0.)
        hex_value = data_hex[position+pos:position+pos+length]
        
        # convert to integer, check range  
        obis_value = hexstr2signedint(hex_value)
        return obis_value


def readPort(port):

        # eHZ-Datentelegramme können mittels eines optischen Auslesekopfs nach DIN EN 62056-21 
        # z. B. über die serielle Schnittstelle eines PC ausgelesen werden.
        # Einstellung: bit/s= 9600, Datenbit = 7, Parität = gerade, Stoppbits = 1, Flusssteuerung = kein.
        ser = serial.Serial(
                port=port, #'/dev/ttyUSB1', 
                baudrate=9600, 
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=2, 
                xonxoff=False, 
                rtscts=False, 
                dsrdtr=False)
        ser.flushInput()
        ser.flushOutput()


        data_hex = ''
        reading_ok = False
        try:
                # read n chars, change that in case it's too short
                while (1):
                        data_raw = ser.read(50)
                        #print(data_raw.encode("hex"))

                        # find start escape sequence: 1b1b1b1b0101010176
                        if data_raw.encode("hex").find("1b1b1b1b0101010176") >= 0 :
                                data_raw += ser.read(750) #lenght is 792
                                reading_ok = True 
                                break # found enough data, stop reading serial port
        except serial.serialutil.SerialException, e:
                reading_ok = False
                logging.debug("Error reading serial port: %s" % (e,))
                print("Error reading serial port: ", e)

        # convert reading to hex:
        data_hex = data_raw.encode("hex")
        # print (data_hex)

        if reading_ok:
                # tested with eHZ-IW8E2Axxx
                isk = parseSML(data_hex,'0100000009ff',34,8) 

                counter = float(float(parseSML(data_hex,'0100010800ff',34,16))/10000)
                print("%-20s %-10s %0.3f" % (port,isk,counter))
        else:
                logging.error("unable to find sml message")


########################################################################
# MAIN          
# 1b1b1b1b010101017607000b06d8119a620062007263010176010107000b025c05de0b0901454d4800004735c7010163a74e007607000b06d8119b620062007263070177010b0901454d4800004735c7070100620affff72620165025cd8f87a77078181c78203ff0101010104454d480177070100000009ff010101010b0901454d4800004735c70177070100010800ff6401018201621e52ff56000308cff70177070100020800ff6401018201621e52ff5600015fc1450177070100010801ff0101621e52ff56000308cff70177070100020801ff0101621e52ff5600015fc1450177070100010802ff0101621e52ff5600000000000177070100020802ff0101621e52ff5600000000000177070100100700ff0101621b52ff5500000b940177078181c78205ff0172620165025cd8f801018302841ead39cbefc83a615721f4639f94b453d6793c0f28883a1a2291deb9b7905b9af9e8bcc3955444cdb68d7078d1351b0101016323d4007607000b06d8119e6200620072630201710163527100001b1b1b1b1a01684c 
#
########################################################################

if len(sys.argv) > 1:
    ports = sys.argv[1:]
else:
    ports = glob.glob('/dev/ttyUSB*')

while True:
    for port in ports:
       readPort(port)
    time.sleep(10)

