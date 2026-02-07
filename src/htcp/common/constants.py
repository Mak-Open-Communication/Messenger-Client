"""
HTCP Constants Module
Protocol constants and configuration values.
"""

# Protocol identification
MAGIC_BYTES = b'HTCP'
PROTOCOL_VERSION = 1

# Packet structure sizes
HEADER_SIZE = 12  # MAGIC(4) + VERSION(1) + TYPE(1) + LENGTH(4) + RESERVED(2)

# Payload limits
MAX_PAYLOAD_SIZE = 16 * 1024 * 1024  # 16 MB default max payload

# Timeouts (in seconds)
DEFAULT_CONNECT_TIMEOUT = 30.0
DEFAULT_READ_TIMEOUT = 60.0
DEFAULT_WRITE_TIMEOUT = 60.0

# Server configuration
DEFAULT_LISTEN_BACKLOG = 128
DEFAULT_MAX_CONNECTIONS = 100
