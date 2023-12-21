#!/usr/bin/env python3

import asyncio
from bleak import BleakClient
from argparse import ArgumentParser


class RadonEyeBeeper:
    UUID_COMMAND = "00001524-0000-1000-8000-00805f9b34fb"

    COMMAND_BEEP = [0xA1, 0x11, 0x17, 0x0C, 0x0B, 0x01, 0x25, 0x28]

    async def beep(self, address, times):
        async with BleakClient(address) as client:
            for x in range(times or 1):
                await client.write_gatt_char(self.UUID_COMMAND, bytearray(self.COMMAND_BEEP))
                await asyncio.sleep(1)


async def main():
    parser = ArgumentParser(description="Triggers beep on Ecosense RadonEye device")
    parser.add_argument(
        "address", help="device address (like mac address on Linux and like UUID on macOS)"
    )
    parser.add_argument("--times", type=int, default=1, help="how many times to beep")
    args = parser.parse_args()

    beeper = RadonEyeBeeper()
    await beeper.beep(args.address, args.times)


if __name__ == "__main__":
    asyncio.run(main())
