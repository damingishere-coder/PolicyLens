from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_AAD = b"PolicyLens-local-DEK-v1"
VALUE_AAD = b"PolicyLens-sensitive-value-v1"
VAULT_AAD = b"PolicyLens-vault-object-v1"


class KeyProtectionError(RuntimeError):
    pass


class KeyProtector(Protocol):
    name: str

    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class DpapiProtector:
    name = "WINDOWS_DPAPI_CURRENT_USER"

    def __init__(self) -> None:
        if os.name != "nt":
            raise KeyProtectionError("Windows DPAPI is only available on Windows")

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(data)
        blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def protect(self, value: bytes) -> bytes:
        input_blob, input_buffer = self._blob(value)
        output_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        ok = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "PolicyLens DEK",
            None,
            None,
            None,
            0x1,
            ctypes.byref(output_blob),
        )
        del input_buffer
        if not ok:
            raise KeyProtectionError(f"DPAPI protect failed: {ctypes.GetLastError()}")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)

    def unprotect(self, value: bytes) -> bytes:
        input_blob, input_buffer = self._blob(value)
        output_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob), None, None, None, None, 0x1, ctypes.byref(output_blob)
        )
        del input_buffer
        if not ok:
            raise KeyProtectionError("DPAPI unlock failed for the current Windows user and machine")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)


class AesTestProtector:
    """Test-only protector used to simulate two incompatible Windows installations."""

    name = "TEST_MACHINE_WRAPPER"

    def __init__(self, machine_key: bytes) -> None:
        if len(machine_key) != 32:
            raise ValueError("test machine key must be exactly 32 bytes")
        self._machine_key = machine_key

    def protect(self, value: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._machine_key).encrypt(nonce, value, KEY_AAD)

    def unprotect(self, value: bytes) -> bytes:
        return AESGCM(self._machine_key).decrypt(value[:12], value[12:], KEY_AAD)


class KeyManager:
    def __init__(self, data_dir: Path, protector: KeyProtector | None = None) -> None:
        self.data_dir = data_dir
        self.keys_dir = data_dir / "keys"
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.key_path = self.keys_dir / "dek.dpapi.json"
        self.protector = protector or DpapiProtector()

    def load_or_create(self) -> bytes:
        if self.key_path.exists():
            payload = json.loads(self.key_path.read_text(encoding="utf-8"))
            if payload.get("version") != 1 or payload.get("protector") != self.protector.name:
                raise KeyProtectionError("unsupported or mismatched local key wrapper")
            return self.protector.unprotect(base64.b64decode(payload["wrapped_dek"]))

        dek = AESGCM.generate_key(bit_length=256)
        self.write_wrapped(dek)
        return dek

    def write_wrapped(self, dek: bytes) -> None:
        wrapped = self.protector.protect(dek)
        payload = {
            "version": 1,
            "protector": self.protector.name,
            "wrapped_dek": base64.b64encode(wrapped).decode("ascii"),
        }
        temporary = self.key_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self.key_path)


class EnvelopeCipher:
    def __init__(self, dek: bytes) -> None:
        if len(dek) != 32:
            raise ValueError("DEK must be 256 bits")
        self._key = bytearray(dek)

    def encrypt_bytes(self, value: bytes, aad: bytes = VALUE_AAD) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(bytes(self._key)).encrypt(nonce, value, aad)

    def decrypt_bytes(self, value: bytes, aad: bytes = VALUE_AAD) -> bytes:
        if len(value) < 29:
            raise ValueError("invalid encrypted envelope")
        return AESGCM(bytes(self._key)).decrypt(value[:12], value[12:], aad)

    def encrypt_text(self, value: str) -> str:
        encoded = self.encrypt_bytes(value.encode("utf-8"))
        return "enc:v1:" + base64.b64encode(encoded).decode("ascii")

    def decrypt_text(self, value: str) -> str:
        if not value.startswith("enc:v1:"):
            raise ValueError("unsupported encrypted value")
        raw = base64.b64decode(value.removeprefix("enc:v1:"))
        return self.decrypt_bytes(raw).decode("utf-8")

    def clear(self) -> None:
        for index in range(len(self._key)):
            self._key[index] = 0
