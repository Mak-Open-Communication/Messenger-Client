"""
HTCP Async Server Connection Module
Async client connection management for server.
"""

import asyncio
from typing import Optional, Tuple


class AsyncServerClientConnection:
    """
    Represents a connected client on the async server side.

    Wrapper around async streams with connection state.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        address: Tuple[str, int],
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None
    ):
        self._reader = reader
        self._writer = writer
        self._address = address
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._connected = True
        self._lock = asyncio.Lock()

    @property
    def reader(self) -> asyncio.StreamReader:
        """Get the stream reader."""
        return self._reader

    @property
    def writer(self) -> asyncio.StreamWriter:
        """Get the stream writer."""
        return self._writer

    @property
    def address(self) -> Tuple[str, int]:
        """Get client address (host, port)."""
        return self._address

    @property
    def read_timeout(self) -> Optional[float]:
        """Get read timeout."""
        return self._read_timeout

    @read_timeout.setter
    def read_timeout(self, value: Optional[float]) -> None:
        self._read_timeout = value

    @property
    def write_timeout(self) -> Optional[float]:
        """Get write timeout."""
        return self._write_timeout

    @property
    def connected(self) -> bool:
        """Check if client is still connected."""
        return self._connected

    @connected.setter
    def connected(self, value: bool) -> None:
        """Set connection state."""
        self._connected = value

    async def close(self) -> None:
        """Close the connection."""
        async with self._lock:
            self._connected = False
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

    def __repr__(self) -> str:
        return f"AsyncServerClientConnection({self._address[0]}:{self._address[1]}, connected={self.connected})"


class AsyncConnectionRegistry:
    """
    Async registry for active client connections.

    Provides atomic operations for connection management.
    """

    def __init__(self, max_connections: int = 0):
        """
        Initialize connection registry.

        Args:
            max_connections: Maximum allowed connections (0 = unlimited)
        """
        self._connections: dict[Tuple[str, int], AsyncServerClientConnection] = {}
        self._lock = asyncio.Lock()
        self._max_connections = max_connections

    async def try_add(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        address: Tuple[str, int],
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None
    ) -> Optional[AsyncServerClientConnection]:
        """
        Atomically check limits and add a connection.

        Args:
            reader: Stream reader
            writer: Stream writer
            address: Client address
            read_timeout: Optional read timeout
            write_timeout: Optional write timeout

        Returns:
            AsyncServerClientConnection if added successfully, None if limit reached
        """
        async with self._lock:
            # Atomic check and add
            if self._max_connections > 0 and len(self._connections) >= self._max_connections:
                return None

            conn = AsyncServerClientConnection(
                reader, writer, address, read_timeout, write_timeout
            )
            self._connections[address] = conn
            return conn

    async def remove(self, address: Tuple[str, int]) -> Optional[AsyncServerClientConnection]:
        """
        Remove a connection by address.

        Args:
            address: Client address to remove

        Returns:
            Removed connection or None if not found
        """
        async with self._lock:
            return self._connections.pop(address, None)

    async def get(self, address: Tuple[str, int]) -> Optional[AsyncServerClientConnection]:
        """Get a connection by address."""
        async with self._lock:
            return self._connections.get(address)

    async def close_all(self) -> None:
        """Close all connections."""
        async with self._lock:
            for conn in self._connections.values():
                await conn.close()
            self._connections.clear()

    async def count(self) -> int:
        """Get current connection count."""
        async with self._lock:
            return len(self._connections)
