from http.client import HTTPConnection
from contextlib import closing
import socket

__all__ = (
    "TCPClient", "UDPClient"
)


class TCPClient(HTTPConnection):
    """"""


class UDPClient(TCPClient):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect((self.host, self.port))


if __name__ == "__main__":
    with closing(UDPClient("239.255.255.250", 1900)) as con:
        print(repr(con))
        con.request("NOTIFY", "*", headers={"USN": "334389048b872a533002b34d73f8c29fd09efc50::upnp:rootdevice"})