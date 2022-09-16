# radoneye-reader

Ecosense RadonEye reader with MQTT and Home Assistant support with automatic discovery.

## Installation

Requires Python 3.x and has been tested to work well on macOS and Linux. Keep in mind, device
addresses are different between macOS (uuid like) and Linux (mac like).

Python `bleak` BLE library is used as the most stable, portable and easy installable (no complex
build toolchain is needed). If you wanted to check with `pygatt` then checkout version `v1.0.0`.

Install dependencies:

```
pip3 install asyncio bleak paho-mqtt
```

## Usage

```
$ ./radoneye-reader.py --help
usage: radoneye-reader.py [-h] [--connect-timeout CONNECT_TIMEOUT] [--read-timeout READ_TIMEOUT]
                          [--reconnect-delay RECONNECT_DELAY] [--attempts ATTEMPTS] [--debug]
                          [--daemon] [--mqtt] [--discovery] [--mqtt-hostname MQTT_HOSTNAME]
                          [--mqtt-port MQTT_PORT] [--mqtt-username MQTT_USERNAME]
                          [--mqtt-password MQTT_PASSWORD] [--mqtt-ca-cert MQTT_CA_CERT]
                          [--device-topic DEVICE_TOPIC] [--discovery-topic DISCOVERY_TOPIC]
                          [--device-retain] [--discovery-retain] [--interval INTERVAL]
                          [--expire-after EXPIRE_AFTER] [--force-update] [--restart-bluetooth]
                          [--restart-bluetooth-delay RESTART_BLUETOOTH_DELAY]
                          [--restart-bluetooth-cmd RESTART_BLUETOOTH_CMD]
                          addr [addr ...]

Reads Ecosense RadonEye device sensor data

positional arguments:
  addr                  device address

optional arguments:
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
  --discovery           enable MQTT home assistant discovery event publishing (default: False)
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
                        MQTT home assistant discovery topic (default: homeassistant/sensor)
  --device-retain       retain device events (default: False)
  --discovery-retain    retain discovery events (default: False)
  --interval INTERVAL   device poll interval in seconds (default: 300)
  --expire-after EXPIRE_AFTER
                        Defines the number of seconds after the sensor's state expires, if it's
                        not updated (default: None)
  --force-update        Sends update events even if the value hasn't changed (default: False)
  --restart-bluetooth   Try to restart bluetooth stack on bluetooth error (default: False)
  --restart-bluetooth-delay RESTART_BLUETOOTH_DELAY
                        Delay in seconds after bluetooth stack has been restarted (default: 10)
  --restart-bluetooth-cmd RESTART_BLUETOOTH_CMD
                        Command to execute when bluetooth stack restart is needed (default:
                        service bluetooth restart)
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

RadonEye updates last radon level every 10 minutes, so reading sensor too often is not really
useful.

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
