from orchestrator import research as research_module
from orchestrator.research import _DuckDuckGoParser, build_report, onchain_search, run_research


def test_duckduckgo_parser_extracts_public_result():
    parser = _DuckDuckGoParser("youtube")
    parser.feed(
        '<a class="result__a" href="https://www.youtube.com/watch?v=abc">Useful video</a>'
        '<a class="result__snippet">A useful public description with enough context.</a>'
    )
    assert parser.results[0]["source"] == "youtube"
    assert parser.results[0]["url"] == "https://www.youtube.com/watch?v=abc"


async def test_research_uses_public_search_without_user_keys(monkeypatch):
    async def fake_public(query: str, source: str = "web", count: int = 10):
        domains = {
            "web": "example.com",
            "youtube": "youtube.com",
            "tiktok": "tiktok.com",
            "instagram": "instagram.com",
        }
        return [
            {
                "source": source,
                "title": f"{source} result",
                "url": f"https://{domains[source]}/{source}",
                "snippet": query,
                "score": 0.8,
            }
        ]

    monkeypatch.setattr("orchestrator.research.public_web_search", fake_public)
    findings, statuses = await run_research(
        "agent teams",
        ["web", "youtube", "tiktok", "instagram"],
        {},
        "quick",
    )
    assert {item["source"] for item in findings} == {
        "web",
        "youtube",
        "tiktok",
        "instagram",
    }
    assert all(value["status"] == "public-web" for value in statuses.values())


def test_empty_report_does_not_ask_user_for_api_key():
    report = build_report("проверить рынок", [], {})
    assert "API-ключи от пользователя не требуются" in report
    assert "Добавьте Brave" not in report


async def test_social_fallback_discards_ads_and_other_domains(monkeypatch):
    async def fake_public(query: str, source: str = "web", count: int = 10):
        return [
            {"source": source, "title": "Ad", "url": "https://ads.example/a", "snippet": "", "score": 0.9},
            {"source": source, "title": "Video", "url": "https://www.youtube.com/watch?v=1", "snippet": "", "score": 0.8},
        ]

    monkeypatch.setattr("orchestrator.research.public_web_search", fake_public)
    findings, _ = await run_research("agent teams", ["youtube"], {}, "quick")
    assert [item["url"] for item in findings] == ["https://www.youtube.com/watch?v=1"]


async def test_onchain_search_collects_native_contract_evidence(monkeypatch):
    address = "0x" + "ab" * 20
    calls: list[str] = []

    def response(tool: str, **values):
        async def value(received: str):
            assert received == address
            calls.append(tool)
            return {"address": address, "explorer": f"https://explorer.test/{tool}", **values}
        return value

    monkeypatch.setattr(
        research_module.chain_tools,
        "token_overview",
        response("chain_token_overview", is_contract=True, name="Orbit", symbol="ORB", decimals=18, total_supply=1_000),
    )
    monkeypatch.setattr(research_module.chain_tools, "contract_audit", response("chain_contract_audit", is_proxy=False, risk_notes=[]))
    monkeypatch.setattr(research_module.chain_tools, "token_activity", response("chain_token_activity", transfer_count=4, window_blocks=500, unique_senders=2, unique_receivers=3))
    monkeypatch.setattr(research_module.chain_tools, "token_age", response("chain_token_age", first_activity_block=123, age_days=2.5))
    monkeypatch.setattr(research_module.chain_tools, "token_holders", response("chain_token_holders", holder_count=10, history_complete=True, top1_share=0.2, top10_share=0.8))
    monkeypatch.setattr(research_module.chain_tools, "token_liquidity", response("chain_token_liquidity", pools_found=1, deepest_paired_reserve=42, window_blocks=600))

    findings = await onchain_search(f"Should we review 0x{'AB' * 20} today?")

    assert calls[0] == "chain_token_overview"
    assert set(calls) == {
        "chain_token_overview", "chain_contract_audit", "chain_token_age",
    }
    assert len(findings) == 3
    assert {item["source"] for item in findings} == {"onchain"}
    assert all(item["provenance"]["address"] == address for item in findings)
    assert all(item["provenance"]["status"] == "ok" for item in findings)
    assert all(item["provenance"]["chain_id"] == 4663 for item in findings)


async def test_onchain_search_checks_wallet_without_token_only_tools(monkeypatch):
    address = "0x" + "cd" * 20
    calls: list[str] = []

    async def overview(received: str):
        calls.append("overview")
        return {"address": received, "is_contract": False, "explorer": "https://explorer.test/address"}

    async def wallet(received: str):
        calls.append("wallet")
        return {"address": received, "native_balance_eth": 1.25, "transaction_count": 7, "is_contract": False, "explorer": "https://explorer.test/address"}

    monkeypatch.setattr(research_module.chain_tools, "token_overview", overview)
    monkeypatch.setattr(research_module.chain_tools, "wallet_report", wallet)
    findings = await onchain_search(f"wallet {address}")

    assert calls == ["overview", "wallet"]
    assert [item["provenance"]["tool"] for item in findings] == ["chain_wallet_report"]
    assert "wallet, not a token" in findings[0]["snippet"]


async def test_onchain_search_requires_address_and_reports_native_failures(monkeypatch):
    async def trending(*_args, **_kwargs):
        return {"window_blocks": 600, "total_transfers": 0, "tokens": []}

    monkeypatch.setattr(research_module.chain_tools, "trending_tokens", trending)
    discovery = await onchain_search("Research the strongest new token")
    assert discovery[0]["provenance"]["tool"] == "chain_trending_tokens"
    assert discovery[0]["provenance"]["status"] == "empty"

    address = "0x" + "ef" * 20

    async def overview(received: str):
        return {"address": received, "is_contract": True, "explorer": "https://explorer.test/token"}

    async def unavailable(_received: str):
        raise RuntimeError("RPC rate limited")

    async def minimal(received: str):
        return {"address": received, "explorer": "https://explorer.test/token"}

    monkeypatch.setattr(research_module.chain_tools, "token_overview", overview)
    monkeypatch.setattr(research_module.chain_tools, "contract_audit", unavailable)
    monkeypatch.setattr(research_module.chain_tools, "token_activity", minimal)
    monkeypatch.setattr(research_module.chain_tools, "token_age", minimal)
    monkeypatch.setattr(research_module.chain_tools, "token_holders", minimal)
    monkeypatch.setattr(research_module.chain_tools, "token_liquidity", minimal)
    findings, statuses = await run_research(f"Audit {address}", ["onchain"], {}, "quick")

    assert statuses["onchain"]["status"] == "partial: 1 native tool(s) unavailable"
    failed = next(item for item in findings if item["provenance"]["status"] == "error")
    assert failed["provenance"]["tool"] == "chain_contract_audit"
    assert "rate limited" in failed["snippet"]
