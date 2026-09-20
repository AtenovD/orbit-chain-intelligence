import json

import httpx
import pytest

from orchestrator.context_connectors import (
    BLOCKSCOUT_API_URL,
    BITQUERY_GRAPHQL_URL,
    BITQUERY_DEX_TRADES_QUERY,
    BITQUERY_WALLET_BALANCES_QUERY,
    _fetch_bitquery,
    _fetch_blockscout,
    get_dex_trades,
    get_token_holders,
    get_wallet_balances,
)


TOKEN = "0x0000000000000000000000000000000000000001"
WALLET = "0x0000000000000000000000000000000000000002"


def test_bitquery_queries_are_scoped_to_robinhood_chain():
    """A valid GraphQL request is not enough: it must not silently inspect Ethereum."""
    assert "EVM(network: robinhood" in BITQUERY_DEX_TRADES_QUERY
    assert "EVM(network: robinhood" in BITQUERY_WALLET_BALANCES_QUERY
    assert "network: eth" not in BITQUERY_DEX_TRADES_QUERY
    assert "network: eth" not in BITQUERY_WALLET_BALANCES_QUERY


@pytest.mark.asyncio
async def test_bitquery_trade_and_balance_queries_use_direct_graphql_api():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == BITQUERY_GRAPHQL_URL
        assert request.headers["X-API-KEY"] == "bitquery-key"
        payload = json.loads(request.content)
        if "TokenDexTrades" in payload["query"]:
            assert payload["variables"] == {"token": TOKEN, "since": "2026-09-10T10:00:00Z"}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "EVM": {
                            "DEXTrades": [
                                {
                                    "Block": {"Time": "2026-09-11T10:00:00Z", "Number": "1"},
                                    "Transaction": {"Hash": "0xtrade", "From": WALLET},
                                    "Trade": {
                                        "Dex": {"ProtocolName": "uniswap_v3"},
                                        "Buy": {"Amount": "7", "AmountInUSD": "14", "PriceInUSD": "2", "Currency": {"Symbol": "ORB"}},
                                        "Sell": {"Amount": "0.01", "AmountInUSD": "14", "Currency": {"Symbol": "ETH"}},
                                    },
                                }
                            ]
                        }
                    }
                },
            )
        assert "WalletBalances" in payload["query"]
        assert payload["variables"] == {"address": WALLET}
        return httpx.Response(
            200,
            json={
                "data": {
                    "EVM": {
                        "Balances": [
                            {"Currency": {"Name": "Orbit", "Symbol": "ORB", "SmartContract": TOKEN}, "Balance": {"Amount": "123"}}
                        ]
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        trades = await get_dex_trades(client, TOKEN, "2026-09-10T10:00:00Z", "bitquery-key")
        balances = await get_wallet_balances(client, WALLET, "bitquery-key")

    assert trades[0]["id"] == "0xtrade"
    assert "uniswap_v3" in trades[0]["content"]
    assert balances == [{"id": f"{WALLET}:{TOKEN}", "title": "Wallet balance · ORB", "content": f"Wallet: {WALLET}\nBalance: 123 ORB\nAsset: Orbit\nContract: {TOKEN}"}]


@pytest.mark.asyncio
async def test_trading_connectors_normalize_data_and_validate_their_targets():
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(BLOCKSCOUT_API_URL):
            if request.url.params.get("apikey"):
                assert request.url.params["apikey"] == "blockscout-key"
                assert request.headers["X-API-KEY"] == "blockscout-key"
            else:
                assert "X-API-KEY" not in request.headers
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"value": "99", "address_hash": {"hash": WALLET, "is_contract": False}},
                    ]
                },
            )
        payload = json.loads(request.content)
        assert "TokenDexTrades" in payload["query"]
        return httpx.Response(200, json={"data": {"EVM": {"DEXTrades": []}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        holders = await get_token_holders(client, TOKEN, "blockscout-key")
        bitquery = await _fetch_bitquery(client, "bitquery-key", f"token:{TOKEN}", None)
        blockscout = await _fetch_blockscout(client, "", TOKEN)
        with pytest.raises(ValueError, match="token: or wallet:"):
            await _fetch_bitquery(client, "bitquery-key", f"holder:{TOKEN}", None)
        with pytest.raises(ValueError, match="Blockscout token address"):
            await _fetch_blockscout(client, "", "not-an-address")

    assert holders[0]["id"] == WALLET
    assert "Balance (raw units): 99" in holders[0]["content"]
    assert bitquery["details"] == {"target_type": "token", "address": TOKEN, "trades": 0}
    assert blockscout["details"] == {"token_address": TOKEN, "holders": 1}
