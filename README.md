Virtual Thermostat
==================

_Create a Thermostat in Home Assistant from one or more radiators and one or more temperature sensors_

Perfect in order to create automations to control the temperature during day/night/away/weather based etc.

This [AppDaemon](https://appdaemon.readthedocs.io/en/latest/#) app for [Home Assistant](https://www.home-assistant.io/) require at least one sensor to get the current temperature from and at least one switch to turn on and off the actual radiator. Currently only Heating is supported.

[![buy-me-a-coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/EvTheFuture)

## MQTT
NOTE: You will need to have [AppDaemon](https://appdaemon.readthedocs.io/en/latest/#) configured with MQTT support in order for this app to work.

*This is an example appdaemon.yaml configuration file with the MQTT plugin enabled:*
```
appdaemon:
  latitude:  57.0
  longitude: 12.0
  elevation: 12
  time_zone: Europe/Stockholm
  plugins:
    HASS:
      type: hass
    MQTT:
      type: mqtt
      namespace: mqtt
      client_host: 192.168.1.10
      client_id: AppDaemon
      client_user: appdaemon
      client_password: !secret appdaemon_mqtt_password
http:
  url: http://127.0.0.1:5050
admin:
api:
hadashboard:
logs:
  main_log:
    filename: /config/appdaemon/log/main_log.log
    log_generations: 1
    log_size: 20971520
```

## Quick Examples

Here are some example configurations for the appdaemon configuration file apps.yaml. If more than one sensor has been defines, then the average temperature between the sensors will be used.

**Please Note:** You need to change the entities to match your setup.
```
gaming_room_radiator:
    module: virtual_thermostat
    class: VirtualThermostat
    temp_sensor: sensor.gaming_room_temperature
    heat_switch: switch.shelly_shsw_25_234567890123_2
    max_temp: 28
    min_temp: 12
    max_interval: 0.8
    max_age: 15
    friendly_name: Gaming Room Radiator
    DEBUG: no

living_room_radiators:
    module: virtual_thermostat
    class: VirtualThermostat
    temp_sensor: sensor.livingroom_temperature
    heat_switch: 
      - switch.shelly_shsw_25_567890123456_2:
      - switch.shelly_shsw_25_567890123456_1:
    max_temp: 28
    min_temp: 12
    max_age: 10
    max_interval: 0.8
    friendly_name: Livingroom Radiators
    DEBUG: no

kitchen_radiator:
    module: virtual_thermostat
    class: VirtualThermostat
    temp_sensor:
      - sensor.kitchen_temperature
      - sensor.kitchen_temperature_sensor_2
      - sensor.kitchen_temperature_sensor_3
    heat_switch: switch.shelly_shsw_25_1234567890ab_2
    max_temp: 28
    min_temp: 12
    max_age: 20
    max_interval: 0.8
    friendly_name: Kitchen Radiator
    DEBUG: no
```

