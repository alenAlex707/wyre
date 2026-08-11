"""
Binary wire protocol for WebSocket messages.

Frame layout:
  [1 byte type][4 bytes length][N bytes payload]

  - type:     message type identifier (MSG_CHAT, MSG_ERROR, ...)
  - length:   payload size in bytes (unsigned 32-bit integer)
  - payload:  UTF-8 encoded JSON object

The length field uses network byte order (big-endian) so both client and
server interpret the same byte sequence as the same integer regardless of
whether the host is little-endian (x86) or big-endian.
"""

import json
import struct

MSG_CHAT = 1
MSG_ERROR = 2

_HEADER_SIZE = 5  # 1 byte type + 4 byte length


def pack_message(msg_type: int, payload: dict) -> bytes:
    payload_bytes = json.dumps(payload).encode("utf-8")
    header = struct.pack("!BI", msg_type, len(payload_bytes))
    return header + payload_bytes


def unpack_message(data: bytes) -> tuple[int, dict]:
    if len(data) < _HEADER_SIZE:
        raise ValueError(
            f"frame too short: expected at least {_HEADER_SIZE} bytes, got {len(data)}"
        )

    msg_type, payload_len = struct.unpack("!BI", data[:_HEADER_SIZE])

    total_len = _HEADER_SIZE + payload_len
    if len(data) < total_len:
        raise ValueError(
            f"frame truncated: expected {total_len} bytes, got {len(data)}"
        )

    payload_bytes = data[_HEADER_SIZE:total_len]
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid payload JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    return msg_type, payload
