import pytest
from conftest import fake_jpeg
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from niview_skill.crypto import (
    AES_KEY,
    decrypt_bytes,
    decrypt_query,
    encrypt_query,
    jpeg_size,
)


def test_query_round_trip():
    value = "alice@example.com"
    assert decrypt_query(encrypt_query(value)) == value


def test_bytes_round_trip():
    payload = b"hello world"
    encrypted = AES.new(AES_KEY, AES.MODE_ECB).encrypt(pad(payload, 16))
    assert decrypt_bytes(encrypted) == payload


def test_jpeg_size():
    assert jpeg_size(fake_jpeg(640, 360)) == (640, 360)


def test_jpeg_size_rejects_non_jpeg():
    assert jpeg_size(b"not a jpeg") is None


@pytest.mark.parametrize("value", ["", "a", "中文", "x" * 100])
def test_query_round_trip_variants(value):
    assert decrypt_query(encrypt_query(value)) == value
