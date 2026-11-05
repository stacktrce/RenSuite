"""Signing of save and persistent files (Ren'Py 8.1+ / 7.6+ "save tokens").

Since 8.1, Ren'Py signs every save and the persistent file with a per-device
ECDSA key (NIST P-256, SHA-1 digest, raw 64-byte r||s signature) stored in
``<RenPy dir>/tokens/security_keys.txt``. An edited file must be re-signed
with that key, otherwise:

* a save triggers a "do you trust this save?" prompt, and
* the persistent file is silently discarded.

This module implements just enough of ECDSA in pure Python to sign data with
the user's *own* existing key — it never creates or changes keys.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from pathlib import Path

from . import locations

# NIST P-256 domain parameters.
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)

_PUBLIC_DER_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d03010703420004")


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    if p[0] == q[0]:
        if (p[1] + q[1]) % _P == 0:
            return None
        lam = (3 * p[0] * p[0] + _A) * pow(2 * p[1], -1, _P) % _P
    else:
        lam = (q[1] - p[1]) * pow(q[0] - p[0], -1, _P) % _P
    x = (lam * lam - p[0] - q[0]) % _P
    return x, (lam * (p[0] - x) - p[1]) % _P


def _mul(k, point):
    result = None
    while k:
        if k & 1:
            result = _add(result, point)
        point = _add(point, point)
        k >>= 1
    return result


def _digest(data: bytes) -> int:
    return int.from_bytes(hashlib.sha1(data).digest(), "big")


def public_key(secret: int):
    return _mul(secret, _G)


def sign(secret: int, data: bytes) -> bytes:
    z = _digest(data)
    while True:
        k = secrets.randbelow(_N - 1) + 1
        r = _mul(k, _G)[0] % _N
        s = pow(k, -1, _N) * (z + r * secret) % _N
        if r and s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify(public, data: bytes, signature: bytes) -> bool:
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if not (0 < r < _N and 0 < s < _N):
        return False
    w = pow(s, -1, _N)
    point = _add(_mul(_digest(data) * w % _N, _G), _mul(r * w % _N, public))
    return point is not None and point[0] % _N == r


def public_der(public) -> bytes:
    return _PUBLIC_DER_PREFIX + public[0].to_bytes(32, "big") + public[1].to_bytes(32, "big")


def parse_public_der(der: bytes):
    if not der.startswith(_PUBLIC_DER_PREFIX) or len(der) != len(_PUBLIC_DER_PREFIX) + 64:
        raise ValueError("unsupported public key encoding")
    body = der[len(_PUBLIC_DER_PREFIX):]
    return int.from_bytes(body[:32], "big"), int.from_bytes(body[32:], "big")


def private_der(secret: int) -> bytes:
    """SEC1 encoding, identical to what Ren'Py writes."""
    pub = public_key(secret)
    return (bytes.fromhex("30770201010420") + secret.to_bytes(32, "big")
            + bytes.fromhex("a00a06082a8648ce3d030107a14403420004")
            + pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big"))


def _der_read(buf: bytes, pos: int):
    tag = buf[pos]
    length = buf[pos + 1]
    pos += 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(buf[pos:pos + n], "big")
        pos += n
    return tag, buf[pos:pos + length], pos + length


def parse_private_der(der: bytes) -> int:
    """Extract the secret scalar from a SEC1 or PKCS#8 encoded key."""
    if len(der) == 32:
        return int.from_bytes(der, "big")
    tag, body, _ = _der_read(der, 0)
    if tag != 0x30:
        raise ValueError("not a DER sequence")
    _, version, pos = _der_read(body, 0)
    version = int.from_bytes(version, "big")
    if version == 1:
        _, secret, _ = _der_read(body, pos)
        return int.from_bytes(secret, "big")
    if version == 0:
        _, _, pos = _der_read(body, pos)
        _, inner, _ = _der_read(body, pos)
        return parse_private_der(inner)
    raise ValueError("unsupported private key encoding")


# ---------------------------------------------------------------------------
# Key file / signature text
# ---------------------------------------------------------------------------

def keys_file():
    for home in locations.renpy_home_dirs():
        path = home / "tokens" / "security_keys.txt"
        if path.is_file():
            return path
    return None


def load_signing_keys(path=None) -> list:
    """Return ``[(secret, verifying_key_der), …]`` from ``security_keys.txt``."""
    path = Path(path) if path else keys_file()
    if path is None or not path.is_file():
        return []
    keys = []
    for line in path.read_text("utf-8", "replace").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "signing-key":
            try:
                secret = parse_private_der(base64.b64decode(parts[1]))
                vk = base64.b64decode(parts[2]) if len(parts) > 2 else public_der(public_key(secret))
                keys.append((secret, vk))
            except (ValueError, IndexError):
                continue
    return keys


def sign_data(data: bytes, keys) -> str:
    """Build the text of a ``signatures`` member, one line per key."""
    lines = []
    for secret, vk in keys:
        sig = sign(secret, data)
        lines.append("signature %s %s\n" % (base64.b64encode(vk).decode("ascii"),
                                            base64.b64encode(sig).decode("ascii")))
    return "".join(lines)


def verify_signatures(data: bytes, signatures: str) -> bool:
    """True if any signature line is a valid signature of ``data``."""
    for line in signatures.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "signature":
            try:
                pub = parse_public_der(base64.b64decode(parts[1]))
                if verify(pub, data, base64.b64decode(parts[2])):
                    return True
            except ValueError:
                continue
    return False
