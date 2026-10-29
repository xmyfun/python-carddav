"""carddav - a minimal, dependency-light CardDAV client library.

The public API surface is re-exported here (and only here). Internal modules
(``_transport`` / ``_xml`` / ``_dav``) are not part of the API.
"""

from ._http import Backend, Response
from ._version import __version__
from .addressbook import AddressBook, Change
from .auth import BasicAuth, BearerAuth, DigestAuth
from .card import Card
from .client import DAVClient, get_davclient
from .errors import (
    AuthenticationError,
    Conflict,
    DAVError,
    DiscoveryError,
    InsufficientStorage,
    MissingUIDError,
    NotFound,
    PermissionDenied,
    PreconditionFailed,
    SyncTokenInvalid,
    TransportError,
    UnsafeXML,
)
from .principal import Principal

__all__ = [
    "get_davclient",
    "DAVClient",
    "Principal",
    "AddressBook",
    "Card",
    "Change",
    "BasicAuth",
    "DigestAuth",
    "BearerAuth",
    "Backend",
    "Response",
    "DAVError",
    "AuthenticationError",
    "PermissionDenied",
    "NotFound",
    "Conflict",
    "PreconditionFailed",
    "InsufficientStorage",
    "SyncTokenInvalid",
    "MissingUIDError",
    "UnsafeXML",
    "TransportError",
    "DiscoveryError",
    "__version__",
]
