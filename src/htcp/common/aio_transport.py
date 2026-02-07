"""
HTCP Async Transport Module
Asynchronous I/O operations for HTCP protocol.
"""

import asyncio
import struct
from typing import Optional

from .constants import MAGIC_BYTES, PROTOCOL_VERSION, HEADER_SIZE, MAX_PAYLOAD_SIZE
from ..exceptions import (
    ConnectionError as HTCPConnectionError,
    ProtocolError,
    MaxPayloadExceededError,
    UnknownPacketTypeError,
)


async def recv_exact(
    reader: asyncio.StreamReader,
    size: int,
    timeout: Optional[float] = None
) -> bytes:
    """
    Receive exact number of bytes from async stream.

    Args:
        reader: Async stream reader
        size: Exact number of bytes to receive
        timeout: Optional timeout in seconds

    Returns:
        Received bytes

    Raises:
        HTCPConnectionError: If connection is closed before receiving all bytes
        TimeoutError: If operation times out
    """
    try:
        if timeout is not None:
            data = await asyncio.wait_for(reader.readexactly(size), timeout=timeout)
        else:
            data = await reader.readexactly(size)
        return data
    except asyncio.IncompleteReadError as e:
        raise HTCPConnectionError(
            f"Connection closed while reading (got {len(e.partial)}/{size} bytes)"
        ) from e
    except asyncio.TimeoutError:
        raise HTCPConnectionError("Read timeout") from None


async def recv_packet(
    reader: asyncio.StreamReader,
    max_payload_size: int = MAX_PAYLOAD_SIZE,
    timeout: Optional[float] = None
) -> 'Packet':
    """
    Receive a complete packet from async stream.

    Args:
        reader: Async stream reader
        max_payload_size: Maximum allowed payload size
        timeout: Optional timeout in seconds

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
    header = await recv_exact(reader, HEADER_SIZE, timeout)

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
        payload = await recv_exact(reader, payload_length, timeout)

    return Packet(packet_type, payload)


async def send_packet(
    writer: asyncio.StreamWriter,
    packet: 'Packet',
    timeout: Optional[float] = None
) -> None:
    """
    Send a packet over async stream.

    Args:
        writer: Async stream writer
        packet: Packet to send
        timeout: Optional timeout in seconds

    Raises:
        HTCPConnectionError: If connection is closed
    """
    try:
        writer.write(packet.to_bytes())
        if timeout is not None:
            await asyncio.wait_for(writer.drain(), timeout=timeout)
        else:
            await writer.drain()
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        raise HTCPConnectionError(f"Failed to send packet: {e}") from e
    except asyncio.TimeoutError:
        raise HTCPConnectionError("Write timeout") from None
