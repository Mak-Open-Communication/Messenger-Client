"""
HTCP Utilities Module
Helper functions for the HTCP protocol.
"""

import inspect
import dataclasses

from typing import Any, Callable, Dict, Type, get_type_hints, get_origin, get_args, Union, Tuple
from .serialization import serialize, deserialize


def get_function_signature(func: Callable) -> Dict[str, Type]:
    """
    Extract parameter types from function signature.
    Returns a dict of {param_name: param_type}.
    """
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    sig = inspect.signature(func)
    result = {}

    for param_name, param in sig.parameters.items():
        if param_name == 'self':
            continue
        if param_name in hints:
            result[param_name] = hints[param_name]
        else:
            result[param_name] = Any

    return result


def get_return_type(func: Callable) -> Type:
    """Get return type annotation from function."""
    try:
        hints = get_type_hints(func)
        return hints.get('return', Any)
    except Exception:
        return Any


def prepare_arguments(func: Callable, raw_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare arguments for function call.
    Converts raw deserialized values to expected types using type hints.
    """
    param_types = get_function_signature(func)
    prepared = {}

    for name, value in raw_args.items():
        expected_type = param_types.get(name)
        if expected_type is not None:
            prepared[name] = convert_to_type(value, expected_type)
        else:
            prepared[name] = value

    return prepared


def convert_to_type(value: Any, expected_type: Type) -> Any:
    """
    Convert a value to the expected type.
    Handles dataclasses, Optional, Union, and generic types.
    """
    if value is None:
        return None

    # Handle Optional[X] and Union types
    origin = get_origin(expected_type)
    if origin is Union:
        args = get_args(expected_type)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            expected_type = non_none[0]
            origin = get_origin(expected_type)

    # If value is already the correct type, return it
    try:
        if not origin and isinstance(value, expected_type):
            return value
    except TypeError:
        pass  # expected_type might not be a valid type for isinstance

    # Handle Enum from dict representation
    from enum import Enum
    if isinstance(value, dict) and "__enum__" in value and "__member__" in value:
        if expected_type and isinstance(expected_type, type) and issubclass(expected_type, Enum):
            return expected_type[value["__member__"]]
        return value

    # Handle dataclasses
    if dataclasses.is_dataclass(expected_type) and not isinstance(expected_type, type):
        return value

    if dataclasses.is_dataclass(expected_type) and isinstance(value, dict):
        # Convert dict to dataclass
        field_types = {}
        try:
            field_types = get_type_hints(expected_type)
        except Exception:
            pass

        converted_fields = {}
        for field in dataclasses.fields(expected_type):
            if field.name in value:
                field_type = field_types.get(field.name, Any)
                converted_fields[field.name] = convert_to_type(value[field.name], field_type)

        return expected_type(**converted_fields)

    # Handle list
    if origin is list:
        args = get_args(expected_type)
        element_type = args[0] if args else Any
        if isinstance(value, (list, tuple)):
            return [convert_to_type(v, element_type) for v in value]

    # Handle tuple
    if origin is tuple:
        args = get_args(expected_type)
        if isinstance(value, (list, tuple)):
            if args:
                # Handle Tuple[X, Y, Z] or Tuple[X, ...]
                if len(args) == 2 and args[1] is ...:
                    return tuple(convert_to_type(v, args[0]) for v in value)
                else:
                    return tuple(
                        convert_to_type(v, args[i] if i < len(args) else Any)
                        for i, v in enumerate(value)
                    )
            return tuple(value)

    # Handle dict
    if origin is dict:
        args = get_args(expected_type)
        if isinstance(value, dict):
            key_type = args[0] if len(args) > 0 else Any
            val_type = args[1] if len(args) > 1 else Any
            return {
                convert_to_type(k, key_type): convert_to_type(v, val_type)
                for k, v in value.items()
            }

    # Handle set
    if origin is set:
        args = get_args(expected_type)
        element_type = args[0] if args else Any
        if isinstance(value, (list, tuple, set, frozenset)):
            return set(convert_to_type(v, element_type) for v in value)

    # Handle frozenset
    if origin is frozenset:
        args = get_args(expected_type)
        element_type = args[0] if args else Any
        if isinstance(value, (list, tuple, set, frozenset)):
            return frozenset(convert_to_type(v, element_type) for v in value)

    return value


def serialize_result(result: Any) -> bytes:
    """Serialize a function result."""
    return serialize(result)


def deserialize_result(data: bytes, result_type: Type) -> Any:
    """Deserialize a function result with expected type."""
    value, _ = deserialize(data, result_type)
    return convert_to_type(value, result_type)


def is_tuple_return(return_type: Type) -> bool:
    """Check if return type is a tuple (multiple return values)."""
    origin = get_origin(return_type)
    return origin is tuple


def unpack_tuple_type(return_type: Type) -> Tuple[Type, ...]:
    """Get element types from a tuple return type."""
    args = get_args(return_type)
    if args:
        return args
    return (Any,)
