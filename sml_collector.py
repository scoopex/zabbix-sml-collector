#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
#
########################################################################
#
# SML Collector
#
########################################################################

import socket
import os
import logging
import json
import argparse
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
logger.setLevel(logging.INFO)


# ------------- #
# settings      #
# ------------- #

# hex string to signed integer, inkl. range check http://stackoverflow.com/a/6727975 
def hexstr2signedint(hexval):
    uintval = int(hexval, 16)
    if uintval > 0x7FFFFFFF:  # > 2147483647
        uintval -= 0x100000000  # -= 4294967296
    return uintval


# parse hex string from USB serial stream and extract values for obis_id
def parseSMLInteger(data_hex, obis_string, pos, length):
    obis_value = 0
    # find position of OBIS-Kennzahl
    position = data_hex.find(obis_string)

    # break
    if position <= 0:
        logger.error("unable to find %s raw:%s" % (obis_string,data_hex))
        return 0

    # extract reading from position start: 34 length: 10 (for 1.8.0.)
    hex_value = data_hex[position + pos:position + pos + length]

    # convert to integer, check range
    logger.debug("Parsed Value after '%s' : >>>%s<<<" % (obis_string,hex_value))
    obis_value = hexstr2signedint(hex_value)
    return obis_value

# parse hex string from USB serial stream and extract values for obis_id
def parseSMLUnsigned(data_hex, obis_string, pos, length):
    obis_value = 0
    # find position of OBIS-Kennzahl
    position = data_hex.find(obis_string)

    # break
    if position <= 0:
        logger.error("unable to find %s raw:%s" % (obis_string,data_hex))
        return 0

    # extract reading from position start: 34 length: 10 (for 1.8.0.)
    hex_value = data_hex[position + pos:position + pos + length]

    #obis_value = int(hex_value,16)
    logger.debug("Parsed Value after '%s' : >>>%s<<<" % (obis_string,hex_value))
    obis_value = int.from_bytes(hex_value, byteorder='little', signed=False)

    return obis_value


def open_port(port):
    # eHZ-Datentelegramme können mittels eines optischen Auslesekopfs nach DIN EN 62056-21
    # z. B. über die serielle Schnittstelle eines PC ausgelesen werden.
    # Einstellung: bit/s= 9600, Datenbit = 7, Parität = gerade, Stoppbits = 1, Flusssteuerung = kein.
    ser = serial.Serial(
        port=port,  # '/dev/ttyUSB1',
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


def readPort(port, ser):
    data_hex = ''
    reading_ok = False

    # read to end of file
    nr_of_waiting_bytes=ser.in_waiting
    ser.read(nr_of_waiting_bytes)
    logger.debug("read %s bytes to move to end" % nr_of_waiting_bytes)


    try:
        # read n chars, change that in case it's too short
        while (1):
            data_raw = ser.read(50)

            # find start escape sequence: 1b1b1b1b0101010176
            if binascii.hexlify(data_raw).find(b"1b1b1b1b0101010176") >= 0:
                data_raw += ser.read(792)  # lenght is 792
                reading_ok = True
                break  # found enough data, stop reading serial port
    except serial.serialutil.SerialException as e:
        reading_ok = False
        logger.debug("Error reading serial port: %s" % e)

    # convert reading to hex:
    data_hex = binascii.hexlify(data_raw)
    logger.debug("HEX DATA: >>>%s<<<" % data_hex)

    if reading_ok:
        # tested with eHZ-IW8E2Axxx
        isk = str(parseSMLInteger(data_hex, b'0100000009ff', 34, 8))
        counter = float((parseSMLInteger(data_hex, b'0100010800ff', 34, 16)) / float(10))
        # 0101621b5200550000023d
        ampere = float((parseSMLUnsigned(data_hex, b'0100100700ff', 12+15, 8)))
        return (port, isk, counter, ampere)
    else:
        logger.error("unable to find sml message")
        raise Exception("DataError")


########################################################################
# MAIN          


parser = argparse.ArgumentParser(
    description='Monitoring daemon for sml data'
)

parser.add_argument(
    '--debug',
    help='show debug info',
    action='store_true', )
parser.add_argument(
    '--interval',
    help='intervall',
    type=int,
    default=120)


args, remaining_args = parser.parse_known_args()


if len(remaining_args) > 0:
    ports = remaining_args
else:
    ports = glob.glob('/dev/ttyUSB*')


if args.debug:
    logger.setLevel(logging.DEBUG)

descriptors = dict()

for port in ports:
    descriptors[port] = open_port(port)

zabbix_sender = ZabbixSender()
hostname = socket.gethostname()

last_value = dict()

last_discovery = 0

mappings_json = os.path.realpath(os.path.dirname(os.path.realpath(__file__))) + "/mappings.json"

if os.path.exists(mappings_json):
    with open(mappings_json) as f:
        discovery_desc = json.load(f)
else:
    logger.warning("no %s, no mappings" % mappings_json)
    discovery_desc = {}

while True:
    try:
        metrics = []
        discovery = []

        for port, ser in descriptors.items():
            (port, isk, counter, ampere) = readPort(port, ser)

            # Discovery
            if isk in discovery_desc:
                desc = discovery_desc[isk]
            else:
                desc = isk
            discovery.append({"{#POWER_METER}": isk, "{#POWER_DESC}": desc})

            # Counter WH
            item_name = 'power_meter[%s,counter_wh]' % isk
            item_value = '%0.4f' % counter
            metrics.append(ZabbixMetric(hostname, item_name, item_value))
            logger.info("[%-20s] : %s = %s" % (desc, item_name, item_value))

            # Ampere
            item_name = 'power_meter[%s,current_ampere]' % isk
            item_value = '%0.4f' % ampere
            metrics.append(ZabbixMetric(hostname, item_name, item_value))
            logger.info("[%-20s] : %s = %s" % (desc, item_name, item_value))


            if isk in last_value:
                item_name = 'power_meter[%s,interval_wh]' % isk
                time_elapsed = time.time() - last_value[isk]["time"]
                #item_value = '%0.4f' % float(float(float(counter - float(last_value[isk]["value"])) / float(time_elapsed)) * 3600)
                item_value = '%0.4f' % float(float(counter - float(last_value[isk]["value"])))
                metrics.append(ZabbixMetric(hostname, item_name, item_value))
                logger.info("[%-20s] : %s = %s" % (desc, item_name, item_value))

            last_value[isk] = {"time": time.time(), "value": counter}

        if time.time() - last_discovery > 9600:
            discovery_key = "power_meter.discovery"
            disovery_value = json.dumps({"data": discovery})
            metrics.append(ZabbixMetric(hostname, discovery_key, disovery_value))
            logger.info("%s = %s" % (discovery_key, disovery_value))
            last_discovery = time.time()

        result = zabbix_sender.send(metrics)
        if result.failed > 0:
            logger.error("failed to sent %s zabbix items: %s" % (len(metrics), result))
        else:
            logger.info("sucessfully sent %s zabbix items" % len(metrics))

        time.sleep(args.interval)
    except Exception as e:
        logger.error("Fatal error in main loop", exc_info=True)
        descriptors = dict()
        for port in ports:
            descriptors[port] = open_port(port)
