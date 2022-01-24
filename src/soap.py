"""Simple Object Access Protocol"""

from . import xml_
from . import http_
from . import media
from . import didl
from . import net
from enum import IntEnum
from http import HTTPStatus
from .xml_ import element as xel
from xml.etree import ElementTree as Et
from pathlib import Path


class Header(http_.Header):
    """HTTP headers"""

    SOAP_ACTION = "SOAPACTION"


class Status(IntEnum):
    """SOAP status codes"""

    def __new__(cls, value: int, phrase: str, description: str = ""):
        """Instantiate status code"""
        self = int.__new__(cls, value)
        self.__init__(value, phrase, description)
        return self

    def __init__(self, value: int, phrase: str, description: str = ""):
        """Instantiate status code"""
        self._value_ = value
        self.phrase = phrase
        self.description = description

    INVALID_ACTION = 401, "Invalid Action", "No action by that name at this service"  # noqa: E501
    INVALID_ARGS = 402, "Invalid Args", "Could be any of the following: not enough in args, args in the wrong order, one or more in args are of the wrong data type"  # noqa: E501
    INVALID_VAR = 404, "Invalid Var", "See UPnP Device Architecture section on Control"  # noqa: E501
    ACTION_FAILD = 501, "Action Failed", "Is allowed to be returned if current state of service prevents invoking that action"  # noqa: E501
    ARGUMENT_VALUE_INVALID = 600, "Argument Value Invalid", "The argument value is invalid"  # noqa: E501
    ARGUMENT_VALUE_OUT = 601, "Argument Value Out of Range", "An argument value is less than the minimum or more than the maximum value of the allowed value range, or is not in the allowed value list"  # noqa: E501
    OPTIONAL_ACTION_NOT_IMPLEMENTED = 602, "Optional Action Not Implemented", "The requested action is optional and is not implemented by the device"  # noqa: E501
    OUT_OF_MEMORY = 603, "Out of Memory", "The device does not have sufficient memory available to complete the  action"  # noqa: E501
    HUMAN_INTERVENTION_REQUIRED = 604, "Human Intervention Required", "The device has encountered an error condition which it cannot resolve itself and required human intervention such as a reset or power cycle"  # noqa: E501
    STRING_ARGUMENT_TOO_LONG = 605, "String Argument Too Long", "A string argument is too long for the device to handle properly"  # noqa: E501
    # 606-612 Reserved These ErrorCodes are reserved for UPnP DeviceSecurity
    # 613-699 TBD Common action errors. Defined by UPnP Forum Technical Committee
    NO_SUCH_OBJECT = 701, "No such object", "The specified ObjectID is invalid"  # noqa: E501
    INVALID_CURRENTTAGVALUE = 702, "Invalid CurrentTagValue", "The tag/value pair(s) listed in CurrentTagValue do not match the current state of the CDS"  # noqa: E501
    INVALID_NEWTAGVALUE = 703, "Invalid NewTagValue", "The specified value for the NewTagValue parameter is invalid"  # noqa: E501
    REQUIRED_TAG = 704, "Required tag", "Unable to delete a required tag"  # noqa: E501
    READ_ONLY_TAG = 705, "Read only tag", "Unable to update a read only tag"  # noqa: E501
    PARAMETER_MISMATCH = 706, "Parameter Mismatch", "The number of tag/value pairs (including empty placeholders) in CurrentTagValue and NewTagValue do not match"  # noqa: E501
    UNSUPPORTED_OR_INVALID_SEARCH_CRITERIA = 708, "Unsupported or invalid search criteria", "The search criteria specified is not supported or is invalid"  # noqa: E501
    UNSUPPORTED_OR_INVALID_SORT_CRITERIA = 709, "Unsupported or invalid sort criteria", "The sort criteria specified is not supported or is invalid"  # noqa: E501
    NO_SUCH_CONTAINER = 710, "No such container", "The specified ContainerID is invalid or identifies an object that is not a container"  # noqa: E501
    RESTRICTED_OBJECT = 711, "Restricted object", "Operation failed because the restricted attribute of object is set to true"  # noqa: E501
    BAD_METADATA = 712, "Bad metadata", "Operation fails because it would result in invalid or disallowed metadata in current object"  # noqa: E501
    RESTRICTED_PARENT = 713, "Restricted parent object", "Operation failed because the restricted attribute of parent object is set to true"  # noqa: E501
    NO_SUCH_RESOURCE = 714, "No such source resource", "Cannot identify the specified source resource"  # noqa: E501
    SOURCE_RESOURCE_ACCES_DENIED = 715, "Source resource access denied", "Cannot access the specified source resource"  # noqa: E501
    TRANSFER_BUSY = 716, "Transfer busy", "Another file transfer is not accepted"  # noqa: E501
    NO_SUCH_FILE_TRANSFER = 717, "No such file transfer", "The file transfer specified by TransferID does not exist"  # noqa: E501
    NO_SUCH_DESTINATION_RESOURCE = 718, "No such destination resource", "Cannot identify the specified destination resource"  # noqa: E501
    DESTINATION_RESOURCE_ACCESS_DENIED = 719, "Destination resource access denied", "Cannot access the specified destination resource"  # noqa: E501
    CANNOT_PROCESS_THE_REQUEST = 720, "Cannot process the request", "Cannot process the request"  # noqa: E501
    # 721-799 TBD Action-specific errors defined by UPnP Forum working committee
    # 800-899 TBD Action-specific errors for non-standard actions defined by UPnP vendor


class Handler:
    """SOAP handler with HTTP-like interface"""

    def __init__(self, request: media.Handler):
        """Prepare and handle request"""
        self.request = request
        self.server = self.request.server
        self.paths = self.server.paths
        self.handle()

    def handle(self) -> None:
        """Handle request with do methods"""
        if not self.parse_request():
            return

        if method := getattr(self, f"do_{self.command}", None):
            method()
        else:
            self.send_error(Status.INVALID_ACTION)

    def parse_request(self) -> bool:
        """Parse headers and request data"""
        sep = "#"
        size = int(self.request.headers.get(Header.CONTENT_LENGTH, 0))
        action = self.request.headers.get(Header.SOAP_ACTION, sep).strip('"')

        self.service, self.command = action.split(sep)
        self.command = net.safe_identifier(self.command)
        data = self.request.rfile.read(size).decode()

        try:
            self.data = Et.fromstring(data)
        except Et.ParseError:
            self.send_error(Status.INVALID_ARGS)
            return False

        return True

    def log_error(self, format: str, *args) -> None:
        self.request.log_error(format, *args)

    def log_message(self, format: str, *args) -> None:
        self.request.log_message(format, *args)

    def send_error(self, code: Status) -> None:
        """Send error reply"""
        self.log_error("code %d, message %s", code.value, code.phrase)
        self.request.send_template("fault", HTTPStatus.INTERNAL_SERVER_ERROR,
                                   errorCode=str(code.value), errorDescription=code.phrase)

    @property
    def browse_object(self) -> didl.Object:
        try:
            id = xml_.find_text(self.data, "ObjectID")
        except AttributeError:
            id = xml_.find_text(self.data, "ContainerID")
        url = self.paths.MEDIA.as_uri(self.request.host)
        return didl.Object(self.server.media, url, id, self.command)

    @property
    def browse_slice(self) -> slice:
        start = int(xml_.find_text(self.data, "StartingIndex"))
        size = int(xml_.find_text(self.data, "RequestedCount"))
        return slice(start, start + size)

    def do_getsearchcapabilities(self):
        self.request.send_file(Path("etc/templates/search.xml"))

    def do_search(self):
        self.do_browse()

    def do_browse(self):
        """Handle a Browse request"""
        element = self.browse_object  # TODO: check in TV, is BrowseMetadata necesary in allow list?
        self.log_message('"%s %s SOAP"', self.command.upper(), element.id_path)

        children = [child.element for child in element[self.browse_slice]]
        result = xml_.serialize(xel("dlna:DIDL-Lite", *children))
        self.request.send_template(f"{self.command}-response", Result=result, UpdateID=element.update,
                                   TotalMatches=len(element), NumberReturned=len(children))
