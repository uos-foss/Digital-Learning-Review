"""
Password hashing primitives.

Passwords are stored with scrypt (memory-hard, salted, work-factored) from the
Python standard library - no third-party dependency, so nothing new to install
in the Docker image.

Stored format is self-describing, so parameters can be raised later without a
second migration:

    scrypt$<n>$<r>$<p>$<base64 salt>$<base64 derived key>

Legacy unsalted SHA-256 hex digests are still accepted so that nobody is locked
out mid-migration. Callers should use `needs_rehash` to upgrade those records
transparently on successful login.

An empty stored hash is never a match. Those rows belong to accounts that sign
in via Google OAuth, where identity is proven by the token exchange rather than
a password - see the note on GoogleOAuthProvider in auth.py.
"""

import base64
import hashlib
import hmac
import logging
import os

# scrypt cost parameters. n is the CPU/memory cost, r the block size, p the
# parallelisation factor. n=2**14 costs roughly 30ms per verification on the
# deployment VM, which is imperceptible at login but a meaningful barrier to
# offline brute force. Raise n if hardware improves; older hashes keep working
# because their parameters travel with them in the stored string.
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16

SCHEME_PREFIX = "scrypt$"
LEGACY_SHA256_LENGTH = 64

# Scheme names returned by verify_password
SCHEME_SCRYPT = "scrypt"
SCHEME_LEGACY = "legacy-sha256"
SCHEME_NONE = "none"


def hash_password(password: str) -> str:
    """Hashes a plaintext password for storage. Each call uses a fresh salt."""
    salt = os.urandom(SALT_BYTES)
    derived = hashlib.scrypt(
        str(password).strip().encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return "$".join([
        SCHEME_SCRYPT,
        str(SCRYPT_N),
        str(SCRYPT_R),
        str(SCRYPT_P),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    ])


def verify_password(password: str, stored_hash: str) -> tuple:
    """
    Checks a plaintext password against a stored hash.

    Returns (is_valid, scheme) where scheme is one of SCHEME_SCRYPT,
    SCHEME_LEGACY or SCHEME_NONE. The scheme lets the caller decide whether
    to upgrade the stored record after a successful login.
    """
    candidate = str(password).strip().encode("utf-8")
    stored = str(stored_hash).strip() if stored_hash is not None else ""

    # Empty hash: OAuth-only account. Never a password match.
    if not stored:
        return False, SCHEME_NONE

    if stored.startswith(SCHEME_PREFIX):
        try:
            _scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
            derived = hashlib.scrypt(
                candidate,
                salt=base64.b64decode(salt_b64),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=SCRYPT_DKLEN,
            )
            return hmac.compare_digest(derived, base64.b64decode(key_b64)), SCHEME_SCRYPT
        except (ValueError, TypeError, base64.binascii.Error) as e:
            # A malformed record must fail closed, but say so - silently
            # returning False here would look identical to a wrong password.
            logging.error(f"❌ Malformed scrypt hash could not be parsed: {e}")
            return False, SCHEME_SCRYPT

    # Legacy unsalted SHA-256 hex digest.
    if len(stored) == LEGACY_SHA256_LENGTH:
        legacy = hashlib.sha256(candidate).hexdigest()
        return hmac.compare_digest(legacy, stored.lower()), SCHEME_LEGACY

    logging.warning("⚠️ Stored password hash is in an unrecognised format; rejecting.")
    return False, SCHEME_NONE


def needs_rehash(stored_hash: str) -> bool:
    """
    True if a successful login against this record should be re-hashed.

    Covers legacy SHA-256 records and scrypt records whose cost parameters are
    below the current settings. Empty hashes are left alone - they are OAuth
    accounts with no password to upgrade.
    """
    stored = str(stored_hash).strip() if stored_hash is not None else ""
    if not stored:
        return False

    if stored.startswith(SCHEME_PREFIX):
        try:
            _scheme, n, r, p, _salt, _key = stored.split("$")
            return (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
        except (ValueError, TypeError):
            return True

    return len(stored) == LEGACY_SHA256_LENGTH
