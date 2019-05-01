#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import logging
import platform
import psutil
import socket
import os

import paho.mqtt.client as mqtt #import the client1
import time

import sys
import uptime

from autopial_lib.thread_worker import AutopialWorker
from autopial_lib.config_driver import ConfigFile

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
steam_handler = logging.StreamHandler()
stream_formatter = logging.Formatter('%(asctime)s|%(levelname)08s | %(message)s')
steam_handler.setFormatter(stream_formatter)
logger.addHandler(steam_handler)



class SystemWorker(AutopialWorker):
    def __init__(self, mqtt_client, time_sleep):
        AutopialWorker.__init__(self, mqtt_client, time_sleep, logger=logger)

    def run(self):
        logger.info("SystemWorker thread starts")
        while self.wait():
            self.get_system_data()
        logger.info("SystemWorker thread ends")

    def get_system_data(self):
        topic = "autopial/system/hostname"
        value = socket.getfqdn()
        self.publish(topic, value)

        topic = "autopial/system/boottime"
        value = uptime.boottime().isoformat()
        self.publish(topic, value)

        topic = "autopial/system/cpu"
        value = {
            "usage": psutil.cpu_percent(interval=1),
            "frequency": psutil.cpu_freq()[0],
            "vcpu": psutil.cpu_count(),
        }
        self.publish(topic, value)

        topic = "autopial/system/ram"
        data = psutil.virtual_memory()
        value = {
            "free": data.available,
            "total": data.total,
            "used": data.used,
            "usage": float(data.used) / float(data.total) * 100.0
        }
        self.publish(topic, value)

        topic = "autopial/system/swap"
        data = psutil.swap_memory()
        value = {
            "free": data.free,
            "total": data.total,
            "used": data.used,
            "usage": float(data.used) / float(data.total) * 100.0
        }
        self.publish(topic, value)

        return

class BandwidthWorker(AutopialWorker):
    def __init__(self, mqtt_client, time_sleep):
        AutopialWorker.__init__(self, mqtt_client, time_sleep, logger=logger)
        self.__previous_rx = None
        self.__previous_tx = None
        self.__previous_ts = None

    def run(self):
        logger.info("BandwidthWorker thread starts")
        while self.wait():
            self.get_network_data()
        logger.info("BandwidthWorker thread ends")

    def get_bytes(self, t, iface):
        with open('/sys/class/net/' + iface + '/statistics/' + t + '_bytes', 'r') as f:
            data = f.read();
            return int(data)

    def get_network_data(self, iface="enp0s3"):
        current_ts = time.time()
        current_tx = self.get_bytes('tx', iface)
        current_rx = self.get_bytes('rx', iface)

        if self.__previous_rx is not None and self.__previous_tx is not None:
            delta_ts = current_ts - self.__previous_ts
            tx_speed = (current_tx - self.__previous_tx) / delta_ts
            rx_speed = (current_rx - self.__previous_rx) / delta_ts

            topic = "autopial/system/network/bandwidth"
            value = {
                "iface": iface,
                "rx_speed": rx_speed,
                "tx_speed": tx_speed,
            }
            self.publish(topic, value)

        self.__previous_rx = current_rx
        self.__previous_tx = current_tx
        self.__previous_ts = current_ts

class PingWorker(AutopialWorker):
    def __init__(self, mqtt_client, time_sleep):
        AutopialWorker.__init__(self, mqtt_client, time_sleep, logger=logger)

    def run(self):
        logger.info("PingWorker thread starts")
        while self.wait():
            self.ping_networks()
        logger.info("PingWorker thread ends")

    def ping(self, hostname):
        giveFeedback = True

        if platform.system() == "Windows":
            response = os.system("ping " + hostname + " -n 1")
        else:
            response = os.system("ping -c 1 " + hostname)

        return True if response == 0 else False

    def ping_networks(self):
        topic = "autopial/system/network/ping/internet"
        value = self.ping('8.8.8.8')
        self.publish(topic, value)

        topic = "autopial/system/network/ping/pixussi"
        value = self.ping('192.168.1.56')
        self.publish(topic, value)
        pass



def get_sysmon():
    sysmon_data = {}

    system, node, release, version, machine, processor = platform.uname()
    #mqtt_client.publish("autopial/system/name", node)

    return

    sysmon_data["filesystem"] = []
    for part in psutil.disk_partitions():
        fs_data = {
            "mountpoint": part.mountpoint,
            "device": part.device,
            "fstype": part.fstype,
        }
        tmp = psutil.disk_usage(part.mountpoint)
        fs_data["free"] = tmp.free
        fs_data["total"] = tmp.total
        fs_data["used"] = tmp.used
        fs_data["usage"] = float(tmp.used) / float(tmp.total) * 100.0

        sysmon_data["filesystem"].append(fs_data)

    return sysmon_data

if __name__ == '__main__':
    cfg = ConfigFile("autopial-system.cfg", logger=logger)
    try:
        system_publish_every = cfg.get("workers", "SystemWorker", "publish_every")
        bandwidth_publish_every = cfg.get("workers", "BandwidthWorker", "publish_every")
        ping_publish_every = cfg.get("workers", "PingWorker", "publish_every")
    except BaseException as e:
        logger.error("Invalid config file: {}".format(e))
        sys.exit(1)


    worker_system = SystemWorker("SystemWorker", time_sleep=system_publish_every)
    worker_system.start()

    worker_bandwidth = BandwidthWorker("BandwidthWorker", time_sleep=bandwidth_publish_every)
    worker_bandwidth.start()

    worker_ping = PingWorker("PingWorker", time_sleep=ping_publish_every)
    worker_ping.start()

    try:
        while 1:
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        worker_system.stop()
        worker_bandwidth.stop()
        worker_ping.stop()


