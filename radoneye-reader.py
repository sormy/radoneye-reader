#!/usr/bin/env python3

import datetime
import json
import logging
import os
import socket
import sys
import time
import paho.mqtt.client as mqtt
from pygatt import GATTToolBackend
from argparse import ArgumentParser
from struct import unpack
from string import Template


class RadonEyeReader:
    SUB_SENSOR_DATA = "00001525-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_SENSOR_DATA = 0x002A
    COMMAND_SENSOR_DATA = bytearray([0x40])
    MTU_DEFAULT = 507

    def __init__(self, logger, adapter, addr, timeout):
        self.device = None
        self.logger = logger
        self.adapter = adapter
        self.addr = addr
        self.timeout = timeout

    def read_short(self, data, start):
        return unpack("<H", data[slice(start, start + 2)])[0]

    def read_str(self, data, start, length):
        return data[slice(start, start + length)].decode()

    def to_pci_l(self, value_bq_m3):
        return round(value_bq_m3 / 37, 2)

    def parse_raw_value(self, data):
        timestamp = str(datetime.datetime.now())
        serial = self.read_str(data, 8, 3) + self.read_str(data, 2, 6) + self.read_str(data, 11, 4)
        model = self.read_str(data, 16, 6)
        vendor = "Ecosense"
        device = "RadonEye"
        version = self.read_str(data, 22, 6)
        latest_bq_m3 = self.read_short(data, 33)
        latest_pci_l = self.to_pci_l(latest_bq_m3)
        day_avg_bq_m3 = self.read_short(data, 35)
        day_avg_pci_l = self.to_pci_l(day_avg_bq_m3)
        month_avg_bq_m3 = self.read_short(data, 37)
        month_avg_pci_l = self.to_pci_l(month_avg_bq_m3)
        peak_bq_m3 = self.read_short(data, 51)
        peak_pci_l = self.to_pci_l(peak_bq_m3)

        return {
            "timestamp": timestamp,
            "serial": serial,
            "address": self.addr,
            "vendor": vendor,
            "model": model,
            "version": version,
            "device": device,
            "latest_bq_m3": latest_bq_m3,
            "latest_pci_l": latest_pci_l,
            "day_avg_bq_m3": day_avg_bq_m3,
            "day_avg_pci_l": day_avg_pci_l,
            "month_avg_bq_m3": month_avg_bq_m3,
            "month_avg_pci_l": month_avg_pci_l,
            "peak_bq_m3": peak_bq_m3,
            "peak_pci_l": peak_pci_l,
        }

    def connect(self):
        self.device = self.adapter.connect(self.addr, timeout=self.timeout)
        self.device.exchange_mtu(self.MTU_DEFAULT)

    def subscribe(self, callback):
        def handle_sensor(handle, raw_data):
            try:
                data = self.parse_raw_value(raw_data)
                self.logger.info("device {}: data (hex): {}".format(self.addr, raw_data.hex()))
                self.logger.info("device {}: data: {}".format(self.addr, json.dumps(data)))
                callback(None, data)
            except Exception as error:
                self.logger.error("device {}: data processing error: {}".format(self.addr, error))
                callback(error, None)

        self.device.subscribe(
            self.SUB_SENSOR_DATA,
            callback=handle_sensor,
            indication=False,
            wait_for_response=False,
        )

    def unsubscribe(self):
        self.device.unsubscribe(self.SUB_SENSOR_DATA)

    def request(self):
        self.device.char_write_handle(
            self.CHARACTERISTIC_SENSOR_DATA, self.COMMAND_SENSOR_DATA, wait_for_response=False
        )

    def read_sensor_data(self):
        try:
            self.adapter.start()

            result_data = None
            result_error = None
            completed = False

            def handle_sensor_data(error, data):
                nonlocal completed, result_data, result_error
                result_data = data
                result_error = error
                completed = True

            self.connect()
            self.subscribe(handle_sensor_data)
            self.request()

            while not completed:
                time.sleep(1)

            self.unsubscribe()

            if result_error is not None:
                raise result_error

            return result_data
        finally:
            self.adapter.stop()


class RadonEyeReaderApp:
    DISCOVERY_EVENT_TEMPLATE = {
        "name": "$vendor $model $serial $attr",
        "unit_of_measurement": "$unit",
        "value_template": "{{ value }}",
        "state_class": "measurement",
        "state_topic": "$state_topic/$state_name",
        "unique_id": "$vendor-$model-$serial-$attr",
        "icon": "mdi:radioactive",
        "device": {
            "identifiers": "$vendor-$model-$serial",
            "name": "$vendor $model $serial",
            "model": "$model",
            "manufacturer": "$vendor",
        },
    }

    DISCOVERY_ATTRIBUTES = [
        {"id": "latest_pci_l", "name": "Latest", "unit": "pCi/L"},
        {"id": "day_avg_pci_l", "name": "DayAvg", "unit": "pCi/L"},
        {"id": "month_avg_pci_l", "name": "MonthAvg", "unit": "pCi/L"},
        {"id": "peak_pci_l", "name": "Peak", "unit": "pCi/L"},
    ]

    def __init__(self):
        self.args = self.parse_args()
        self.logger = logging.getLogger()
        self.adapter = GATTToolBackend()
        self.mqttc = mqtt.Client()

        if self.args.debug:
            logging.basicConfig(level=logging.DEBUG)

    def parse_args(self):
        parser = ArgumentParser(description="Reads Ecosense RadonEye device sensor data")
        parser.add_argument("addresses", metavar="addr", nargs="+", help="device address")
        parser.add_argument("--timeout", type=int, default=5, help="device connect timeout")
        parser.add_argument("--retries", type=int, default=5, help="device read attempt count")
        parser.add_argument("--debug", action="store_true", help="debug mode")
        parser.add_argument("--daemon", action="store_true", help="run continuosly")
        parser.add_argument(
            "--mqtt", action="store_true", help="enable MQTT device state publishing"
        )
        parser.add_argument(
            "--discovery",
            action="store_true",
            help="enable MQTT home assistant discovery event publishing",
        )
        parser.add_argument("--mqtt-hostname", type=str, default="localhost", help="MQTT hostname")
        parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT port")
        parser.add_argument("--mqtt-username", type=str, help="MQTT username")
        parser.add_argument("--mqtt-password", type=str, help="MQTT password")
        parser.add_argument("--mqtt-ca-cert", type=str, help="MQTT CA cert")
        parser.add_argument(
            "--device-topic",
            type=str,
            default="radon_eye/{hostname}/devices/{vendor}/{model}/{serial}",
            help="MQTT device state topic",
        )
        parser.add_argument(
            "--discovery-topic",
            type=str,
            default="homeassistant/sensor",
            help="MQTT home assistant discovery topic",
        )
        parser.add_argument("--device-retain", action="store_true", help="retain device events")
        parser.add_argument(
            "--discovery-retain", action="store_true", help="retain discovery events"
        )
        parser.add_argument(
            "--interval", type=int, default=5 * 60, help="device poll interval in seconds"
        )
        parser.add_argument(
            "--expire-after",
            type=int,
            help="Defines the number of seconds after the sensor's state expires, if it's not updated",
        )
        parser.add_argument(
            "--force-update",
            action="store_true",
            help="Sends update events even if the value hasn't changed",
        )

        args = parser.parse_args()

        args.addresses = args.addresses if type(args.addresses) is list else [args.addresses]

        if not args.mqtt_username and "MQTT_USERNAME" in os.environ:
            args.mqtt_username = os.environ["MQTT_USERNAME"]

        if not args.mqtt_password and "MQTT_PASSWORD" in os.environ:
            args.mqtt_password = os.environ["MQTT_PASSWORD"]

        return args

    def mqtt_init(self):
        if self.args.mqtt:
            if self.args.debug:
                self.mqttc.enable_logger()

            if self.args.mqtt_username is not None:
                self.mqttc.username_pw_set(self.args.mqtt_username, self.args.mqtt_password)

            if self.args.mqtt_ca_cert is not None:
                self.mqttc.tls_set(ca_certs=self.args.mqtt_ca_cert)

            self.mqttc.connect_async(self.args.mqtt_hostname, self.args.mqtt_port, 60)

            self.mqttc.loop_start()

    def publish_device_event(self, data):
        device_topic = self.args.device_topic.format(**data, hostname=socket.gethostname())

        for key, value in data.items():
            self.mqttc.publish(device_topic + "/" + key, value, retain=self.args.device_retain)

    def publish_discovery_event(self, data):
        device_topic = self.args.device_topic.format(**data, hostname=socket.gethostname())

        for attr in self.DISCOVERY_ATTRIBUTES:
            discovery_topic = (
                self.args.discovery_topic
                + "/{vendor}-{model}-{serial}/{vendor}-{model}-{serial}-{attr}/config".format(
                    **data, attr=attr.get("name")
                )
            )

            event_template = self.DISCOVERY_EVENT_TEMPLATE.copy()
            if self.args.force_update:
                event_template.update({"force_update": "true"})
            if self.args.expire_after:
                event_template.update({"expire_after": self.args.expire_after})

            discovery_event = Template(json.dumps(event_template)).substitute(
                **data,
                attr=attr.get("name"),
                unit=attr.get("unit"),
                state_topic=device_topic,
                state_name=attr.get("id")
            )

            self.mqttc.publish(discovery_topic, discovery_event, retain=self.args.discovery_retain)

    def print_sensor_data(self, data):
        print("{}".format(json.dumps(data)))
        sys.stdout.flush()

    def handle_sensor_error(self, addr, error):
        print(
            "ERROR: device {}: unable to obtain sensor data due to error: {}".format(addr, error),
            file=sys.stderr,
        )
        sys.stderr.flush()

    def handle_device_event_error(self, addr, error):
        print(
            "ERROR: device {}: unable to publish device event data to MQTT due to error: {}".format(
                addr, error
            ),
            file=sys.stderr,
        )
        sys.stderr.flush()

    def handle_discovery_event_error(self, addr, error):
        print(
            "ERROR: device {}: unable to publish discovery event data to MQTT due to error: {}".format(
                addr, error
            ),
            file=sys.stderr,
        )
        sys.stderr.flush()

    def run(self):
        if self.args.mqtt:
            self.mqtt_init()

        while True:
            for addr in self.args.addresses:
                reader = RadonEyeReader(self.logger, self.adapter, addr, self.args.timeout)

                data = None

                attempt = self.args.retries
                while attempt != 0:
                    try:
                        data = reader.read_sensor_data()
                        attempt = 0
                        self.print_sensor_data(data)
                    except Exception as error:
                        self.handle_sensor_error(addr, error)
                        attempt = attempt - 1

                if self.args.mqtt and (data is not None):
                    if self.args.discovery:
                        try:
                            self.publish_discovery_event(data)
                        except Exception as error:
                            self.handle_discovery_event_error(addr, error)
                    try:
                        self.publish_device_event(data)
                    except Exception as error:
                        self.handle_device_event_error(addr, error)

            if self.args.daemon:
                time.sleep(self.args.interval)
            else:
                break

        if self.args.mqtt:
            self.mqttc.loop_stop()


def main():
    app = RadonEyeReaderApp()
    app.run()


if __name__ == "__main__":
    main()
