"""DLNA AV classes"""

import re
import magic
from .xml_ import element as xel
from pathlib import Path
from datetime import datetime
from . import http_
from xml.etree import ElementTree as Et
from collections.abc import Generator
# import enum


# class Operation(enum.IntFlag):
#     """Supported seek operations"""
#
#     NONE = 0
#     RANGE = 0x01
#     TIME = 0x10
#
#     def __str__(self):
#         return f"{self.value:02x}"
#
#
# class PlaySpeed(enum.IntEnum):
#     """Playback speed validity"""
#
#     INVALID = 0
#     NORMAL = 1
#
#     def __str__(self):
#         return f"{self.value}"
#
#
# class Conversion(enum.IntEnum):
#     """Identifies transcoded media"""
#
#     NONE = 0
#     TRANSCODED = 1
#
#     def __str__(self):
#         return f"{self.value}"
#
#
# class Flags(enum.IntFlag):
#     """Other DLNA media flags"""
#
#     SENDER_PACED = 1 << 31
#     TIME_BASED_SEEK = 1 << 30
#     BYTE_BASED_SEEK = 1 << 29
#     PLAY_CONTAINER = 1 << 28
#     S0_INCREASE = 1 << 27
#     SN_INCREASE = 1 << 26
#     RTSP_PAUSE = 1 << 25
#     STREAMING_TRANSFER_MODE = 1 << 24
#     INTERACTIVE_TRANSFERT_MODE = 1 << 23
#     BACKGROUND_TRANSFERT_MODE = 1 << 22
#     CONNECTION_STALL = 1 << 21
#     DLNA_V15 = 1 << 20
#
#     def __str__(self):
#         return f"{self.value:024x}"
#
#
# parameters = {
#     "DLNA.ORG_PN": str
#     "DLNA.ORG_OP": Operation
#     "DLNA.ORG_PS":
#     "DLNA.ORG_CI":
#     "DLNA.ORG_FLAGS":
# }
#
#
# def protocol_info(profile: Parameter = None, operation: Operation = None, play_speed: PlaySpeed = None,
#                   conversion: Conversion = None, flags: Flags = None):
#     field = []
#
#     if profile is not None:
#         field.append(profile)
#     if operation is not None:
#         field.append(operation)
#     if play_speed is not None:
#         field.append(play_speed)
#     if conversion is not None:
#         field.append(conversion)
#     if flags is not None:
#         field.append(flags)
#
#     return ";".join(f"{value}"for key, value in field.items())
#
#
# def protocol_info(profile: Parameter = None, operation: Operation = None, play_speed: PlaySpeed = None,
#                   conversion: Conversion = None, flags: Flag = None):
#     field = {
#
#     if profile is not None:
#         field[Parameter.PROFILE] = profile
#     if operation is not None:
#         field[Parameter.OPERATION] = operation
#     if play_speed is not None:
#         field[Parameter.PLAY_SPEED] = play_speed
#     if conversion is not None:
#         field[Parameter.CONVERSION] = conversion
#     if flags is not None:
#         field[Parameter.FLAG] = flags
#
#     return ";".join(f"{key}={value}"for key, value in field.items())

class IdPath(http_.UrlPath):
    """ID as a path-like"""

    __slots__ = ()

    @classmethod
    def from_id(cls, id: str) -> "IdPath":
        """Construct a path from a ID"""
        if id == "0":
            return cls("/")
        else:
            return cls(id)

    def as_id(self) -> str:
        """Return the path as a ID"""
        cls = self.__class__
        if self == cls("/"):
            return "0"
        else:
            return str(self)

    @classmethod
    def from_path(cls, root: Path, path: Path) -> "IdPath":
        return cls("/", path.relative_to(root))

    def as_path(self, root: Path) -> Path:
        return root / self.relative_to("/")


class Object:
    def __init__(self, root: Path, url: str, id: str, command):
        self.root = root
        self.url = url
        self.id_path = IdPath.from_id(id)
        self.command = command

    @property
    def path(self) -> Path:
        return self.id_path.as_path(self.root)

    @property
    def mime(self) -> str:
        return magic.detect_from_filename(self.path).mime_type

    @property
    def mime_type(self) -> str:
        return self.mime.split("/")[0]

    @property
    def qname(self) -> str:
        """XML qualified tagname"""
        if self.path.is_dir():
            return "dlna:container"
        else:
            return "dlna:item"

    @property
    def uclass(self):
        """UPnP class path"""
        if self.path.is_dir():
            return "object.container"
        else:
            return f"object.item.{self.mime_type}Item"

    @property
    def update(self) -> int:  # TODO: check if anybody cares (check if cached if always 0)
        if self.path == self.root:
            return int(datetime.now().timestamp())
        else:
            return int(self.path.stat().st_mtime)

    @property
    def id(self) -> str:
        return self.id_path.as_id()

    @property
    def parent_id(self) -> str:  # TODO: check in TV, parent of root may need to be -1 insted of root again
        return self.id_path.parent.as_id()

    def __iter__(self) -> "Generator[Object, None, None]":
        cls = self.__class__
        if self.command == "browse":
            result = self.path.glob("*")
        elif self.command == "search":
            result = self.path.rglob("*")
        else:
            result = []
        for path in result:
            element = cls(self.root, self.url, IdPath.from_path(self.root, path).as_id(), "browse")
            if element.path.is_dir() or element.mime_type in {"image", "audio", "video"}:
                yield element  # TODO: check in TV, is check needed or can we provide invalid upnp classes

    @property
    def children(self) -> "list[Object]":
        return list(iter(self))

    def __getitem__(self, key):
        return self.children[key]

    def __len__(self):
        return len(self.children)

    @property
    def location(self) -> str:
        return self.id_path.as_uri(self.url)

    @property
    def element(self) -> Et.Element:
        attrs = {
            "id": self.id,
            "parentID": self.parent_id
        }

        root = xel(self.qname,
                   xel("upnp:class", self.uclass),
                   xel("dc:title", self.path.name), **attrs)

        if not self.path.is_dir():
            root.append(xel("dlna:res", self.location, protocolInfo=f"http-get:*:{self.mime}:DLNA.ORG_OP=01"))

        return root
