import logging
from datetime import timedelta
from typing import Any, Callable, Dict, Optional
import requests
from lxml import etree
import re
import datetime

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (
    ATTR_NAME,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
)

from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

DOMAIN = "go_south_coast"

CONF_URL_PREFIX = "url_prefix"
CONF_BUS_STOPS = "bus_stops"
CONF_MAX_BUSSES = "max_busses"
CONF_MAX_SUMMARY_BUSSES = "max_summary_busses"
CONF_SERVICE = "service"
CONF_DESTINATION = "destination"

CONF_BUS_STOP = "bus_stop"

USER_AGENT = f"Home Assistant Go South Coast Integration"

BUS_STOP_SCHEMA = vol.Schema({
    vol.Required(CONF_BUS_STOP): cv.string,
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_SERVICE): cv.string,
    vol.Optional(CONF_DESTINATION): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default="bluestar"): cv.string,
        vol.Optional(CONF_URL_PREFIX, default="https://www.bluestarbus.co.uk/stops/"): cv.string,
        vol.Optional(CONF_MAX_BUSSES, default=10): cv.positive_int,
        vol.Optional(CONF_MAX_SUMMARY_BUSSES, default=3): cv.positive_int,
        vol.Required(CONF_BUS_STOPS): vol.All(
            cv.ensure_list, [BUS_STOP_SCHEMA],
        ),
        vol.Required(CONF_SCAN_INTERVAL): cv.time_period,
    }
)

_LOGGER: logging.Logger = logging.getLogger(__name__)

regex = 'Service - (.*?)\. Destination - (.*?)\. Departure time - (.*?)\.'

async def async_setup_platform(
    hass: HomeAssistant,  # noqa: ARG001
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,  # noqa: ARG001
) -> None:
    sensors = []
    for bus_stop in config[CONF_BUS_STOPS]:
        sensors.append(go_south_coastSensor(
            name=config.get(CONF_NAME, ""),
            url_prefix=config.get(CONF_URL_PREFIX),
            bus_stop=bus_stop.get(CONF_BUS_STOP),
            bus_stop_name=bus_stop.get(CONF_NAME),
            service=bus_stop.get(CONF_SERVICE),
            destination=bus_stop.get(CONF_DESTINATION),
            max_busses=config.get(CONF_MAX_BUSSES),
            max_summary_busses=config.get(CONF_MAX_SUMMARY_BUSSES),
            scan_interval=config[CONF_SCAN_INTERVAL],
        ))

    add_entities(sensors, update_before_add=True)

class go_south_coastSensor(SensorEntity):
    """Representation of a Go South Coast sensor."""

    # force update the entity since the number of feed entries does not necessarily
    # change, but we still want to update the extra_state_attributes
    _attr_force_update = True

    def __init__(
        self,
        name: str,
        url_prefix: str,
        bus_stop: str,
        bus_stop_name: str | None,
        service: str | None,
        destination: str | None,
        max_busses: int,
        max_summary_busses: int,
        scan_interval: timedelta,
    ) -> None:
        """Initialize the Go South Coast parser sensor."""
        self._name = name
        self._url_prefix = url_prefix
        self._bus_stop = bus_stop
        self._bus_stop_name = bus_stop_name
        self._service = service
        self._destination = destination
        self._max_busses = max_busses
        self._max_summary_busses = max_summary_busses
        self._scan_interval = scan_interval

        self._states: list[str] = []
        self._attr_attribution = "Data retrieved from Go South Coast (" + self._name + ")"

        self._entity_id = "sensor.go_south_coast_" + name.lower() + "_" + bus_stop.lower()

        self._attributes = {
            "moving_queue": [],
            "stationary_queue": [],
            "title": bus_stop_name,
            "summary": None,
        }

        _LOGGER.info("Go South Coast %s: %s bus_stop: %s sensor initialized", self._name, self._url_prefix, self._bus_stop)

    def update(self):
        _LOGGER.info("Go South Coast updating!")
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        res = s.get(self._url_prefix + self._bus_stop)
        res.raise_for_status()

        root = etree.HTML(res.text)

        self._attributes["moving_queue"].clear()
        self._attributes["stationary_queue"].clear()

        title = root.xpath('/html/head/title')[0].text # TODO: catch no match
        title = re.sub(" - Live Departures$", "", title)
        self._attributes["title"] = title

        self._attributes["summary"] = ""
        i = 0
        for elem in root.xpath('/html/body/div/div/div/ol/li/a/p'):
            match = re.search(regex, elem.text, re.IGNORECASE)
            service = match.group(1)
            destination = match.group(2)
            when = match.group(3)
            if (
                    (self._service == None or self._service == service) and
                    (self._destination == None or self._destination == destination)
                ):
                now = datetime.datetime.now()
                this_minute_now = datetime.datetime(now.year, now.month, now.day, now.hour, now.minute)
                this_day_now = datetime.datetime(now.year, now.month, now.day)

                if (i < self._max_busses):
                    if ((match := re.search("(\d+) min", when)) != None):
                        new_when = this_minute_now + datetime.timedelta(0, 0, 0, 0, int(match.group(1)))

                        self._attributes["moving_queue"].append({
                            "service": service,
                            "destination": destination,
                            "when": new_when,
                        })
                    elif (when == "Due"):
                        self._attributes["moving_queue"].append({
                            "service": service,
                            "destination": destination,
                            "when": this_minute_now,
                        })
                    elif ((match := re.search("(\d+):(\d+)", when)) != None):
                        new_when = this_day_now + datetime.timedelta(0, 0, 0, 0, int(match.group(2)), int(match.group(1)))
                        # Calculated date before now, then it wrapped - shift forwared a day
                        if (new_when < this_minute_now):
                            new_when = new_when + datetime.timedelta(1)

                        self._attributes["stationary_queue"].append({
                            "service": service,
                            "destination": destination,
                            "when": new_when,
                        })

                    if (i < self._max_summary_busses):
                        self._attributes["summary"] = self._attributes["summary"] + " " + when

                self._attributes["summary"] = re.sub(" mins", "m", self._attributes["summary"])
                self._attributes["summary"] = re.sub(" min", "m", self._attributes["summary"])

                i = i + 1

        _LOGGER.info("Go South Coast: Status %d Moving Queue %s Stationary Queue %s", res.status_code,
            self._attributes["moving_queue"], self._attributes["stationary_queue"])

    @property
    def entity_id(self):
        """Return the entity_id of the sensor."""
        return self._entity_id

    @property
    def name(self):
        """Return the name of the sensor."""
        if (self._bus_stop_name == None):
            return self._attributes["title"]
        else:
            return self._bus_stop_name

    @property
    def state(self):
        """Return the date of departure of the next moving bus."""
        if (len(self._attributes["moving_queue"])):
            now = datetime.datetime.now()
            this_minute_now = datetime.datetime(now.year, now.month, now.day, now.hour, now.minute)
            difference = self._attributes["moving_queue"][0]["when"] - this_minute_now
            return int(difference.seconds / 60)
        else:
            return None
        
    @property
    def native_unit_of_measurement(self):
        return "min"


    @property
    def extra_state_attributes(self):
        """Return the attributes of the bus stop."""
        return self._attributes
