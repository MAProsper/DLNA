"""Digital Living Network Alliance Media Server"""

import typing
from . import xml_
from . import http_
from http import HTTPStatus
from collections.abc import Callable
from pathlib import Path


__all__ = (
    "Server", "Handler"
)


class Server(http_.Server):
    """DLNA Media Server"""

    sub = {}
    services = {
        "urn:schemas-upnp-org:device:MediaServer:1",
        "urn:schemas-upnp-org:service:ContentDirectory:1",
        "urn:schemas-upnp-org:service:ConnectionManager:1"
    }

    class paths(http_.UrlPath):  # noqa: N801
        """Paths used by the server and handler"""

        DEV = http_.UrlPath("/device-description.xml")
        NET = http_.UrlPath("/connection-manager.xml")
        SRV = http_.UrlPath("/content-directory.xml")
        MRR = http_.UrlPath("/media-receiver-registrar.xml")
        MEDIA = http_.UrlPath("/media/")

    def __init__(self, address: tuple[str, int], handler: "Callable[..., Handler]", soap: "Callable",
                 name: str, media: Path):
        """Initialize media server"""
        super().__init__(address, handler)
        self.name = name
        self.media = media
        self._soap = soap

    def get_template(self, name: str) -> Path:
        """Get template path from its name"""
        return Path("etc/templates", name).with_suffix(".xml")


class Handler(http_.Handler):
    """DLNA Media Handler"""

    server: Server
    path: http_.UrlPath

    def parse_request(self) -> bool:
        """Parse path to pathlib unquoting"""
        if super().parse_request():
            self.paths = self.server.paths
            self.path = http_.UrlPath.from_uri(typing.cast(str, self.path))
            return True
        else:
            return False

    def send_template(self, name: str, code: HTTPStatus = HTTPStatus.OK, **kwds):
        """Send a templated reply"""
        path = self.server.get_template(name)
        text = xml_.serialize(xml_.format(xml_.parse(path), **kwds))
        self.send_text(self.mime(path), text, code)

    def do_get(self):
        """Handle GET requests"""
        if self.path == self.paths.MRR:
            self.send_file(Path("etc/templates", self.paths.MRR.relative_to("/")))

        elif self.path in {self.paths.SRV, self.paths.NET}:
            self.send_file(Path("etc/templates", str(self.path.relative_to("/")).replace(".", "2.")))
            #self.send_template(self.path.stem)

        elif self.path == self.paths.DEV:
            #self.send_file(Path("etc/templates", str(self.path.relative_to("/")).replace(".", "2.")))
            self.send_template(self.path.stem, friendlyName=self.server.name, UDN=self.server.uuid.urn)

        elif self.path.is_relative_to(self.paths.MEDIA):
            path = self.server.media / self.path.relative_to(self.paths.MEDIA)
            if path.is_file():
                range = self.headers.get(http_.Header.RANGE, "")
                self.send_file(path, http_.Range(path, range))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        else:
            self.send_error(HTTPStatus.BAD_REQUEST)

    def do_post(self):
        """Handle POST requests"""
        if self.path == self.paths.SRV:
            self.server._soap(self)

        else:
            self.send_error(HTTPStatus.BAD_REQUEST)

    def do_subscribe(self):
        #self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
        """
        Content-Type: text/xml; charset="utf-8"
        Connection: close
        Content-Length: 0
        Server: 5.4.0-1039-azure DLNADOC/1.50 UPnP/1.0 MiniDLNA/1.3.0
        Timeout: Second-300
        SID: uuid:c6fdae58-f7a8-11eb-8c35-444770920886
        Date: Sat, 07 Aug 2021 17:56:23 GMT
        EXT:
        """
        if "Callback" in self.headers:
            import uuid
            url = self.headers["Callback"].strip("<>")
            sid = uuid.uuid5(uuid.NAMESPACE_URL, url).urn[4:]
            self.server.sub[sid] = url
            print("SUB=FIRST")
        else:
            sid = self.headers["SID"]
            url = self.server.sub[sid]
            print("SUB+NEXT")
        self.send_response(HTTPStatus.OK)
        self.send_header("Timeout", self.headers["Timeout"])
        self.send_header("SID", sid)
        self.send_header("EXT", "")
        self.end_headers()
        from http.client import HTTPConnection
        from urllib.parse import urlsplit
        split = urlsplit(url)
        con = HTTPConnection(split.hostname, split.port, timeout=int(self.headers["Timeout"].split("-")[1]))
        con.connect()
        con.request("NOTIFY", split.path, body='<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0"></e:propertyset>', headers={
        "Content-Type": 'text/xml; charset="utf-8"',
        "NT": "upnp:event",
        "NTS": "upnp:propchange",
        "SID": sid,
        "SEQ": "0"
        })
        res = con.getresponse()
        print(res.getheaders())
        res.close()
        con.close()
