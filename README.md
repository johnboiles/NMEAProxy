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

Startup Script
--------------
An init.d startup script is included in the `scripts` directory. To use it make sure `nmea_proxy.py` is somewhere in your `$PATH`. For example, you could symlink `nmea_proxy.py` to a `bin` directory.

    ln -s $PWD/NMEAProxy/nmea_proxy.py /usr/local/bin/nmea_proxy.py

Then copy the script into the `/etc/init.d` directory.

    cp scripts/nmea_proxy /etc/init.d/

You can then configure NMEAProxy to start at boot with (using SysV)

    sudo update-rc.d nmea_proxy defaults
    sudo update-rc.d nmea_proxy enable

Or (using SystemD)

    sudo systemctl enable nmea_proxy

Note that you may need to edit the `nmea_proxy` script with the desired options depending on your setup.

License
-------
NMEA Proxy is released under the GNU General Public License v3 or later
