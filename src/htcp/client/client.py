"""
HTCP Client Module
TCP client for connecting to HTCP servers.
"""

import logging
import uuid
from typing import Any, Dict, Iterator, Optional, Type

from ..common.constants import DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT, DEFAULT_WRITE_TIMEOUT
from ..common.proto import Packet, PacketType
from ..common.messages import (
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
from ..common.utils import convert_to_type
from ..exceptions import ConnectionError as HTCPConnectionError

from .connection import ClientConnection


class SubscriptionIterator:
    """
    Iterator for receiving subscription data.

    Usage:
        with client.subscribe(event_type="notifications", user_id=123) as sub:
            for data in sub:
                print(data)
    """

    def __init__(
        self,
        client: 'Client',
        subscription_id: str,
        event_type: str,
        data_type: Optional[Type] = None
    ):
        self._client = client
        self._subscription_id = subscription_id
        self._event_type = event_type
        self._data_type = data_type
        self._active = True
        self._ended = False

    @property
    def subscription_id(self) -> str:
        return self._subscription_id

    @property
    def event_type(self) -> str:
        return self._event_type

    @property
    def active(self) -> bool:
        return self._active and not self._ended

    def __iter__(self) -> Iterator[Any]:
        return self

    def __next__(self) -> Any:
        if not self._active or self._ended:
            raise StopIteration

        if not self._client._connection.connected:
            self._active = False
            raise StopIteration

        try:
            packet = self._client._connection.receive()

            if packet.packet_type == PacketType.SUBSCRIBE_DATA:
                data_msg = SubscribeData.from_packet(packet)
                if data_msg.subscription_id == self._subscription_id:
                    if self._data_type is not None and data_msg.data is not None:
                        return convert_to_type(data_msg.data, self._data_type)
                    return data_msg.data

            elif packet.packet_type == PacketType.SUBSCRIBE_END:
                end_msg = SubscribeEnd.from_packet(packet)
                if end_msg.subscription_id == self._subscription_id:
                    self._ended = True
                    raise StopIteration

            elif packet.packet_type == PacketType.SUBSCRIBE_ERROR:
                error_msg = SubscribeError.from_packet(packet)
                if error_msg.subscription_id == self._subscription_id:
                    self._ended = True
                    raise RuntimeError(f"Subscription error: {error_msg.message}")

            elif packet.packet_type == PacketType.ERROR:
                error = ErrorPacket.from_packet(packet)
                self._ended = True
                raise RuntimeError(f"Server error: {error.message}")

            # Unexpected packet type
            raise RuntimeError(f"Unexpected packet type: {packet.packet_type}")

        except HTCPConnectionError:
            self._active = False
            raise StopIteration

    def cancel(self) -> None:
        """Cancel the subscription."""
        if not self._active or self._ended:
            return

        self._active = False
        try:
            request = UnsubscribeRequest(subscription_id=self._subscription_id)
            self._client._connection.send(request.to_packet())
        except Exception:
            pass

    def __enter__(self) -> 'SubscriptionIterator':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cancel()


class Client:
    """
    HTCP Client.

    Thread-safe client for connecting to HTCP servers.

    Example usage:
        client = Client(server_host="127.0.0.1", server_port=2353)
        client.connect()

        # Transaction call
        result = client.call(transaction="greet", name="World")
        print(result)  # "Hello, World!"

        # Subscription
        with client.subscribe(event_type="notifications", user_id=123) as sub:
            for notification in sub:
                print(notification)

        client.disconnect()
    """

    def __init__(
        self,
        server_host: str = "127.0.0.1",
        server_port: int = 2353,
        logger: Optional[logging.Logger] = None,
        connect_timeout: Optional[float] = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: Optional[float] = DEFAULT_READ_TIMEOUT,
        write_timeout: Optional[float] = DEFAULT_WRITE_TIMEOUT,
    ):
        self.server_host = server_host
        self.server_port = server_port
        self.logger = logger or logging.getLogger(__name__)

        self._connection = ClientConnection(
            server_host,
            server_port,
            connect_timeout,
            read_timeout,
            write_timeout,
        )
        self._server_name = "unknown"
        self._available_transactions: list[str] = []

    @property
    def connected(self) -> bool:
        """Check if client is connected to server."""
        return self._connection.connected

    def connect(self) -> None:
        """Connect to the HTCP server."""
        if self._connection.connected:
            self.logger.warning("Already connected")
            return

        try:
            self._connection.connect()

            # Perform handshake
            self._handshake()

            self.logger.info(f"Connected to {self.server_host}:{self.server_port}")

        except Exception as e:
            self._cleanup()
            raise HTCPConnectionError(f"Failed to connect: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from the server."""
        if not self._connection.connected:
            return

        try:
            # Send disconnect packet
            packet = DisconnectPacket().to_packet()
            self._connection.send(packet)
        except Exception:
            pass

        self._cleanup()
        self.logger.info("Disconnected from server")

    def _cleanup(self) -> None:
        """Clean up connection resources."""
        self._server_name = "unknown"
        self._available_transactions = []
        self._connection.disconnect()

    def _handshake(self) -> None:
        """Perform handshake with server."""
        request = HandshakeRequest()
        self._connection.send(request.to_packet())

        response_packet = self._connection.receive()

        if response_packet.packet_type == PacketType.ERROR:
            error = ErrorPacket.from_packet(response_packet)
            raise HTCPConnectionError(f"Handshake error: {error.message}")

        if response_packet.packet_type != PacketType.HANDSHAKE_RESPONSE:
            raise HTCPConnectionError(f"Unexpected response type: {response_packet.packet_type}")

        response = HandshakeResponse.from_packet(response_packet)
        self._server_name = response.server_name
        self._available_transactions = response.transactions

    def server_info(self) -> Dict[str, Any]:
        """
        Get server information.

        Returns:
            Dict with server_name, server_addr (host, port), and connected status
        """
        return {
            "server_name": self._server_name,
            "server_addr": {
                "host": self.server_host if self._connection.connected else "unknown",
                "port": self.server_port if self._connection.connected else 0
            },
            "connected": self._connection.connected,
            "available_transactions": self._available_transactions
        }

    def call(self, transaction: str, result_type: Type = None, **kwargs) -> Any:
        """
        Call a transaction on the server.

        This method is thread-safe.

        Args:
            transaction: Transaction code to call
            result_type: Optional expected return type for proper deserialization
            **kwargs: Arguments to pass to the transaction

        Returns:
            The result of the transaction

        Example:
            # Simple call
            result = client.call(transaction="greet", name="World")

            # Call with expected type for dataclass
            result = client.call(
                transaction="get_user",
                result_type=User,
                user_id=123
            )
        """
        if not self._connection.connected:
            raise HTCPConnectionError("Not connected to server")

        # Send transaction call
        call = TransactionCall(transaction_code=transaction, arguments=kwargs)
        self._connection.send(call.to_packet())

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"Called transaction '{transaction}' with args: {kwargs}")
        else:
            self.logger.info(f"Called transaction '{transaction}'")

        # Receive response
        response_packet = self._connection.receive()

        if response_packet.packet_type == PacketType.ERROR:
            error = ErrorPacket.from_packet(response_packet)
            raise RuntimeError(f"Server error: {error.message}")

        if response_packet.packet_type != PacketType.TRANSACTION_RESULT:
            raise RuntimeError(f"Unexpected response type: {response_packet.packet_type}")

        result = TransactionResult.from_packet(response_packet)

        if not result.success:
            raise RuntimeError(f"Transaction failed: {result.error_message}")

        # Convert result to expected type if specified
        if result_type is not None and result.result is not None:
            return convert_to_type(result.result, result_type)

        return result.result

    def subscribe(
        self,
        event_type: str,
        data_type: Optional[Type] = None,
        **kwargs
    ) -> SubscriptionIterator:
        """
        Subscribe to server events.

        Returns an iterator that yields data from the subscription.
        Use as a context manager to ensure proper cleanup.

        Args:
            event_type: Event type to subscribe to
            data_type: Optional expected data type for proper deserialization
            **kwargs: Arguments to pass to the subscription handler

        Returns:
            SubscriptionIterator that yields subscription data

        Example:
            with client.subscribe(event_type="notifications", user_id=123) as sub:
                for notification in sub:
                    print(notification)
                    if should_stop:
                        break  # Will send unsubscribe on context exit
        """
        if not self._connection.connected:
            raise HTCPConnectionError("Not connected to server")

        subscription_id = str(uuid.uuid4())

        # Send subscribe request
        request = SubscribeRequest(
            subscription_id=subscription_id,
            event_type=event_type,
            arguments=kwargs
        )
        self._connection.send(request.to_packet())

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"Subscribed to '{event_type}' with args: {kwargs}")
        else:
            self.logger.info(f"Subscribed to '{event_type}'")

        return SubscriptionIterator(
            client=self,
            subscription_id=subscription_id,
            event_type=event_type,
            data_type=data_type
        )

    def __enter__(self) -> 'Client':
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()
