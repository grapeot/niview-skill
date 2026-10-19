import base64
import urllib.parse

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

AES_KEY = b"d5%kBl^Rg3C%sfZl"


def _cipher() -> AES:
    return AES.new(AES_KEY, AES.MODE_ECB)


def encrypt_query(value: str) -> str:
    """Encode a query value the way the mobile client does."""
    encrypted = _cipher().encrypt(pad(value.encode("utf-8"), 16))
    encoded = base64.b64encode(encrypted).decode("ascii") + "\n"
    return urllib.parse.quote(encoded, safe="")


def decrypt_query(value: str) -> str:
    """Decode a response `data` field or an encrypted query value."""
    raw = base64.b64decode(urllib.parse.unquote(value))
    return unpad(_cipher().decrypt(raw), 16).decode("utf-8")


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt an event image ending in `.encrypt`."""
    return unpad(_cipher().decrypt(data), 16)


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Return (width, height) from a JPEG SOF marker, or None."""
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 3 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in (0xD8, 0xD9):
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if index + 7 > len(data):
                return None
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += length
    return None
