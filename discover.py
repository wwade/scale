import asyncio

from bleak import BleakScanner


async def discover_acaia_scales():
    """Discover Acaia scales via Bluetooth LE."""
    print("Scanning for Bluetooth devices...")
    devices = await BleakScanner.discover(timeout=10.0)

    print(f"\nFound {len(devices)} devices:\n")

    acaia_devices = []
    for device in devices:
        # Acaia devices typically have names like "PROCHBT", "ACAIA", or "PYXIS"
        name = device.name or "Unknown"
        print(f"  {device.address} - {name}")

        if any(keyword in name.upper() for keyword in ["PROCH", "PR BT", "ACAIA", "PYXIS", "LUNAR", "PEARL"]):
            acaia_devices.append(device)
            print("    ^^^ Possible Acaia device!")

    if acaia_devices:
        print(f"\n\nFound {len(acaia_devices)} potential Acaia device(s):")
        for device in acaia_devices:
            print(f"  MAC: {device.address}")
            print(f"  Name: {device.name}")
            print()
    else:
        print("\nNo Acaia devices found. Make sure your scale is on and in pairing mode.")

    return acaia_devices

if __name__ == "__main__":
    asyncio.run(discover_acaia_scales())
