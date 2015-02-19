#!/usr/bin/env python
import argparse
import logging
import socket
import threading
import sys
import time
import signal
import Queue
import serial
import select

handler_threads = []
handlers = []


class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, **kwargs):
        super(StoppableThread, self).__init__(**kwargs)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()


class NMEAHandler(object):
    """Abstract superclass for devices that exchange NMEA data"""
    def __init__(self):
        self.queue = Queue.Queue()
        self.running = True
        self.connected = False
        self.nmea_buffer = ''
        self.message_rx_count = 0
        self.message_tx_count = 0

    def send(self, data):
        """Subclasses should override this to transmit data"""
        pass

    def receive(self):
        """Subclasses should override this to receive data"""
        pass

    def close(self):
        """Subclasses should override this to perform shutdown-related tasks"""
        pass

    def put_queue_data(self, data):
        if self.running and self.connected:
            self.queue.put(data)

    def stop(self):
        self.running = False
        self.close()
        # TODO: Empty the queue

    def handle(self):
        # Receive data
        data = self.receive()
        if data:
            lines = (self.nmea_buffer + data).split('\r')
            self.nmea_buffer = lines.pop()
            # TODO: Checksum?
            for nmea_message in lines:
                nmea_message = nmea_message.strip()
                logging.debug("%s received message: %s" % (self, nmea_message))
                self.message_rx_count += 1
                for handler in handlers:
                    if handler != self:
                        handler.put_queue_data(nmea_message)

        # Transmit data
        while not self.queue.empty():
            data = self.queue.get()
            logging.debug("%s will transmit message: %s" % (self, data))
            self.message_tx_count += 1
            self.send(data + '\r\n')

        time.sleep(0.01)

    def loop(self):
        while self.running:
            self.handle()


class NMEASerialDevice(NMEAHandler):
    """Opens a serial port with the specified path and baud for receiving NMEA Messages"""
    def __init__(self, device_path, baud_rate):
        super(NMEASerialDevice, self).__init__()
        self.device = serial.Serial(device_path, baud_rate, timeout=0)
        self.connected = True

    def send(self, data):
        self.device.write(data)

    def receive(self):
        return self.device.read(1024)

    def close(self):
        self.device.close()

    def __str__(self):
        return '%s (%s)' % (self.__class__.__name__, self.device.portstr)


class NMEATCPServer(NMEAHandler):
    """Opens a TCP socket on the specified port for receiving NMEA Messages"""
    def __init__(self, port):
        super(NMEATCPServer, self).__init__()

        self.port = port

        backlog = 5
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', port))
        self.socket.setblocking(0)
        self.socket.settimeout(0)
        self.socket.listen(backlog)

        self.client = None
        self.address = None

    def send(self, data):
        ready = select.select([], [self.client], [], 0)
        if ready[1]:
            self.client.send(data)
            return True
        else:
            return False

    def receive(self):
        ready = select.select([self.client], [], [], 0)
        if ready[0]:
            return self.client.recv(1024)

    def close(self):
        if self.client:
            self.client.close()

    def loop(self):
        while self.running:
            try:
                self.client, self.address = self.socket.accept()
                self.connected = True
                logging.info('Client connected: %s' % self.address[0])
                super(NMEATCPServer, self).loop()
            except socket.error:
                if self.connected:
                    logging.info('Client %s disconnected' % self.address[0])
                    self.connected = False
                    self.client = None
                    self.address = None
                else:
                    logging.debug('Waiting for connection on port %s' % self.port)
                    time.sleep(1)

    def __str__(self):
        if self.connected:
            status_string = '%s:%s' % (self.address[0], self.port)
        else:
            status_string = 'waiting:%s' % self.port
        return '%s (%s:%s)' % (self.__class__.__name__, status_string, self.port)


def main_loop():
    while 1:
        time.sleep(0.01)


def thread_cleanup(signal, frame):
    for handler in handlers:
        handler.stop()

    for thread in handler_threads:
        thread.stop()
        logging.info('Cleaning up thread: %s' % thread.name)
    sys.exit(0)


def show_stats(signal, frame):
    for handler in handlers:
        logging.info("%s TX: %d RX: %d" % (handler, handler.message_tx_count, handler.message_rx_count))


signal.signal(signal.SIGINT, thread_cleanup)
signal.signal(signal.SIGUSR1, show_stats)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Multiplexes and forwards NMEA streams from serial ports and TCP sockets.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--loglevel', help='Set log level to DEBUG, INFO, WARNING, or ERROR', default='INFO')
    parser.add_argument('--logfile', help='Log file to append to.',)
    parser.add_argument('--uart', help='File descriptor of UART to connect to proxy.', metavar="DEVICE[,BAUD]", action='append', default=[])
    parser.add_argument('--tcp', help='Listening ports to open for proxy.', type=int, action='append', default=[])

    args = parser.parse_args()
    log_level = args.loglevel
    log_file = args.logfile
    uart_devices = args.uart
    tcp_ports = args.tcp

    numeric_log_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_log_level, int):
        raise ValueError('Invalid log level: %s' % log_level)
    logging.basicConfig(level=numeric_log_level, format='%(asctime)s %(levelname)s:%(message)s', filename=log_file)

    for tcp_port in tcp_ports:
        handler = NMEATCPServer(tcp_port)
        handler_thread = StoppableThread(target=handler.loop)
        handler_thread.daemon = True
        handler_thread.start()
        handler_threads.append(handler_thread)
        handlers.append(handler)
        logging.info("TCP server for port %d running in thread: %s" % (tcp_port, handler_thread.name))

    for uart_device in uart_devices:
        if ',' in uart_device:
            device, baud = uart_device.split(',')
        else:
            device = uart_device
            baud = 115200
        handler = NMEASerialDevice(device, baud)
        handler_thread = StoppableThread(target=handler.loop)
        handler_thread.daemon = True
        handler_thread.start()
        handler_threads.append(handler_thread)
        handlers.append(handler)
        logging.info("Serial handler for %s running in thread: %s" % (uart_device, handler_thread.name))

    main_loop()
