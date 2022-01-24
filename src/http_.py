"""Extended HTTP server and handler"""

import re
from .net import LogServerMixIn
from . import net
import uuid
import magic
import socket
import typing
from http import HTTPStatus
from urllib import parse as urllib
from pathlib import Path, PurePosixPath
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

__all__ = (
    "Server", "Handler", "Header", "Range", "UrlPath"
)


class UrlPath(PurePosixPath):
    """URL as a path-like"""

    __slots__ = ()

    @classmethod
    def from_uri(cls, uri: str) -> "UrlPath":
        """Construct a path from a URI"""
        url_split = urllib.urlsplit(uri)
        # issue: some clients send relative paths
        return cls("/", urllib.unquote(url_split.path))

    def as_uri(self, uri: str = None) -> str:
        """Return the path as a file URI or join it to an existing one"""
        if uri is None:
            return super().as_uri()
        else:
            path = self.from_uri(uri) / self.relative_to("/")
            path = urllib.urlsplit(path.as_uri()).path
            return urllib.urlsplit(uri)._replace(path=path).geturl()


class Header:
    """HTTP headers"""

    HOST = "Host"
    DATE = "Date"
    RANGE = "Range"
    SERVER = "Server"
    LOCATION = "Location"
    CONTENT_TYPE = "Content-Type"
    CACHE_CONTROL = "Cache-Control"
    CONTENT_RANGE = "Content-Range"
    CONTENT_LENGTH = "Content-Length"


class Range:
    """HTTP range (both ends inclusive)"""

    _parser = re.compile(r'bytes=(\d+)-(\d+)?')

    def __init__(self, path: Path, header: str = ""):
        if match := self._parser.fullmatch(header):
            start, end = match.groups()
        else:
            start = end = None
        self._partial = bool(match)
        self.size = path.stat().st_size
        self.start = int(start) if start else 0
        self.end = int(end) if end else self.size - 1

    def __bool__(self):
        return self._partial

    def __str__(self):
        return f'bytes {self.start}-{self.end}/{self.size}'

    def __len__(self):
        return self.end - self.start + 1


class Server(LogServerMixIn, ThreadingHTTPServer):
    """HTTP server with complete address reuse and multicast support"""

    RequestHandlerClass: type[BaseHTTPRequestHandler]

    allow_multicast = False
    
    def server_bind(self) -> None:
        """Set socket options for address reuse and multicast membership"""
        if self.allow_reuse_address:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        if self.allow_multicast:  # TODO: not needed?
            #self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            #self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
            #self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("192.168.1.10"))
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, net.ip_membership(self.server_address[0]))
            #self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        super().server_bind()

    @property
    def host(self) -> str:
        """Server's Host URL"""
        return "http://{}:{}".format(*self.server_address)

    @property
    def uuid(self) -> uuid.UUID:
        """Server's UUID (based on address)"""
        return uuid.uuid5(uuid.NAMESPACE_URL, self.host)

    def handle_error(self, request, client_address):
        import sys
        from traceback import TracebackException
        print("-" * 50)
        print("".join(TracebackException.from_exception(
            typing.cast(BaseException, sys.exc_info()[1]), capture_locals=True).format()))
        print("-" * 50)


class Handler(BaseHTTPRequestHandler):
    """HTTP handler with flexible methods"""

    server: Server

    @property
    def host(self) -> str:
        """Server's Host URL"""
        return f"http://{self.headers[Header.HOST]}"

    def mime(self, path: Path) -> str:
        """Get MIME type from path"""
        from contextlib import closing
        with closing(magic.open(magic.MAGIC_MIME)) as mfd:
            mfd.load()
            return mfd.file(path)

    def copyfile(self, fp, offset: int = 0, count: int = None) -> None:
        """Copy file-like via zero-copy"""
        self.wfile.flush()
        socket_ = self.request if isinstance(self.request, socket.socket) else self.request[1]

        from contextlib import suppress
        with suppress(ConnectionError):
            socket_.sendfile(fp, offset, count)

    def send_header(self, keyword: str, value) -> None:
        super().send_header(keyword, str(value))

    def send_response_content(self, code: HTTPStatus, type: str, size: int):
        self.send_response(code)
        self.send_header(Header.CONTENT_TYPE, type)
        self.send_header(Header.CONTENT_LENGTH, size)

    def send_file(self, path: Path, range: Range = None) -> None:
        """Send a file reply"""
        if range is None:
            range = Range(path)

        if len(range) <= 0:
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            return

        # Headers
        status = HTTPStatus.PARTIAL_CONTENT if range else HTTPStatus.OK
        self.send_response_content(status, self.mime(path), len(range))
        if range:
            self.send_header(Header.CONTENT_RANGE, range)
        self.end_headers()

        # Data
        with path.open("rb") as fp:
            self.copyfile(fp, range.start, len(range))

    def send_text(self, mime: str, text: str, code: HTTPStatus = HTTPStatus.OK) -> None:
        """Send a text reply"""
        data = text.encode()

        # Headers
        self.send_response_content(code, mime, len(data))
        self.end_headers()

        # Data
        self.wfile.write(data)

    def parse_request(self) -> bool:
        """Replace invalid identifier charaters in command"""
        if super().parse_request():
            self.command = net.safe_identifier(self.command)
            return True
        else:
            return False

    def send_response(self, code: HTTPStatus, message=None) -> None:
        """Send response without automatic headers"""
        self.log_request(code)
        self.send_response_only(code, message)
