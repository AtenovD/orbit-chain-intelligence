"""Sign-In with Ethereum (EIP-4361) helpers.

A wallet proves ownership by signing a server-issued message. The nonce is an
HMAC-signed timestamp, so it needs no storage to issue, and it is recorded in
``wallet_nonces`` when spent so a captured signature cannot be replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from eth_account import Account
from eth_account.messages import encode_defunct

from orchestrator.config import get_settings

NONCE_TTL = timedelta(minutes=10)
ROBINHOOD_CHAIN_ID = 4663
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


class WalletAuthError(ValueError):
    pass


def _secret() -> bytes:
    return (get_settings().secret_encryption_key or "orbit-local-wallet-nonce").encode()


def issue_nonce(now: datetime | None = None) -> str:
    stamp = int((now or datetime.now(timezone.utc)).timestamp())
    body = f"{stamp:x}{secrets.token_hex(8)}"
    mac = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{body}{mac}"


def check_nonce(nonce: str, now: datetime | None = None) -> None:
    if not re.fullmatch(r"[0-9a-f]{8,}", nonce or "") or len(nonce) < 8 + 16 + 24:
        raise WalletAuthError("Invalid sign-in nonce")
    body, mac = nonce[:-24], nonce[-24:]
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(mac, expected):
        raise WalletAuthError("Invalid sign-in nonce")
    issued = datetime.fromtimestamp(int(body[:-16], 16), timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current - issued > NONCE_TTL or issued - current > timedelta(minutes=1):
        raise WalletAuthError("The sign-in request expired. Try again")


def expected_domain() -> str:
    return urlparse(get_settings().public_url).netloc


def build_message(*, address: str, nonce: str, issued_at: datetime, domain: str | None = None, uri: str | None = None) -> str:
    domain = domain or expected_domain()
    uri = uri or get_settings().public_url.rstrip("/")
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n{address}\n\n"
        "Sign in to Orbit. This does not send a transaction or cost gas.\n\n"
        f"URI: {uri}\nVersion: 1\nChain ID: {ROBINHOOD_CHAIN_ID}\nNonce: {nonce}\n"
        f"Issued At: {issued_at.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
    )


def _field(message: str, name: str) -> str:
    match = re.search(rf"^{name}: (.+)$", message, re.M)
    if not match:
        raise WalletAuthError("Malformed sign-in message")
    return match.group(1).strip()


def verify_signed_message(message: str, signature: str, *, now: datetime | None = None) -> tuple[str, str]:
    """Return ``(lower-cased address, nonce)`` when the signature is valid for our own message."""
    lines = message.split("\n")
    if len(lines) < 8 or not _ADDRESS.fullmatch(lines[1] or ""):
        raise WalletAuthError("Malformed sign-in message")
    address = lines[1]
    if lines[0] != f"{expected_domain()} wants you to sign in with your Ethereum account:":
        raise WalletAuthError("The sign-in message is for a different site")
    nonce = _field(message, "Nonce")
    check_nonce(nonce, now)
    if _field(message, "Version") != "1":
        raise WalletAuthError("Unsupported sign-in message version")
    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception as exc:  # eth_account raises several unrelated types on bad input
        raise WalletAuthError("The wallet signature is invalid") from exc
    if recovered.lower() != address.lower():
        raise WalletAuthError("The wallet signature does not match the address")
    return address.lower(), nonce
