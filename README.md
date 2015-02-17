NMEA Proxy
==========
Tool for forwarding NMEA messages from TCP sockets and serial ports. Useful when two or more NMEA device(s) need to all share data. Loosely inspired by [@tridge](https://github.com/tridge)'s [MAVProxy](https://github.com/tridge/MAVProxy).

Features
--------
* Multiplex data from multiple NMEA sources
* Supports multiple 'talkers'. For example, data from a connected GPS can be combined with autopilot routing information from OpenCPN.

Requirements
------------
* Python 2.7
* pyserial (`pip install pyserial`)

Example
-------
Here's how I use it on my RaspberryPi to share NMEA data from /dev/ttyACM0 (a USB SeaTalk <-> NMEA converter) with devices on the network (my iPad, iPhone, and laptop):

    ./nmea_proxy.py --tcp 2001 --tcp 2002 --tcp 2003 --uart /dev/ttyACM0

License
-------
NMEA Proxy is released under the GNU General Public License v3 or later
