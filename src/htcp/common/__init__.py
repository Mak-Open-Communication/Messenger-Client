"""HTCP Common Package - shared utilities and protocol definitions."""

from .constants import (
    MAGIC_BYTES,
    PROTOCOL_VERSION,
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_WRITE_TIMEOUT,
    DEFAULT_LISTEN_BACKLOG,
    DEFAULT_MAX_CONNECTIONS,
)
from .serialization import serialize, deserialize, TypeTag
from .proto import Packet, PacketType, ErrorCode
from .messages import (
    HandshakeRequest,
    HandshakeResponse,
    TransactionCall,
    TransactionResult,
    ErrorPacket,
    DisconnectPacket,
    SubscribeRequest,
    UnsubscribeRequest,
    SubscribeData,
    SubscribeEnd,
    SubscribeError,
)
from .transport import recv_exact, recv_packet, send_packet
from .utils import get_function_signature, get_return_type, convert_to_type

__all__ = [
    # Constants
    'MAGIC_BYTES', 'PROTOCOL_VERSION', 'HEADER_SIZE', 'MAX_PAYLOAD_SIZE',
    'DEFAULT_CONNECT_TIMEOUT', 'DEFAULT_READ_TIMEOUT', 'DEFAULT_WRITE_TIMEOUT',
    'DEFAULT_LISTEN_BACKLOG', 'DEFAULT_MAX_CONNECTIONS',
    # Serialization
    'serialize', 'deserialize', 'TypeTag',
    # Protocol
    'Packet', 'PacketType', 'ErrorCode',
    # Messages
    'HandshakeRequest', 'HandshakeResponse', 'TransactionCall',
    'TransactionResult', 'ErrorPacket', 'DisconnectPacket',
    'SubscribeRequest', 'UnsubscribeRequest', 'SubscribeData',
    'SubscribeEnd', 'SubscribeError',
    # Transport
    'recv_exact', 'recv_packet', 'send_packet',
    # Utils
    'get_function_signature', 'get_return_type', 'convert_to_type',
]
