#!/usr/bin/env python3

import asyncio
import datetime
import json
import logging
import os
import socket
import sys
import traceback
import paho.mqtt.client as mqtt
from bleak import BleakClient
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from struct import unpack
from string import Template
import math


class RadonEyeParser:
    def read_short(self, data: bytearray, start: int) -> int:
        return unpack("<H", data[slice(start, start + 2)])[0]

    def read_str(self, data: bytearray, start: int, length: int) -> str:
        return data[slice(start, start + length)].decode()

    def to_pci_l(self, value_bq_m3: int) -> float:
        return round(value_bq_m3 / 37, 2)

    def parse_sensor_data(self, data: bytearray) -> dict:
        serial = self.read_str(data, 8, 3) + self.read_str(data, 2, 6) + self.read_str(data, 11, 4)
        model = self.read_str(data, 16, 6)
        version = self.read_str(data, 22, 6)
        latest_bq_m3 = self.read_short(data, 33)
        latest_pci_l = self.to_pci_l(latest_bq_m3)
        day_avg_bq_m3 = self.read_short(data, 35)
        day_avg_pci_l = self.to_pci_l(day_avg_bq_m3)
        month_avg_bq_m3 = self.read_short(data, 37)
        month_avg_pci_l = self.to_pci_l(month_avg_bq_m3)
        counts_current = self.read_short(data, 39)
        counts_previous = self.read_short(data, 41)
        counts_str = f"{counts_current}/{counts_previous}"
        uptime_minutes = self.read_short(data, 43)
        uptime_days = math.floor(uptime_minutes / (60 * 24))
        uptime_hours = math.floor(uptime_minutes % (60 * 24) / 60)
        uptime_mins = uptime_minutes % 60
        uptime_str = f"{uptime_days}d {uptime_hours:02}:{uptime_mins:02}"
        peak_bq_m3 = self.read_short(data, 51)
        peak_pci_l = self.to_pci_l(peak_bq_m3)

        return {
            "serial": serial,
            "model": model,
            "version": version,
            "latest_bq_m3": latest_bq_m3,
            "latest_pci_l": latest_pci_l,
            "day_avg_bq_m3": day_avg_bq_m3,
            "day_avg_pci_l": day_avg_pci_l,
            "month_avg_bq_m3": month_avg_bq_m3,
            "month_avg_pci_l": month_avg_pci_l,
            "peak_bq_m3": peak_bq_m3,
            "peak_pci_l": peak_pci_l,
            "counts_current": counts_current,
            "counts_previous": counts_previous,
            "counts_str": counts_str,
            "uptime_minutes": uptime_minutes,
            "uptime_str": uptime_str,
        }


class RadonEyeReader:
    UUID_COMMAND = "00001524-0000-1000-8000-00805f9b34fb"
    UUID_CURRENT = "00001525-0000-1000-8000-00805f9b34fb"

    COMMAND_CURRENT = 0x40

    VENDOR = "Ecosense"
    DEVICE = "RadonEye"

    def __init__(self, address: str, connect_timeout: int, read_timeout: int):
        self.address = address
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.parser = RadonEyeParser()

    def decode_sensor_data(self, data: bytearray):
        return {
            "timestamp": str(datetime.datetime.now()),
            "vendor": self.VENDOR,
            "device": self.DEVICE,
            "address": self.address,
            **self.parser.parse_sensor_data(data),
        }

    async def read_sensor_data(self) -> dict:
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def callback(sender: int, data: bytearray):
            future.set_result(self.decode_sensor_data(data))

        async with BleakClient(self.address, timout=self.connect_timeout) as client:
            await client.start_notify(self.UUID_CURRENT, callback)
            await client.write_gatt_char(self.UUID_COMMAND, bytearray([self.COMMAND_CURRENT]))
            return await asyncio.wait_for(future, timeout=self.read_timeout)


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
        if self.args.debug:
            logging.basicConfig(level=logging.DEBUG)

    def parse_args(self):
        parser = ArgumentParser(
            description="Reads Ecosense RadonEye device sensor data",
            formatter_class=ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument("addresses", metavar="addr", nargs="+", help="device address")
        parser.add_argument(
            "--connect-timeout", type=int, default=10, help="device connect timeout in seconds"
        )
        parser.add_argument(
            "--read-timeout", type=int, default=5, help="device sendor data read timeout in seconds"
        )
        parser.add_argument(
            "--reconnect-delay", type=int, default=1, help="device reconnect delay in seconds"
        )
        parser.add_argument("--attempts", type=int, default=5, help="device read attempt count")
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
            "--discovery-delay",
            type=int,
            default=1,
            help="Delay after discovery event before sending device event",
        )
        parser.add_argument(
            "--interval", type=int, default=5 * 60, help="device poll interval in seconds"
        )
        parser.add_argument(
            "--expire-after",
            type=int,
            help=(
                "Defines the number of seconds after the sensor's state expires, if it's not"
                " updated"
            ),
        )
        parser.add_argument(
            "--force-update",
            action="store_true",
            help="Sends update events even if the value hasn't changed",
        )
        parser.add_argument(
            "--restart-bluetooth",
            action="store_true",
            help="Try to restart bluetooth stack on bluetooth error",
        )
        parser.add_argument(
            "--restart-bluetooth-delay",
            type=int,
            default=10,
            help="Delay in seconds after bluetooth stack has been restarted",
        )
        parser.add_argument(
            "--restart-bluetooth-cmd",
            type=str,
            default="service bluetooth restart",
            help="Command to execute when bluetooth stack restart is needed",
        )

        args = parser.parse_args()

        args.addresses = args.addresses if isinstance(args.addresses, list) else [args.addresses]

        if not args.mqtt_username and "MQTT_USERNAME" in os.environ:
            args.mqtt_username = os.environ["MQTT_USERNAME"]

        if not args.mqtt_password and "MQTT_PASSWORD" in os.environ:
            args.mqtt_password = os.environ["MQTT_PASSWORD"]

        return args

    def mqtt_init(self):
        if self.args.mqtt:
            self.mqttc = mqtt.Client("radoneye_{hostname}".format(hostname=socket.gethostname()))

            if self.args.debug:
                self.mqttc.enable_logger()

            if self.args.mqtt_username is not None:
                self.mqttc.username_pw_set(self.args.mqtt_username, self.args.mqtt_password)

            if self.args.mqtt_ca_cert is not None:
                self.mqttc.tls_set(ca_certs=self.args.mqtt_ca_cert)

            self.mqttc.connect_async(self.args.mqtt_hostname, self.args.mqtt_port)

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
                state_name=attr.get("id"),
            )

            self.mqttc.publish(discovery_topic, discovery_event, retain=self.args.discovery_retain)

    def print_sensor_data(self, data):
        print("{}".format(json.dumps(data)), flush=True)

    def str_err(self, error: Exception):
        type_str = type(error).__name__
        msg_str = str(error)
        return f"[{type_str}]: {msg_str}" if msg_str else f"[{type_str}]"

    async def handle_sensor_error(self, addr, error, attempt):
        print(
            f"ERROR: DEV {addr}: unable to obtain sensor data from {attempt} attempt due to error:"
            f" {self.str_err(error)}",
            file=sys.stderr,
            flush=True,
        )

        # after last failed attempt there is no point to try to wait or restart bluetooth
        if attempt < self.args.attempts:
            # restart bluetooth before last attempt if enabled
            if attempt == self.args.attempts - 1 and self.args.restart_bluetooth:
                self.restart_bluetooth_stack()
                await asyncio.sleep(self.args.restart_bluetooth_delay)
            # otherwise just wait
            else:
                await asyncio.sleep(self.args.reconnect_delay)

    def handle_device_event_error(self, addr, error):
        print(
            f"ERROR: DEV {addr}: unable to publish device event data to MQTT due to error:"
            f" {self.str_err(error)}",
            file=sys.stderr,
            flush=True,
        )

    def handle_discovery_event_error(self, addr, error):
        print(
            f"ERROR: DEV {addr}: unable to publish discovery event data to MQTT due to error:"
            f" {self.str_err(error)}",
            file=sys.stderr,
            flush=True,
        )

    def restart_bluetooth_stack(self):
        print(
            "WARNING: Restarting bluetooth stack...",
            file=sys.stderr,
            flush=True,
        )
        os.system(self.args.restart_bluetooth_cmd)

    async def run(self):
        if self.args.mqtt:
            self.mqtt_init()

        while True:
            for address in self.args.addresses:
                print(
                    f"INFO: DEV {address}: reading device sensor data", file=sys.stderr, flush=True
                )

                reader = RadonEyeReader(address, self.args.connect_timeout, self.args.read_timeout)

                data = None

                attempt = 1
                while attempt > 0 and attempt <= self.args.attempts:
                    try:
                        data = await asyncio.wait_for(
                            reader.read_sensor_data(),
                            timeout=self.args.connect_timeout + self.args.read_timeout,
                        )
                        attempt = 0
                    except Exception as error:
                        await self.handle_sensor_error(address, error, attempt)
                        if self.args.debug:
                            traceback.print_exc(file=sys.stderr)
                        attempt = attempt + 1

                if data is not None:
                    self.print_sensor_data(data)

                if data is not None and self.args.mqtt and self.args.discovery:
                    try:
                        self.publish_discovery_event(data)
                        await asyncio.sleep(self.args.discovery_delay)
                    except Exception as error:
                        self.handle_discovery_event_error(address, error)

                if data is not None and self.args.mqtt:
                    try:
                        self.publish_device_event(data)
                    except Exception as error:
                        self.handle_device_event_error(address, error)

            if self.args.daemon:
                print(
                    f"INFO: sleeping for {self.args.interval} sec...",
                    file=sys.stderr,
                    flush=True,
                )
                await asyncio.sleep(self.args.interval)
            else:
                break

        if self.args.mqtt:
            self.mqttc.loop_stop()


async def main():
    await RadonEyeReaderApp().run()


if __name__ == "__main__":
    asyncio.run(main())
