from __future__ import annotations

import pytest

from orchestrator import chain_tools, research

ADDRESS = "0x" + "ab" * 20


def _overview(**overrides):
    base = {
        "address": ADDRESS,
        "is_contract": True,
        "name": "Attention",
        "symbol": "ATTENTION",
        "decimals": 18,
        "total_supply": 1_000_000_000.0,
        "explorer": "https://explorer/token/" + ADDRESS,
    }
    base.update(overrides)
    return base


def _audit(**overrides):
    base = {
        "address": ADDRESS,
        "is_proxy": True,
        "owner": "0x" + "cd" * 20,
        "ownership_renounced": False,
        "risk_notes": ["Upgradeable proxy: the admin can replace the token logic entirely."],
        "explorer": "https://explorer/token/" + ADDRESS,
    }
    base.update(overrides)
    return base


def _age(**overrides):
    base = {
        "address": ADDRESS,
        "first_activity_block": 22_690_689,
        "age_days": 46.9,
        "first_minter": "0x" + "ef" * 20,
        "explorer": "https://explorer/token/" + ADDRESS,
    }
    base.update(overrides)
    return base


def _trending(tokens=None):
    return {
        "window_blocks": 600,
        "total_transfers": 26_370,
        "tokens": tokens
        if tokens is not None
        else [
            {
                "address": ADDRESS,
                "symbol": "ATTENTION",
                "transfers": 1638,
                "unique_receivers": 120,
                "explorer": "https://explorer/token/" + ADDRESS,
            }
        ],
    }


@pytest.fixture
def chain(monkeypatch):
    """Stub the chain layer so the source is tested without touching the network."""
    calls: dict[str, list] = {"overview": [], "audit": [], "age": [], "liquidity": [], "holders": [], "candles": []}

    async def overview(address):
        calls["overview"].append(address)
        return _overview()

    async def audit(address):
        calls["audit"].append(address)
        return _audit()

    async def age(address):
        calls["age"].append(address)
        return _age()

    async def trending(blocks=600, limit=10):
        return _trending()

    async def liquidity(address, blocks=600):
        calls["liquidity"].append(address)
        return {
            "pools_found": 2,
            "pools": [
                {
                    "token_reserve": 15_352_570.77,
                    "paired_reserve": 4562.58,
                    "paired_symbol": "WETH",
                    "price_in_paired": 0.000297,
                    "explorer": "https://explorer/address/pool",
                }
            ],
        }

    async def holders(address, top=5):
        calls["holders"].append(address)
        return {
            "holder_count": 1919,
            "top1_share": 0.2457,
            "top10_share": 0.8609,
            "history_complete": False,
            "explorer": "https://explorer/token/" + ADDRESS,
        }

    async def candles(address):
        calls["candles"].append(address)
        return {
            "pool": "0x" + "12" * 20,
            "paired_symbol": "WETH",
            "live_price_in_paired": 0.000297,
            "swaps_used": 3,
            "candles": [{"open": 0.0002, "high": 0.0004, "low": 0.0002, "close": 0.000297}],
            "explorer": "https://explorer/address/pool",
        }

    monkeypatch.setattr(chain_tools, "token_overview", overview)
    monkeypatch.setattr(chain_tools, "contract_audit", audit)
    monkeypatch.setattr(chain_tools, "token_age", age)
    monkeypatch.setattr(chain_tools, "trending_tokens", trending)
    monkeypatch.setattr(chain_tools, "token_liquidity", liquidity)
    monkeypatch.setattr(chain_tools, "token_holders", holders)
    monkeypatch.setattr(chain_tools, "token_candles", candles)
    return calls


async def test_an_address_in_the_query_is_profiled_directly(chain):
    findings = await research.onchain_search(f"is {ADDRESS} safe to buy?")
    assert chain["overview"] == [ADDRESS]
    titles = " ".join(item["title"] for item in findings)
    assert "on-chain identity" in titles
    assert "age and first minter" in titles
    assert "contract risk surface" in titles
    assert all(item["source"] == "onchain" for item in findings)


async def test_a_ticker_is_matched_against_tokens_moving_on_chain(chain):
    findings = await research.onchain_search("is $ATTENTION worth buying")
    assert chain["overview"] == [ADDRESS]
    assert findings[0]["title"].startswith("ATTENTION")


async def test_quick_depth_skips_the_expensive_reads(chain):
    await research.onchain_search(f"look at {ADDRESS}")
    assert chain["liquidity"] == []
    assert chain["holders"] == []


async def test_deep_depth_adds_liquidity_and_concentration(chain):
    findings = await research.onchain_search(f"look at {ADDRESS}", depth="deep")
    assert chain["liquidity"] == [ADDRESS]
    assert chain["candles"] == [ADDRESS]
    titles = " ".join(item["title"] for item in findings)
    assert "DEX liquidity" in titles
    assert "holder concentration" in titles
    assert "executed-swap candles" in titles
    concentration = next(item for item in findings if "concentration" in item["title"])
    assert "lower bound" in concentration["snippet"]  # truncation must be disclosed


async def test_a_query_without_a_target_reports_what_is_trading(chain):
    findings = await research.onchain_search("what memecoins are hot right now")
    assert chain["overview"] == []
    assert "moving right now" in findings[0]["title"]
    assert "26370 transfers" in findings[0]["snippet"]


async def test_a_wallet_address_is_reported_as_not_a_token(monkeypatch, chain):
    async def wallet(address):
        return _overview(is_contract=False, name=None, symbol=None)

    async def wallet_report(address):
        return {
            "address": address,
            "is_contract": False,
            "native_balance_eth": 1.25,
            "transaction_count": 7,
            "explorer": "https://explorer/address/" + address,
        }

    monkeypatch.setattr(chain_tools, "token_overview", wallet)
    monkeypatch.setattr(chain_tools, "wallet_report", wallet_report)
    findings = await research.onchain_search(f"check {ADDRESS}")
    assert len(findings) == 1
    assert "wallet, not a token" in findings[0]["snippet"]


async def test_a_failing_chain_read_drops_that_finding_rather_than_the_search(monkeypatch, chain):
    async def broken(address):
        raise chain_tools.ChainError("endpoint unavailable")

    monkeypatch.setattr(chain_tools, "token_age", broken)
    findings = await research.onchain_search(f"check {ADDRESS}")
    titles = " ".join(item["title"] for item in findings)
    assert "age and first minter" not in titles
    assert "on-chain identity" in titles


def test_function_words_are_not_mistaken_for_tickers():
    symbols = research._candidate_symbols("is it worth buying or should we hold")
    assert symbols == []


def test_a_real_ticker_survives_the_filter():
    assert "ATTENTION" in research._candidate_symbols("thoughts on $ATTENTION?")
    assert "AI" in research._candidate_symbols("what about AI")


async def test_the_source_is_reachable_through_run_research(monkeypatch, chain):
    findings, statuses = await research.run_research(
        query=f"check {ADDRESS}", sources=["onchain"], credentials={}, depth="quick"
    )
    assert statuses["onchain"]["status"] == "robinhood-chain"
    assert findings and all(item["source"] == "onchain" for item in findings)
