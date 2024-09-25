# Go South Coast bus timetable integration for Home Assistant

[Go South Coast Ltd](https://gosouthcoast.co.uk/) provides bus services for the south of England and runs various bus companies in Dorset, Wiltshire, Hampshire and the Isle of Wight. Since these companies share a common web platform this integration should be able to retrieve timetable (including real time) information on all of Go South Coast busses, though only a subset has been tested. This integration operates by scraping the same web pages a user might look at when obtaining bus timetable information.

## Installation

Only manual installation is supported at present. Copy the `custom_components/go_south_coast` directory into your Home Assistant `custom_components` directory, amend your `configuration.yaml` as required, and then restart Home Assistant.

## Sensor data format

This integration will create sensors for the configured bus stops. The sensor entity IDs are formed up as follows:

`sensor.go_south_coast_(sub company name)_(bus stop identifier)`

Eg:

`sensor.go_south_coast_morebus_1280POA11807` for the MoreBus stop listed below.

Each sensor's state is the estimated time until the arrival of the next "in motion" bus in minutes, ie. the first one that is listed as a time in minutes on the bus stop's web page.

In addition the following attributes are provided:

* moving_queue: This is an array of entries for each currently moving bus which will stop at (or at least drive past) the named bus stop.
  * when: A timestamp for the arrival time of the bus
  * destination: The ultimate destination of the bus
  * service: The service number (actually a string, since some busses have alphanumeric route numbers) of the bus
* stationary_queue: The same as the above but for busses which have a listed time of day against them. These busses have either not started their route or they are not currently moving.
* summary: This is a string summarizing the arrival times of all busses, in motion and stationary, in the order presented on the web page for that bus stop. This field is used, in my own Home Assistant deployment, to feed my [LED Matrix Display](https://github.com/aslak3/matrix-display) screen with a concise string such that it will fit in the 64 pixel wide display. To make it fit, "mins" are truncated to "m", etc.
* title: The title of the web page providing the data.

## Configuration

Configuration is entirely done through the Home Assistant `configuration.yaml` file, at present.

Here is an example from my own setup, with some elaboration:

````yaml
sensor:
  - platform: go_south_coast
    scan_interval: 00:01:00
    max_busses: 8
    max_summary_busses: 3
    bus_stops:
      - bus_stop: 1900HA080357
        service: 9
        name: Hythe, all 9s
      - bus_stop: 1980HAA13582
        service: 9
        name: Westquay, 9s Towards Hythe
  - platform: go_south_coast
    name: morebus
    url_prefix: https://www.morebus.co.uk/stops/
    scan_interval: 0:05:00
    bus_stops:
      - bus_stop: 1280POA11807
````

* `platform`: the integration domain.
* `scan_interval`: the polling interval. 1 minute is a bit aggressive but seems to be acceptable to the backends. Ideally tune this down. This field is required.
* `max_busses`: The maximum number of busses to obtain information for. This count will be split into the moving and stationary queues. All configured bus stops use this setting. Defaults to 10.
* `max_summary_busses`: The maximum number of busses to use when formatting the summary. This should be lower than the `max_busses` field. Defaults to 3.
* `bus_stops`: The array of bus stop records.
  * `bus_stop`: The bus stop identifier, which is the last path element for the URL as viewed in a browser.
  * `service`: This (and the following) field acts as a filter: if a bus stop serves multiple services it is helpful to ignore busses which you are not interested in following.
  * `destination`: Not used above, this field forms the rest of the filter. If both `service` and `destination` are specified both must match. If neither is specified then all busses for all services and destinations are included in the queues (and summary).
  * `name`: This is an override for the sensor name. Ordinarily the page title obtained from the complete URL will be used, but it is possible to override it with this field.
* `name`: This is the "sub company" bus provider name and is only used to form up the sensor entity IDs. The default is `bluestar` simply because that happens to be my local bus company.
* `url_prefix`: The URL prefix for the bus stop data, as served up by Go South Coast's infrastructure. The default is `https://www.bluestarbus.co.uk/stops/`, only because that happens to be my local bus company.

## TODO

* Better error handling
* Add a integration icon.
* Add a simple configuration UI.
* A custom dashboard card!
* Figure out how to create a Home Assistant addon, assuming anyone actually uses this thing.

## Note!

I'm new to Python. The code is currently beta quality at best. But, it works for me (tm).
