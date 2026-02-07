"""
HTCP Server Subscription Module
Subscription registration and management.
"""

import threading
import inspect

from typing import Callable, Dict, Optional, Type, Any, Generator, AsyncGenerator

from ..common.utils import get_function_signature


class Subscription:
    """Registered subscription information."""

    def __init__(
        self,
        event_type: str,
        func: Callable,
        param_types: Dict[str, Type],
        yield_type: Type,
        is_async: bool
    ):
        self.event_type = event_type
        self.func = func
        self.param_types = param_types
        self.yield_type = yield_type
        self.is_async = is_async


def _get_yield_type(func: Callable) -> Type:
    """Extract yield type from generator function."""
    try:
        from typing import get_type_hints, get_origin, get_args
        hints = get_type_hints(func)
        return_hint = hints.get("return", Any)

        origin = get_origin(return_hint)
        if origin in (Generator, AsyncGenerator):
            args = get_args(return_hint)
            if args:
                return args[0]  # First arg is yield type
        return Any
    except Exception:
        return Any


class SubscriptionRegistry:
    """
    Thread-safe registry for server subscriptions.

    Provides methods to register and retrieve subscription handlers.
    """

    def __init__(self):
        self._subscriptions: Dict[str, Subscription] = {}
        self._lock = threading.RLock()

    def register(
        self,
        event_type: str,
        func: Callable,
        param_types: Optional[Dict[str, Type]] = None,
        yield_type: Optional[Type] = None
    ) -> Subscription:
        """
        Register a subscription handler.

        Args:
            event_type: Unique subscription event type identifier
            func: Handler generator function (sync or async)
            param_types: Optional parameter types (auto-detected if not provided)
            yield_type: Optional yield type (auto-detected if not provided)

        Returns:
            Created Subscription object

        Raises:
            ValueError: If event_type is already registered or func is not a generator
        """
        # Check if it's a generator function
        is_async = inspect.isasyncgenfunction(func)
        is_sync_gen = inspect.isgeneratorfunction(func)

        if not is_async and not is_sync_gen:
            raise ValueError(
                f"Subscription handler '{event_type}' must be a generator function (use yield)"
            )

        if param_types is None:
            param_types = get_function_signature(func)

        if yield_type is None:
            yield_type = _get_yield_type(func)

        sub = Subscription(
            event_type=event_type,
            func=func,
            param_types=param_types,
            yield_type=yield_type,
            is_async=is_async
        )

        with self._lock:
            if event_type in self._subscriptions:
                raise ValueError(f"Subscription '{event_type}' is already registered")
            self._subscriptions[event_type] = sub

        return sub

    def get(self, event_type: str) -> Optional[Subscription]:
        """
        Get a subscription by event_type.

        Args:
            event_type: Subscription event type identifier

        Returns:
            Subscription object or None if not found
        """
        with self._lock:
            return self._subscriptions.get(event_type)

    def list_event_types(self) -> list[str]:
        """
        Get list of all registered subscription event types.

        Returns:
            List of event types
        """
        with self._lock:
            return list(self._subscriptions.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    def __contains__(self, event_type: str) -> bool:
        with self._lock:
            return event_type in self._subscriptions


class ActiveSubscription:
    """Represents an active subscription for a client."""

    def __init__(
        self,
        subscription_id: str,
        event_type: str,
        client_address: tuple,
        generator: Any,  # Generator or AsyncGenerator
        is_async: bool
    ):
        self.subscription_id = subscription_id
        self.event_type = event_type
        self.client_address = client_address
        self.generator = generator
        self.is_async = is_async
        self.active = True
        self._lock = threading.Lock()

    def cancel(self) -> None:
        """Cancel this subscription."""
        with self._lock:
            self.active = False
            # Close the generator
            try:
                if self.is_async:
                    # For async generators, we need to handle this in async context
                    pass
                else:
                    self.generator.close()
            except Exception:
                pass

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self.active


class ActiveSubscriptionRegistry:
    """
    Thread-safe registry for active client subscriptions.
    """

    def __init__(self):
        self._subscriptions: Dict[str, ActiveSubscription] = {}
        self._by_client: Dict[tuple, set[str]] = {}
        self._lock = threading.RLock()

    def add(
        self,
        subscription_id: str,
        event_type: str,
        client_address: tuple,
        generator: Any,
        is_async: bool
    ) -> ActiveSubscription:
        """Add an active subscription."""
        with self._lock:
            sub = ActiveSubscription(
                subscription_id, event_type, client_address, generator, is_async
            )
            self._subscriptions[subscription_id] = sub

            if client_address not in self._by_client:
                self._by_client[client_address] = set()
            self._by_client[client_address].add(subscription_id)

            return sub

    def get(self, subscription_id: str) -> Optional[ActiveSubscription]:
        """Get an active subscription by ID."""
        with self._lock:
            return self._subscriptions.get(subscription_id)

    def remove(self, subscription_id: str) -> Optional[ActiveSubscription]:
        """Remove and return an active subscription."""
        with self._lock:
            sub = self._subscriptions.pop(subscription_id, None)
            if sub:
                client_subs = self._by_client.get(sub.client_address)
                if client_subs:
                    client_subs.discard(subscription_id)
                    if not client_subs:
                        del self._by_client[sub.client_address]
            return sub

    def cancel_for_client(self, client_address: tuple) -> list[ActiveSubscription]:
        """Cancel and remove all subscriptions for a client."""
        with self._lock:
            sub_ids = self._by_client.pop(client_address, set())
            cancelled = []
            for sub_id in sub_ids:
                sub = self._subscriptions.pop(sub_id, None)
                if sub:
                    sub.cancel()
                    cancelled.append(sub)
            return cancelled

    def get_for_client(self, client_address: tuple) -> list[ActiveSubscription]:
        """Get all active subscriptions for a client."""
        with self._lock:
            sub_ids = self._by_client.get(client_address, set())
            return [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]
