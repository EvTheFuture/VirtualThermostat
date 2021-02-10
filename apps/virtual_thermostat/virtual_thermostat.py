"""
    Create a Thermostat in HA from switches and sensors
    Copyright (C) 2020    Magnus Sandin <magnus.sandin@gmail.com>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

Arguments in config file:

Args:
friendly_name:     O: A Friendly Name to use
heat_switch:       M: entity or list of entities to switch on/off for heating
max_interval:      O: interval where state is not chenged around target temp
max_temp:          O: max temperature that can be set
min_temp:          O: min temperature that can be set
temp_sensor:       M: entity or list of entities to read temperature from
friendly_name:     O: a friendly name for the user
DEBUG:             O: yes | no (activate debug logging)
"""

import appdaemon.plugins.hass.hassapi as hass
import appdaemon.plugins.mqtt.mqttapi as mqtt
import json

VERSION = "0.9.7"
MANUFACTURER = "Valitron AB"
MODEL = "Virtual Thermostat"

DEFAULT_MAX_TEMP = 30.0
DEFAULT_MIN_TEMP = 10.0
DEFAULT_TARGET_TEMP = 18
DEFAULT_MAX_INTERVAL = 0.8

# Store all attributes every day to disk
STORE_STATE_EVERY = 24 * 60 * 60

# Make sure to publish MQTT state at least every 5 minutes
MAX_TIME_BETWEEN_PUBLISH = 5 * 60

UUID_PREFIX = "virtual_thermostat_"
TOPIC_PREFIX = "virtual_thermostat/"

class VirtualThermostat(mqtt.Mqtt, hass.Hass):
    def initialize(self):
        self.hass = self.get_plugin_api("HASS")

        if "DEBUG" in self.args and self.args["DEBUG"]:
            self.hass.set_log_level("DEBUG")

        self.publish_timer = None

        self.max_interval = (
            self.args["max_interval"]
            if "max_interval" in self.args
            else DEFAULT_MAX_INTERVAL
        )

        # This is the file where we store current states
        # between restarts for this app
        self.persistance_file = (
            __file__.rsplit("/", 1)[0] + f"/{self.name}.json"
        )

        self.debug(f"DB FILE: {self.persistance_file}")
        self.load_persistance_file()

        self.set_namespace("mqtt")

        self.parse_and_register()

        self.listen_event(self.handle_mqtt_message, "MQTT_MESSAGE")

        # Save the current state every STORE_STATE_EVERY seconds
        self.hass.run_every(
            callback=self.save_persistance_file,
            start=f"now+{STORE_STATE_EVERY}",
            interval=STORE_STATE_EVERY,
        )

    def terminate(self):
        """Store persistance data to file when app terminates"""
        try:
            topic = self.topic_subscription
            self.debug(f"Unsubscribing from topic {topic}")
            self.call_service("mqtt/unsubscribe", topic=topic)

        except Exception as e:
            self.error(f"Unexpected Exception when unsubscribing {e}")

        self.save_persistance_file()

    def debug(self, text):
        """Print debug text to log if DEBUG is set to yes in config

        Parameters
        ----------
        text : str
            The string to write to the log
        """
        self.get_main_log().debug(text)

    def load_persistance_file(self):
        """Load persistance data from file when app starts
        and initialize mandatory data if it doenst exist."""
        try:
            with open(self.persistance_file, "r") as f:
                self.data = json.load(f)

        except IOError as e:
            self.log(f"Persistance file {self.persistance_file} not found...")
            self.data = {}

        except Exception as e:
            self.error(f"Exception when loading persistance file: {e}")
            self.data = {}

        if not "target_temp" in self.data:
            self.data["target_temp"] = DEFAULT_TARGET_TEMP

        if not "high_temp" in self.data:
            self.data["high_temp"] = DEFAULT_TARGET_TEMP

        if not "low_temp" in self.data:
            self.data["low_temp"] = DEFAULT_TARGET_TEMP

        if not "mode" in self.data:
            self.data["mode"] = "off"

    def save_persistance_file(self, kwargs=None):
        """Save persistance data to file"""
        try:
            with open(self.persistance_file, "w") as f:
                f.write(json.dumps(self.data, indent=4))

            self.log(f"Persistance entries written to {self.persistance_file}")

        except Exception as e:
            self.error(f"Exception when storing persistance file: {e}")
            return False

    def parse_and_register(self):
        """Parse the configuration and publish to MQTT"""

        if "friendly_name" in self.args:
            friendly_name = self.args["friendly_name"]
        else:
            friendly_name = self.name

        if "heat_switch" not in self.args:
            self.error(f"Missing attribute 'heat_switch'")
            return

        if "temp_sensor" not in self.args:
            self.error(f"Missing attribute 'temp_sensor'")
            return

        # Handle both single switch and multiple switches
        if isinstance(self.args["heat_switch"], list):
            switches = []
            for l in self.args["heat_switch"]:
                if isinstance(l, dict):
                    switches += list(l.keys())
                elif isinstance(l, str):
                    switches += [l]
                else:
                    self.error(f"Unknown switch configuration: {l}")
        else:
            switches = [self.args["heat_switch"]]

        self.radiator_switches = []
        for s in switches:
            if self.hass.entity_exists(s):
                self.radiator_switches.append(s)
            else:
                self.error(f"{s} does not exists, skipping...")

        if not len(self.radiator_switches):
            self.error("No matching switch entities found in Home Assistant")
            return

        self.debug(f"Radiators configured {self.radiator_switches}")

        # Handle both single sensor and multiple sensors
        if isinstance(self.args["temp_sensor"], list):
            sensors = []
            for l in self.args["temp_sensor"]:
                if isinstance(l, dict):
                    sensors += list(l.keys())
                elif isinstance(l, str):
                    sensors += [l]
                else:
                    self.error(f"Unknown sensor configuration: {l}")
        else:
            sensors = [self.args["temp_sensor"]]

        self.debug(f"Configured sensors: {sensors}")

        self.temp_sensors = []
        for s in sensors:
            if self.hass.entity_exists(s):
                self.temp_sensors.append(s)
                self.hass.listen_state(
                    callback=self.handle_state_change, entity=s
                )
                self.debug(f"Subscribing to state updates on {s}")
            else:
                self.error(f"{s} does not exists, skipping...")

        if not len(self.temp_sensors):
            self.error(
                "No matching temperature entities found in Home Assistant"
            )
            self.set_radiator_switch("off")

        self.debug(f"Sensors active: {self.temp_sensors}")
        self.log(f"Adding Thermostat {friendly_name}")

        device_id = self.name
        self.topic_base = f"{TOPIC_PREFIX}{device_id}/"

        device = {
            "identifiers": [f"{UUID_PREFIX}{device_id}"],
            "name": friendly_name,
            "sw_version": str(VERSION),
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

        config = {
            "~": self.topic_base,
            "device": device,
            "name": friendly_name,
            "unique_id": f"{UUID_PREFIX}{device_id}",
            "action_topic": "~state",
            "action_template": "{{ value_json.action }}",
            #            "aux_command_topic": "~aux_command",
            #            "aux_state_topic": "~state",
            #            "aux_state_template": "{{ value_json.aux_state }}",
            "current_temperature_topic": "~state",
            "current_temperature_template": "{{ value_json.current_temperature }}",
            #            "fan_modes": "['auto']",
            "max_temp": self.args["max_temp"]
            if "max_temp" in self.args
            else DEFAULT_MAX_TEMP,
            "min_temp": self.args["min_temp"]
            if "min_temp" in self.args
            else DEFAULT_MIN_TEMP,
            "mode_command_topic": "~set_mode",
            "mode_state_topic": "~state",
            "mode_state_template": "{{value_json.mode }}",
            "modes": ["off", "heat"],
            "power_command_topic": "~set_power",
            "swing_modes": ["off"],
            "temperature_command_topic": "~set_target_temp",
            #            "temperature_high_command_topic": "~set_high_temp",
            #            "temperature_high_state_topic": "~state",
            #            "temperature_high_state_template": "{{value_json.high_temp }}",
            #            "temperature_low_command_topic": "~set_low_temp",
            #            "temperature_low_state_topic": "~state",
            #            "temperature_low_state_template": "{{value_json.low_temp }}",
            "temperature_state_topic": "~state",
            "temperature_state_template": "{{value_json.target_temp }}",
            "temperature_unit": "C",
            "temp_step": "0.5",
        }

        self.call_service(
            "mqtt/publish",
            topic=f"homeassistant/climate/{device_id}/config",
            payload=json.dumps(config),
            retain=False,
        )

        self.debug(f"Published config for Thermostat: {device_id}")

        self.topic_subscription = f"{self.topic_base}#"
        self.call_service("mqtt/subscribe", topic=self.topic_subscription)
        self.debug(f"Subscribed to: {self.topic_subscription}")

        self.evaluate_status()
        self.publish_state()

    def handle_mqtt_message(self, callback, event, kwargs):
        """This is called when a MQTT message has been received"""

        TOPIC_HANDLERS = {
            "~set_target_temp": VirtualThermostat.handle_set_temp,
            "~set_high_temp": VirtualThermostat.handle_set_temp,
            "~set_low_temp": VirtualThermostat.handle_set_temp,
            "~set_power": VirtualThermostat.handle_set_power,
            "~set_mode": VirtualThermostat.handle_set_mode,
        }

        full_topic = event["topic"]
        if not full_topic.startswith(TOPIC_PREFIX):
            return

        if full_topic.startswith(self.topic_base):
            topic = full_topic.replace(self.topic_base, "~")
            if topic == "~state":
                return

            if topic in TOPIC_HANDLERS:
                TOPIC_HANDLERS[topic](self, event)
                self.evaluate_status()
                self.publish_state()
            else:
                self.log(f"No handler found for topic: {topic}")

    def handle_set_power(self, event):
        self.debug(f"INSIDE handle_set_power {event}")

    def handle_set_mode(self, event):
        self.data["mode"] = event["payload"]

    def handle_set_temp(self, event):
        temp_type = event["topic"].replace(self.topic_base + "set_", "")
        self.debug(f"TYPE: {temp_type}")

        self.debug(f"INSIDE handle_set_temp {event}")
        self.data[temp_type] = event["payload"]
        self.evaluate_status()

    def publish_state(self):
        # Valid action values: off, heating, cooling, drying, idle, fan.
        payload = {
            "current_temperature": self.current_temperature(),
            "target_temp": self.data["target_temp"],
            #            "high_temp": self.data["high_temp"],
            #            "low_temp": self.data["low_temp"],
            "action": self.current_action,
            "mode": self.data["mode"],
        }

        self.call_service(
            "mqtt/publish",
            topic=f"{self.topic_base}state",
            payload=json.dumps(payload),
            retain=False,
        )

        self.debug(f"State Published: {payload}")
        self.debug("Setting up timer to make sure we reqularily publish")

        try:
            self.hass.cancel_timer(self.publish_timer)
            self.debug("Successfully canceled publish timer")
        except Exception as e:
            pass

        self.publish_timer = self.hass.run_in(
            callback=self.force_eval_and_publish,
            delay=MAX_TIME_BETWEEN_PUBLISH,
        )

    def force_eval_and_publish(self, kwargs):
        self.debug(f"Forcing evaluation and publish to MQTT broker")
        self.evaluate_status()
        self.publish_state()

    def handle_state_change(self, entity, attribute, old, new, kwargs):
        self.debug(f"New state on {entity}, {attribute}, {old}, {new}")
        self.evaluate_status()
        self.publish_state()

    def evaluate_status(self):
        """This is the function that handle the logic on when
        to switch radiator(s) on and off, depending on temperature"""

        if self.data["mode"] == "off" or not len(self.temp_sensors):
            self.set_radiator_switch("off")
            self.current_action = "off"
            return

        current_temp = self.current_temperature()

        target_temp = float(self.data["target_temp"])
        lowest_temp = target_temp - self.max_interval / 2
        highest_temp = target_temp + self.max_interval / 2

        if current_temp < lowest_temp:
            self.set_radiator_switch("on")
        elif current_temp >= highest_temp:
            self.set_radiator_switch("off")

        if self.hass.get_state(self.radiator_switches[0]) == "off":
            self.current_action = "idle"
        else:
            self.current_action = "heating"

    def set_radiator_switch(self, state):
        for s in self.radiator_switches:
            self.debug(f"Setting state \"{state}\" to '{s}'")
            self.hass.call_service(
                f"switch/turn_{state}", entity_id=s,
            )

    def current_temperature(self):
        if not len(self.temp_sensors):
            return 0.0

        temp = 0.0

        for s in self.temp_sensors:
            temp += float(self.hass.get_state(s))

        temp /= len(self.temp_sensors)

        self.debug(f"Current Temperature is: {temp})")
        return round(temp, 1)
