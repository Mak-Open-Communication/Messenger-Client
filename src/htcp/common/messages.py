"""
HTCP Messages Module
High-level message types for HTCP protocol.
"""

from typing import Any, Dict

from .proto import Packet, PacketType, ErrorCode
from .serialization import serialize, deserialize


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

    def __init__(
        self,
        success: bool,
        result: Any = None,
        error_code: ErrorCode = ErrorCode.SUCCESS,
        error_message: str = ""
    ):
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


class DisconnectPacket:
    """Disconnect notification packet."""

    def to_packet(self) -> Packet:
        return Packet(PacketType.DISCONNECT, b'')

    @classmethod
    def from_packet(cls, packet: Packet) -> 'DisconnectPacket':
        return cls()


class SubscribeRequest:
    """Subscribe request from client to server."""

    def __init__(self, subscription_id: str, event_type: str, arguments: Dict[str, Any]):
        self.subscription_id = subscription_id
        self.event_type = event_type
        self.arguments = arguments

    def to_packet(self) -> Packet:
        payload = serialize({
            "subscription_id": self.subscription_id,
            "event_type": self.event_type,
            "arguments": self.arguments
        })
        return Packet(PacketType.SUBSCRIBE_REQUEST, payload)

    @classmethod
    def from_packet(cls, packet: Packet) -> 'SubscribeRequest':
        data, _ = deserialize(packet.payload)
        return cls(
            subscription_id=data.get("subscription_id", ""),
            event_type=data.get("event_type", ""),
            arguments=data.get("arguments", {})
        )


class UnsubscribeRequest:
    """Unsubscribe request from client to server."""

    def __init__(self, subscription_id: str):
        self.subscription_id = subscription_id

    def to_packet(self) -> Packet:
        payload = serialize({
            "subscription_id": self.subscription_id
        })
        return Packet(PacketType.UNSUBSCRIBE_REQUEST, payload)

    @classmethod
    def from_packet(cls, packet: Packet) -> 'UnsubscribeRequest':
        data, _ = deserialize(packet.payload)
        return cls(subscription_id=data.get("subscription_id", ""))


class SubscribeData:
    """Data packet for subscription from server to client."""

    def __init__(self, subscription_id: str, data: Any):
        self.subscription_id = subscription_id
        self.data = data

    def to_packet(self) -> Packet:
        payload = serialize({
            "subscription_id": self.subscription_id,
            "data": self.data
        })
        return Packet(PacketType.SUBSCRIBE_DATA, payload)

    @classmethod
    def from_packet(cls, packet: Packet, data_type=None) -> 'SubscribeData':
        raw, _ = deserialize(packet.payload)
        return cls(
            subscription_id=raw.get("subscription_id", ""),
            data=raw.get("data")
        )


class SubscribeEnd:
    """End of subscription stream from server to client."""

    def __init__(self, subscription_id: str):
        self.subscription_id = subscription_id

    def to_packet(self) -> Packet:
        payload = serialize({
            "subscription_id": self.subscription_id
        })
        return Packet(PacketType.SUBSCRIBE_END, payload)

    @classmethod
    def from_packet(cls, packet: Packet) -> 'SubscribeEnd':
        data, _ = deserialize(packet.payload)
        return cls(subscription_id=data.get("subscription_id", ""))


class SubscribeError:
    """Error in subscription from server to client."""

    def __init__(self, subscription_id: str, error_code: ErrorCode, message: str):
        self.subscription_id = subscription_id
        self.error_code = error_code
        self.message = message

    def to_packet(self) -> Packet:
        payload = serialize({
            "subscription_id": self.subscription_id,
            "error_code": int(self.error_code),
            "message": self.message
        })
        return Packet(PacketType.SUBSCRIBE_ERROR, payload)

    @classmethod
    def from_packet(cls, packet: Packet) -> 'SubscribeError':
        data, _ = deserialize(packet.payload)
        return cls(
            subscription_id=data.get("subscription_id", ""),
            error_code=ErrorCode(data.get("error_code", 0)),
            message=data.get("message", "")
        )
