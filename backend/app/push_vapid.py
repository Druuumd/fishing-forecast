"""VAPID keypair generation + helpers.

Web Push uses VAPID (RFC 8292) so the app server can sign push messages
that browser push services trust. The keypair is generated once and
stored in env (VAPID_PRIVATE_KEY_PEM, VAPID_PUBLIC_KEY_B64); the
public key is also exposed via /v1/push/vapid-public-key for the
browser's pushManager.subscribe() call.

Run as a script to print fresh keys:
    docker compose exec api python -m app.push_vapid
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_vapid_keypair() -> tuple[str, str]:
    """Returns (public_key_b64url, private_key_pem). Public is the 65-byte
    uncompressed P-256 point encoded as base64url-without-padding —
    that's what the browser expects as applicationServerKey.
    """
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key()

    public_bytes = public.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()

    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    return public_b64, private_pem


if __name__ == "__main__":
    pub, priv = generate_vapid_keypair()
    print("# Add these to your .env (or compose env):")
    print(f"VAPID_PUBLIC_KEY_B64={pub}")
    print("VAPID_PRIVATE_KEY_PEM='" + priv.replace("\n", "\\n") + "'")
    print()
    print(
        "# After deploying, the browser fetches the public key via "
        "GET /v1/push/vapid-public-key"
    )
