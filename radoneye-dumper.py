#!/usr/bin/env python3

import asyncio
from binascii import hexlify
from struct import unpack
from bleak import BleakClient
from argparse import ArgumentParser
import math


class RadonEyeDumper:
    UUID_COMMAND = "00001524-0000-1000-8000-00805f9b34fb"
    UUID_CURRENT = "00001525-0000-1000-8000-00805f9b34fb"
    UUID_HISTORY = "00001526-0000-1000-8000-00805f9b34fb"

    COMMAND_CURRENT = 0x40
    COMMAND_HISTORY = 0x41

    def __init__(self, timeout) -> None:
        self.timeout = timeout
        pass

    def to_pci_l(self, value_bq_m3):
        return round(value_bq_m3 / 37, 2)

    def read_short(self, data, start):
        return unpack("<H", data[slice(start, start + 2)])[0]

    def read_str(self, data, start, length):
        return data[slice(start, start + length)].decode()

    def decode_history_data(self, data: bytearray):
        command = data.pop(0)
        page_count = data.pop(0)
        page_no = data.pop(0)
        value_count = data.pop(0)
        values_bq_m3 = unpack("<" + "H" * (len(data) // 2), data)
        values_pci_l = [self.to_pci_l(x) for x in values_bq_m3]

        if command != self.COMMAND_HISTORY:
            print("hmm: expected command {} but found {}", self.COMMAND_HISTORY, command)
        if len(values_bq_m3) != value_count:
            print("hmm: expected value count {} but found {}", value_count, len(values_bq_m3))

        if page_count == page_no:
            self.history_done = True

        return {
            "command": command,
            "page_count": page_count,
            "page_no": page_no,
            "value_count": value_count,
            "values_bq_m3": values_bq_m3,
            "values_pci_l": values_pci_l,
        }

    def decode_current_data(self, data: bytearray):
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

    async def dump(self, address):
        self.countdown = self.timeout
        self.history_done = False

        def current_callback(sender: int, data: bytearray):
            print(
                "[CURRENT]\nsender={}\nsize={}\nhex={}\nstr={}\ndecoded={}\n".format(
                    sender, len(data), hexlify(data), data, self.decode_current_data(data)
                )
            )

        def history_callback(sender: int, data: bytearray):
            print(
                "[HISTORY]\nsender={}\nsize={}\nhex={}\ndecoded={}\n".format(
                    sender, len(data), hexlify(data), self.decode_history_data(data)
                )
            )

        async with BleakClient(address) as client:
            await client.start_notify(self.UUID_CURRENT, current_callback)
            await client.start_notify(self.UUID_HISTORY, history_callback)
            await client.write_gatt_char(self.UUID_COMMAND, bytearray([self.COMMAND_CURRENT]))
            await client.write_gatt_char(self.UUID_COMMAND, bytearray([self.COMMAND_HISTORY]))
            while not self.history_done and self.countdown > 0:
                await asyncio.sleep(1)
                self.countdown -= 1


async def main():
    parser = ArgumentParser(description="Reads Ecosense RadonEye device raw sensor data")
    parser.add_argument(
        "address", help="device address (like mac address on Linux and like UUID on macOS)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="max wait time to retrieve status and all history packets",
    )
    args = parser.parse_args()

    dumper = RadonEyeDumper(args.timeout)
    await dumper.dump(args.address)


if __name__ == "__main__":
    asyncio.run(main())
