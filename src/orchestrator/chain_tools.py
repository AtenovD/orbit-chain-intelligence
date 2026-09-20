"""Native Robinhood Chain tools the crew can call during a run.

These talk to the public JSON-RPC endpoint directly: no API key, no indexer,
and no Cloudflare-protected explorer in the path. Every tool is read-only and
returns a compact dict sized for a model context rather than a raw dump.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

import httpx

RPC_URL = os.getenv("ROBINHOOD_CHAIN_RPC", "https://rpc.mainnet.chain.robinhood.com")
CHAIN_ID = 4663
EXPLORER = "https://robinhoodchain.blockscout.com"

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"

# Read off a live pool's factory() rather than assumed: this chain's own V3 deployment.
V3_FACTORY = os.getenv(
    "ROBINHOOD_CHAIN_V3_FACTORY", "0x1f7d7550b1b028f7571e69a784071f0205fd2efa"
)
V3_FEE_TIERS = (100, 500, 3000, 10000)
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
QUOTE_ASSETS = (WETH, USDG)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# ERC-165/721 identifiers and selectors. ERC-721 deliberately makes
# ``totalSupply`` optional; an absent value is reported as unavailable instead
# of pretending a transfer count is the collection supply.
SUPPORTS_INTERFACE_SELECTOR = "01ffc9a7"
ERC165_INTERFACE_ID = "01ffc9a7"
ERC721_INTERFACE_ID = "80ac58cd"
ERC721_METADATA_INTERFACE_ID = "5b5e139f"
ERC721_ENUMERABLE_INTERFACE_ID = "780e9d63"

# EIP-1967 storage slots: a proxy hides its real logic behind these.
EIP1967_IMPLEMENTATION = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
LEGACY_IMPLEMENTATION = "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3"

# Selectors whose presence in deployed bytecode changes the risk picture.
RISK_SELECTORS: dict[str, str] = {
    "40c10f19": "mint(address,uint256)",
    "8456cb59": "pause()",
    "3f4ba83a": "unpause()",
    "f2fde38b": "transferOwnership(address)",
    "715018a6": "renounceOwnership()",
    "f9f92be4": "blacklist(address)",
    "1e89d545": "setBlacklist",
    "9dc29fac": "burn(address,uint256)",
    "42966c68": "burn(uint256)",
    "a9059cbb": "transfer(address,uint256)",
    "dd62ed3e": "allowance(address,address)",
}
# Selectors that hand an owner unilateral power over holders' funds.
DANGEROUS = {"40c10f19", "8456cb59", "f9f92be4", "1e89d545", "9dc29fac"}

_MAX_BLOCK_WINDOW = 2000
_RPC_RETRIES = 4
_MAX_CANDLES = 48


def _is_address(value: str) -> bool:
    value = (value or "").strip()
    return value.startswith("0x") and len(value) == 42


def _normalise(value: str) -> str:
    return (value or "").strip().lower()


def _explorer_link(address: str, kind: str = "address") -> str:
    return f"{EXPLORER}/{kind}/{address}"


class ChainError(RuntimeError):
    """Raised when the chain cannot answer; surfaced to the agent verbatim."""


async def _rpc(client: httpx.AsyncClient, method: str, params: list[Any]) -> Any:
    # The public endpoint is rate limited, and the multi-call tools below (bisecting
    # for a token's first block, paging transfer history) trip it without a backoff.
    delay = 0.6
    last: Exception | None = None
    for attempt in range(_RPC_RETRIES):
        try:
            response = await client.post(
                RPC_URL,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"rpc {response.status_code}", request=response.request, response=response
                )
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last = exc
            if attempt == _RPC_RETRIES - 1:
                break
            await asyncio.sleep(delay)
            delay *= 2
            continue
        payload = response.json()
        if "error" in payload:
            raise ChainError(f"{method}: {payload['error'].get('message', 'rpc error')}")
        return payload.get("result")
    raise ChainError(f"{method}: chain endpoint unavailable ({last})")


async def _call(client: httpx.AsyncClient, to: str, selector: str) -> str | None:
    try:
        return await _rpc(client, "eth_call", [{"to": to, "data": f"0x{selector}"}, "latest"])
    except (ChainError, httpx.HTTPError):
        return None


def _abi_word(value: str | int) -> str:
    if isinstance(value, int):
        return hex(value)[2:].rjust(64, "0")
    return value[2:].rjust(64, "0")


async def _call_with_args(
    client: httpx.AsyncClient, to: str, selector: str, args: list[str | int]
) -> str | None:
    data = "0x" + selector + "".join(_abi_word(arg) for arg in args)
    try:
        return await _rpc(client, "eth_call", [{"to": to, "data": data}, "latest"])
    except (ChainError, httpx.HTTPError):
        return None


async def _supports_interface(client: httpx.AsyncClient, address: str, interface_id: str) -> bool | None:
    """Ask ERC-165 about a four-byte interface without encoding it as an integer.

    ABI ``bytes4`` values are left-aligned in their word, unlike uints. Sending
    an integer-encoded interface id produces a valid-looking but wrong call.
    """
    if len(interface_id) != 8:
        raise ValueError("interface_id must be exactly four bytes")
    data = "0x" + SUPPORTS_INTERFACE_SELECTOR + interface_id.lower() + "0" * 56
    try:
        raw = await _rpc(client, "eth_call", [{"to": address, "data": data}, "latest"])
    except (ChainError, httpx.HTTPError):
        return None
    value = _decode_uint(raw)
    return bool(value) if value is not None else None


def _decode_string(raw: str | None) -> str | None:
    """Decode an ABI-encoded string, tolerating bytes32-style returns."""
    if not raw or raw == "0x":
        return None
    body = raw[2:]
    try:
        if len(body) >= 128:
            length = int(body[64:128], 16)
            if 0 < length <= 256:
                text = bytes.fromhex(body[128 : 128 + length * 2]).decode("utf-8", "ignore")
                if text.strip():
                    return text.strip()
        text = bytes.fromhex(body).decode("utf-8", "ignore").replace("\x00", "").strip()
        return text or None
    except ValueError:
        return None


def _decode_uint(raw: str | None) -> int | None:
    if not raw or raw == "0x":
        return None
    try:
        return int(raw, 16)
    except ValueError:
        return None


def _decode_address(raw: str | None) -> str | None:
    if not raw or len(raw) < 66:
        return None
    return "0x" + raw[-40:]


def _human(amount: int | None, decimals: int | None) -> float | None:
    if amount is None:
        return None
    return round(amount / (10 ** (decimals if decimals is not None else 18)), 6)


def _v3_sqrt_price_x96(log_or_slot: str | None) -> int | None:
    """Decode sqrtPriceX96 from V3 Swap event data or slot0() return data.

    A Swap has amount0, amount1, then sqrtPriceX96; slot0 starts directly with
    sqrtPriceX96. Callers pass the appropriate 32-byte word rather than relying
    on an ABI library for one integer.
    """
    if not log_or_slot or log_or_slot == "0x":
        return None
    body = log_or_slot[2:] if log_or_slot.startswith("0x") else log_or_slot
    if len(body) < 64:
        return None
    try:
        return int(body[:64], 16)
    except ValueError:
        return None


def _v3_price_in_quote(
    sqrt_price_x96: int | None,
    token0: str | None,
    token1: str | None,
    token: str,
    quote: str,
    token0_decimals: int | None,
    token1_decimals: int | None,
) -> float | None:
    """Convert a V3 sqrt price to quote units per one whole token."""
    if not sqrt_price_x96 or sqrt_price_x96 <= 0 or not token0 or not token1:
        return None
    token0, token1, token, quote = map(_normalise, (token0, token1, token, quote))
    if {token0, token1} != {token, quote}:
        return None
    try:
        with localcontext() as context:
            context.prec = 72
            raw_token1_per_token0 = (Decimal(sqrt_price_x96) ** 2) / (Decimal(2) ** 192)
            human_token1_per_token0 = raw_token1_per_token0 * (Decimal(10) ** (
                (token0_decimals if token0_decimals is not None else 18)
                - (token1_decimals if token1_decimals is not None else 18)
            ))
            price = (
                human_token1_per_token0
                if token == token0 and quote == token1
                else Decimal(1) / human_token1_per_token0
            )
            if not price.is_finite() or price <= 0:
                return None
            return float(price)
    except (ArithmeticError, InvalidOperation, OverflowError):
        return None


def _v3_swap_sqrt_price(log: dict[str, Any]) -> int | None:
    """Extract the third data word (sqrtPriceX96) from a V3 Swap event."""
    data = str(log.get("data") or "")
    body = data[2:] if data.startswith("0x") else data
    if len(body) < 64 * 3:
        return None
    return _v3_sqrt_price_x96("0x" + body[128:192])


def _build_candles(
    swaps: list[dict[str, Any]], start_block: int, interval_blocks: int
) -> list[dict[str, Any]]:
    """Make bounded block-range OHLC candles from chronologically ordered swaps."""
    buckets: dict[int, list[dict[str, Any]]] = {}
    for swap in sorted(swaps, key=_log_order):
        price = swap.get("price_in_paired")
        block = _decode_uint(swap.get("blockNumber"))
        if not isinstance(price, (int, float)) or price <= 0 or block is None:
            continue
        bucket = (block - start_block) // interval_blocks
        buckets.setdefault(bucket, []).append(swap)
    candles: list[dict[str, Any]] = []
    for bucket, items in sorted(buckets.items())[-_MAX_CANDLES:]:
        prices = [float(item["price_in_paired"]) for item in items]
        first_block = _decode_uint(items[0].get("blockNumber")) or start_block
        last_block = _decode_uint(items[-1].get("blockNumber")) or first_block
        candles.append(
            {
                "from_block": start_block + bucket * interval_blocks,
                "to_block": start_block + (bucket + 1) * interval_blocks - 1,
                "first_swap_block": first_block,
                "last_swap_block": last_block,
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "swap_count": len(items),
            }
        )
    return candles


async def _window(client: httpx.AsyncClient, blocks: int) -> tuple[int, int]:
    latest = _decode_uint(await _rpc(client, "eth_blockNumber", [])) or 0
    span = max(1, min(int(blocks or 500), _MAX_BLOCK_WINDOW))
    return max(0, latest - span), latest


async def token_overview(address: str) -> dict[str, Any]:
    """Identity and supply of an ERC-20/721 contract."""
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=25) as client:
        code = await _rpc(client, "eth_getCode", [address, "latest"])
        if not code or code == "0x":
            return {
                "address": address,
                "is_contract": False,
                "verdict_hint": "This address holds no code — it is a wallet, not a token.",
                "explorer": _explorer_link(address),
            }
        name, symbol, decimals, supply = await asyncio.gather(
            _call(client, address, "06fdde03"),
            _call(client, address, "95d89b41"),
            _call(client, address, "313ce567"),
            _call(client, address, "18160ddd"),
        )
    decimals_value = _decode_uint(decimals)
    supply_value = _decode_uint(supply)
    return {
        "address": address,
        "is_contract": True,
        "name": _decode_string(name),
        "symbol": _decode_string(symbol),
        "decimals": decimals_value,
        "total_supply_raw": supply_value,
        "total_supply": _human(supply_value, decimals_value),
        "bytecode_size": (len(code) - 2) // 2,
        "explorer": _explorer_link(address, "token"),
    }


async def _implementation_of(client: httpx.AsyncClient, address: str) -> tuple[str | None, str | None]:
    """Resolve a proxy's implementation and admin, if the address is a proxy."""
    for slot, kind in ((EIP1967_IMPLEMENTATION, "impl"), (LEGACY_IMPLEMENTATION, "impl")):
        try:
            raw = await _rpc(client, "eth_getStorageAt", [address, slot, "latest"])
        except (ChainError, httpx.HTTPError):
            continue
        candidate = _decode_address(raw)
        if candidate and candidate.lower() != ZERO_ADDRESS and kind == "impl":
            admin_raw = None
            try:
                admin_raw = await _rpc(client, "eth_getStorageAt", [address, EIP1967_ADMIN, "latest"])
            except (ChainError, httpx.HTTPError):
                pass
            admin = _decode_address(admin_raw)
            return candidate, (admin if admin and admin.lower() != ZERO_ADDRESS else None)
    return None, None


def _scan_selectors(body: str) -> tuple[list[str], list[str]]:
    """Find risk selectors, matching the PUSH4 form to avoid coincidental hits."""
    present: list[str] = []
    for selector, signature in RISK_SELECTORS.items():
        if f"63{selector}" in body or selector in body:
            present.append(signature)
    dangerous = sorted(
        RISK_SELECTORS[selector]
        for selector in DANGEROUS
        if f"63{selector}" in body or selector in body
    )
    return sorted(present), dangerous


async def contract_audit(address: str) -> dict[str, Any]:
    """Ownership, upgradeability and privileged-function surface — the rug-risk read."""
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=30) as client:
        code = await _rpc(client, "eth_getCode", [address, "latest"])
        if not code or code == "0x":
            raise ChainError(f"{address} has no bytecode; nothing to audit")
        implementation, proxy_admin = await _implementation_of(client, address)
        scanned = code
        if implementation:
            impl_code = await _rpc(client, "eth_getCode", [implementation, "latest"])
            if impl_code and impl_code != "0x":
                scanned = impl_code
        owner_raw = await _call(client, address, "8da5cb5b")
    body = scanned[2:].lower()
    present, dangerous = _scan_selectors(body)
    owner = _decode_address(owner_raw)
    renounced = owner is not None and owner.lower() == ZERO_ADDRESS
    return {
        "address": address,
        "is_proxy": bool(implementation),
        "implementation": implementation,
        "proxy_admin": proxy_admin,
        "owner": owner,
        "ownership_renounced": renounced,
        "privileged_functions": dangerous,
        "detected_functions": present,
        "bytecode_size": len(body) // 2,
        "risk_notes": [
            note
            for note in [
                "Upgradeable proxy: whoever controls the admin can replace the token logic entirely."
                if implementation
                else None,
                "Owner can mint new supply at will." if "mint(address,uint256)" in dangerous else None,
                "Owner can pause transfers, trapping holders." if "pause()" in dangerous else None,
                "Contract can blacklist addresses." if any("lacklist" in item for item in dangerous) else None,
                "Owner can burn balances held by others." if "burn(address,uint256)" in dangerous else None,
                "Ownership is renounced — owner-gated calls are dead." if renounced else None,
                "Owner address is still live; privileged calls remain callable."
                if owner and not renounced
                else None,
                "No owner() function exposed; ownership checks are inconclusive from bytecode alone."
                if owner is None
                else None,
            ]
            if note
        ],
        "explorer": _explorer_link(address, "token"),
    }


async def token_activity(address: str, blocks: int = 500) -> dict[str, Any]:
    """Transfer flow over a recent block window: volume, reach, concentration."""
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=40) as client:
        start, latest = await _window(client, blocks)
        decimals = _decode_uint(await _call(client, address, "313ce567"))
        logs = await _rpc(
            client,
            "eth_getLogs",
            [
                {
                    "address": address,
                    "fromBlock": hex(start),
                    "toBlock": hex(latest),
                    "topics": [TRANSFER_TOPIC],
                }
            ],
        )
    logs = logs or []
    senders: dict[str, int] = {}
    receivers: dict[str, int] = {}
    largest = 0
    minted = 0
    burned = 0
    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        sender = "0x" + topics[1][-40:]
        receiver = "0x" + topics[2][-40:]
        value = _decode_uint(log.get("data")) or 0
        senders[sender] = senders.get(sender, 0) + 1
        receivers[receiver] = receivers.get(receiver, 0) + 1
        largest = max(largest, value)
        if sender == ZERO_ADDRESS:
            minted += value
        if receiver == ZERO_ADDRESS:
            burned += value
    participants = set(senders) | set(receivers)
    top_sender = max(senders.items(), key=lambda item: item[1], default=None)
    return {
        "address": address,
        "window_blocks": latest - start,
        "from_block": start,
        "to_block": latest,
        "transfer_count": len(logs),
        "unique_senders": len(senders),
        "unique_receivers": len(receivers),
        "unique_participants": len(participants),
        "largest_transfer": _human(largest, decimals),
        "minted_in_window": _human(minted, decimals),
        "burned_in_window": _human(burned, decimals),
        "busiest_sender": {"address": top_sender[0], "transfers": top_sender[1]} if top_sender else None,
        "sender_concentration": round(top_sender[1] / len(logs), 3) if top_sender and logs else None,
        "explorer": _explorer_link(address, "token"),
    }


def _log_address(topics: list[Any], index: int) -> str | None:
    """Read an indexed address topic, returning None for malformed RPC logs."""
    if len(topics) <= index or not isinstance(topics[index], str) or len(topics[index]) < 42:
        return None
    return "0x" + topics[index][-40:].lower()


def _log_order(log: dict[str, Any]) -> tuple[int, int, int]:
    """JSON-RPC normally sorts logs, but do not rely on that for ownership state."""
    return (
        _decode_uint(log.get("blockNumber")) or 0,
        _decode_uint(log.get("transactionIndex")) or 0,
        _decode_uint(log.get("logIndex")) or 0,
    )


def _marketplace_data_unavailable() -> dict[str, Any]:
    """Make the RPC boundary explicit so agents never hallucinate market metrics."""
    return {
        "available": False,
        "floor_price": None,
        "recent_sales": None,
        "note": (
            "The public Robinhood Chain JSON-RPC exposes contract calls and logs, not marketplace "
            "order books or indexed sale semantics. Floor price and market sales require a marketplace "
            "or NFT indexer connection."
        ),
    }


async def nft_collection_overview(address: str) -> dict[str, Any]:
    """Verify an ERC-721 collection and read only standard, on-chain identity data."""
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a collection contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=30) as client:
        code = await _rpc(client, "eth_getCode", [address, "latest"])
        if not code or code == "0x":
            return {
                "address": address,
                "is_contract": False,
                "is_erc721": False,
                "total_supply": None,
                "market_data": _marketplace_data_unavailable(),
                "note": "This address has no deployed bytecode, so it cannot be an NFT collection contract.",
                "explorer": _explorer_link(address),
            }
        name, symbol, supply, erc165, erc721, metadata, enumerable = await asyncio.gather(
            _call(client, address, "06fdde03"),
            _call(client, address, "95d89b41"),
            _call(client, address, "18160ddd"),
            _supports_interface(client, address, ERC165_INTERFACE_ID),
            _supports_interface(client, address, ERC721_INTERFACE_ID),
            _supports_interface(client, address, ERC721_METADATA_INTERFACE_ID),
            _supports_interface(client, address, ERC721_ENUMERABLE_INTERFACE_ID),
        )
    total_supply = _decode_uint(supply)
    return {
        "address": address,
        "is_contract": True,
        "is_erc721": erc721 is True,
        "erc721_verification": (
            "ERC-721 support confirmed through supportsInterface(0x80ac58cd)."
            if erc721 is True
            else "ERC-721 support was not confirmed through ERC-165; do not treat this as a verified collection."
        ),
        "name": _decode_string(name),
        "symbol": _decode_string(symbol),
        "interfaces": {
            "erc165": erc165,
            "erc721": erc721,
            "erc721_metadata": metadata,
            "erc721_enumerable": enumerable,
        },
        "total_supply": total_supply,
        "total_supply_source": (
            "totalSupply()" if total_supply is not None else "unavailable: totalSupply() is optional for ERC-721"
        ),
        "bytecode_size": (len(code) - 2) // 2,
        "market_data": _marketplace_data_unavailable(),
        "explorer": _explorer_link(address, "token"),
    }


async def nft_collection_activity(address: str, blocks: int = 500) -> dict[str, Any]:
    """Report bounded, recent ERC-721 Transfer activity without inventing market data.

    Holder metrics only cover token IDs observed in the requested window. That is
    useful for fresh mints and active collections, but is not a collection-wide
    holder count unless an indexer or a complete history scan is available.
    """
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a collection contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=45) as client:
        code = await _rpc(client, "eth_getCode", [address, "latest"])
        if not code or code == "0x":
            return {
                "address": address,
                "is_contract": False,
                "is_erc721": False,
                "market_data": _marketplace_data_unavailable(),
                "note": "This address has no deployed bytecode, so it cannot emit ERC-721 Transfer events.",
                "explorer": _explorer_link(address),
            }
        erc721 = await _supports_interface(client, address, ERC721_INTERFACE_ID)
        if erc721 is not True:
            return {
                "address": address,
                "is_contract": True,
                "is_erc721": False,
                "market_data": _marketplace_data_unavailable(),
                "note": "ERC-721 support was not confirmed through ERC-165; no NFT activity metrics were calculated.",
                "explorer": _explorer_link(address, "token"),
            }
        start, latest = await _window(client, blocks)
        # A popular collection can exceed the node's log-result limit even in
        # a modest window. Split only this bounded range and mark the metrics
        # partial if the public endpoint cannot serve every subrange.
        logs, activity_complete = await _collect_transfers(client, address, start, latest, budget=24)

    valid_logs = [
        log
        for log in (logs or [])
        if len(log.get("topics") or []) >= 4
        and _log_address(log.get("topics") or [], 1)
        and _log_address(log.get("topics") or [], 2)
    ]
    owners: dict[int, str] = {}
    observed_token_ids: set[int] = set()
    mint_recipients: set[str] = set()
    active_wallets: set[str] = set()
    mint_count = transfer_count = burn_count = 0
    for log in sorted(valid_logs, key=_log_order):
        topics = log.get("topics") or []
        sender = _log_address(topics, 1)
        receiver = _log_address(topics, 2)
        token_id = _decode_uint(topics[3])
        if sender is None or receiver is None or token_id is None:
            continue
        observed_token_ids.add(token_id)
        if sender == ZERO_ADDRESS:
            mint_count += 1
            mint_recipients.add(receiver)
        elif receiver == ZERO_ADDRESS:
            burn_count += 1
        else:
            transfer_count += 1
        if sender != ZERO_ADDRESS:
            active_wallets.add(sender)
        if receiver != ZERO_ADDRESS:
            active_wallets.add(receiver)
            owners[token_id] = receiver
        else:
            owners.pop(token_id, None)
    observed_holders = set(owners.values())
    return {
        "address": address,
        "is_contract": True,
        "is_erc721": True,
        "window_blocks": latest - start,
        "from_block": start,
        "to_block": latest,
        "activity_complete": activity_complete,
        "transfer_events": len(valid_logs),
        "mints_in_window": mint_count,
        "transfers_in_window": transfer_count,
        "burns_in_window": burn_count,
        "unique_minters_in_window": len(mint_recipients),
        "unique_minters_definition": "Unique recipient wallets in zero-address Transfer mint events.",
        "unique_active_wallets_in_window": len(active_wallets),
        "observed_token_ids_in_window": len(observed_token_ids),
        "observed_current_token_ids": len(owners),
        "unique_holders_observed_in_window": len(observed_holders),
        "holder_count_scope": (
            "Only current owners of token IDs that emitted a Transfer within this bounded block window; "
            "this is not a collection-wide holder count."
            + ("" if activity_complete else " The RPC could not serve every subrange, so activity metrics are partial.")
        ),
        "market_data": _marketplace_data_unavailable(),
        "explorer": _explorer_link(address, "token"),
    }


async def wallet_report(address: str, token: str | None = None) -> dict[str, Any]:
    """Native balance, activity and an optional ERC-20 position for a wallet."""
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a wallet address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=25) as client:
        balance_raw, nonce_raw, code = await asyncio.gather(
            _rpc(client, "eth_getBalance", [address, "latest"]),
            _rpc(client, "eth_getTransactionCount", [address, "latest"]),
            _rpc(client, "eth_getCode", [address, "latest"]),
        )
        position: dict[str, Any] | None = None
        if token and _is_address(token):
            token = _normalise(token)
            padded = address[2:].rjust(64, "0")
            raw, decimals = await asyncio.gather(
                _rpc(client, "eth_call", [{"to": token, "data": f"0x70a08231{padded}"}, "latest"]),
                _call(client, token, "313ce567"),
            )
            decimals_value = _decode_uint(decimals)
            position = {
                "token": token,
                "balance": _human(_decode_uint(raw), decimals_value),
                "balance_raw": _decode_uint(raw),
            }
    return {
        "address": address,
        "native_balance_eth": _human(_decode_uint(balance_raw), 18),
        "transaction_count": _decode_uint(nonce_raw),
        "is_contract": bool(code and code != "0x"),
        "token_position": position,
        "explorer": _explorer_link(address),
    }


async def trending_tokens(blocks: int = 300, limit: int = 10) -> dict[str, Any]:
    """Contracts with the most transfer activity right now — the movement scan."""
    async with httpx.AsyncClient(timeout=45) as client:
        start, latest = await _window(client, blocks)
        logs = await _rpc(
            client,
            "eth_getLogs",
            [{"fromBlock": hex(start), "toBlock": hex(latest), "topics": [TRANSFER_TOPIC]}],
        )
        logs = logs or []
        counts: dict[str, int] = {}
        holders: dict[str, set[str]] = {}
        for log in logs:
            contract = _normalise(log.get("address") or "")
            if not contract:
                continue
            counts[contract] = counts.get(contract, 0) + 1
            topics = log.get("topics") or []
            if len(topics) >= 3:
                holders.setdefault(contract, set()).add("0x" + topics[2][-40:])
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[: max(1, min(limit, 25))]
        named = await asyncio.gather(
            *(_call(client, contract, "95d89b41") for contract, _ in ranked)
        )
    return {
        "window_blocks": latest - start,
        "from_block": start,
        "to_block": latest,
        "total_transfers": len(logs),
        "tokens": [
            {
                "address": contract,
                "symbol": _decode_string(symbol),
                "transfers": count,
                "unique_receivers": len(holders.get(contract, ())),
                "explorer": _explorer_link(contract, "token"),
            }
            for (contract, count), symbol in zip(ranked, named)
        ],
    }


async def _first_activity_block(client: httpx.AsyncClient, address: str, latest: int) -> int | None:
    """Binary-search the earliest block holding a Transfer for this token.

    The public node keeps no historical state, so the contract's creation block
    cannot be probed with eth_getCode. It does accept full-range log queries and
    only caps the response at 10k rows, which is enough to bisect.
    """
    low, high, found = 0, latest, None
    while low < high:
        middle = (low + high) // 2
        try:
            logs = await _rpc(
                client,
                "eth_getLogs",
                [
                    {
                        "address": address,
                        "fromBlock": hex(low),
                        "toBlock": hex(middle),
                        "topics": [TRANSFER_TOPIC],
                    }
                ],
            )
        except ChainError as exc:
            if "exceeds limit" not in str(exc):
                raise
            high = middle  # too many rows means the earliest one is in here
            continue
        if logs:
            found = _decode_uint(logs[0].get("blockNumber"))
            high = middle
        else:
            low = middle + 1
    return found if found is not None else (low if low < latest else None)


async def token_age(address: str) -> dict[str, Any]:
    """How old the token is, and who signed its first mint."""
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=60) as client:
        latest = _decode_uint(await _rpc(client, "eth_blockNumber", [])) or 0
        first = await _first_activity_block(client, address, latest)
        if first is None:
            return {
                "address": address,
                "first_activity_block": None,
                "note": "No Transfer events found; the token has never moved.",
                "explorer": _explorer_link(address, "token"),
            }
        block, head = await asyncio.gather(
            _rpc(client, "eth_getBlockByNumber", [hex(first), False]),
            _rpc(client, "eth_getBlockByNumber", [hex(latest), False]),
        )
        first_logs = await _rpc(
            client,
            "eth_getLogs",
            [
                {
                    "address": address,
                    "fromBlock": hex(first),
                    "toBlock": hex(min(first + 50, latest)),
                    "topics": [TRANSFER_TOPIC],
                }
            ],
        )
        minter = None
        mint = next(
            (
                log
                for log in (first_logs or [])
                if len(log.get("topics") or []) >= 3
                and "0x" + log["topics"][1][-40:] == ZERO_ADDRESS
            ),
            None,
        )
        if mint and mint.get("transactionHash"):
            transaction = await _rpc(client, "eth_getTransactionByHash", [mint["transactionHash"]])
            minter = (transaction or {}).get("from")
    first_ts = _decode_uint((block or {}).get("timestamp"))
    head_ts = _decode_uint((head or {}).get("timestamp"))
    age_seconds = (head_ts - first_ts) if first_ts and head_ts else None
    return {
        "address": address,
        "first_activity_block": first,
        "first_activity_timestamp": first_ts,
        "age_hours": round(age_seconds / 3600, 1) if age_seconds is not None else None,
        "age_days": round(age_seconds / 86400, 2) if age_seconds is not None else None,
        "first_minter": minter,
        "note": (
            "first_minter is the account that signed the first mint, which is the deployer for "
            "most launches. The contract's own creation transaction is not recoverable here: this "
            "node keeps no archive state, and factory deployments leave no top-level transaction."
        ),
        "explorer": _explorer_link(address, "token"),
    }


async def _collect_transfers(
    client: httpx.AsyncClient,
    address: str,
    start: int,
    end: int,
    budget: int,
    topic: str = TRANSFER_TOPIC,
) -> tuple[list[dict[str, Any]], bool]:
    """Page one event topic across a range, splitting chunks the node refuses."""
    collected: list[dict[str, Any]] = []
    pending: list[tuple[int, int]] = [(start, end)]
    complete = True
    while pending:
        if budget <= 0:
            complete = False
            break
        low, high = pending.pop(0)
        budget -= 1
        try:
            logs = await _rpc(
                client,
                "eth_getLogs",
                [
                    {
                        "address": address,
                        "fromBlock": hex(low),
                        "toBlock": hex(high),
                        "topics": [topic],
                    }
                ],
            )
        except ChainError as exc:
            if "exceeds limit" not in str(exc) or high <= low:
                complete = False
                continue
            middle = (low + high) // 2
            pending[:0] = [(low, middle), (middle + 1, high)]
            continue
        collected.extend(logs or [])
    return collected, complete


async def token_holders(address: str, top: int = 10) -> dict[str, Any]:
    """Reconstruct balances from the full transfer history to expose concentration."""
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=90) as client:
        latest = _decode_uint(await _rpc(client, "eth_blockNumber", [])) or 0
        first = await _first_activity_block(client, address, latest)
        if first is None:
            raise ChainError(f"{address} has no transfer history to rebuild balances from")
        decimals = _decode_uint(await _call(client, address, "313ce567"))
        logs, complete = await _collect_transfers(client, address, first, latest, budget=40)
    balances: dict[str, int] = {}
    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        sender = "0x" + topics[1][-40:]
        receiver = "0x" + topics[2][-40:]
        value = _decode_uint(log.get("data")) or 0
        if sender != ZERO_ADDRESS:
            balances[sender] = balances.get(sender, 0) - value
        if receiver != ZERO_ADDRESS:
            balances[receiver] = balances.get(receiver, 0) + value
    holders = sorted(
        ((holder, amount) for holder, amount in balances.items() if amount > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    circulating = sum(amount for _, amount in holders)
    ranked = holders[: max(1, min(top, 50))]
    # The largest holder is usually the liquidity pool, not a whale about to dump.
    async with httpx.AsyncClient(timeout=30) as client:
        codes = await asyncio.gather(
            *(_rpc(client, "eth_getCode", [holder, "latest"]) for holder, _ in ranked),
            return_exceptions=True,
        )
    return {
        "address": address,
        "holder_count": len(holders),
        "transfers_scanned": len(logs),
        "history_complete": complete,
        "circulating_from_history": _human(circulating, decimals),
        "top_holders": [
            {
                "address": holder,
                "balance": _human(amount, decimals),
                "share": round(amount / circulating, 4) if circulating else None,
                "is_contract": bool(
                    isinstance(code, str) and code not in ("", "0x")
                ),
            }
            for (holder, amount), code in zip(ranked, codes)
        ],
        "top1_share": round(ranked[0][1] / circulating, 4) if ranked and circulating else None,
        "top10_share": round(sum(a for _, a in holders[:10]) / circulating, 4) if circulating else None,
        "note": (
            "Balances are rebuilt from transfer history. A top holder with is_contract true is "
            "usually the liquidity pool rather than a whale."
            + ("" if complete else " History was truncated, so shares are a lower bound.")
        ),
        "explorer": _explorer_link(address, "token"),
    }


async def token_liquidity(address: str, blocks: int = 600) -> dict[str, Any]:
    """Find the DEX pools holding this token and read real depth on both sides.

    Pools are resolved through the V3 factory rather than by watching swaps, so a
    token with deep liquidity but no recent trades is still reported.
    """
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a contract address")
    address = _normalise(address)
    async with httpx.AsyncClient(timeout=60) as client:
        lookups = [
            (quote, fee)
            for quote in QUOTE_ASSETS
            if quote != address
            for fee in V3_FEE_TIERS
        ]
        raw_pools = await asyncio.gather(
            *(
                _call_with_args(client, V3_FACTORY, "1698ee82", [address, quote, fee])
                for quote, fee in lookups
            )
        )
        found: list[tuple[str, str, int]] = []
        for (quote, fee), raw in zip(lookups, raw_pools):
            pool = _decode_address(raw)
            if pool and pool.lower() != ZERO_ADDRESS:
                found.append((pool.lower(), quote, fee))

        start, latest = await _window(client, blocks)
        swap_counts: dict[str, int] = {}
        if found:
            try:
                logs = await _rpc(
                    client,
                    "eth_getLogs",
                    [{"fromBlock": hex(start), "toBlock": hex(latest), "topics": [V3_SWAP_TOPIC]}],
                )
                for log in logs or []:
                    pool = _normalise(log.get("address") or "")
                    swap_counts[pool] = swap_counts.get(pool, 0) + 1
            except ChainError:
                swap_counts = {}

        results = []
        for pool, quote, fee in found[:8]:
            padded = pool[2:].rjust(64, "0")
            own_raw, own_decimals, quote_raw, quote_decimals, quote_symbol = await asyncio.gather(
                _rpc(client, "eth_call", [{"to": address, "data": f"0x70a08231{padded}"}, "latest"]),
                _call(client, address, "313ce567"),
                _rpc(client, "eth_call", [{"to": quote, "data": f"0x70a08231{padded}"}, "latest"]),
                _call(client, quote, "313ce567"),
                _call(client, quote, "95d89b41"),
            )
            own = _human(_decode_uint(own_raw), _decode_uint(own_decimals))
            paired = _human(_decode_uint(quote_raw), _decode_uint(quote_decimals))
            results.append(
                {
                    "pool": pool,
                    "fee_tier_bps": fee // 100,
                    "paired_with": quote,
                    "paired_symbol": _decode_string(quote_symbol),
                    "token_reserve": own,
                    "paired_reserve": paired,
                    "price_in_paired": round(paired / own, 12) if own else None,
                    "swaps_in_window": swap_counts.get(pool, 0),
                    "explorer": _explorer_link(pool),
                }
            )
    deepest = max((item["paired_reserve"] or 0 for item in results), default=0)
    return {
        "address": address,
        "window_blocks": latest - start,
        "pools_found": len(results),
        "deepest_paired_reserve": deepest,
        "pools": sorted(results, key=lambda item: item["paired_reserve"] or 0, reverse=True),
        "note": (
            "Depth is each pool's live balance on both sides; price_in_paired is the ratio of those "
            "balances, not a routed quote. swaps_in_window is 0 when the pool exists but has not "
            "traded recently."
            if results
            else "No V3 pool exists for this token against WETH or USDG."
        ),
        "explorer": _explorer_link(address, "token"),
    }


async def token_candles(
    address: str, blocks: int = 600, interval_blocks: int = 50
) -> dict[str, Any]:
    """Derive recent block-range OHLC candles from actual V3 Swap events.

    This is deliberately a price *history*, not a quote API: each candle is
    built from executed swaps of the deepest discovered WETH/USDG V3 pool. A
    silent pool returns an empty history plus a live slot0 price instead of
    fabricating volume or carrying a reserve ratio forward as a candle.
    """
    if not _is_address(address):
        raise ChainError(f"'{address}' is not a contract address")
    address = _normalise(address)
    span = max(1, min(int(interval_blocks or 50), _MAX_BLOCK_WINDOW))
    liquidity = await token_liquidity(address, blocks=blocks)
    pools = list(liquidity.get("pools") or [])
    if not pools:
        return {
            "address": address,
            "pool": None,
            "paired_with": None,
            "paired_symbol": None,
            "candles": [],
            "swaps_scanned": 0,
            "history_complete": True,
            "note": "No V3 pool exists against WETH or USDG, so no on-chain swap candles can be derived.",
            "explorer": _explorer_link(address, "token"),
        }

    selected = pools[0]
    pool = _normalise(str(selected["pool"]))
    quote = _normalise(str(selected["paired_with"]))
    async with httpx.AsyncClient(timeout=75) as client:
        start, latest = await _window(client, blocks)
        token0_raw, token1_raw, token_decimals_raw, quote_decimals_raw, slot0_raw = await asyncio.gather(
            _call(client, pool, "0dfe1681"),  # token0()
            _call(client, pool, "d21220a7"),  # token1()
            _call(client, address, "313ce567"),
            _call(client, quote, "313ce567"),
            _call(client, pool, "3850c7bd"),  # slot0()
        )
        token0 = _decode_address(token0_raw)
        token1 = _decode_address(token1_raw)
        token_decimals = _decode_uint(token_decimals_raw)
        quote_decimals = _decode_uint(quote_decimals_raw)
        if not token0 or not token1 or {token0.lower(), token1.lower()} != {address, quote}:
            return {
                "address": address,
                "pool": pool,
                "paired_with": quote,
                "paired_symbol": selected.get("paired_symbol"),
                "candles": [],
                "swaps_scanned": 0,
                "history_complete": False,
                "note": "The discovered pool's token0/token1 do not match the requested token pair; no price was inferred.",
                "explorer": _explorer_link(pool),
            }
        token0_decimals = token_decimals if token0.lower() == address else quote_decimals
        token1_decimals = token_decimals if token1.lower() == address else quote_decimals
        logs, history_complete = await _collect_transfers(
            client, pool, start, latest, budget=32, topic=V3_SWAP_TOPIC
        )

        swaps: list[dict[str, Any]] = []
        for log in logs:
            sqrt_price = _v3_swap_sqrt_price(log)
            price = _v3_price_in_quote(
                sqrt_price, token0, token1, address, quote, token0_decimals, token1_decimals
            )
            if price is not None:
                swaps.append({**log, "price_in_paired": price})
        candles = _build_candles(swaps, start, span)

        # Attach block timestamps only to candle boundaries. This avoids one RPC
        # request per swap while preserving the time range represented by each OHLC.
        boundary_blocks = sorted({
            block
            for candle in candles
            for block in (candle["first_swap_block"], candle["last_swap_block"])
        })
        headers = await asyncio.gather(
            *(_rpc(client, "eth_getBlockByNumber", [hex(block), False]) for block in boundary_blocks),
            return_exceptions=True,
        )
    timestamps = {
        block: _decode_uint(header.get("timestamp"))
        for block, header in zip(boundary_blocks, headers)
        if isinstance(header, dict)
    }
    for candle in candles:
        candle["opened_at"] = timestamps.get(candle["first_swap_block"])
        candle["closed_at"] = timestamps.get(candle["last_swap_block"])

    live_price = _v3_price_in_quote(
        _v3_sqrt_price_x96(slot0_raw), token0, token1, address, quote, token0_decimals, token1_decimals
    )
    return {
        "address": address,
        "pool": pool,
        "fee_tier_bps": selected.get("fee_tier_bps"),
        "paired_with": quote,
        "paired_symbol": selected.get("paired_symbol"),
        "from_block": start,
        "to_block": latest,
        "interval_blocks": span,
        "live_price_in_paired": live_price,
        "candles": candles,
        "swaps_scanned": len(logs),
        "swaps_used": len(swaps),
        "history_complete": history_complete,
        "note": (
            "Candles are derived from executed V3 Swap events, grouped by block range. "
            "They do not include off-chain trades, V2 pools, volume, or a USD conversion."
            + ("" if history_complete else " The public RPC could not serve every log subrange, so the history is partial.")
        ),
        "explorer": _explorer_link(pool),
    }


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "chain_nft_collection_overview",
        "description": (
            "Verify a Robinhood Chain NFT collection as ERC-721 through ERC-165 and read its on-chain "
            "name, symbol, supported interfaces, optional totalSupply(), and bytecode size. This RPC tool "
            "does not have marketplace/indexer data, so floor price and recent sales are explicitly unavailable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "ERC-721 collection contract address (0x...)"}
            },
            "required": ["address"],
        },
        "handler": nft_collection_overview,
    },
    {
        "name": "chain_nft_collection_activity",
        "description": (
            "Read recent ERC-721 Transfer events for a verified Robinhood Chain collection: mints, transfers, "
            "burns, unique mint recipients, and observed active holders in a bounded recent block window. "
            "Observed holders are not a collection-wide holder count; floor and sales remain unavailable without "
            "a marketplace or NFT indexer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "ERC-721 collection contract address (0x...)"},
                "blocks": {
                    "type": "integer",
                    "description": "Recent block window to scan (default 500, max 2000)",
                },
            },
            "required": ["address"],
        },
        "handler": nft_collection_activity,
    },
    {
        "name": "chain_token_overview",
        "description": (
            "Read a Robinhood Chain token's on-chain identity: name, symbol, decimals, "
            "total supply, and whether the address holds contract code at all. "
            "Use this first for any token address before making claims about it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address (0x...)"}
            },
            "required": ["address"],
        },
        "handler": token_overview,
    },
    {
        "name": "chain_contract_audit",
        "description": (
            "Audit a Robinhood Chain contract for rug-pull surface: current owner, whether "
            "ownership is renounced, and which privileged functions (mint, pause, blacklist, "
            "burn-from) exist in the deployed bytecode. Use before any ENTER verdict."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address (0x...)"}
            },
            "required": ["address"],
        },
        "handler": contract_audit,
    },
    {
        "name": "chain_token_activity",
        "description": (
            "Measure real transfer flow for a token over a recent block window: transfer count, "
            "unique senders and receivers, largest transfer, mint/burn in the window, and how "
            "concentrated activity is in one sender (a wash-trading signal)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address (0x...)"},
                "blocks": {
                    "type": "integer",
                    "description": "How many recent blocks to scan (default 500, max 2000)",
                },
            },
            "required": ["address"],
        },
        "handler": token_activity,
    },
    {
        "name": "chain_wallet_report",
        "description": (
            "Inspect a wallet on Robinhood Chain: native balance, transaction count, whether it "
            "is actually a contract, and optionally its balance of a specific token. Use to check "
            "a deployer or a whale before trusting a narrative."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Wallet address (0x...)"},
                "token": {
                    "type": "string",
                    "description": "Optional token contract to report this wallet's position in",
                },
            },
            "required": ["address"],
        },
        "handler": wallet_report,
    },
    {
        "name": "chain_token_age",
        "description": (
            "How old a Robinhood Chain token is: first activity block, timestamp, age in hours and "
            "days, and the account that signed the first mint (the deployer for most launches). "
            "A token minted hours ago is a different risk class from one trading for months."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address (0x...)"}
            },
            "required": ["address"],
        },
        "handler": token_age,
    },
    {
        "name": "chain_token_holders",
        "description": (
            "Rebuild holder balances from the token's full transfer history and report holder "
            "count plus concentration (top-1 and top-10 share). High concentration means a few "
            "wallets can dump on everyone else — check this before any ENTER verdict."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address (0x...)"},
                "top": {"type": "integer", "description": "How many holders to list (default 10)"},
            },
            "required": ["address"],
        },
        "handler": token_holders,
    },
    {
        "name": "chain_token_liquidity",
        "description": (
            "Find the DEX pools trading this token and read live depth on both sides, the paired "
            "asset, the implied price and recent swap counts. Thin liquidity means the position "
            "cannot be exited at the quoted price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address (0x...)"},
                "blocks": {
                    "type": "integer",
                    "description": "How many recent blocks to scan for swaps (default 600, max 2000)",
                },
            },
            "required": ["address"],
        },
        "handler": token_liquidity,
    },
    {
        "name": "chain_token_candles",
        "description": (
            "Build recent OHLC candles from executed V3 Swap events in the deepest discovered "
            "WETH/USDG pool for a Robinhood Chain token. Returns a live V3 slot0 price when the "
            "pool is quiet, and explicitly discloses that volume, USD conversion, V2 pools, and "
            "off-chain trades are outside this native RPC read."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address (0x...)"},
                "blocks": {
                    "type": "integer",
                    "description": "Recent block range for executed swaps (default 600, max 2000)",
                },
                "interval_blocks": {
                    "type": "integer",
                    "description": "Blocks per OHLC candle (default 50)",
                },
            },
            "required": ["address"],
        },
        "handler": token_candles,
    },
    {
        "name": "chain_trending_tokens",
        "description": (
            "Scan recent Robinhood Chain blocks and rank contracts by transfer activity right now. "
            "Use to discover what is actually moving on-chain instead of guessing from social chatter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "blocks": {
                    "type": "integer",
                    "description": "How many recent blocks to scan (default 300, max 2000)",
                },
                "limit": {"type": "integer", "description": "How many tokens to return (default 10)"},
            },
        },
    },
]
# trending_tokens is attached separately so the spec list stays declarative.
TOOL_SPECS[-1]["handler"] = trending_tokens

HANDLERS = {spec["name"]: spec["handler"] for spec in TOOL_SPECS}


def tool_definitions() -> list[dict[str, Any]]:
    """Schemas handed to the model — handlers stripped."""
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "input_schema": spec["input_schema"],
            "source": "chain",
            "risk": "read",
        }
        for spec in TOOL_SPECS
    ]


async def call_chain_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = HANDLERS.get(name)
    if handler is None:
        raise ChainError(f"Unknown chain tool '{name}'")
    kwargs = {key: value for key, value in (arguments or {}).items() if value not in (None, "")}
    return await handler(**kwargs)
