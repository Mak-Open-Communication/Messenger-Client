"""
HTCP Async Client Module
Async TCP client for connecting to HTCP servers.
"""

import logging
import uuid
from typing import Any, AsyncIterator, Dict, Optional, Type

from ..common.constants import DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT, DEFAULT_WRITE_TIMEOUT
from ..common.proto import PacketType
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

from .connection import AsyncClientConnection


class AsyncSubscriptionIterator:
    """
    Async iterator for receiving subscription data.

    Usage:
        async with client.subscribe(event_type="notifications", user_id=123) as sub:
            async for data in sub:
                print(data)
    """

    def __init__(
        self,
        client: 'AsyncClient',
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

    def __aiter__(self) -> AsyncIterator[Any]:
        return self

    async def __anext__(self) -> Any:
        if not self._active or self._ended:
            raise StopAsyncIteration

        if not self._client._connection.connected:
            self._active = False
            raise StopAsyncIteration

        try:
            packet = await self._client._connection.receive()

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
                    raise StopAsyncIteration

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
            raise StopAsyncIteration

    async def cancel(self) -> None:
        """Cancel the subscription."""
        if not self._active or self._ended:
            return

        self._active = False
        try:
            request = UnsubscribeRequest(subscription_id=self._subscription_id)
            await self._client._connection.send(request.to_packet())
        except Exception:
            pass

    async def __aenter__(self) -> 'AsyncSubscriptionIterator':
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cancel()


class AsyncClient:
    """
    HTCP Async Client.

    Async client for connecting to HTCP servers.

    Example usage:
        client = AsyncClient(server_host="127.0.0.1", server_port=2353)
        await client.connect()

        # Transaction call
        result = await client.call(transaction="greet", name="World")
        print(result)  # "Hello, World!"

        # Subscription
        async with client.subscribe(event_type="notifications", user_id=123) as sub:
            async for notification in sub:
                print(notification)

        await client.disconnect()

    Or with async context manager:
        async with AsyncClient(server_host="127.0.0.1", server_port=2353) as client:
            result = await client.call(transaction="greet", name="World")
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

        self._connection = AsyncClientConnection(
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

    async def connect(self) -> None:
        """Connect to the HTCP server."""
        if self._connection.connected:
            self.logger.warning("Already connected")
            return

        try:
            await self._connection.connect()

            # Perform handshake
            await self._handshake()

            self.logger.info(f"Connected to {self.server_host}:{self.server_port}")

        except Exception as e:
            await self._cleanup()
            raise HTCPConnectionError(f"Failed to connect: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if not self._connection.connected:
            return

        try:
            # Send disconnect packet
            packet = DisconnectPacket().to_packet()
            await self._connection.send(packet)
        except Exception:
            pass

        await self._cleanup()
        self.logger.info("Disconnected from server")

    async def _cleanup(self) -> None:
        """Clean up connection resources."""
        self._server_name = "unknown"
        self._available_transactions = []
        await self._connection.disconnect()

    async def _handshake(self) -> None:
        """Perform handshake with server."""
        request = HandshakeRequest()
        await self._connection.send(request.to_packet())

        response_packet = await self._connection.receive()

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

    async def call(self, transaction: str, result_type: Type = None, **kwargs) -> Any:
        """
        Call a transaction on the server.

        Args:
            transaction: Transaction code to call
            result_type: Optional expected return type for proper deserialization
            **kwargs: Arguments to pass to the transaction

        Returns:
            The result of the transaction

        Example:
            # Simple call
            result = await client.call(transaction="greet", name="World")

            # Call with expected type for dataclass
            result = await client.call(
                transaction="get_user",
                result_type=User,
                user_id=123
            )
        """
        if not self._connection.connected:
            raise HTCPConnectionError("Not connected to server")

        # Send transaction call
        call = TransactionCall(transaction_code=transaction, arguments=kwargs)
        await self._connection.send(call.to_packet())

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"Called transaction '{transaction}' with args: {kwargs}")
        else:
            self.logger.info(f"Called transaction '{transaction}'")

        # Receive response
        response_packet = await self._connection.receive()

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
    ) -> AsyncSubscriptionIterator:
        """
        Subscribe to server events.

        Returns an async iterator that yields data from the subscription.
        Use as an async context manager to ensure proper cleanup.

        Args:
            event_type: Event type to subscribe to
            data_type: Optional expected data type for proper deserialization
            **kwargs: Arguments to pass to the subscription handler

        Returns:
            AsyncSubscriptionIterator that yields subscription data

        Example:
            async with client.subscribe(event_type="notifications", user_id=123) as sub:
                async for notification in sub:
                    print(notification)
                    if should_stop:
                        break  # Will send unsubscribe on context exit
        """
        if not self._connection.connected:
            raise HTCPConnectionError("Not connected to server")

        subscription_id = str(uuid.uuid4())

        # Send subscribe request synchronously (will be awaited by iterator)
        # Actually we need to send it now
        import asyncio
        loop = asyncio.get_event_loop()

        # Create and return the iterator - it will send the request
        return _AsyncSubscriptionIteratorWithInit(
            client=self,
            subscription_id=subscription_id,
            event_type=event_type,
            data_type=data_type,
            kwargs=kwargs
        )

    async def __aenter__(self) -> 'AsyncClient':
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()


class _AsyncSubscriptionIteratorWithInit(AsyncSubscriptionIterator):
    """Extended async subscription iterator that sends subscribe request on enter."""

    def __init__(
        self,
        client: 'AsyncClient',
        subscription_id: str,
        event_type: str,
        data_type: Optional[Type],
        kwargs: Dict[str, Any]
    ):
        super().__init__(client, subscription_id, event_type, data_type)
        self._kwargs = kwargs
        self._initialized = False

    async def __aenter__(self) -> 'AsyncSubscriptionIterator':
        # Send subscribe request
        request = SubscribeRequest(
            subscription_id=self._subscription_id,
            event_type=self._event_type,
            arguments=self._kwargs
        )
        await self._client._connection.send(request.to_packet())

        if self._client.logger.isEnabledFor(logging.DEBUG):
            self._client.logger.debug(f"Subscribed to '{self._event_type}' with args: {self._kwargs}")
        else:
            self._client.logger.info(f"Subscribed to '{self._event_type}'")

        self._initialized = True
        return self

    async def __anext__(self) -> Any:
        if not self._initialized:
            raise RuntimeError("Subscription not initialized. Use 'async with client.subscribe(...) as sub:'")
        return await super().__anext__()
