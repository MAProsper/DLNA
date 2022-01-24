"""Connection utilities"""

from . import net
import re
import socket
import logging
import socketserver as ss
from threading import Thread
from collections import namedtuple
from contextlib import contextmanager

__all__ = (
    "UDPServerMixIn", "UDPHandlerMixIn", "UDPClientMixIn", "with_server", "safe_identifier", "ip_membership"
)


mixin = namedtuple("UnpackMixIn", ["override", "base"])
UDPServerMixIn = mixin(ss.UDPServer, ss.TCPServer)
UDPHandlerMixIn = mixin(ss.DatagramRequestHandler, ss.StreamRequestHandler)


_re_alnum = re.compile(r"[^\w]+")


def safe_identifier(method: str) -> str:
    """Transform a HTTP into a valid identifier"""
    return _re_alnum.sub("_", method).lower()


def ip_membership(group: str, addr: str = "0.0.0.0") -> bytes:
    """Construct a IP membership request"""
    return socket.inet_aton(group) + socket.inet_aton(addr)


class UDPClientMixIn:
    """HTTP Client over UDP mix-in"""

    host: str
    port: int
    source_address: tuple[str, int]
    allow_reuse_address = False
    allow_multicast = False

    def connect(self) -> None:
        """Connect to the host and port via UDP"""
        # send to multicast addres; send though bind addres, if ADDR_ANY, send only though ip in defualt route
        # so auto ip discovery imposible, need extra package
        # however thant doesnt solve ssdp:alive not working, try send on same port?
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.allow_reuse_address:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        if self.allow_multicast:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        #if self.allow_multicast and self.source_address:
            #print(f"MEMBER: GRP={self.host} IP={self.source_address[0]}")
            #self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                 #net.ip_membership(self.host, self.source_address[0]))
        if self.source_address:
            self.sock.bind(self.source_address)
        self.sock.connect((self.host, self.port))


from functools import cached_property

class LogServerMixIn:
    @cached_property
    def logger(self) -> logging.Logger:
        cls = self.__class__
        logger = logging.getLogger(f"{cls.__module__}.{cls.__name__}")
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def serve_forever(self) -> None:
        self.logger.info("started")
        try:
            super().serve_forever()
        finally:
            self.logger.info("stopped")

    # def finish_request(self, request, client_address):
    #     self.logger.info("handler started")
    #     try:
    #         super().finish_request(request, client_address)
    #     finally:
    #         self.logger.info("handler stopped")


@contextmanager
def with_server(server: ss.BaseServer):
    """Execute server in the background while in context"""
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join()
