"""
A read-only bridge so the existing scrypt password hashes keep working.

`security.py` stores `scrypt$<n>$<r>$<p>$<b64 salt>$<b64 key>`, which Django
cannot read on its own. This hasher verifies that format and nothing else: it
refuses to *write* it (`encode` raises), because new passwords should be stored
in Django's own format, and because a second writer of that format would be one
more thing to keep in step with `security.py`.

Legacy unsalted SHA-256 digests are deliberately not handled here. They exist
in the live data, and `security.py` upgrades them on successful login, so the
Streamlit app should finish that migration before accounts move across. If any
remain when the move happens, those people reset their password.
"""

from django.contrib.auth.hashers import BasePasswordHasher


class LegacyScryptHasher(BasePasswordHasher):
    """Verifies hashes written by security.hash_password(). Verify only."""

    algorithm = "scrypt_legacy"

    def encode(self, password, salt, **kwargs):
        raise NotImplementedError(
            "LegacyScryptHasher verifies existing hashes only. New passwords are "
            "written by the first hasher in settings.PASSWORD_HASHERS."
        )

    def salt(self):
        raise NotImplementedError("LegacyScryptHasher never writes a hash.")

    def verify(self, password, encoded):
        from security import verify_password

        # Django prefixes stored hashes with "<algorithm>$"; strip ours back to
        # the exact string security.py wrote, so one function decides the answer.
        stored = encoded[len(self.algorithm) + 1:] if encoded.startswith(
            self.algorithm + "$") else encoded
        is_valid, _scheme = verify_password(password, stored)
        return bool(is_valid)

    def safe_summary(self, encoded):
        return {"algorithm": self.algorithm, "hash": "********"}

    def must_update(self, encoded):
        # Always re-hash into Django's own format on the next successful login.
        return True

    def harden_runtime(self, password, encoded):
        # scrypt's own cost is the hardening; nothing to add.
        pass
