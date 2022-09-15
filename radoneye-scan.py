#!/usr/bin/env python3

import asyncio
from bleak import BleakScanner


async def main():
    devices = await BleakScanner.discover()

    await asyncio.sleep(5)

    for device in devices:
        if device.name.startswith("FR:"):
            print(f"{device.address}: {device.name}")


asyncio.run(main())
