"""
HTCP Exceptions Module
Exception hierarchy for HTCP protocol.
"""


class HTCPError(Exception):
    """Base exception for all HTCP errors."""
    pass


class ConnectionError(HTCPError):
    """Connection-related errors."""
    pass


class ProtocolError(HTCPError):
    """Protocol-level errors (invalid packets, version mismatch, etc.)."""
    pass


class SerializationError(HTCPError):
    """Errors during serialization/deserialization."""
    pass


class TransactionError(HTCPError):
    """Transaction execution errors."""
    pass


class TimeoutError(HTCPError):
    """Operation timeout errors."""
    pass


class MaxPayloadExceededError(ProtocolError):
    """Payload size exceeds maximum allowed."""

    def __init__(self, size: int, max_size: int):
        self.size = size
        self.max_size = max_size
        super().__init__(f"Payload size {size} exceeds maximum {max_size}")


class UnknownPacketTypeError(ProtocolError):
    """Unknown packet type received."""

    def __init__(self, packet_type: int):
        self.packet_type = packet_type
        super().__init__(f"Unknown packet type: 0x{packet_type:02X}")


class HandshakeError(ConnectionError):
    """Handshake failed."""
    pass
