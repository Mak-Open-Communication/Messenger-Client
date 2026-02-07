"""
HTCP Protocol Module
Defines the binary protocol format for client-server communication.
"""

import struct
import warnings

from enum import IntEnum
from typing import Any, Dict

from .serialization import serialize, deserialize
from .constants import MAGIC_BYTES, PROTOCOL_VERSION, HEADER_SIZE, MAX_PAYLOAD_SIZE


class PacketType(IntEnum):
    """Types of packets in HTCP protocol."""
    # Client -> Server
    HANDSHAKE_REQUEST = 0x01
    TRANSACTION_CALL = 0x02
    DISCONNECT = 0x03
    SUBSCRIBE_REQUEST = 0x04
    UNSUBSCRIBE_REQUEST = 0x05

    # Server -> Client
    HANDSHAKE_RESPONSE = 0x11
    TRANSACTION_RESULT = 0x12
    ERROR = 0x13
    SUBSCRIBE_DATA = 0x14
    SUBSCRIBE_END = 0x15
    SUBSCRIBE_ERROR = 0x16


class ErrorCode(IntEnum):
    """Error codes for protocol errors."""
    SUCCESS = 0
    UNKNOWN_TRANSACTION = 1
    INVALID_ARGUMENTS = 2
    EXECUTION_ERROR = 3
    PROTOCOL_ERROR = 4
    INTERNAL_ERROR = 5


class Packet:
    """
    HTCP Protocol Packet.

    Binary format:
    +--------+--------+------+--------+----------+---------+
    | MAGIC  | VERSION| TYPE | LENGTH | RESERVED | PAYLOAD |
    | 4 bytes| 1 byte |1 byte| 4 bytes| 2 bytes  | N bytes |
    +--------+--------+------+--------+----------+---------+
    """

    def __init__(self, packet_type: PacketType, payload: bytes = b''):
        self.packet_type = packet_type
        self.payload = payload

    def to_bytes(self) -> bytes:
        """Serialize packet to bytes."""
        header = (
            MAGIC_BYTES +
            struct.pack('>B', PROTOCOL_VERSION) +
            struct.pack('>B', self.packet_type) +
            struct.pack('>I', len(self.payload)) +
            b'\x00\x00'  # Reserved bytes
        )
        return header + self.payload

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Packet':
        """Deserialize packet from bytes."""
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Data too short for packet header: {len(data)} < {HEADER_SIZE}")

        magic = data[:4]
        if magic != MAGIC_BYTES:
            raise ValueError(f"Invalid magic bytes: {magic}")

        version = data[4]
        if version != PROTOCOL_VERSION:
            raise ValueError(f"Unsupported protocol version: {version}")

        packet_type = PacketType(data[5])
        payload_length = struct.unpack('>I', data[6:10])[0]

        if len(data) < HEADER_SIZE + payload_length:
            raise ValueError(f"Incomplete packet: expected {HEADER_SIZE + payload_length}, got {len(data)}")

        payload = data[HEADER_SIZE:HEADER_SIZE + payload_length]
        return cls(packet_type, payload)

    @classmethod
    def read_from_socket(cls, sock, max_payload_size: int = MAX_PAYLOAD_SIZE) -> 'Packet':
        """
        Read a complete packet from socket.

        Deprecated: Use htcp.common.transport.recv_packet() instead.
        """
        warnings.warn(
            "Packet.read_from_socket() is deprecated, use recv_packet() from htcp.common.transport",
            DeprecationWarning,
            stacklevel=2
        )
        from .transport import recv_packet
        return recv_packet(sock, max_payload_size)


class HandshakeRequest:
    """Handshake request from client to server."""

    def to_packet(self) -> Packet:
        return Packet(PacketType.HANDSHAKE_REQUEST, b'')

    @classmethod
    def from_packet(cls, packet: Packet) -> 'HandshakeRequest':
        return cls()


class HandshakeResponse:
    """Handshake response from server to client."""

    def __init__(self, server_name: str, transactions: list[str]):
        self.server_name = server_name
        self.transactions = transactions

    def to_packet(self) -> Packet:
        payload = serialize({
            "server_name": self.server_name,
            "transactions": self.transactions
        })
        return Packet(PacketType.HANDSHAKE_RESPONSE, payload)

    @classmethod
    def from_packet(cls, packet: Packet) -> 'HandshakeResponse':
        data, _ = deserialize(packet.payload)
        return cls(
            server_name=data.get("server_name", "unknown"),
            transactions=data.get("transactions", [])
        )


class TransactionCall:
    """Transaction call from client to server."""

    def __init__(self, transaction_code: str, arguments: Dict[str, Any]):
        self.transaction_code = transaction_code
        self.arguments = arguments

    def to_packet(self) -> Packet:
        payload = serialize({
            "transaction": self.transaction_code,
            "arguments": self.arguments
        })
        return Packet(PacketType.TRANSACTION_CALL, payload)

    @classmethod
    def from_packet(cls, packet: Packet) -> 'TransactionCall':
        data, _ = deserialize(packet.payload)
        return cls(
            transaction_code=data.get("transaction", ""),
            arguments=data.get("arguments", {})
        )


class TransactionResult:
    """Transaction result from server to client."""

    def __init__(self, success: bool, result: Any = None, error_code: ErrorCode = ErrorCode.SUCCESS, error_message: str = ""):
        self.success = success
        self.result = result
        self.error_code = error_code
        self.error_message = error_message

    def to_packet(self) -> Packet:
        payload = serialize({
            "success": self.success,
            "result": self.result,
            "error_code": int(self.error_code),
            "error_message": self.error_message
        })
        return Packet(PacketType.TRANSACTION_RESULT, payload)

    @classmethod
    def from_packet(cls, packet: Packet, result_type=None) -> 'TransactionResult':
        data, _ = deserialize(packet.payload)

        result = data.get("result")

        # If we have an expected result type and result is dict-like from dataclass
        if result_type is not None and result is not None:
            from .serialization import deserialize as deser
            import dataclasses
            if dataclasses.is_dataclass(result_type) and isinstance(result, dict):
                # Result was serialized as dataclass but came back as dict
                # This happens when the result was serialized without type info
                pass

        return cls(
            success=data.get("success", False),
            result=result,
            error_code=ErrorCode(data.get("error_code", 0)),
            error_message=data.get("error_message", "")
        )


class ErrorPacket:
    """Error packet from server to client."""

    def __init__(self, error_code: ErrorCode, message: str):
        self.error_code = error_code
        self.message = message

    def to_packet(self) -> Packet:
        payload = serialize({
            "error_code": int(self.error_code),
            "message": self.message
        })
        return Packet(PacketType.ERROR, payload)

    @classmethod
    def from_packet(cls, packet: Packet) -> 'ErrorPacket':
        data, _ = deserialize(packet.payload)
        return cls(
            error_code=ErrorCode(data.get("error_code", 0)),
            message=data.get("message", "")
        )
