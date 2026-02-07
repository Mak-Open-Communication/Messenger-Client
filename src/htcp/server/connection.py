"""
HTCP Server Connection Module
Client connection management for server.
"""

import socket
import threading
from typing import Optional, Tuple


class ServerClientConnection:
    """
    Represents a connected client on the server side.

    Thread-safe wrapper around a client socket with connection state.
    """

    def __init__(
        self,
        sock: socket.socket,
        address: Tuple[str, int],
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None
    ):
        self._socket = sock
        self._address = address
        self._connected = True
        self._lock = threading.Lock()

        # Set socket timeouts
        if read_timeout is not None or write_timeout is not None:
            # Use the larger timeout for the socket
            timeout = max(
                read_timeout or 0,
                write_timeout or 0
            )
            if timeout > 0:
                self._socket.settimeout(timeout)

    @property
    def socket(self) -> socket.socket:
        """Get the underlying socket."""
        return self._socket

    @property
    def address(self) -> Tuple[str, int]:
        """Get client address (host, port)."""
        return self._address

    @property
    def connected(self) -> bool:
        """Check if client is still connected."""
        with self._lock:
            return self._connected

    @connected.setter
    def connected(self, value: bool) -> None:
        """Set connection state."""
        with self._lock:
            self._connected = value

    def close(self) -> None:
        """Close the connection."""
        with self._lock:
            self._connected = False
            try:
                self._socket.close()
            except Exception:
                pass

    def __repr__(self) -> str:
        return f"ServerClientConnection({self._address[0]}:{self._address[1]}, connected={self.connected})"


class ConnectionRegistry:
    """
    Thread-safe registry for active client connections.

    Provides atomic operations for connection management to avoid race conditions.
    """

    def __init__(self, max_connections: int = 0):
        """
        Initialize connection registry.

        Args:
            max_connections: Maximum allowed connections (0 = unlimited)
        """
        self._connections: dict[Tuple[str, int], ServerClientConnection] = {}
        self._lock = threading.Lock()
        self._max_connections = max_connections

    def try_add(
        self,
        sock: socket.socket,
        address: Tuple[str, int],
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None
    ) -> Optional[ServerClientConnection]:
        """
        Atomically check limits and add a connection.

        This prevents race conditions between checking connection count
        and adding new connections.

        Args:
            sock: Client socket
            address: Client address
            read_timeout: Optional read timeout
            write_timeout: Optional write timeout

        Returns:
            ServerClientConnection if added successfully, None if limit reached
        """
        with self._lock:
            # Atomic check and add
            if 0 < self._max_connections <= len(self._connections):
                return None

            conn = ServerClientConnection(sock, address, read_timeout, write_timeout)
            self._connections[address] = conn
            return conn

    def remove(self, address: Tuple[str, int]) -> Optional[ServerClientConnection]:
        """
        Remove a connection by address.

        Args:
            address: Client address to remove

        Returns:
            Removed connection or None if not found
        """
        with self._lock:
            return self._connections.pop(address, None)

    def get(self, address: Tuple[str, int]) -> Optional[ServerClientConnection]:
        """Get a connection by address."""
        with self._lock:
            return self._connections.get(address)

    def close_all(self) -> None:
        """Close all connections."""
        with self._lock:
            for conn in self._connections.values():
                conn.close()
            self._connections.clear()

    def count(self) -> int:
        """Get current connection count."""
        with self._lock:
            return len(self._connections)

    def __len__(self) -> int:
        return self.count()
