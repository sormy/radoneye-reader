#!/usr/bin/env python3

import asyncio
from binascii import hexlify
from struct import unpack
from bleak import BleakClient
from argparse import ArgumentParser

UUID_COMMAND = "00001524-0000-1000-8000-00805f9b34fb"
UUID_CURRENT = "00001525-0000-1000-8000-00805f9b34fb"
UUID_HISTORY = "00001526-0000-1000-8000-00805f9b34fb"

COMMAND_CURRENT = 0x40
COMMAND_HISTORY = 0x41


async def main():
    parser = ArgumentParser(description="Reads Ecosense RadonEye device raw sensor data")
    parser.add_argument(
        "address", help="device address (like mac address on Linux and like UUID on macOS)"
    )
    parser.add_argument(
        "--delay", type=int, default=10, help="delay to retrieve all history packets"
    )
    args = parser.parse_args()

    def to_pci_l(value_bq_m3):
        return round(value_bq_m3 / 37, 2)

    def read_short(data, start):
        return unpack("<H", data[slice(start, start + 2)])[0]

    def read_str(data, start, length):
        return data[slice(start, start + length)].decode()

    def decode_history_data(data: bytearray):
        command = data.pop(0)
        response_count = data.pop(0)
        response_no = data.pop(0)
        value_count = data.pop(0)
        values_bq_m3 = unpack("<" + "H" * (len(data) // 2), data)
        values_pci_l = [to_pci_l(x) for x in values_bq_m3]

        if command != COMMAND_HISTORY:
            print("hmm: expected command {} but found {}", COMMAND_HISTORY, command)
        if len(values_bq_m3) != value_count:
            print("hmm: expected value count {} but found {}", value_count, len(values_bq_m3))

        return {
            "command": command,
            "response_count": response_count,
            "response_no": response_no,
            "value_count": value_count,
            "values_bq_m3": values_bq_m3,
            "values_pci_l": values_pci_l,
        }

    def decode_current_data(data: bytearray):
        serial = read_str(data, 8, 3) + read_str(data, 2, 6) + read_str(data, 11, 4)
        model = read_str(data, 16, 6)
        version = read_str(data, 22, 6)
        latest_bq_m3 = read_short(data, 33)
        latest_pci_l = to_pci_l(latest_bq_m3)
        day_avg_bq_m3 = read_short(data, 35)
        day_avg_pci_l = to_pci_l(day_avg_bq_m3)
        month_avg_bq_m3 = read_short(data, 37)
        month_avg_pci_l = to_pci_l(month_avg_bq_m3)
        peak_bq_m3 = read_short(data, 51)
        peak_pci_l = to_pci_l(peak_bq_m3)

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
        }

    def current_callback(sender: int, data: bytearray):
        print(
            "[CURRENT]\nsender={}\nsize={}\nhex={}\nstr={}\ndecoded={}\n".format(
                sender, len(data), hexlify(data), data, decode_current_data(data)
            )
        )

    def history_callback(sender: int, data: bytearray):
        print(
            "[HISTORY]\nsender={}\nsize={}\nhex={}\ndecoded={}\n".format(
                sender, len(data), hexlify(data), decode_history_data(data)
            )
        )

    async with BleakClient(args.address) as client:
        await client.start_notify(UUID_CURRENT, current_callback)
        await client.start_notify(UUID_HISTORY, history_callback)
        await client.write_gatt_char(UUID_COMMAND, bytearray([COMMAND_CURRENT]))
        await client.write_gatt_char(UUID_COMMAND, bytearray([COMMAND_HISTORY]))
        await asyncio.sleep(args.delay)


if __name__ == "__main__":
    asyncio.run(main())
