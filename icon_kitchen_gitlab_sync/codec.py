import base64
import gzip
import json
from typing import Any, Dict


def _base64_to_base64url(data: bytes) -> str:
    """bytes -> url-safe base64 string without padding."""
    b64 = base64.b64encode(data).decode("ascii")
    return b64.replace("+", "-").replace("/", "_").rstrip("=")


def _base64url_to_bytes(s: str) -> bytes:
    """url-safe base64 string (no padding) -> bytes."""
    s = s.replace("-", "+").replace("_", "/")
    # restore padding
    while len(s) % 4:
        s += "="
    return base64.b64decode(s)


def encode_json_to_url_fragment(obj: Any) -> str:
    """Encode a JSON-compatible object into a gzip+base64url fragment for `/i/<...>`.

    The result can be appended to `https://icon.kitchen/i/`.
    """
    json_str = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
    compressed = gzip.compress(json_str.encode("utf-8"))
    return _base64_to_base64url(compressed)


def decode_url_fragment_to_json(fragment: str) -> Dict[str, Any]:
    """Decode a base64url+gzip fragment from `/i/<...>` back to a JSON dict."""
    raw = _base64url_to_bytes(fragment)
    decompressed = gzip.decompress(raw).decode("utf-8")
    return json.loads(decompressed)


def build_icon_kitchen_url(fragment: str) -> str:
    """Build a full icon.kitchen URL from a fragment."""
    return f"https://icon.kitchen/i/{fragment}"

