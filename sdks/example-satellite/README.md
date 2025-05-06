# Omi Bluetooth Wyoming Satellite
Creates a wyoming satellite that streams audio from an Omi device to a remote server.

## Usage

```bash
uv run python main.py --omi-mac <mac-address> --wake-uri <uri> --wake-word-name <name>
```

To scan for Omi devices and list them:
```bash
uv run python3 -c 'from omi.bluetooth import print_devices;print_devices()'
```


