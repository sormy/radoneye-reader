# radoneye-reader

Ecosense RadonEye reader with MQTT and Home Assistant support with automatic discovery.

## Dependencies

Requires Python 3.x and has been tested to work well on macOS and Linux. Keep in mind, device
addresses are different between macOS (uuid like) and Linux (mac like).

Python `bleak` BLE library is used as the most stable, portable and easy installable (no complex
build toolchain is needed). If you wanted to check with `pygatt` then checkout version `v1.0.0`.

## Installation

### System-level

Example:

```sh
apt-get install git python3 python3-pip
mkdir -p /srv/
cd /srv/
git clone https://github.com/sormy/radoneye-reader.git
cd radoneye-reader
pip3 install -r requirements.txt
ln -sf /srv/radoneye-reader/radoneye-reader.py /usr/local/bin/radoneye-reader
ln -sf /srv/radoneye-reader/radoneye-scan.py /usr/local/bin/radoneye-scan
ln -sf /srv/radoneye-reader/radoneye-dumper.py /usr/local/bin/radoneye-dumper
```

Usage:

```sh
$ radoneye-reader ...
```

### Environment-level

Example:

```sh
apt-get install git python3 python3-pip
mkdir -p /srv/
cd /srv/
git clone https://github.com/sormy/radoneye-reader.git
cd radoneye-reader
python3 -m venv .
source bin/activate
pip3 install -r requirements.txt
deactivate
```

Usage:

```sh
$ /srv/radoneye-reader/bin/python3 /srv/radoneye-reader/radoneye-reader.py ...
```

## Usage

Discover hardware IDs for RadonEye devices (different for macOS and Linux):

```
$ ./radoneye-scan.py
```

All available options for reader itself:

```
$ ./radoneye-reader.py --help
usage: radoneye-reader.py [-h] [--connect-timeout CONNECT_TIMEOUT]
                          [--read-timeout READ_TIMEOUT]
                          [--reconnect-delay RECONNECT_DELAY] [--attempts ATTEMPTS]
                          [--debug] [--daemon] [--mqtt] [--discovery]
                          [--mqtt-hostname MQTT_HOSTNAME] [--mqtt-port MQTT_PORT]
                          [--mqtt-username MQTT_USERNAME]
                          [--mqtt-password MQTT_PASSWORD]
                          [--mqtt-ca-cert MQTT_CA_CERT] [--device-topic DEVICE_TOPIC]
                          [--discovery-topic DISCOVERY_TOPIC] [--device-retain]
                          [--discovery-retain] [--discovery-delay DISCOVERY_DELAY]
                          [--interval INTERVAL] [--expire-after EXPIRE_AFTER]
                          [--force-update] [--restart-bluetooth]
                          [--restart-bluetooth-delay RESTART_BLUETOOTH_DELAY]
                          [--restart-bluetooth-cmd RESTART_BLUETOOTH_CMD]
                          addr [addr ...]

Reads Ecosense RadonEye device sensor data

positional arguments:
  addr                  device address

options:
  -h, --help            show this help message and exit
  --connect-timeout CONNECT_TIMEOUT
                        device connect timeout in seconds (default: 10)
  --read-timeout READ_TIMEOUT
                        device sendor data read timeout in seconds (default: 5)
  --reconnect-delay RECONNECT_DELAY
                        device reconnect delay in seconds (default: 1)
  --attempts ATTEMPTS   device read attempt count (default: 5)
  --debug               debug mode (default: False)
  --daemon              run continuosly (default: False)
  --mqtt                enable MQTT device state publishing (default: False)
  --discovery           enable MQTT home assistant discovery event publishing
                        (default: False)
  --mqtt-hostname MQTT_HOSTNAME
                        MQTT hostname (default: localhost)
  --mqtt-port MQTT_PORT
                        MQTT port (default: 1883)
  --mqtt-username MQTT_USERNAME
                        MQTT username (default: None)
  --mqtt-password MQTT_PASSWORD
                        MQTT password (default: None)
  --mqtt-ca-cert MQTT_CA_CERT
                        MQTT CA cert (default: None)
  --device-topic DEVICE_TOPIC
                        MQTT device state topic (default:
                        radon_eye/{hostname}/devices/{vendor}/{model}/{serial})
  --discovery-topic DISCOVERY_TOPIC
                        MQTT home assistant discovery topic (default:
                        homeassistant/sensor)
  --device-retain       retain device events (default: False)
  --discovery-retain    retain discovery events (default: False)
  --discovery-delay DISCOVERY_DELAY
                        Delay after discovery event before sending device event
                        (default: 1)
  --interval INTERVAL   device poll interval in seconds (default: 300)
  --expire-after EXPIRE_AFTER
                        Defines the number of seconds after the sensor's state
                        expires, if it's not updated (default: None)
  --force-update        Sends update events even if the value hasn't changed (default:
                        False)
  --restart-bluetooth   Try to restart bluetooth stack on bluetooth error (default:
                        False)
  --restart-bluetooth-delay RESTART_BLUETOOTH_DELAY
                        Delay in seconds after bluetooth stack has been restarted
                        (default: 10)
  --restart-bluetooth-cmd RESTART_BLUETOOTH_CMD
                        Command to execute when bluetooth stack restart is needed
                        (default: service bluetooth restart)
```

Environment variables:

- `MQTT_USERNAME` - pass MQTT username to avoid exposing it in list of processes
- `MQTT_PASSWORD` - pass MQTT password to avoid exposing it in list of processes

Just read sensors as JSON to stdout:

```
./radoneye-reader.py <device1_addr> <device2_addr> <...>
```

Read continuosly and publish to MQTT with Home Assistant auto discovery:

```
./radoneye-reader.py --mqtt --discovery --daemon <device1_addr> <device2_addr> <...>
```

Dump detailed RadonEye sensor data (most for debugging purposes):

```
$ ./radoneye-dumper.py
usage: radoneye-dumper.py [-h] [--timeout TIMEOUT] address
```

RadonEye updates last radon level every 10 minutes, so reading sensor too often is not really
useful.

## Daemonization using systemd on Linux

Below is the example of naive quick setup with python modules installed in system under `root` user
and `radoneye-reader` running under `root` as well with MQTT and Home Assistant (Core) running on
the same host.

If you wanted to run it under different user with dedicated environment then look on Home Assistant
example: https://www.home-assistant.io/installation/linux#create-an-account

Install radoneye-reader as venv:

```sh
apt-get install git python3 python3-pip
mkdir -p /srv/
cd /srv/
git clone https://github.com/sormy/radoneye-reader.git
cd radoneye-reader
python3 -m venv .
source bin/activate
pip3 install -r requirements.txt
deactivate
```

Add service unit:

```sh
nano /etc/systemd/system/radoneye.service
```

with content:

```ini
[Unit]
Description=RadonEye sensor reader
After=network-online.target

[Service]
Type=simple
User=root
ExecStart=/srv/radoneye-reader/bin/python3 /srv/radoneye-reader/radoneye-reader.py \
  --mqtt --discovery --daemon <addr1> <addr2> <addr3>
Environment=MQTT_USERNAME=radoneye
Environment=MQTT_PASSWORD=secret

[Install]
WantedBy=multi-user.target
```

Enable service:

```sh
systemctl daemon-reload
systemctl enable radoneye
systemctl start radoneye
```

Check service status and logs:

```sh
systemctl status radoneye
journalctl -f -u radoneye
```

## Troubleshooting

Q: Radon level reads are the same every time until application is restarted on Linux.

A: Evaluate if you can use `--restart-bluetooth` option, otherwise disable bluez caching:

```
nano /etc/bluetooth/main.conf

[GATT]
Cache=no

systemctl bluetooth restart
```

## Inspiration

This script is inspired by these examples:

- https://community.home-assistant.io/t/radoneye-ble-interface/94962/121 (working code sample for
  the newest RD200N)
- https://github.com/merbanan/rtl_433/blob/master/examples/rtl_433_mqtt_hass.py (example of hass
  integration using mqtt)
- https://github.com/ceandre/radonreader (reader for older devices RD200)
- https://github.com/EtoTen/radonreader (reader for older and newer devices RD200)

## Device Support

The application was tested with RD200N model (bluetooth only) manufactured in 2022/Q2. Support for
older devices can be ported from https://github.com/ceandre/radonreader but I can't test it because
I don't have these devices.

## Contribution

Feel free to submit PR with additional support for other versions of RadonEye devices.

## License

MIT
