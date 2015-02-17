#!/usr/bin/env python
import argparse
import logging
import socket
import threading
import SocketServer
import sys
import time
import signal
import Queue
import serial
import errno

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
    def __init__(self):
        self.queue = Queue.Queue()
        self.running = True

    def send(self, data):
        pass

    def receive(self):
        yield None

    def close(self):
        pass

    def stop(self):
        self.running = False
        self.close()

    def handle(self):
        for data in self.receive():
            if data:
                for handler in handlers:
                    if handler != self:
                        handler.queue.put(data)
        while not self.queue.empty():
            data = self.queue.get()
            logging.debug("%s will send data: %s" % (self.__class__, data))
            self.send(data + '\r\n')

        time.sleep(0.01)

    def loop(self):
        while self.running:
            self.handle()


class NMEASerialDevice(NMEAHandler):
    def __init__(self, device_path, baud_rate):
        super(NMEASerialDevice, self).__init__()
        self.device = serial.Serial(device_path, baud_rate, timeout=0)

    def send(self, data):
        self.device.write(data)

    def receive(self):
        yield self.device.readline()

    def close(self):
        self.device.close()


class NMEATCPServer(NMEAHandler):
    def __init__(self, port):
        super(NMEATCPServer, self).__init__()

        # TODO: This is kinda ugly, but works
        server = self
        class RequestHandler(SocketServer.StreamRequestHandler):
            nmea_buffer = ''
            timeout = 0

            def handle(self):
                while 1:
                    try:
                        data = self.request.recv(1024)
                        lines = (self.nmea_buffer + data).split('\r')
                        self.nmea_buffer = lines.pop()
                        for line in lines:
                            for handler in handlers:
                                if handler != server:
                                    handler.queue.put(data)
                    except socket.error, error:
                        err = error.args[0]
                        if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                            pass
                        else:
                            # a "real" error occurred
                            print error
                            sys.exit(1)

                    while not server.queue.empty():
                        data = server.queue.get()
                        self.wfile.write(data + '\r\n')

                    time.sleep(0.01)

        self.server = SocketServer.TCPServer(('0.0.0.0', port), RequestHandler)

    def loop(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()


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


signal.signal(signal.SIGINT, thread_cleanup)


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
