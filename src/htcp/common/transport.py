"""
HTCP Transport Module
Synchronous socket I/O operations for HTCP protocol.
"""

import socket
import struct
import warnings
from typing import Optional

from .constants import MAGIC_BYTES, PROTOCOL_VERSION, HEADER_SIZE, MAX_PAYLOAD_SIZE
from ..exceptions import (
    ConnectionError as HTCPConnectionError,
    ProtocolError,
    MaxPayloadExceededError,
    UnknownPacketTypeError,
)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """
    Receive exact number of bytes from socket.

    Uses bytearray and memoryview for O(n) performance instead of O(n^2)
    from repeated bytes concatenation.

    Args:
        sock: Socket to read from
        size: Exact number of bytes to receive

    Returns:
        Received bytes

    Raises:
        HTCPConnectionError: If connection is closed before receiving all bytes
    """
    buffer = bytearray(size)
    view = memoryview(buffer)
    received = 0

    while received < size:
        chunk_size = sock.recv_into(view[received:], size - received)
        if chunk_size == 0:
            raise HTCPConnectionError(
                f"Connection closed while reading (got {received}/{size} bytes)"
            )
        received += chunk_size

    return bytes(buffer)


def recv_packet(sock: socket.socket, max_payload_size: int = MAX_PAYLOAD_SIZE) -> 'Packet':
    """
    Receive a complete packet from socket.

    Args:
        sock: Socket to read from
        max_payload_size: Maximum allowed payload size

    Returns:
        Received Packet object

    Raises:
        HTCPConnectionError: If connection is closed
        ProtocolError: If packet is malformed
        MaxPayloadExceededError: If payload exceeds max size
        UnknownPacketTypeError: If packet type is unknown
    """
    from .proto import Packet, PacketType

    # Read header
    header = recv_exact(sock, HEADER_SIZE)

    # Validate magic bytes
    magic = header[:4]
    if magic != MAGIC_BYTES:
        raise ProtocolError(f"Invalid magic bytes: {magic!r}")

    # Validate version
    version = header[4]
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"Unsupported protocol version: {version}")

    # Parse packet type with validation
    packet_type_byte = header[5]
    try:
        packet_type = PacketType(packet_type_byte)
    except ValueError:
        raise UnknownPacketTypeError(packet_type_byte)

    # Parse payload length
    payload_length = struct.unpack('>I', header[6:10])[0]

    # Validate payload size
    if payload_length > max_payload_size:
        raise MaxPayloadExceededError(payload_length, max_payload_size)

    # Read payload
    payload = b''
    if payload_length > 0:
        payload = recv_exact(sock, payload_length)

    return Packet(packet_type, payload)


def send_packet(sock: socket.socket, packet: 'Packet') -> None:
    """
    Send a packet over socket.

    Args:
        sock: Socket to send to
        packet: Packet to send

    Raises:
        HTCPConnectionError: If connection is closed
    """
    try:
        sock.sendall(packet.to_bytes())
    except (BrokenPipeError, OSError) as e:
        raise HTCPConnectionError(f"Failed to send packet: {e}") from e


# Deprecated function for backwards compatibility
def _recv_exact(sock: socket.socket, size: int) -> bytes:
    """
    Deprecated: Use recv_exact() instead.
    """
    warnings.warn(
        "_recv_exact is deprecated, use recv_exact from htcp.common.transport",
        DeprecationWarning,
        stacklevel=2
    )
    try:
        return recv_exact(sock, size)
    except HTCPConnectionError:
        # Return partial data for backwards compatibility
        buffer = bytearray()
        while len(buffer) < size:
            try:
                chunk = sock.recv(size - len(buffer))
                if not chunk:
                    return bytes(buffer)
                buffer.extend(chunk)
            except Exception:
                return bytes(buffer)
        return bytes(buffer)
