"""
HTCP Client Connection Module
Thread-safe connection management for client.
"""

import socket
import threading
from typing import Optional

from ..common.constants import DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT, DEFAULT_WRITE_TIMEOUT
from ..common.proto import Packet
from ..common.transport import recv_packet, send_packet
from ..exceptions import ConnectionError as HTCPConnectionError


class ClientConnection:
    """
    Thread-safe client connection wrapper.

    Provides synchronized access to socket operations for safe
    concurrent use from multiple threads.
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

        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.RLock()

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def connected(self) -> bool:
        """Check if connection is active."""
        with self._lock:
            return self._connected

    def connect(self) -> None:
        """
        Establish connection to server.

        Raises:
            HTCPConnectionError: If connection fails
        """
        with self._lock:
            if self._connected:
                return

            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                # Set connect timeout
                if self._connect_timeout is not None:
                    self._socket.settimeout(self._connect_timeout)

                self._socket.connect((self._host, self._port))

                # Set read/write timeout after connection
                timeout = max(
                    self._read_timeout or 0,
                    self._write_timeout or 0
                )
                if timeout > 0:
                    self._socket.settimeout(timeout)
                else:
                    self._socket.settimeout(None)

                self._connected = True

            except (socket.error, OSError) as e:
                self._cleanup_socket()
                raise HTCPConnectionError(f"Failed to connect to {self._host}:{self._port}: {e}") from e

    def disconnect(self) -> None:
        """Close the connection."""
        with self._lock:
            self._connected = False
            self._cleanup_socket()

    def send(self, packet: Packet) -> None:
        """
        Send a packet to server.

        Args:
            packet: Packet to send

        Raises:
            HTCPConnectionError: If not connected or send fails
        """
        with self._lock:
            if not self._connected or self._socket is None:
                raise HTCPConnectionError("Not connected")
            try:
                send_packet(self._socket, packet)
            except Exception as e:
                self._connected = False
                raise HTCPConnectionError(f"Send failed: {e}") from e

    def receive(self) -> Packet:
        """
        Receive a packet from server.

        Returns:
            Received Packet

        Raises:
            HTCPConnectionError: If not connected or receive fails
        """
        with self._lock:
            if not self._connected or self._socket is None:
                raise HTCPConnectionError("Not connected")
            try:
                return recv_packet(self._socket)
            except Exception as e:
                self._connected = False
                raise HTCPConnectionError(f"Receive failed: {e}") from e

    def _cleanup_socket(self) -> None:
        """Clean up socket resources."""
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def __enter__(self) -> 'ClientConnection':
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
