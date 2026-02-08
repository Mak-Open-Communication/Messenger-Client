"""
HTCP Async Server Module
Async TCP server with transaction and subscription decorator support.
"""

import asyncio
import inspect
import logging
import signal

from typing import Callable, Optional, Dict, Any

from ..common.constants import (
    DEFAULT_LISTEN_BACKLOG,
    DEFAULT_MAX_CONNECTIONS,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_WRITE_TIMEOUT,
)
from ..common.proto import Packet, PacketType, ErrorCode
from ..common.messages import (
    HandshakeRequest,
    HandshakeResponse,
    TransactionCall,
    TransactionResult,
    ErrorPacket,
    SubscribeRequest,
    UnsubscribeRequest,
    SubscribeData,
    SubscribeEnd,
    SubscribeError,
)
from ..common.aio_transport import recv_packet, send_packet
from ..common.utils import prepare_arguments
from ..exceptions import ConnectionError as HTCPConnectionError

from ..server.transaction import Transaction, TransactionRegistry
from ..server.subscription import Subscription, SubscriptionRegistry
from .connection import AsyncServerClientConnection, AsyncConnectionRegistry


class AsyncActiveSubscription:
    """Represents an active async subscription for a client."""

    def __init__(
        self,
        subscription_id: str,
        event_type: str,
        client_address: tuple,
        task: asyncio.Task
    ):
        self.subscription_id = subscription_id
        self.event_type = event_type
        self.client_address = client_address
        self.task = task
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel this subscription."""
        self._cancelled = True
        if not self.task.done():
            self.task.cancel()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class AsyncActiveSubscriptionRegistry:
    """Async registry for active client subscriptions."""

    def __init__(self):
        self._subscriptions: Dict[str, AsyncActiveSubscription] = {}
        self._by_client: Dict[tuple, set[str]] = {}
        self._lock = asyncio.Lock()

    async def add(
        self,
        subscription_id: str,
        event_type: str,
        client_address: tuple,
        task: asyncio.Task
    ) -> AsyncActiveSubscription:
        """Add an active subscription."""
        async with self._lock:
            sub = AsyncActiveSubscription(
                subscription_id, event_type, client_address, task
            )
            self._subscriptions[subscription_id] = sub

            if client_address not in self._by_client:
                self._by_client[client_address] = set()
            self._by_client[client_address].add(subscription_id)

            return sub

    async def get(self, subscription_id: str) -> Optional[AsyncActiveSubscription]:
        """Get an active subscription by ID."""
        async with self._lock:
            return self._subscriptions.get(subscription_id)

    async def remove(self, subscription_id: str) -> Optional[AsyncActiveSubscription]:
        """Remove and return an active subscription."""
        async with self._lock:
            sub = self._subscriptions.pop(subscription_id, None)
            if sub:
                client_subs = self._by_client.get(sub.client_address)
                if client_subs:
                    client_subs.discard(subscription_id)
                    if not client_subs:
                        del self._by_client[sub.client_address]
            return sub

    async def cancel_for_client(self, client_address: tuple) -> list[AsyncActiveSubscription]:
        """Cancel and remove all subscriptions for a client."""
        async with self._lock:
            sub_ids = self._by_client.pop(client_address, set())
            cancelled = []
            for sub_id in sub_ids:
                sub = self._subscriptions.pop(sub_id, None)
                if sub:
                    sub.cancel()
                    cancelled.append(sub)
            return cancelled


class AsyncServer:
    """
    HTCP Async Server.

    Example usage:
        app = AsyncServer(name="my-server", host="0.0.0.0", port=2353)

        @app.transaction(code="greet")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        @app.subscription(event_type="notifications")
        async def notify(user_id: int):
            while True:
                notifications = await get_new_notifications(user_id)
                if notifications:
                    yield notifications
                await asyncio.sleep(1)

        await app.up()
    """

    def __init__(
        self,
        name: str = "htcp-server",
        host: str = "0.0.0.0",
        port: int = 2353,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        expose_transactions: bool = True,
        logger: Optional[logging.Logger] = None,
        read_timeout: Optional[float] = DEFAULT_READ_TIMEOUT,
        write_timeout: Optional[float] = DEFAULT_WRITE_TIMEOUT,
        listen_backlog: int = DEFAULT_LISTEN_BACKLOG,
    ):
        self.name = name
        self.host = host
        self.port = port
        self.max_connections = max_connections  # 0 = unlimited
        self.expose_transactions = expose_transactions
        self.logger = logger or logging.getLogger(__name__)
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.listen_backlog = listen_backlog

        self._transactions = TransactionRegistry()
        self._subscriptions = SubscriptionRegistry()
        self._active_subscriptions = AsyncActiveSubscriptionRegistry()
        self._server: Optional[asyncio.Server] = None
        self._running = False
        self._clients = AsyncConnectionRegistry(max_connections)
        self._shutdown_event = asyncio.Event()

    def transaction(self, code: str) -> Callable:
        """
        Decorator to register a transaction handler.

        The handler can be either sync or async function.

        Args:
            code: Unique transaction identifier

        Example:
            @app.transaction(code="get_user")
            async def get_user(user_id: int) -> User:
                return await db.get_user(user_id)
        """
        def decorator(func: Callable) -> Callable:
            self._transactions.register(code, func)
            self.logger.debug(f"Registered transaction '{code}'")
            return func

        return decorator

    def subscription(self, event_type: str) -> Callable:
        """
        Decorator to register a subscription handler.

        The handler must be an async generator function that yields data.

        Args:
            event_type: Unique subscription event type identifier

        Example:
            @app.subscription(event_type="notifications")
            async def notify_user(user_id: int):
                while True:
                    notifications = await get_new_notifications(user_id)
                    if notifications:
                        yield notifications
                    await asyncio.sleep(1)
        """
        def decorator(func: Callable) -> Callable:
            self._subscriptions.register(event_type, func)
            self.logger.debug(f"Registered subscription '{event_type}'")
            return func

        return decorator

    async def up(self) -> None:
        """Start the server and begin accepting connections."""
        if self._running:
            self.logger.warning("Server is already running")
            return

        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
            backlog=self.listen_backlog,
        )

        self._running = True
        self._shutdown_event.clear()

        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info(
                f"Registered {len(self._transactions)} transactions, "
                f"{len(self._subscriptions)} subscriptions"
            )
        self.logger.info(f"Async server '{self.name}' started on {self.host}:{self.port}")

        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        try:
            async with self._server:
                await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.down()

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        self.logger.info("Shutdown signal received")
        self._shutdown_event.set()

    async def down(self) -> None:
        """Stop the server."""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        # Close all client connections
        await self._clients.close_all()

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self.logger.info(f"Async server '{self.name}' stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """Handle a new client connection."""
        peername = writer.get_extra_info('peername')
        address = (peername[0], peername[1]) if peername else ('unknown', 0)

        # Atomic check-and-add to prevent race condition
        client = await self._clients.try_add(
            reader,
            writer,
            address,
            self.read_timeout,
            self.write_timeout
        )

        if client is None:
            self.logger.warning(
                f"Connection from {address} rejected: max connections ({self.max_connections}) reached"
            )
            writer.close()
            await writer.wait_closed()
            return

        self.logger.info(f"New connection from {address[0]}:{address[1]}")

        try:
            while self._running and client.connected:
                try:
                    packet = await recv_packet(reader, timeout=client.read_timeout)
                    await self._process_packet(client, packet)
                except HTCPConnectionError:
                    break
                except asyncio.TimeoutError:
                    self.logger.warning(f"Client {address} timed out")
                    break
                except Exception as e:
                    self.logger.error(f"Error processing packet from {address}: {e}")
                    await self._send_error(client, ErrorCode.PROTOCOL_ERROR, str(e))
                    break

        finally:
            # Cancel all active subscriptions for this client
            await self._active_subscriptions.cancel_for_client(address)

            await self._clients.remove(address)
            await client.close()
            self.logger.info(f"Client {address[0]}:{address[1]} disconnected")

    async def _process_packet(
        self,
        client: AsyncServerClientConnection,
        packet: Packet
    ) -> None:
        """Process incoming packet from client."""
        if packet.packet_type == PacketType.HANDSHAKE_REQUEST:
            await self._handle_handshake(client, packet)

        elif packet.packet_type == PacketType.TRANSACTION_CALL:
            await self._handle_transaction(client, packet)

        elif packet.packet_type == PacketType.SUBSCRIBE_REQUEST:
            await self._handle_subscribe(client, packet)

        elif packet.packet_type == PacketType.UNSUBSCRIBE_REQUEST:
            await self._handle_unsubscribe(client, packet)

        elif packet.packet_type == PacketType.DISCONNECT:
            client.connected = False

        else:
            await self._send_error(
                client,
                ErrorCode.PROTOCOL_ERROR,
                f"Unknown packet type: {packet.packet_type}"
            )

    async def _handle_handshake(
        self,
        client: AsyncServerClientConnection,
        packet: Packet
    ) -> None:
        """Handle handshake request."""
        try:
            HandshakeRequest.from_packet(packet)

            transactions = self._transactions.list_codes() if self.expose_transactions else []
            response = HandshakeResponse(
                server_name=self.name,
                transactions=transactions
            )
            await self._send_packet(client, response.to_packet())

        except Exception as e:
            self.logger.error(f"Handshake error: {e}")
            await self._send_error(client, ErrorCode.PROTOCOL_ERROR, str(e))

    async def _handle_transaction(
        self,
        client: AsyncServerClientConnection,
        packet: Packet
    ) -> None:
        """Handle transaction call."""
        try:
            call = TransactionCall.from_packet(packet)
            transaction_code = call.transaction_code

            self.logger.info(
                f"Transaction call '{transaction_code}' from {client.address[0]}:{client.address[1]}"
            )

            # Find transaction
            trans = self._transactions.get(transaction_code)
            if not trans:
                self.logger.info(f"Unknown transaction: {transaction_code}")
                await self._send_result(client, TransactionResult(
                    success=False,
                    error_code=ErrorCode.UNKNOWN_TRANSACTION,
                    error_message=f"Unknown transaction: {transaction_code}"
                ))
                return

            # Prepare arguments with type conversion
            try:
                prepared_args = prepare_arguments(trans.func, call.arguments)
            except Exception as e:
                self.logger.error(f"Argument preparation error: {e}")
                await self._send_result(client, TransactionResult(
                    success=False,
                    error_code=ErrorCode.INVALID_ARGUMENTS,
                    error_message=str(e)
                ))
                return

            # Execute transaction
            try:
                # Support both sync and async handlers
                if asyncio.iscoroutinefunction(trans.func):
                    result = await trans.func(**prepared_args)
                else:
                    # Run sync function in executor to avoid blocking
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None, lambda: trans.func(**prepared_args)
                    )

                self.logger.debug(f"Transaction '{transaction_code}' completed successfully")
                await self._send_result(client, TransactionResult(
                    success=True,
                    result=result,
                    error_code=ErrorCode.SUCCESS
                ))

            except Exception as e:
                self.logger.error(f"Transaction execution error: {e}")
                await self._send_result(client, TransactionResult(
                    success=False,
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message=str(e)
                ))

        except Exception as e:
            self.logger.error(f"Transaction handling error: {e}")
            await self._send_error(client, ErrorCode.INTERNAL_ERROR, str(e))

    async def _handle_subscribe(
        self,
        client: AsyncServerClientConnection,
        packet: Packet
    ) -> None:
        """Handle subscription request."""
        try:
            request = SubscribeRequest.from_packet(packet)
            subscription_id = request.subscription_id
            event_type = request.event_type

            self.logger.info(
                f"Subscribe request '{event_type}' (id={subscription_id}) "
                f"from {client.address[0]}:{client.address[1]}"
            )

            # Find subscription handler
            sub = self._subscriptions.get(event_type)
            if not sub:
                self.logger.info(f"Unknown subscription: {event_type}")
                await self._send_subscribe_error(
                    client, subscription_id,
                    ErrorCode.UNKNOWN_TRANSACTION,
                    f"Unknown subscription event type: {event_type}"
                )
                return

            # Prepare arguments
            try:
                prepared_args = prepare_arguments(sub.func, request.arguments)
            except Exception as e:
                self.logger.error(f"Subscription argument preparation error: {e}")
                await self._send_subscribe_error(
                    client, subscription_id,
                    ErrorCode.INVALID_ARGUMENTS,
                    str(e)
                )
                return

            # Start subscription task
            try:
                task = asyncio.create_task(
                    self._run_subscription(client, subscription_id, sub, prepared_args)
                )

                # Register active subscription
                await self._active_subscriptions.add(
                    subscription_id=subscription_id,
                    event_type=event_type,
                    client_address=client.address,
                    task=task
                )

                # Disable read timeout — subscribed clients don't send packets
                client.read_timeout = None

            except Exception as e:
                self.logger.error(f"Subscription start error: {e}")
                await self._send_subscribe_error(
                    client, subscription_id,
                    ErrorCode.EXECUTION_ERROR,
                    str(e)
                )

        except Exception as e:
            self.logger.error(f"Subscribe handling error: {e}")
            await self._send_error(client, ErrorCode.INTERNAL_ERROR, str(e))

    async def _run_subscription(
        self,
        client: AsyncServerClientConnection,
        subscription_id: str,
        sub: Subscription,
        prepared_args: Dict[str, Any]
    ) -> None:
        """Run subscription generator and send data to client."""
        try:
            # Get the active subscription to check cancellation
            active_sub = await self._active_subscriptions.get(subscription_id)

            if sub.is_async:
                # Async generator
                async for data in sub.func(**prepared_args):
                    if (active_sub and active_sub.is_cancelled) or not client.connected or not self._running:
                        break

                    msg = SubscribeData(subscription_id=subscription_id, data=data)
                    await self._send_packet(client, msg.to_packet())
            else:
                # Sync generator - run in executor
                loop = asyncio.get_running_loop()
                generator = sub.func(**prepared_args)

                while True:
                    if (active_sub and active_sub.is_cancelled) or not client.connected or not self._running:
                        break

                    try:
                        data = await loop.run_in_executor(None, next, generator)
                        msg = SubscribeData(subscription_id=subscription_id, data=data)
                        await self._send_packet(client, msg.to_packet())
                    except StopIteration:
                        break

            # Send end of subscription
            if client.connected and self._running:
                end_msg = SubscribeEnd(subscription_id=subscription_id)
                await self._send_packet(client, end_msg.to_packet())

        except asyncio.CancelledError:
            # Subscription was cancelled
            pass
        except Exception as e:
            self.logger.error(f"Subscription '{subscription_id}' error: {e}")
            if client.connected:
                await self._send_subscribe_error(
                    client, subscription_id,
                    ErrorCode.EXECUTION_ERROR,
                    str(e)
                )
        finally:
            await self._active_subscriptions.remove(subscription_id)
            self.logger.debug(f"Subscription '{subscription_id}' ended")

    async def _handle_unsubscribe(
        self,
        client: AsyncServerClientConnection,
        packet: Packet
    ) -> None:
        """Handle unsubscribe request."""
        try:
            request = UnsubscribeRequest.from_packet(packet)
            subscription_id = request.subscription_id

            self.logger.info(
                f"Unsubscribe request (id={subscription_id}) "
                f"from {client.address[0]}:{client.address[1]}"
            )

            active_sub = await self._active_subscriptions.remove(subscription_id)
            if active_sub:
                active_sub.cancel()
                self.logger.debug(f"Cancelled subscription '{subscription_id}'")

        except Exception as e:
            self.logger.error(f"Unsubscribe handling error: {e}")

    async def _send_packet(
        self,
        client: AsyncServerClientConnection,
        packet: Packet
    ) -> None:
        """Send packet to client."""
        try:
            await send_packet(client.writer, packet, client.write_timeout)
        except Exception as e:
            self.logger.error(f"Error sending packet: {e}")
            client.connected = False

    async def _send_result(
        self,
        client: AsyncServerClientConnection,
        result: TransactionResult
    ) -> None:
        """Send transaction result to client."""
        await self._send_packet(client, result.to_packet())

    async def _send_error(
        self,
        client: AsyncServerClientConnection,
        error_code: ErrorCode,
        message: str
    ) -> None:
        """Send error packet to client."""
        error = ErrorPacket(error_code, message)
        await self._send_packet(client, error.to_packet())

    async def _send_subscribe_error(
        self,
        client: AsyncServerClientConnection,
        subscription_id: str,
        error_code: ErrorCode,
        message: str
    ) -> None:
        """Send subscription error packet to client."""
        error = SubscribeError(subscription_id, error_code, message)
        await self._send_packet(client, error.to_packet())
