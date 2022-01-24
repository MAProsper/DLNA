"""Simple Service Discovery Protocol"""

from collections import namedtuple
import socket
import typing
from socketserver import BaseServer
from . import http_
from urllib.parse import urlsplit
from collections.abc import Callable, Generator
from http import HTTPStatus
from http.client import HTTPConnection
from .net import LogServerMixIn, UDPServerMixIn, UDPHandlerMixIn, UDPClientMixIn
from datetime import datetime
import threading

from src import net

__all__ = (
    "Header", "Message", "Server", "Handler"
)


class Header(http_.Header):
    """SSDP HTTP Headers"""

    NT = "NT"    # Notification type
    NTS = "NTS"  # Notification sub-type
    ST = "ST"    # Search target
    MX = "MX"    # Maximum wait time
    USN = "USN"  # Unique service name
    EXT = "EXT"  # Extension acknowledge flag


class Message:
    """SSDP Mesage Types"""

    ALIVE = "ssdp:alive"
    BYE = "ssdp:byebye"
    ALL = "ssdp:all"


class Address(dict):
    ANY = "0.0.0.0"
    timeout = float("inf")
    _data = namedtuple("data", ["timeout", "packed"])

    def __init__(self, address: str, timeout: float):
        self.add(address)
        self.timeout = timeout

    @staticmethod
    def _now() -> int:
        return int(datetime.now().timestamp())

    @staticmethod
    def _pack(address: str) -> int:
        return int.from_bytes(socket.inet_aton(address), "big")

    def select(self, address: str) -> str:
        packed = self._pack(address)
        return min(self, key=lambda address: self[address].packed ^ packed, default=self.ANY)

    def add(self, address: str) -> None:
        self[address] = self._data(self._now() + self.timeout, self._pack(address))

    def update(self) -> None:
        now = self._now()
        for address in self:
            if now > self[address].timeout:
                del self[address]

    def __iter__(self):
        copy = self.copy()
        if Address.ANY in copy and len(copy) > 1:
            del copy[Address.ANY]
        return iter(copy)


class Server(http_.Server, *UDPServerMixIn):  # type: ignore
    """SSDP Server"""

    timeout: int = 30
    allow_multicast = 1

    def __init__(self, handler: "Callable[..., Handler]", location: str, services: set[str]) -> None:
        """Initialize address and targets"""
        super().__init__(("239.255.255.250", 1900), handler)  # TODO: send M-SEARCH with ST self to discover self ip?

        self.client = Client(self)
        self._location = urlsplit(location)
        self.addresses = Address(typing.cast(str, self._location.hostname), self.timeout)
        self.targets = {
            service: f"{self.device}::{service}"
            for service in services.union({"upnp:rootdevice"})
        }
        self.targets[self.device] = self.device

    @property
    def locations(self) -> Generator[str, None, None]:
        for address in self.addresses:
            yield self._replace_location(address)

    def location_for(self, address: str) -> str:
        return self._replace_location(self.addresses.select(address))

    def _replace_location(self, address: str):
        return self._location._replace(netloc="{}:{}".format(address, self._location.port)).geturl()

    @property
    def device(self) -> str:
        return self.uuid.urn[4:]

    def serve_forever(self) -> None:
        with net.with_server(self.client):
            return super().serve_forever()


class C(UDPClientMixIn, HTTPConnection, BaseServer):
    allow_reuse_address = 1
    allow_multicast = 1

    def __init__(self, server: Server):
        self.server = server
        self.__shutdown_request = threading.Event()
        self.__is_shut_down = threading.Event()
        super().__init__(*self.server.server_address)

    def send_notifies(self, type) -> None:
        self.server.addresses.update()
        self.logger.info("addresses %s", self.server.addresses)
        for _ in range(2):
            for address in self.server.addresses:
                for target in self.server.targets:
                    self.send_notify(target, type, address)
            import time
            time.sleep(0.2)

    def send_notify(self, target, type, address: str) -> None:
        self.source_address = (address, 50927)
        self.putrequest("NOTIFY", "*", skip_accept_encoding=True, skip_host=True)
        self.putheader("HOST", "239.255.255.250:1900")
        self.putheader("SERVER", "Ubuntu DLNADOC/1.50 UPnP/1.0 MiniDLNA/1.2.1")
        self.putheader(Header.NT, target)
        self.putheader(Header.NTS, type)
        self.putheader(Header.USN, self.server.targets[target])
        if type == Message.ALIVE and address != Address.ANY:
            self.putheader(Header.CACHE_CONTROL.upper(), f"max-age={self.server.timeout}")
            self.putheader(Header.LOCATION.upper(), self.server._replace_location(address))
        self.endheaders()
        self.close()

    def serve_forever(self):
        self.__shutdown_request.clear()
        self.__is_shut_down.clear()
        # add event on somehow started
        self.send_notifies(Message.BYE)
        while True: 
            self.send_notifies(Message.ALIVE)
            if self.__shutdown_request.wait(self.server.timeout // 3):
                break
        self.send_notifies(Message.BYE)
        self.__is_shut_down.set()

    def shutdown(self):
        self.__shutdown_request.set()
        self.__is_shut_down.wait()


class Client(LogServerMixIn, C):
    pass


class Handler(http_.Handler, *UDPHandlerMixIn):  # type: ignore
    """SSDP Handler"""

    server: Server

    def do_nop(self):
        """Handle NOP requests"""

    def do_notify(self):
        if self.headers[Header.USN] in self.server.targets.values():
            self.server.addresses.add(self.client_address[0])
        elif self.client_address[0] == "192.168.1.2":
            print(f"{'-'*50}<{self.client_address[0]}:{self.client_address[1]}>{'-'*50}\n{self.headers}")

    def do_m_search(self):
        """Handle M-SEARCH requests"""
        target = self.headers[Header.ST]  # TODO: send ST dev or root or media to discover, esto solo te dice todas las ip, pero no se sabe como elegir al no saber la mask
        #if target == Message.ALL:  # VLC: works without
        #    for target in self.server.targets:
        #        self.send_discover(target)
        # if target in self.server.targets:
        #     self.send_discover(target)
           #self.server.client.send_notify(target, "http://192.168.1.10:8096/", Message.ALIVE)

    def send_discover(self, target):
        """Send discover response for specific target"""
        self.send_response(HTTPStatus.OK)
        self.send_header(Header.EXT, "")  # VLC: fine without
        self.send_header(Header.ST, target)
        self.send_header(Header.LOCATION, self.server.location_for(self.client_address[0]))  # TODO: get self interface (self) addres, minidlna gets one on the same network as client
        self.send_header(Header.USN, self.server.targets[target])
        self.send_header(Header.CACHE_CONTROL, f"max-age={self.server.timeout}")
        self.end_headers()

    def __getattr__(self, name):
        """Ignore unsuported requests"""
        if name.startswith("do_"):
            return self.do_nop
        else:
            raise AttributeError(name)
