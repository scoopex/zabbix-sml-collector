#!/usr/bin/env python3
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

import socket
import sys
import os
import serial
import time
import logging
from datetime import datetime
import math
import json

import sys
import glob
import time
import serial
import binascii
from pyzabbix import ZabbixMetric, ZabbixSender

# logging
global logging
logging.basicConfig(level=logging.INFO, 
                                format='%(asctime)s %(levelname)s %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
            logger.debug("%s int:%s raw:%s" % ("180",isk, data_hex))
            return 0

        # extract reading from position start: 34 length: 10 (for 1.8.0.)
        hex_value = data_hex[position+pos:position+pos+length]
        
        # convert to integer, check range  
        obis_value = hexstr2signedint(hex_value)
        return obis_value

def open_port(port):
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

        return ser

def readPort(port,ser):

        data_hex = ''
        reading_ok = False
        try:
                # read n chars, change that in case it's too short
                while (1):
                        data_raw = ser.read(50)

                        # find start escape sequence: 1b1b1b1b0101010176
                        if binascii.hexlify(data_raw).find(b"1b1b1b1b0101010176") >= 0 :
                                data_raw += ser.read(750) #lenght is 792
                                reading_ok = True 
                                break # found enough data, stop reading serial port
        except serial.serialutil.SerialException as e:
                reading_ok = False
                logger.debug("Error reading serial port: %s" % (e,))
                print("Error reading serial port: ", e)

        # convert reading to hex:
        data_hex = binascii.hexlify(data_raw)

        if reading_ok:
                # tested with eHZ-IW8E2Axxx
                isk = parseSML(data_hex,b'0100000009ff',34,8) 
                counter = float(float(parseSML(data_hex,b'0100010800ff',34,16))/100)
                return (port,isk,counter)
        else:
                logger.error("unable to find sml message")
                raise Exception("DataError")


########################################################################
# MAIN          

if len(sys.argv) > 1:
    ports = sys.argv[1:]
else:
    ports = glob.glob('/dev/ttyUSB*')

descriptors=dict()

for port in ports:
    descriptors[port] = open_port(port)

zabbix_sender = ZabbixSender()
hostname = socket.gethostname()
cycle_time = 120

last_value=dict()

last_discovery = 0

while True:
    try:
        metrics=[]
        discovery = []
        
        for port,ser in descriptors.items():
           (port,isk,counter) = readPort(port,ser)
           discovery.append({"{#POWER_METER}" : isk})

           item_name='power_meter[%s]' % isk
           item_value='%0.4f' % counter
           metrics.append(ZabbixMetric(hostname,item_name,item_value))
           logger.info("%s : %s = %s" % (port,item_name,item_value))

           if isk in last_value:
               item_name='power_meter[%s,current]' % isk
               time_elapsed = time.time() - last_value[isk]["time"]
               item_value='%0.4f' % float(float(float(counter - float(last_value[isk]["value"]))/time_elapsed) * 3600)
               metrics.append(ZabbixMetric(hostname,item_name,item_value))
               logger.info("%s : %s = %s" % (port,item_name,item_value))
           
           last_value[isk] = { "time": time.time() , "value" : counter }
    
        if time.time() - last_discovery > 9600:
            discovery_key = "power_meter.discovery"
            disovery_value = json.dumps({"data": discovery})
            metrics.append(ZabbixMetric(hostname,discovery_key,disovery_value))
            logger.info("%s = %s" % (discovery_key,disovery_value))
            last_discovery = time.time()

        result = zabbix_sender.send(metrics)
        if result.failed > 0:
            logger.error("failed to sent %s zabbix items: %s" % (len(metrics),result))
        else:
            logger.info("sucessfully sent %s zabbix items" % len(metrics))

        time.sleep(cycle_time)
    except Exception as e:
        logger.error("Fatal error in main loop", exc_info=True)
        descriptors=dict()
        for port in ports:
            descriptors[port] = open_port(port)


