"""
HTCP Server Module
TCP server with transaction and subscription decorator support.
"""

import socket
import threading
import logging

from typing import Callable, Optional

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
from ..common.transport import recv_packet, send_packet
from ..common.utils import prepare_arguments
from ..exceptions import ConnectionError as HTCPConnectionError

from .transaction import TransactionRegistry
from .connection import ServerClientConnection, ConnectionRegistry
from .subscription import SubscriptionRegistry, ActiveSubscriptionRegistry


class Server:
    """
    HTCP Server.

    Example usage:
        app = Server(name="my-server", host="0.0.0.0", port=2353)

        @app.transaction(code="greet")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        @app.subscription(event_type="notifications")
        def notify(user_id: int):
            while True:
                # Get new notifications
                notifies = get_new_notifications(user_id)
                if notifies:
                    yield notifies
                time.sleep(1)

        app.up()
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
        self._active_subscriptions = ActiveSubscriptionRegistry()
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None
        self._clients = ConnectionRegistry(max_connections)

    def transaction(self, code: str) -> Callable:
        """
        Decorator to register a transaction handler.

        Args:
            code: Unique transaction identifier

        Example:
            @app.transaction(code="get_user")
            def get_user(user_id: int) -> User:
                return db.get_user(user_id)
        """
        def decorator(func: Callable) -> Callable:
            self._transactions.register(code, func)
            self.logger.debug(f"Registered transaction '{code}'")
            return func

        return decorator

    def subscription(self, event_type: str) -> Callable:
        """
        Decorator to register a subscription handler.

        The handler must be a generator function that yields data.

        Args:
            event_type: Unique subscription event type identifier

        Example:
            @app.subscription(event_type="notifications")
            def notify_user(user_id: int):
                while True:
                    notifications = get_new_notifications(user_id)
                    if notifications:
                        yield notifications
                    time.sleep(1)
        """
        def decorator(func: Callable) -> Callable:
            self._subscriptions.register(event_type, func)
            self.logger.debug(f"Registered subscription '{event_type}'")
            return func

        return decorator

    def up(self) -> None:
        """Start the server and begin accepting connections."""
        if self._running:
            self.logger.warning("Server is already running")
            return

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.listen(self.listen_backlog)

        self._running = True
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info(
                f"Registered {len(self._transactions)} transactions, "
                f"{len(self._subscriptions)} subscriptions"
            )
        self.logger.info(f"Server '{self.name}' started on {self.host}:{self.port}")

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

        # Block main thread
        try:
            self._accept_thread.join()
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
            self.down()

    def down(self) -> None:
        """Stop the server."""
        if not self._running:
            return

        self._running = False

        # Close all client connections (this will also cancel subscriptions)
        self._clients.close_all()

        # Close server socket
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        self.logger.info(f"Server '{self.name}' stopped")

    def _accept_loop(self) -> None:
        """Accept incoming connections."""
        while self._running:
            try:
                client_sock, address = self._socket.accept()

                # Atomic check-and-add to prevent race condition
                client = self._clients.try_add(
                    client_sock,
                    address,
                    self.read_timeout,
                    self.write_timeout
                )

                if client is None:
                    self.logger.warning(
                        f"Connection from {address} rejected: max connections ({self.max_connections}) reached"
                    )
                    client_sock.close()
                    continue

                self.logger.info(f"New connection from {address[0]}:{address[1]}")

                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client,),
                    daemon=True
                )
                thread.start()

            except OSError:
                # Socket was closed
                break
            except Exception as e:
                if self._running:
                    self.logger.error(f"Error accepting connection: {e}")

    def _handle_client(self, client: ServerClientConnection) -> None:
        """Handle a single client connection."""
        try:
            while self._running and client.connected:
                try:
                    packet = recv_packet(client.socket)
                    self._process_packet(client, packet)
                except HTCPConnectionError:
                    break
                except socket.timeout:
                    self.logger.warning(f"Client {client.address} timed out")
                    break
                except Exception as e:
                    self.logger.error(f"Error processing packet from {client.address}: {e}")
                    self._send_error(client, ErrorCode.PROTOCOL_ERROR, str(e))
                    break

        finally:
            # Cancel all active subscriptions for this client
            self._active_subscriptions.cancel_for_client(client.address)

            self._clients.remove(client.address)
            client.close()
            self.logger.info(f"Client {client.address[0]}:{client.address[1]} disconnected")

    def _process_packet(self, client: ServerClientConnection, packet: Packet) -> None:
        """Process incoming packet from client."""
        if packet.packet_type == PacketType.HANDSHAKE_REQUEST:
            self._handle_handshake(client, packet)

        elif packet.packet_type == PacketType.TRANSACTION_CALL:
            self._handle_transaction(client, packet)

        elif packet.packet_type == PacketType.SUBSCRIBE_REQUEST:
            self._handle_subscribe(client, packet)

        elif packet.packet_type == PacketType.UNSUBSCRIBE_REQUEST:
            self._handle_unsubscribe(client, packet)

        elif packet.packet_type == PacketType.DISCONNECT:
            client.connected = False

        else:
            self._send_error(client, ErrorCode.PROTOCOL_ERROR, f"Unknown packet type: {packet.packet_type}")

    def _handle_handshake(self, client: ServerClientConnection, packet: Packet) -> None:
        """Handle handshake request."""
        try:
            HandshakeRequest.from_packet(packet)

            transactions = self._transactions.list_codes() if self.expose_transactions else []
            response = HandshakeResponse(
                server_name=self.name,
                transactions=transactions
            )
            self._send_packet(client, response.to_packet())

        except Exception as e:
            self.logger.error(f"Handshake error: {e}")
            self._send_error(client, ErrorCode.PROTOCOL_ERROR, str(e))

    def _handle_transaction(self, client: ServerClientConnection, packet: Packet) -> None:
        """Handle transaction call."""
        try:
            call = TransactionCall.from_packet(packet)
            transaction_code = call.transaction_code

            self.logger.info(f"Transaction call '{transaction_code}' from {client.address[0]}:{client.address[1]}")

            # Find transaction
            trans = self._transactions.get(transaction_code)
            if not trans:
                self.logger.info(f"Unknown transaction: {transaction_code}")
                self._send_result(client, TransactionResult(
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
                self._send_result(client, TransactionResult(
                    success=False,
                    error_code=ErrorCode.INVALID_ARGUMENTS,
                    error_message=str(e)
                ))
                return

            # Execute transaction
            try:
                result = trans.func(**prepared_args)

                self.logger.debug(f"Transaction '{transaction_code}' completed successfully")
                self._send_result(client, TransactionResult(
                    success=True,
                    result=result,
                    error_code=ErrorCode.SUCCESS
                ))

            except Exception as e:
                self.logger.error(f"Transaction execution error: {e}")
                self._send_result(client, TransactionResult(
                    success=False,
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message=str(e)
                ))

        except Exception as e:
            self.logger.error(f"Transaction handling error: {e}")
            self._send_error(client, ErrorCode.INTERNAL_ERROR, str(e))

    def _handle_subscribe(self, client: ServerClientConnection, packet: Packet) -> None:
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
                self._send_subscribe_error(
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
                self._send_subscribe_error(
                    client, subscription_id,
                    ErrorCode.INVALID_ARGUMENTS,
                    str(e)
                )
                return

            # Start subscription in a separate thread
            try:
                generator = sub.func(**prepared_args)

                # Register active subscription
                active_sub = self._active_subscriptions.add(
                    subscription_id=subscription_id,
                    event_type=event_type,
                    client_address=client.address,
                    generator=generator,
                    is_async=sub.is_async
                )

                # Run generator in separate thread
                thread = threading.Thread(
                    target=self._run_subscription,
                    args=(client, active_sub),
                    daemon=True
                )
                thread.start()

            except Exception as e:
                self.logger.error(f"Subscription start error: {e}")
                self._send_subscribe_error(
                    client, subscription_id,
                    ErrorCode.EXECUTION_ERROR,
                    str(e)
                )

        except Exception as e:
            self.logger.error(f"Subscribe handling error: {e}")
            self._send_error(client, ErrorCode.INTERNAL_ERROR, str(e))

    def _run_subscription(self, client: ServerClientConnection, active_sub) -> None:
        """Run subscription generator and send data to client."""
        subscription_id = active_sub.subscription_id

        try:
            for data in active_sub.generator:
                if not active_sub.is_active or not client.connected or not self._running:
                    break

                # Send data to client
                msg = SubscribeData(subscription_id=subscription_id, data=data)
                self._send_packet(client, msg.to_packet())

            # Send end of subscription
            if client.connected and self._running:
                end_msg = SubscribeEnd(subscription_id=subscription_id)
                self._send_packet(client, end_msg.to_packet())

        except GeneratorExit:
            # Subscription was cancelled
            pass
        except Exception as e:
            self.logger.error(f"Subscription '{subscription_id}' error: {e}")
            if client.connected:
                self._send_subscribe_error(
                    client, subscription_id,
                    ErrorCode.EXECUTION_ERROR,
                    str(e)
                )
        finally:
            self._active_subscriptions.remove(subscription_id)
            self.logger.debug(f"Subscription '{subscription_id}' ended")

    def _handle_unsubscribe(self, client: ServerClientConnection, packet: Packet) -> None:
        """Handle unsubscribe request."""
        try:
            request = UnsubscribeRequest.from_packet(packet)
            subscription_id = request.subscription_id

            self.logger.info(
                f"Unsubscribe request (id={subscription_id}) "
                f"from {client.address[0]}:{client.address[1]}"
            )

            active_sub = self._active_subscriptions.remove(subscription_id)
            if active_sub:
                active_sub.cancel()
                self.logger.debug(f"Cancelled subscription '{subscription_id}'")

        except Exception as e:
            self.logger.error(f"Unsubscribe handling error: {e}")

    def _send_packet(self, client: ServerClientConnection, packet: Packet) -> None:
        """Send packet to client."""
        try:
            send_packet(client.socket, packet)
        except Exception as e:
            self.logger.error(f"Error sending packet: {e}")
            client.connected = False

    def _send_result(self, client: ServerClientConnection, result: TransactionResult) -> None:
        """Send transaction result to client."""
        self._send_packet(client, result.to_packet())

    def _send_error(self, client: ServerClientConnection, error_code: ErrorCode, message: str) -> None:
        """Send error packet to client."""
        error = ErrorPacket(error_code, message)
        self._send_packet(client, error.to_packet())

    def _send_subscribe_error(
        self,
        client: ServerClientConnection,
        subscription_id: str,
        error_code: ErrorCode,
        message: str
    ) -> None:
        """Send subscription error packet to client."""
        error = SubscribeError(subscription_id, error_code, message)
        self._send_packet(client, error.to_packet())
