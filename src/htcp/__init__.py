"""
HTCP - Binary TCP Protocol for Python

A library for building TCP-based client-server applications
with automatic type serialization and RPC support.
"""

from .server import Server
from .client import Client
from .aio_server import AsyncServer
from .aio_client import AsyncClient
from .exceptions import (
    HTCPError,
    ConnectionError,
    ProtocolError,
    SerializationError,
    TransactionError,
    TimeoutError,
    MaxPayloadExceededError,
    UnknownPacketTypeError,
    HandshakeError,
)

__version__ = "0.2.0"
__all__ = [
    # Sync
    'Server',
    'Client',
    # Async
    'AsyncServer',
    'AsyncClient',
    # Exceptions
    'HTCPError',
    'ConnectionError',
    'ProtocolError',
    'SerializationError',
    'TransactionError',
    'TimeoutError',
    'MaxPayloadExceededError',
    'UnknownPacketTypeError',
    'HandshakeError',
]
