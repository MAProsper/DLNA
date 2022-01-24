"""Execute a DLNA Media Server with SSDP"""

import platform
from src import ssdp
from src import soap
from src import media
from src import net
from pathlib import Path
from argparse import ArgumentParser

parser = ArgumentParser(prog="dlna", description="Execute a DLNA Media Server")
parser.add_argument("-a", "--address", type=str, default="", help="address which the server should bind to")
parser.add_argument("-p", "--port", type=int, default=0, help="port which the server should bind to")
parser.add_argument("-m", "--media", type=Path, default=Path(), help="path the server should serve")
parser.add_argument("-n", "--name", type=str, default=platform.node(), help="display name of the server")
args = parser.parse_args()

with media.Server((args.address, args.port), media.Handler, soap.Handler, args.name, args.media) as server:
    with net.with_server(ssdp.Server(ssdp.Handler, server.paths.DEV.as_uri(server.host), server.services)):
        try:
            #print(server.host)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
