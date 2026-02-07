"""
HTCP Serialization Module
Supports automatic serialization/deserialization of all Python types.
"""

import struct
import dataclasses

from datetime import datetime, date, time, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID
from typing import Any, Type, get_type_hints, get_origin, get_args, Union

try:
    from pydantic import BaseModel as PydanticBaseModel
    PYDANTIC_AVAILABLE = True
except ImportError:
    PydanticBaseModel = None
    PYDANTIC_AVAILABLE = False


def _is_pydantic_model(obj: Any) -> bool:
    """Check if object is a Pydantic model instance."""

    if not PYDANTIC_AVAILABLE:
        return False
    return isinstance(obj, PydanticBaseModel)


def _is_pydantic_model_class(cls: Type) -> bool:
    """Check if class is a Pydantic model class."""

    if not PYDANTIC_AVAILABLE:
        return False
    try:
        return isinstance(cls, type) and issubclass(cls, PydanticBaseModel)
    except TypeError:
        return False


class TypeTag:
    """Type tags for binary protocol."""
    NONE = 0x00
    BOOL_TRUE = 0x01
    BOOL_FALSE = 0x02
    INT = 0x03
    FLOAT = 0x04
    STR = 0x05
    BYTES = 0x06
    LIST = 0x07
    TUPLE = 0x08
    DICT = 0x09
    SET = 0x0A
    FROZENSET = 0x0B
    DATACLASS = 0x0C
    DATETIME = 0x0D
    DATE = 0x0E
    TIME = 0x0F
    TIMEDELTA = 0x10
    DECIMAL = 0x11
    COMPLEX = 0x12
    UUID = 0x13
    ENUM = 0x14
    INT_NEGATIVE = 0x15
    INT_BIG = 0x16
    INT_BIG_NEGATIVE = 0x17
    PYDANTIC_MODEL = 0x18


def serialize(obj: Any) -> bytes:
    """Serialize any Python object to bytes."""
    if obj is None:
        return bytes([TypeTag.NONE])

    if isinstance(obj, bool):
        return bytes([TypeTag.BOOL_TRUE if obj else TypeTag.BOOL_FALSE])

    if isinstance(obj, int):
        return _serialize_int(obj)

    if isinstance(obj, float):
        data = struct.pack('>d', obj)
        return bytes([TypeTag.FLOAT]) + data

    if isinstance(obj, str):
        encoded = obj.encode('utf-8')
        return bytes([TypeTag.STR]) + _pack_length(len(encoded)) + encoded

    if isinstance(obj, bytes):
        return bytes([TypeTag.BYTES]) + _pack_length(len(obj)) + obj

    if isinstance(obj, list):
        return _serialize_sequence(obj, TypeTag.LIST)

    if isinstance(obj, tuple):
        return _serialize_sequence(obj, TypeTag.TUPLE)

    if isinstance(obj, dict):
        return _serialize_dict(obj)

    if isinstance(obj, set):
        return _serialize_sequence(obj, TypeTag.SET)

    if isinstance(obj, frozenset):
        return _serialize_sequence(obj, TypeTag.FROZENSET)

    if isinstance(obj, Enum):
        return _serialize_enum(obj)

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _serialize_dataclass(obj)

    if _is_pydantic_model(obj):
        return _serialize_pydantic(obj)

    if isinstance(obj, datetime):
        return _serialize_datetime(obj)

    if isinstance(obj, date):
        return _serialize_date(obj)

    if isinstance(obj, time):
        return _serialize_time(obj)

    if isinstance(obj, timedelta):
        return _serialize_timedelta(obj)

    if isinstance(obj, Decimal):
        return _serialize_decimal(obj)

    if isinstance(obj, complex):
        return _serialize_complex(obj)

    if isinstance(obj, UUID):
        return bytes([TypeTag.UUID]) + obj.bytes

    raise TypeError(f"Cannot serialize type: {type(obj)}")


def deserialize(data: bytes, expected_type: Type = None) -> tuple[Any, int]:
    """
    Deserialize bytes to Python object.
    Returns (object, bytes_consumed).
    """
    if not data:
        raise ValueError("Empty data")

    tag = data[0]
    offset = 1

    if tag == TypeTag.NONE:
        return None, offset

    if tag == TypeTag.BOOL_TRUE:
        return True, offset

    if tag == TypeTag.BOOL_FALSE:
        return False, offset

    if tag == TypeTag.INT:
        value = struct.unpack('>q', data[offset:offset + 8])[0]
        return value, offset + 8

    if tag == TypeTag.INT_NEGATIVE:
        value = struct.unpack('>q', data[offset:offset + 8])[0]
        return value, offset + 8

    if tag == TypeTag.INT_BIG:
        length, len_size = _unpack_length(data[offset:])
        offset += len_size
        value = int.from_bytes(data[offset:offset + length], 'big', signed=False)
        return value, offset + length

    if tag == TypeTag.INT_BIG_NEGATIVE:
        length, len_size = _unpack_length(data[offset:])
        offset += len_size
        value = -int.from_bytes(data[offset:offset + length], 'big', signed=False)
        return value, offset + length

    if tag == TypeTag.FLOAT:
        value = struct.unpack('>d', data[offset:offset + 8])[0]
        return value, offset + 8

    if tag == TypeTag.STR:
        length, len_size = _unpack_length(data[offset:])
        offset += len_size
        value = data[offset:offset + length].decode('utf-8')
        return value, offset + length

    if tag == TypeTag.BYTES:
        length, len_size = _unpack_length(data[offset:])
        offset += len_size
        value = data[offset:offset + length]
        return value, offset + length

    if tag == TypeTag.LIST:
        return _deserialize_sequence(data, offset, list, expected_type)

    if tag == TypeTag.TUPLE:
        items, consumed = _deserialize_sequence(data, offset, list, expected_type)
        return tuple(items), consumed

    if tag == TypeTag.DICT:
        return _deserialize_dict(data, offset, expected_type)

    if tag == TypeTag.SET:
        items, consumed = _deserialize_sequence(data, offset, list, expected_type)
        return set(items), consumed

    if tag == TypeTag.FROZENSET:
        items, consumed = _deserialize_sequence(data, offset, list, expected_type)
        return frozenset(items), consumed

    if tag == TypeTag.DATACLASS:
        return _deserialize_dataclass(data, offset, expected_type)

    if tag == TypeTag.PYDANTIC_MODEL:
        return _deserialize_pydantic(data, offset, expected_type)

    if tag == TypeTag.DATETIME:
        return _deserialize_datetime(data, offset)

    if tag == TypeTag.DATE:
        return _deserialize_date(data, offset)

    if tag == TypeTag.TIME:
        return _deserialize_time(data, offset)

    if tag == TypeTag.TIMEDELTA:
        return _deserialize_timedelta(data, offset)

    if tag == TypeTag.DECIMAL:
        return _deserialize_decimal(data, offset)

    if tag == TypeTag.COMPLEX:
        return _deserialize_complex(data, offset)

    if tag == TypeTag.UUID:
        return UUID(bytes=data[offset:offset + 16]), offset + 16

    if tag == TypeTag.ENUM:
        return _deserialize_enum(data, offset, expected_type)

    raise ValueError(f"Unknown type tag: {tag}")


def _pack_length(length: int) -> bytes:
    """Pack length as 4-byte big-endian."""
    return struct.pack('>I', length)


def _unpack_length(data: bytes) -> tuple[int, int]:
    """Unpack length, returns (length, bytes_consumed)."""
    return struct.unpack('>I', data[:4])[0], 4


def _serialize_int(obj: int) -> bytes:
    """Serialize integer, handling big integers.
    """
    if -9223372036854775808 <= obj <= 9223372036854775807:
        if obj >= 0:
            return bytes([TypeTag.INT]) + struct.pack('>q', obj)
        else:
            return bytes([TypeTag.INT_NEGATIVE]) + struct.pack('>q', obj)
    else:
        abs_val = abs(obj)
        byte_length = (abs_val.bit_length() + 7) // 8
        int_bytes = abs_val.to_bytes(byte_length, 'big', signed=False)
        if obj >= 0:
            return bytes([TypeTag.INT_BIG]) + _pack_length(byte_length) + int_bytes
        else:
            return bytes([TypeTag.INT_BIG_NEGATIVE]) + _pack_length(byte_length) + int_bytes


def _serialize_sequence(obj, tag: int) -> bytes:
    """Serialize list, tuple, set, frozenset."""
    items = list(obj)
    result = bytearray([tag])
    result.extend(_pack_length(len(items)))
    for item in items:
        result.extend(serialize(item))
    return bytes(result)


def _deserialize_sequence(data: bytes, offset: int, container_type: type, expected_type: Type = None) -> tuple[list, int]:
    """Deserialize a sequence."""
    length, len_size = _unpack_length(data[offset:])
    offset += len_size

    element_type = None
    if expected_type:
        origin = get_origin(expected_type)
        if origin in (list, set, frozenset, tuple):
            args = get_args(expected_type)
            if args:
                element_type = args[0]

    items = []
    for _ in range(length):
        item, consumed = deserialize(data[offset:], element_type)
        items.append(item)
        offset += consumed

    return items, offset


def _serialize_dict(obj: dict) -> bytes:
    """Serialize dictionary."""
    result = bytearray([TypeTag.DICT])
    result.extend(_pack_length(len(obj)))
    for key, value in obj.items():
        result.extend(serialize(key))
        result.extend(serialize(value))
    return bytes(result)


def _deserialize_dict(data: bytes, offset: int, expected_type: Type = None) -> tuple[dict, int]:
    """Deserialize dictionary."""
    length, len_size = _unpack_length(data[offset:])
    offset += len_size

    key_type = None
    value_type = None
    if expected_type:
        origin = get_origin(expected_type)
        if origin is dict:
            args = get_args(expected_type)
            if len(args) >= 2:
                key_type = args[0]
                value_type = args[1]

    result = {}
    for _ in range(length):
        key, consumed = deserialize(data[offset:], key_type)
        offset += consumed
        value, consumed = deserialize(data[offset:], value_type)
        offset += consumed
        result[key] = value

    return result, offset


def _serialize_dataclass(obj) -> bytes:
    """Serialize dataclass instance."""
    cls = type(obj)
    class_name = f"{cls.__module__}.{cls.__qualname__}"
    name_bytes = class_name.encode('utf-8')

    fields = dataclasses.fields(obj)
    result = bytearray([TypeTag.DATACLASS])
    result.extend(_pack_length(len(name_bytes)))
    result.extend(name_bytes)
    result.extend(_pack_length(len(fields)))

    for field in fields:
        field_name = field.name.encode('utf-8')
        result.extend(_pack_length(len(field_name)))
        result.extend(field_name)
        result.extend(serialize(getattr(obj, field.name)))

    return bytes(result)


def _deserialize_dataclass(data: bytes, offset: int, expected_type: Type = None) -> tuple[Any, int]:
    """Deserialize dataclass instance."""
    name_len, len_size = _unpack_length(data[offset:])
    offset += len_size
    class_name = data[offset:offset + name_len].decode('utf-8')
    offset += name_len

    field_count, len_size = _unpack_length(data[offset:])
    offset += len_size

    field_values = {}
    field_types = {}

    if expected_type and dataclasses.is_dataclass(expected_type):
        try:
            field_types = get_type_hints(expected_type)
        except Exception:
            pass

    for _ in range(field_count):
        fname_len, len_size = _unpack_length(data[offset:])
        offset += len_size
        field_name = data[offset:offset + fname_len].decode('utf-8')
        offset += fname_len

        field_type = field_types.get(field_name)
        value, consumed = deserialize(data[offset:], field_type)
        offset += consumed
        field_values[field_name] = value

    if expected_type and dataclasses.is_dataclass(expected_type):
        return expected_type(**field_values), offset

    # Return as dict when no expected_type - will be converted later by prepare_arguments
    return field_values, offset


def _serialize_pydantic(obj) -> bytes:
    """Serialize Pydantic model instance."""

    cls = type(obj)
    class_name = f"{cls.__module__}.{cls.__qualname__}"
    name_bytes = class_name.encode('utf-8')

    model_data = obj.model_dump()
    fields = list(model_data.keys())

    result = bytearray([TypeTag.PYDANTIC_MODEL])
    result.extend(_pack_length(len(name_bytes)))
    result.extend(name_bytes)
    result.extend(_pack_length(len(fields)))

    for field_name in fields:
        fname_bytes = field_name.encode('utf-8')
        result.extend(_pack_length(len(fname_bytes)))
        result.extend(fname_bytes)
        result.extend(serialize(model_data[field_name]))

    return bytes(result)


def _deserialize_pydantic(data: bytes, offset: int, expected_type: Type = None) -> tuple[Any, int]:
    """Deserialize Pydantic model instance."""

    name_len, len_size = _unpack_length(data[offset:])
    offset += len_size
    class_name = data[offset:offset + name_len].decode('utf-8')
    offset += name_len

    field_count, len_size = _unpack_length(data[offset:])
    offset += len_size

    field_values = {}
    field_types = {}

    if expected_type and _is_pydantic_model_class(expected_type):
        try:
            field_types = get_type_hints(expected_type)
        except Exception:
            pass

    for _ in range(field_count):
        fname_len, len_size = _unpack_length(data[offset:])
        offset += len_size
        field_name = data[offset:offset + fname_len].decode('utf-8')
        offset += fname_len

        field_type = field_types.get(field_name)
        value, consumed = deserialize(data[offset:], field_type)
        offset += consumed
        field_values[field_name] = value

    if expected_type and _is_pydantic_model_class(expected_type):
        return expected_type.model_validate(field_values), offset

    # Return as dict when no expected_type
    return field_values, offset


def _serialize_datetime(obj: datetime) -> bytes:
    """Serialize datetime as ISO format string."""
    iso = obj.isoformat().encode('utf-8')
    return bytes([TypeTag.DATETIME]) + _pack_length(len(iso)) + iso


def _deserialize_datetime(data: bytes, offset: int) -> tuple[datetime, int]:
    """Deserialize datetime from ISO format string."""
    length, len_size = _unpack_length(data[offset:])
    offset += len_size
    iso = data[offset:offset + length].decode('utf-8')
    return datetime.fromisoformat(iso), offset + length


def _serialize_date(obj: date) -> bytes:
    """Serialize date as ISO format string."""
    iso = obj.isoformat().encode('utf-8')
    return bytes([TypeTag.DATE]) + _pack_length(len(iso)) + iso


def _deserialize_date(data: bytes, offset: int) -> tuple[date, int]:
    """Deserialize date from ISO format string."""
    length, len_size = _unpack_length(data[offset:])
    offset += len_size
    iso = data[offset:offset + length].decode('utf-8')
    return date.fromisoformat(iso), offset + length


def _serialize_time(obj: time) -> bytes:
    """Serialize time as ISO format string."""
    iso = obj.isoformat().encode('utf-8')
    return bytes([TypeTag.TIME]) + _pack_length(len(iso)) + iso


def _deserialize_time(data: bytes, offset: int) -> tuple[time, int]:
    """Deserialize time from ISO format string."""
    length, len_size = _unpack_length(data[offset:])
    offset += len_size
    iso = data[offset:offset + length].decode('utf-8')
    return time.fromisoformat(iso), offset + length


def _serialize_timedelta(obj: timedelta) -> bytes:
    """Serialize timedelta as total seconds."""
    data = struct.pack('>d', obj.total_seconds())
    return bytes([TypeTag.TIMEDELTA]) + data


def _deserialize_timedelta(data: bytes, offset: int) -> tuple[timedelta, int]:
    """Deserialize timedelta from total seconds."""
    seconds = struct.unpack('>d', data[offset:offset + 8])[0]
    return timedelta(seconds=seconds), offset + 8


def _serialize_decimal(obj: Decimal) -> bytes:
    """Serialize Decimal as string."""
    s = str(obj).encode('utf-8')
    return bytes([TypeTag.DECIMAL]) + _pack_length(len(s)) + s


def _deserialize_decimal(data: bytes, offset: int) -> tuple[Decimal, int]:
    """Deserialize Decimal from string."""
    length, len_size = _unpack_length(data[offset:])
    offset += len_size
    s = data[offset:offset + length].decode('utf-8')
    return Decimal(s), offset + length


def _serialize_complex(obj: complex) -> bytes:
    """Serialize complex number."""
    data = struct.pack('>dd', obj.real, obj.imag)
    return bytes([TypeTag.COMPLEX]) + data


def _deserialize_complex(data: bytes, offset: int) -> tuple[complex, int]:
    """Deserialize complex number."""
    real, imag = struct.unpack('>dd', data[offset:offset + 16])
    return complex(real, imag), offset + 16


def _serialize_enum(obj: Enum) -> bytes:
    """Serialize Enum member."""
    cls = type(obj)
    class_name = f"{cls.__module__}.{cls.__qualname__}".encode('utf-8')
    member_name = obj.name.encode('utf-8')

    result = bytearray([TypeTag.ENUM])
    result.extend(_pack_length(len(class_name)))
    result.extend(class_name)
    result.extend(_pack_length(len(member_name)))
    result.extend(member_name)
    return bytes(result)


def _deserialize_enum(data: bytes, offset: int, expected_type: Type = None) -> tuple[Any, int]:
    """Deserialize Enum member."""
    cname_len, len_size = _unpack_length(data[offset:])
    offset += len_size
    class_name = data[offset:offset + cname_len].decode('utf-8')
    offset += cname_len

    mname_len, len_size = _unpack_length(data[offset:])
    offset += len_size
    member_name = data[offset:offset + mname_len].decode('utf-8')
    offset += mname_len

    if expected_type and issubclass(expected_type, Enum):
        return expected_type[member_name], offset

    # Return as dict with metadata when no expected_type
    return {"__enum__": class_name, "__member__": member_name}, offset


def get_inner_type(annotation: Type) -> Type:
    """Extract inner type from Optional, Union, etc."""
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation
