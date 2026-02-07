"""
HTCP Async Client Connection Module
Async connection management for client.
"""

import asyncio
from typing import Optional

from ..common.constants import DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT, DEFAULT_WRITE_TIMEOUT
from ..common.proto import Packet
from ..common.aio_transport import recv_packet, send_packet
from ..exceptions import ConnectionError as HTCPConnectionError


class AsyncClientConnection:
    """
    Async client connection wrapper.

    Provides async access to socket operations.
    """

    def __init__(
        self,
        host: str,
        port: int,
        connect_timeout: Optional[float] = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: Optional[float] = DEFAULT_READ_TIMEOUT,
        write_timeout: Optional[float] = DEFAULT_WRITE_TIMEOUT,
    ):
        self._host = host
        self._port = port
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def connected(self) -> bool:
        """Check if connection is active."""
        return self._connected

    async def connect(self) -> None:
        """
        Establish connection to server.

        Raises:
            HTCPConnectionError: If connection fails
        """
        async with self._lock:
            if self._connected:
                return

            try:
                coro = asyncio.open_connection(self._host, self._port)
                if self._connect_timeout is not None:
                    self._reader, self._writer = await asyncio.wait_for(
                        coro, timeout=self._connect_timeout
                    )
                else:
                    self._reader, self._writer = await coro

                self._connected = True

            except asyncio.TimeoutError:
                await self._cleanup()
                raise HTCPConnectionError(
                    f"Connection to {self._host}:{self._port} timed out"
                ) from None
            except (OSError, ConnectionRefusedError) as e:
                await self._cleanup()
                raise HTCPConnectionError(
                    f"Failed to connect to {self._host}:{self._port}: {e}"
                ) from e

    async def disconnect(self) -> None:
        """Close the connection."""
        async with self._lock:
            self._connected = False
            await self._cleanup()

    async def send(self, packet: Packet) -> None:
        """
        Send a packet to server.

        Args:
            packet: Packet to send

        Raises:
            HTCPConnectionError: If not connected or send fails
        """
        async with self._lock:
            if not self._connected or self._writer is None:
                raise HTCPConnectionError("Not connected")
            try:
                await send_packet(self._writer, packet, self._write_timeout)
            except Exception as e:
                self._connected = False
                raise HTCPConnectionError(f"Send failed: {e}") from e

    async def receive(self) -> Packet:
        """
        Receive a packet from server.

        Returns:
            Received Packet

        Raises:
            HTCPConnectionError: If not connected or receive fails
        """
        async with self._lock:
            if not self._connected or self._reader is None:
                raise HTCPConnectionError("Not connected")
            try:
                return await recv_packet(self._reader, timeout=self._read_timeout)
            except Exception as e:
                self._connected = False
                raise HTCPConnectionError(f"Receive failed: {e}") from e

    async def _cleanup(self) -> None:
        """Clean up connection resources."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._reader = None

    async def __aenter__(self) -> 'AsyncClientConnection':
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()
