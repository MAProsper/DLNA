"""XML constants and function helpers"""

import re
from pathlib import Path
from xml.etree import ElementTree as Et


__all__ = (
    "parse", "serialize", "format", "element", "find_text"
)


namespaces = {
    # SOAP protocol
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",

    # DIDL metadata
    "dc": "http://purl.org/dc/elements/1.1/",
    "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
    "dlna": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",

    # UPnP media server
    "dev": "urn:schemas-upnp-org:device-1-0",
    "ctrl": "urn:schemas-upnp-org:control-1-0",
    "srv": "urn:schemas-upnp-org:service-1-0",
    "cd": "urn:schemas-upnp-org:service:ContentDirectory:1",
}

for prefix, uri in namespaces.items():
    Et.register_namespace(prefix, uri)

_re_namespace = re.compile(r"{(.+)}")


def _qname(namespace: str, local: str) -> str:
    """Construct a namespaced tagname"""
    return str(Et.QName(namespaces[namespace], local))


def element(qname: str, *args, **kwds) -> Et.Element:
    """Construct a namespaced element"""
    namespace, local = qname.split(":")
    element = Et.Element(_qname(namespace, local), {
        _qname(namespace, key): str(value)
        for key, value in kwds.items()
    })

    for arg in args:
        if isinstance(arg, Et.Element):
            element.append(arg)
        else:
            element.text = str(arg)

    return element


def parse(path: Path) -> Et.Element:
    """Parse XML data from a Path object"""
    return Et.parse(str(path)).getroot()


def serialize(element: Et.Element) -> str:
    """Serialize a XML element to a string"""
    match = _re_namespace.search(element.tag)
    if match is None or element.find(".//{}*") is not None:
        namespace = None
    else:
        namespace = match[1]
    return Et.tostring(element, encoding="unicode", xml_declaration=True, default_namespace=namespace)


def format(element: Et.Element, /, **kwds) -> Et.Element:
    """Format XML tag's text content"""
    for key, value in kwds.items():
        el = element.find(f".//{{*}}{key}")
        if el is None:
            raise AttributeError(key)
        else:
            el.text = str(value)
    return element


def find_text(element: Et.Element, qname: str) -> str:
    """Find element and get its inner text (default empty)"""
    el = element.find(f".//{{*}}{qname}")
    if el is None:
        raise AttributeError(qname)
    elif el.text:
        return el.text
    else:
        return ""
