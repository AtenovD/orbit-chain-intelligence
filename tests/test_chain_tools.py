from __future__ import annotations

import asyncio

import pytest

from orchestrator import chain_tools


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = None

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Answers eth_* calls from a scripted table keyed by method and selector."""

    script: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def post(self, url, json=None, headers=None):
        method = json["method"]
        params = json.get("params") or []
        key = method
        if method == "eth_call":
            key = f"eth_call:{params[0]['data'][:10]}"
        elif method == "eth_getStorageAt":
            key = f"eth_getStorageAt:{params[1]}"
        value = self.script.get(key, "0x")
        if isinstance(value, Exception):
            raise value
        return _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": value})


def _encoded_string(text: str) -> str:
    body = text.encode().hex()
    padded = body.ljust(64, "0")
    return "0x" + "20".rjust(64, "0") + hex(len(text))[2:].rjust(64, "0") + padded


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    monkeypatch.setattr(chain_tools.httpx, "AsyncClient", _FakeClient)
    _FakeClient.script = {}
    yield


async def test_token_overview_decodes_identity_and_supply():
    _FakeClient.script = {
        "eth_getCode": "0x60806040" + "ab" * 100,
        "eth_call:0x06fdde03": _encoded_string("Testicles"),
        "eth_call:0x95d89b41": _encoded_string("TESTICLES"),
        "eth_call:0x313ce567": "0x" + "12".rjust(64, "0"),
        "eth_call:0x18160ddd": "0x" + hex(5_000 * 10**18)[2:].rjust(64, "0"),
    }
    result = await chain_tools.token_overview("0x" + "11" * 20)
    assert result["is_contract"] is True
    assert result["name"] == "Testicles"
    assert result["symbol"] == "TESTICLES"
    assert result["decimals"] == 18
    assert result["total_supply"] == 5000.0


async def test_token_overview_flags_a_wallet_rather_than_a_token():
    _FakeClient.script = {"eth_getCode": "0x"}
    result = await chain_tools.token_overview("0x" + "22" * 20)
    assert result["is_contract"] is False
    assert "wallet" in result["verdict_hint"]


async def test_contract_audit_follows_a_proxy_and_flags_upgradeability():
    implementation = "0x" + "ab" * 20
    _FakeClient.script = {
        "eth_getCode": "0x6080604052" + "63" + "40c10f19" + "00" * 20,
        f"eth_getStorageAt:{chain_tools.EIP1967_IMPLEMENTATION}": "0x" + implementation[2:].rjust(64, "0"),
        f"eth_getStorageAt:{chain_tools.EIP1967_ADMIN}": "0x" + ("cd" * 20).rjust(64, "0"),
        "eth_call:0x8da5cb5b": "0x" + ("ef" * 20).rjust(64, "0"),
    }
    result = await chain_tools.contract_audit("0x" + "33" * 20)
    assert result["is_proxy"] is True
    assert result["implementation"] == implementation
    assert result["proxy_admin"] is not None
    assert "mint(address,uint256)" in result["privileged_functions"]
    assert any("Upgradeable proxy" in note for note in result["risk_notes"])


async def test_contract_audit_reports_renounced_ownership():
    _FakeClient.script = {
        "eth_getCode": "0x6080604052" + "00" * 40,
        "eth_call:0x8da5cb5b": "0x" + "0" * 64,
    }
    result = await chain_tools.contract_audit("0x" + "44" * 20)
    assert result["ownership_renounced"] is True
    assert result["is_proxy"] is False
    assert any("renounced" in note for note in result["risk_notes"])


async def test_token_activity_summarises_transfer_flow():
    sender = "0x" + "aa" * 20
    receiver = "0x" + "bb" * 20
    logs = [
        {
            "address": "0x" + "55" * 20,
            "topics": [
                chain_tools.TRANSFER_TOPIC,
                "0x" + sender[2:].rjust(64, "0"),
                "0x" + receiver[2:].rjust(64, "0"),
            ],
            "data": "0x" + hex(2 * 10**18)[2:].rjust(64, "0"),
        }
        for _ in range(3)
    ]
    _FakeClient.script = {
        "eth_blockNumber": hex(1000),
        "eth_call:0x313ce567": "0x" + "12".rjust(64, "0"),
        "eth_getLogs": logs,
    }
    result = await chain_tools.token_activity("0x" + "55" * 20, blocks=100)
    assert result["transfer_count"] == 3
    assert result["unique_senders"] == 1
    assert result["unique_receivers"] == 1
    assert result["largest_transfer"] == 2.0
    assert result["sender_concentration"] == 1.0


async def test_token_activity_caps_the_block_window():
    _FakeClient.script = {"eth_blockNumber": hex(10_000_000), "eth_getLogs": []}
    result = await chain_tools.token_activity("0x" + "66" * 20, blocks=999_999)
    assert result["window_blocks"] == chain_tools._MAX_BLOCK_WINDOW


async def test_nft_collection_overview_verifies_erc721_and_never_invents_market_data():
    collection = "0x" + "67" * 20

    class _NftOverviewClient(_FakeClient):
        async def post(self, url, json=None, headers=None):
            method = json["method"]
            params = json.get("params") or []
            if method == "eth_getCode":
                return _FakeResponse({"result": "0x60806040" + "ab" * 100})
            if method == "eth_call":
                data = params[0]["data"]
                if data.startswith("0x06fdde03"):
                    return _FakeResponse({"result": _encoded_string("Orbit Punks")})
                if data.startswith("0x95d89b41"):
                    return _FakeResponse({"result": _encoded_string("ORBP")})
                if data.startswith("0x18160ddd"):
                    return _FakeResponse({"result": "0x" + hex(1234)[2:].rjust(64, "0")})
                if data.startswith("0x01ffc9a7"):
                    interface_id = data[10:18]
                    supported = interface_id in {
                        chain_tools.ERC165_INTERFACE_ID,
                        chain_tools.ERC721_INTERFACE_ID,
                        chain_tools.ERC721_METADATA_INTERFACE_ID,
                    }
                    return _FakeResponse({"result": "0x" + ("1" if supported else "0").rjust(64, "0")})
            return _FakeResponse({"result": "0x"})

    chain_tools.httpx.AsyncClient = _NftOverviewClient
    result = await chain_tools.nft_collection_overview(collection)
    assert result["is_contract"] is True
    assert result["is_erc721"] is True
    assert result["name"] == "Orbit Punks"
    assert result["symbol"] == "ORBP"
    assert result["total_supply"] == 1234
    assert result["interfaces"] == {
        "erc165": True,
        "erc721": True,
        "erc721_metadata": True,
        "erc721_enumerable": False,
    }
    assert result["market_data"]["available"] is False
    assert result["market_data"]["floor_price"] is None
    assert result["market_data"]["recent_sales"] is None


async def test_nft_activity_reports_only_bounded_transfer_derived_metrics():
    collection = "0x" + "68" * 20
    alice = "0x" + "aa" * 20
    bob = "0x" + "bb" * 20
    carol = "0x" + "cc" * 20

    def transfer(sender, receiver, token_id, block, index):
        return {
            "blockNumber": hex(block),
            "transactionIndex": "0x0",
            "logIndex": hex(index),
            "topics": [
                chain_tools.TRANSFER_TOPIC,
                "0x" + sender[2:].rjust(64, "0"),
                "0x" + receiver[2:].rjust(64, "0"),
                "0x" + hex(token_id)[2:].rjust(64, "0"),
            ],
            "data": "0x",
        }

    logs = [
        transfer(alice, carol, 1, 901, 0),
        transfer(chain_tools.ZERO_ADDRESS, alice, 1, 900, 0),
        transfer(chain_tools.ZERO_ADDRESS, bob, 2, 900, 1),
        transfer(bob, chain_tools.ZERO_ADDRESS, 2, 902, 0),
        # An ERC-20 Transfer shares topic0 but does not have indexed tokenId.
        {
            "topics": [
                chain_tools.TRANSFER_TOPIC,
                "0x" + alice[2:].rjust(64, "0"),
                "0x" + carol[2:].rjust(64, "0"),
            ],
            "data": "0x" + "1".rjust(64, "0"),
        },
    ]

    class _NftActivityClient(_FakeClient):
        async def post(self, url, json=None, headers=None):
            method = json["method"]
            params = json.get("params") or []
            if method == "eth_getCode":
                return _FakeResponse({"result": "0x60806040"})
            if method == "eth_blockNumber":
                return _FakeResponse({"result": hex(1000)})
            if method == "eth_getLogs":
                return _FakeResponse({"result": logs})
            if method == "eth_call" and params[0]["data"].startswith("0x01ffc9a7"):
                interface_id = params[0]["data"][10:18]
                supported = interface_id == chain_tools.ERC721_INTERFACE_ID
                return _FakeResponse({"result": "0x" + ("1" if supported else "0").rjust(64, "0")})
            return _FakeResponse({"result": "0x"})

    chain_tools.httpx.AsyncClient = _NftActivityClient
    result = await chain_tools.nft_collection_activity(collection, blocks=200)
    assert result["is_erc721"] is True
    assert result["window_blocks"] == 200
    assert result["activity_complete"] is True
    assert result["transfer_events"] == 4
    assert result["mints_in_window"] == 2
    assert result["transfers_in_window"] == 1
    assert result["burns_in_window"] == 1
    assert result["unique_minters_in_window"] == 2
    assert result["unique_active_wallets_in_window"] == 3
    assert result["observed_token_ids_in_window"] == 2
    assert result["observed_current_token_ids"] == 1
    assert result["unique_holders_observed_in_window"] == 1
    assert "not a collection-wide holder count" in result["holder_count_scope"]
    assert result["market_data"]["available"] is False


async def test_trending_tokens_ranks_contracts_by_transfer_count():
    busy = "0x" + "77" * 20
    quiet = "0x" + "88" * 20
    receiver = "0x" + "bb" * 20
    topics = lambda: [
        chain_tools.TRANSFER_TOPIC,
        "0x" + ("aa" * 20).rjust(64, "0"),
        "0x" + receiver[2:].rjust(64, "0"),
    ]
    _FakeClient.script = {
        "eth_blockNumber": hex(5000),
        "eth_getLogs": [{"address": busy, "topics": topics(), "data": "0x0"} for _ in range(4)]
        + [{"address": quiet, "topics": topics(), "data": "0x0"}],
        "eth_call:0x95d89b41": _encoded_string("BANK"),
    }
    result = await chain_tools.trending_tokens(blocks=100, limit=5)
    assert result["total_transfers"] == 5
    assert result["tokens"][0]["address"] == busy
    assert result["tokens"][0]["transfers"] == 4
    assert result["tokens"][0]["symbol"] == "BANK"


async def test_token_age_bisects_history_and_names_the_first_minter():
    token = "0x" + "cc" * 20
    minter = "0x" + "de" * 20
    mint_log = {
        "blockNumber": hex(400),
        "transactionHash": "0x" + "fe" * 32,
        "topics": [
            chain_tools.TRANSFER_TOPIC,
            "0x" + "0" * 64,
            "0x" + ("bb" * 20).rjust(64, "0"),
        ],
        "data": "0x0",
    }

    class _AgeClient(_FakeClient):
        async def post(self, url, json=None, headers=None):
            method = json["method"]
            params = json.get("params") or []
            if method == "eth_blockNumber":
                return _FakeResponse({"result": hex(1000)})
            if method == "eth_getLogs":
                high = int(params[0]["toBlock"], 16)
                return _FakeResponse({"result": [mint_log] if high >= 400 else []})
            if method == "eth_getBlockByNumber":
                at = int(params[0], 16)
                return _FakeResponse({"result": {"timestamp": hex(1_000_000 + at * 2)}})
            if method == "eth_getTransactionByHash":
                return _FakeResponse({"result": {"from": minter}})
            return _FakeResponse({"result": "0x"})

    chain_tools.httpx.AsyncClient = _AgeClient
    result = await chain_tools.token_age(token)
    assert result["first_activity_block"] == 400
    assert result["first_minter"] == minter
    assert result["age_hours"] == round((1000 - 400) * 2 / 3600, 1)


async def test_token_holders_rebuilds_balances_and_flags_the_pool():
    pool = "0x" + "11" * 20
    whale = "0x" + "22" * 20

    def transfer(sender, receiver, amount):
        return {
            "blockNumber": hex(10),
            "topics": [
                chain_tools.TRANSFER_TOPIC,
                "0x" + sender[2:].rjust(64, "0"),
                "0x" + receiver[2:].rjust(64, "0"),
            ],
            "data": "0x" + hex(amount)[2:].rjust(64, "0"),
        }

    logs = [
        transfer(chain_tools.ZERO_ADDRESS, pool, 70 * 10**18),
        transfer(chain_tools.ZERO_ADDRESS, whale, 30 * 10**18),
    ]

    class _HolderClient(_FakeClient):
        async def post(self, url, json=None, headers=None):
            method = json["method"]
            params = json.get("params") or []
            if method == "eth_blockNumber":
                return _FakeResponse({"result": hex(50)})
            if method == "eth_getLogs":
                return _FakeResponse({"result": logs})
            if method == "eth_call":
                return _FakeResponse({"result": "0x" + "12".rjust(64, "0")})
            if method == "eth_getCode":
                return _FakeResponse({"result": "0x6080" if params[0] == pool else "0x"})
            return _FakeResponse({"result": "0x"})

    chain_tools.httpx.AsyncClient = _HolderClient
    result = await chain_tools.token_holders("0x" + "33" * 20, top=5)
    assert result["holder_count"] == 2
    assert result["history_complete"] is True
    assert result["top1_share"] == 0.7
    top = result["top_holders"][0]
    assert top["address"] == pool
    assert top["is_contract"] is True
    assert result["top_holders"][1]["is_contract"] is False


async def test_token_holders_splits_ranges_the_node_refuses():
    """A range the node rejects must be halved, not dropped on the floor."""
    holder = "0x" + "99" * 20
    log = {
        "blockNumber": hex(10),
        "topics": [
            chain_tools.TRANSFER_TOPIC,
            "0x" + "0" * 64,
            "0x" + holder[2:].rjust(64, "0"),
        ],
        "data": "0x" + hex(10**18)[2:].rjust(64, "0"),
    }
    refused: list[tuple[int, int]] = []
    served: list[tuple[int, int]] = []

    class _SplitClient(_FakeClient):
        async def post(self, url, json=None, headers=None):
            method = json["method"]
            params = json.get("params") or []
            if method == "eth_blockNumber":
                return _FakeResponse({"result": hex(100)})
            if method == "eth_getLogs":
                low = int(params[0]["fromBlock"], 16)
                high = int(params[0]["toBlock"], 16)
                if high - low > 40:
                    refused.append((low, high))
                    return _FakeResponse(
                        {"error": {"message": "logs matched by query exceeds limit of 10000"}}
                    )
                served.append((low, high))
                return _FakeResponse({"result": [log] if low <= 10 <= high else []})
            if method == "eth_call":
                return _FakeResponse({"result": "0x" + "12".rjust(64, "0")})
            if method == "eth_getCode":
                return _FakeResponse({"result": "0x"})
            return _FakeResponse({"result": "0x"})

    chain_tools.httpx.AsyncClient = _SplitClient
    result = await chain_tools.token_holders("0x" + "44" * 20, top=3)
    assert refused, "the oversized range should have been refused at least once"
    assert served, "the refused range should have been retried in halves"
    assert all(high - low <= 40 for low, high in served)
    assert result["history_complete"] is True
    assert result["holder_count"] == 1
    assert result["top_holders"][0]["address"] == holder


async def test_token_liquidity_resolves_pools_through_the_factory():
    pool = "0x" + "ab" * 20

    class _LiquidityClient(_FakeClient):
        async def post(self, url, json=None, headers=None):
            method = json["method"]
            params = json.get("params") or []
            if method == "eth_blockNumber":
                return _FakeResponse({"result": hex(900)})
            if method == "eth_getLogs":
                return _FakeResponse({"result": []})
            if method == "eth_call":
                data = params[0]["data"]
                if data.startswith("0x1698ee82"):
                    # selector + token word + quote word + fee word, each 64 hex chars
                    quote = "0x" + data[98:138]
                    fee = int(data[138:202], 16)
                    hit = fee == 10000 and quote == chain_tools.WETH
                    return _FakeResponse(
                        {"result": "0x" + (pool[2:] if hit else "0" * 40).rjust(64, "0")}
                    )
                if data.startswith("0x70a08231"):
                    return _FakeResponse({"result": "0x" + hex(4 * 10**18)[2:].rjust(64, "0")})
                if data.startswith("0x313ce567"):
                    return _FakeResponse({"result": "0x" + "12".rjust(64, "0")})
                if data.startswith("0x95d89b41"):
                    return _FakeResponse({"result": _encoded_string("WETH")})
            return _FakeResponse({"result": "0x"})

    chain_tools.httpx.AsyncClient = _LiquidityClient
    result = await chain_tools.token_liquidity("0x" + "55" * 20, blocks=100)
    assert result["pools_found"] == 1
    found = result["pools"][0]
    assert found["pool"] == pool
    assert found["fee_tier_bps"] == 100
    assert found["swaps_in_window"] == 0  # exists even with no recent trading


def test_v3_price_respects_token_order_and_decimals():
    sqrt_price = 1 << 96
    token = "0x" + "aa" * 20
    quote = "0x" + "bb" * 20
    assert chain_tools._v3_price_in_quote(
        sqrt_price, token, quote, token, quote, 18, 18
    ) == 1.0
    assert chain_tools._v3_price_in_quote(
        sqrt_price, token, quote, token, quote, 6, 18
    ) == pytest.approx(1e-12)
    assert chain_tools._v3_price_in_quote(
        sqrt_price, token, quote, quote, token, 6, 18
    ) == pytest.approx(1e12)


def test_build_candles_keeps_real_ohlc_order_and_latest_buckets():
    swaps = [
        {"blockNumber": hex(101), "transactionIndex": "0x0", "logIndex": "0x1", "price_in_paired": 2.0},
        {"blockNumber": hex(101), "transactionIndex": "0x0", "logIndex": "0x0", "price_in_paired": 1.0},
        {"blockNumber": hex(109), "transactionIndex": "0x0", "logIndex": "0x0", "price_in_paired": 4.0},
        {"blockNumber": hex(112), "transactionIndex": "0x0", "logIndex": "0x0", "price_in_paired": 3.0},
    ]
    candles = chain_tools._build_candles(swaps, start_block=100, interval_blocks=10)
    assert candles == [
        {
            "from_block": 100, "to_block": 109, "first_swap_block": 101, "last_swap_block": 109,
            "open": 1.0, "high": 4.0, "low": 1.0, "close": 4.0, "swap_count": 3,
        },
        {
            "from_block": 110, "to_block": 119, "first_swap_block": 112, "last_swap_block": 112,
            "open": 3.0, "high": 3.0, "low": 3.0, "close": 3.0, "swap_count": 1,
        },
    ]


async def test_token_candles_uses_v3_swap_prices_not_pool_reserve_ratio():
    token = "0x" + "55" * 20
    quote = chain_tools.WETH
    pool = "0x" + "ab" * 20

    def address_word(value: str) -> str:
        return "0x" + value[2:].rjust(64, "0")

    def swap(block: int, index: int, sqrt_price: int) -> dict:
        return {
            "address": pool,
            "blockNumber": hex(block),
            "transactionIndex": "0x0",
            "logIndex": hex(index),
            "topics": [chain_tools.V3_SWAP_TOPIC, "0x" + "0" * 64, "0x" + "0" * 64],
            "data": "0x" + "0" * 128 + hex(sqrt_price)[2:].rjust(64, "0") + "0" * 128,
        }

    class _CandleClient(_FakeClient):
        async def post(self, url, json=None, headers=None):
            method = json["method"]
            params = json.get("params") or []
            if method == "eth_blockNumber":
                return _FakeResponse({"result": hex(900)})
            if method == "eth_getLogs":
                request = params[0]
                if request.get("address") == pool and request.get("topics") == [chain_tools.V3_SWAP_TOPIC]:
                    return _FakeResponse({"result": [
                        swap(805, 1, 1 << 96),
                        swap(808, 0, 2 << 96),
                        swap(855, 0, 1 << 95),
                    ]})
                return _FakeResponse({"result": []})
            if method == "eth_getBlockByNumber":
                block = int(params[0], 16)
                return _FakeResponse({"result": {"timestamp": hex(1_000_000 + block)}})
            if method == "eth_call":
                data = params[0]["data"]
                if data.startswith("0x1698ee82"):
                    target_quote = "0x" + data[98:138]
                    fee = int(data[138:202], 16)
                    hit = target_quote == quote and fee == 10000
                    return _FakeResponse({"result": address_word(pool if hit else chain_tools.ZERO_ADDRESS)})
                if data.startswith("0x70a08231"):
                    return _FakeResponse({"result": "0x" + hex(4 * 10**18)[2:].rjust(64, "0")})
                if data.startswith("0x313ce567"):
                    return _FakeResponse({"result": "0x" + "12".rjust(64, "0")})
                if data.startswith("0x95d89b41"):
                    return _FakeResponse({"result": _encoded_string("WETH")})
                if data.startswith("0x0dfe1681"):
                    return _FakeResponse({"result": address_word(token)})
                if data.startswith("0xd21220a7"):
                    return _FakeResponse({"result": address_word(quote)})
                if data.startswith("0x3850c7bd"):
                    return _FakeResponse({"result": "0x" + hex(1 << 96)[2:].rjust(64, "0")})
            return _FakeResponse({"result": "0x"})

    chain_tools.httpx.AsyncClient = _CandleClient
    result = await chain_tools.token_candles(token, blocks=100, interval_blocks=50)
    assert result["pool"] == pool
    assert result["live_price_in_paired"] == 1.0
    assert result["swaps_scanned"] == 3
    assert result["swaps_used"] == 3
    assert result["candles"][0]["open"] == 1.0
    assert result["candles"][0]["high"] == 4.0
    assert result["candles"][0]["close"] == 4.0
    assert result["candles"][1]["close"] == 0.25
    assert result["candles"][0]["opened_at"] == 1_000_805
    assert "executed V3 Swap events" in result["note"]


async def test_rpc_retries_a_rate_limited_endpoint(monkeypatch):
    attempts = {"count": 0}
    slept: list[float] = []

    class _Throttled(_FakeClient):
        async def post(self, url, json=None, headers=None):
            attempts["count"] += 1
            if attempts["count"] < 3:
                return _FakeResponse({}, status_code=429)
            return _FakeResponse({"result": "0x2a"})

    async def _no_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(chain_tools.asyncio, "sleep", _no_sleep)
    chain_tools.httpx.AsyncClient = _Throttled
    async with _Throttled() as client:
        value = await chain_tools._rpc(client, "eth_blockNumber", [])
    assert value == "0x2a"
    assert attempts["count"] == 3
    assert slept == [0.6, 1.2]  # backs off instead of hammering


async def test_rpc_gives_up_with_a_clear_error(monkeypatch):
    class _Down(_FakeClient):
        async def post(self, url, json=None, headers=None):
            return _FakeResponse({}, status_code=503)

    async def _no_sleep(seconds):
        return None

    monkeypatch.setattr(chain_tools.asyncio, "sleep", _no_sleep)
    chain_tools.httpx.AsyncClient = _Down
    async with _Down() as client:
        with pytest.raises(chain_tools.ChainError, match="unavailable"):
            await chain_tools._rpc(client, "eth_blockNumber", [])


async def test_invalid_address_is_rejected_before_any_rpc_call():
    with pytest.raises(chain_tools.ChainError):
        await chain_tools.token_overview("not-an-address")
    with pytest.raises(chain_tools.ChainError):
        await chain_tools.contract_audit("0x123")


async def test_call_chain_tool_dispatches_and_rejects_unknown_names():
    _FakeClient.script = {"eth_getCode": "0x"}
    result = await chain_tools.call_chain_tool("chain_token_overview", {"address": "0x" + "99" * 20})
    assert result["is_contract"] is False
    with pytest.raises(chain_tools.ChainError):
        await chain_tools.call_chain_tool("chain_unknown", {})


def test_tool_definitions_are_declared_for_the_model():
    definitions = chain_tools.tool_definitions()
    names = {definition["name"] for definition in definitions}
    assert names == set(chain_tools.HANDLERS)
    assert all(definition["source"] == "chain" for definition in definitions)
    assert all(definition["risk"] == "read" for definition in definitions)
    assert all("handler" not in definition for definition in definitions)
    assert {"chain_nft_collection_overview", "chain_nft_collection_activity"} <= names
