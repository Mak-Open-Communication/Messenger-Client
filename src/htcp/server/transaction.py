"""
HTCP Server Transaction Module
Transaction registration and management.
"""

import threading

from typing import Callable, Dict, Optional, Type

from ..common.utils import get_function_signature, get_return_type


class Transaction:
    """Registered transaction information."""

    def __init__(
        self,
        code: str,
        func: Callable,
        param_types: Dict[str, Type],
        return_type: Type
    ):
        self.code = code
        self.func = func
        self.param_types = param_types
        self.return_type = return_type


class TransactionRegistry:
    """
    Thread-safe registry for server transactions.

    Provides methods to register and retrieve transaction handlers.
    """

    def __init__(self):
        self._transactions: Dict[str, Transaction] = {}
        self._lock = threading.RLock()

    def register(
        self,
        code: str,
        func: Callable,
        param_types: Optional[Dict[str, Type]] = None,
        return_type: Optional[Type] = None
    ) -> Transaction:
        """
        Register a transaction handler.

        Args:
            code: Unique transaction identifier
            func: Handler function
            param_types: Optional parameter types (auto-detected if not provided)
            return_type: Optional return type (auto-detected if not provided)

        Returns:
            Created Transaction object

        Raises:
            ValueError: If transaction code is already registered
        """
        if param_types is None:
            param_types = get_function_signature(func)
        if return_type is None:
            return_type = get_return_type(func)

        trans = Transaction(
            code=code,
            func=func,
            param_types=param_types,
            return_type=return_type
        )

        with self._lock:
            if code in self._transactions:
                raise ValueError(f"Transaction '{code}' is already registered")
            self._transactions[code] = trans

        return trans

    def get(self, code: str) -> Optional[Transaction]:
        """
        Get a transaction by code.

        Args:
            code: Transaction identifier

        Returns:
            Transaction object or None if not found
        """
        with self._lock:
            return self._transactions.get(code)

    def list_codes(self) -> list[str]:
        """
        Get list of all registered transaction codes.

        Returns:
            List of transaction codes
        """
        with self._lock:
            return list(self._transactions.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._transactions)

    def __contains__(self, code: str) -> bool:
        with self._lock:
            return code in self._transactions
