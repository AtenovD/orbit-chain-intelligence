from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree

import httpx

from orchestrator import chain_tools

_ONCHAIN_ADDRESS = re.compile(r"(?<![0-9a-fA-F])0[xX][a-fA-F0-9]{40}(?![0-9a-fA-F])")
_ONCHAIN_CHAIN_ID = 4663
_ONCHAIN_NETWORK = "Robinhood Chain"

def _finding(source: str, title: str, url: str, snippet: str, **extra: Any) -> dict[str, Any]:
    return {
        "source": source,
        "title": title.strip() or "Untitled",
        "url": url,
        "snippet": snippet.strip(),
        "score": min(
            1.0,
            0.55
            + (0.15 if url.startswith("https://") else 0)
            + (0.1 if len(snippet) > 100 else 0),
        ),
        **extra,
    }


def _onchain_provenance(address: str | None, tool: str, status: str, **extra: Any) -> dict[str, Any]:
    """Small, auditable description of a native RPC observation."""
    return {
        "kind": "native_chain_rpc",
        "network": _ONCHAIN_NETWORK,
        "chain_id": _ONCHAIN_CHAIN_ID,
        "address": address,
        "tool": tool,
        "status": status,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def _onchain_url(address: str, result: dict[str, Any] | None = None) -> str:
    return str((result or {}).get("explorer") or f"{chain_tools.EXPLORER}/address/{address}")


def _onchain_summary(tool: str, result: dict[str, Any]) -> tuple[str, str]:
    """Turn native tool output into a concise finding without inferring a verdict."""
    address = str(result.get("address") or "the supplied address")
    if tool == "chain_token_overview":
        if not result.get("is_contract"):
            return (
                f"Wallet overview · {address}",
                str(result.get("verdict_hint") or "The address has no contract bytecode; treating it as a wallet."),
            )
        identity = " ".join(value for value in [result.get("name"), result.get("symbol")] if value) or "Unnamed contract"
        return (
            f"Token overview · {identity}",
            f"Contract {address}; decimals={result.get('decimals')}, total supply={result.get('total_supply')}, "
            f"bytecode={result.get('bytecode_size')} bytes.",
        )
    if tool == "chain_contract_audit":
        risks = "; ".join(str(value) for value in (result.get("risk_notes") or [])[:3]) or "No specific risk note returned."
        privileged = ", ".join(str(value) for value in (result.get("privileged_functions") or [])) or "none detected"
        return (
            "Contract control-surface audit",
            f"Proxy={bool(result.get('is_proxy'))}; owner={result.get('owner') or 'not exposed'}; "
            f"privileged functions={privileged}. {risks}",
        )
    if tool == "chain_token_activity":
        return (
            "Recent transfer activity",
            f"{result.get('transfer_count', 0)} transfers across {result.get('window_blocks')} blocks; "
            f"senders={result.get('unique_senders', 0)}, receivers={result.get('unique_receivers', 0)}, "
            f"largest transfer={result.get('largest_transfer')}, sender concentration={result.get('sender_concentration')}.",
        )
    if tool == "chain_token_age":
        return (
            "Token age and first mint",
            f"First activity block={result.get('first_activity_block')}; age={result.get('age_days')} days; "
            f"first minter={result.get('first_minter') or 'not recovered'}. {result.get('note') or ''}",
        )
    if tool == "chain_token_holders":
        completeness = "complete" if result.get("history_complete") else "partial"
        return (
            "Holder concentration",
            f"Holders={result.get('holder_count')}; top-1 share={result.get('top1_share')}; "
            f"top-10 share={result.get('top10_share')}; reconstructed history is {completeness}. "
            f"{result.get('note') or ''}",
        )
    if tool == "chain_token_liquidity":
        return (
            "DEX liquidity",
            f"Pools found={result.get('pools_found')}; deepest paired reserve={result.get('deepest_paired_reserve')}; "
            f"window={result.get('window_blocks')} blocks. {result.get('note') or ''}",
        )
    if tool == "chain_wallet_report":
        return (
            f"Wallet report · {address}",
            f"Native balance={result.get('native_balance_eth')}; transaction count={result.get('transaction_count')}; "
            f"is_contract={bool(result.get('is_contract'))}.",
        )
    return tool, f"Native chain tool returned data for {address}."


def _onchain_result_finding(address: str, tool: str, result: dict[str, Any]) -> dict[str, Any]:
    title, snippet = _onchain_summary(tool, result)
    return _finding(
        "onchain",
        title,
        _onchain_url(address, result),
        snippet,
        score=0.96,
        provenance=_onchain_provenance(address, tool, "ok"),
    )


def _onchain_error_finding(address: str | None, tool: str, error: Exception | str) -> dict[str, Any]:
    message = str(error).strip()[:300] or "Native chain tool returned no usable result"
    url = _onchain_url(address) if address else chain_tools.EXPLORER
    return _finding(
        "onchain",
        f"On-chain source unavailable · {tool}",
        url,
        message,
        score=0.2,
        provenance=_onchain_provenance(address, tool, "error", error=message),
    )


def _finding_identity(finding: dict[str, Any]) -> str:
    """Keep distinct native observations even when they share an explorer URL."""
    if finding.get("source") == "onchain":
        provenance = finding.get("provenance") or {}
        return "onchain:{address}:{tool}".format(
            address=provenance.get("address") or "discovery",
            tool=provenance.get("tool") or finding.get("title") or "unknown",
        )
    return str(finding.get("url") or f"{finding.get('source')}:{finding.get('title')}")


def _matches_domains(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


class _DuckDuckGoParser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source
        self.results: list[dict[str, Any]] = []
        self._href = ""
        self._title: list[str] = []
        self._snippet: list[str] = []
        self._inside_title = False
        self._inside_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self._inside_title = True
            self._href = values.get("href") or ""
            self._title = []
            self._snippet = []
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self._inside_snippet = True

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self._title.append(data)
        if self._inside_snippet:
            self._snippet.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._inside_title:
            self._inside_title = False
        if tag in {"a", "div"} and self._inside_snippet:
            self._inside_snippet = False
            target = self._href
            parsed = urlparse(target)
            if parsed.netloc.endswith("duckduckgo.com"):
                target = unquote((parse_qs(parsed.query).get("uddg") or [target])[0])
            if target and self._title:
                self.results.append(
                    _finding(
                        self.source,
                        unescape(" ".join(self._title)),
                        target,
                        unescape(" ".join(self._snippet)),
                    )
                )


async def brave_search(
    query: str, key: str, source: str = "web", count: int = 10
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count, "extra_snippets": "true"},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
        )
        response.raise_for_status()
    return [
        _finding(
            source,
            item.get("title", "Untitled"),
            item.get("url", ""),
            item.get("description", ""),
        )
        for item in response.json().get("web", {}).get("results", [])
    ]


async def public_web_search(
    query: str, source: str = "web", count: int = 10
) -> list[dict[str, Any]]:
    """API-free fallback owned by Orbit, never configured by an end user."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=headers) as client:
        try:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            response.raise_for_status()
            parser = _DuckDuckGoParser(source)
            parser.feed(response.text)
            if parser.results:
                return parser.results[:count]
        except httpx.HTTPError:
            pass

        try:
            response = await client.get(
                "https://www.bing.com/search",
                params={"q": query, "format": "rss", "count": count},
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
            items = []
            for item in root.findall(".//item")[:count]:
                items.append(
                    _finding(
                        source,
                        item.findtext("title") or "Untitled",
                        item.findtext("link") or "",
                        item.findtext("description") or "",
                    )
                )
            if items:
                return items
        except (httpx.HTTPError, ElementTree.ParseError):
            pass
        return []


async def youtube_search(query: str, key: str, count: int = 12) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": count,
                "order": "relevance",
                "key": key,
            },
        )
        response.raise_for_status()
    findings = []
    for item in response.json().get("items", []):
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})
        if video_id:
            findings.append(
                _finding(
                    "youtube",
                    snippet.get("title", "YouTube video"),
                    f"https://www.youtube.com/watch?v={video_id}",
                    snippet.get("description", ""),
                    author=snippet.get("channelTitle"),
                    published_at=snippet.get("publishedAt"),
                    thumbnail=(snippet.get("thumbnails", {}).get("medium", {}) or {}).get("url"),
                )
            )
    return findings


async def tiktok_search(query: str, token: str, count: int = 20) -> list[dict[str, Any]]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=30)
    fields = "id,video_description,create_time,username,view_count,like_count,comment_count,share_count,hashtag_names"
    body = {
        "query": {"and": [{"operation": "EQ", "field_name": "keyword", "field_values": [query]}]},
        "max_count": count,
        "start_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "is_random": False,
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"https://open.tiktokapis.com/v2/research/video/query/?fields={fields}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
    return [
        _finding(
            "tiktok",
            video.get("video_description") or f"TikTok by @{video.get('username', 'unknown')}",
            f"https://www.tiktok.com/@{video.get('username')}/video/{video.get('id')}",
            video.get("video_description", ""),
            author=video.get("username"),
            metrics={key: video.get(key, 0) for key in ("view_count", "like_count", "comment_count", "share_count")},
        )
        for video in response.json().get("data", {}).get("videos", [])
    ]


async def instagram_search(
    query: str, token: str, account_id: str, count: int = 20
) -> list[dict[str, Any]]:
    hashtag = query.lstrip("#").split()[0]
    async with httpx.AsyncClient(base_url="https://graph.facebook.com", timeout=30) as client:
        tag_response = await client.get(
            "/ig_hashtag_search",
            params={"user_id": account_id, "q": hashtag, "access_token": token},
        )
        tag_response.raise_for_status()
        tags = tag_response.json().get("data", [])
        if not tags:
            return []
        media_response = await client.get(
            f"/{tags[0]['id']}/recent_media",
            params={
                "user_id": account_id,
                "fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
                "limit": count,
                "access_token": token,
            },
        )
        media_response.raise_for_status()
    return [
        _finding(
            "instagram",
            (item.get("caption") or "Instagram post")[:100],
            item.get("permalink", ""),
            item.get("caption", ""),
            published_at=item.get("timestamp"),
            metrics={"like_count": item.get("like_count", 0), "comments_count": item.get("comments_count", 0)},
        )
        for item in media_response.json().get("data", [])
    ]


_SYMBOL_PATTERN = re.compile(r"\$?([A-Za-z][A-Za-z0-9]{1,14})")

# Avoid treating ordinary phrasing ("is it worth buying") as a token ticker.
_SYMBOL_STOPWORDS = {
    "a", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "it", "me",
    "my", "no", "of", "on", "or", "so", "to", "up", "us", "we", "am", "are", "was",
    "the", "and", "for", "with", "this", "that", "what", "when", "why", "how", "who",
    "should", "would", "could", "can", "will", "now", "new", "out", "any", "all",
    "token", "coin", "memecoin", "contract", "wallet", "chain", "robinhood", "price",
    "buy", "sell", "hold", "risk", "rug", "audit", "holders", "liquidity", "supply",
    "analyse", "analyze", "research", "check", "about", "into", "look", "find",
    "worth", "safe", "scam", "good", "bad", "best", "top", "give", "tell", "show",
}


def _is_stopword(word: str) -> bool:
    lowered = word.lower()
    if lowered in _SYMBOL_STOPWORDS:
        return True
    return any(lowered.endswith(suffix) and lowered[: -len(suffix)] in _SYMBOL_STOPWORDS for suffix in ("ing", "ed", "es", "s"))


def _candidate_symbols(query: str) -> list[str]:
    seen: list[str] = []
    for match in _SYMBOL_PATTERN.finditer(query):
        symbol = match.group(1)
        if _is_stopword(symbol) or symbol.lower().startswith("0x"):
            continue
        if symbol.upper() not in seen:
            seen.append(symbol.upper())
    return seen[:6]


def _onchain_finding(
    title: str,
    url: str,
    snippet: str,
    *,
    address: str | None,
    tool: str,
    score: float = 0.95,
    status: str = "ok",
) -> dict[str, Any]:
    return _finding(
        "onchain", title, url, snippet, score=score,
        provenance=_onchain_provenance(address, tool, status),
    )


async def _resolve_address(query: str) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Resolve an explicit address or a ticker observed in the live trend window."""
    direct = _ONCHAIN_ADDRESS.search(query or "")
    if direct:
        return direct.group(0).lower(), None, None
    symbols = _candidate_symbols(query)
    if not symbols:
        return None, None, None
    trending = await chain_tools.trending_tokens(blocks=600, limit=25)
    for token in trending.get("tokens", []):
        symbol = (token.get("symbol") or "").upper()
        if symbol and symbol in symbols:
            return str(token["address"]).lower(), symbol, trending
    return None, None, trending


def _trend_findings(trending: dict[str, Any]) -> list[dict[str, Any]]:
    tokens = list(trending.get("tokens") or [])
    if not tokens:
        return [
            _onchain_finding(
                "Robinhood Chain: no token transfers in the sampled window",
                f"{chain_tools.EXPLORER}/tokens",
                f"No token transfer was returned for the last {trending.get('window_blocks', 'sampled')} blocks.",
                address=None, tool="chain_trending_tokens", score=0.7, status="empty",
            )
        ]
    listing = ", ".join(
        f"{item.get('symbol') or str(item.get('address', ''))[:10]} ({item.get('transfers', 0)} transfers)"
        for item in tokens
    )
    findings = [
        _onchain_finding(
            "Robinhood Chain: what is moving right now",
            f"{chain_tools.EXPLORER}/tokens",
            f"Over the last {trending.get('window_blocks')} blocks the chain saw "
            f"{trending.get('total_transfers')} transfers. Most active: {listing}.",
            address=None, tool="chain_trending_tokens", score=0.8,
        )
    ]
    findings.extend(
        _onchain_finding(
            f"{item.get('symbol') or 'Token'} — {item.get('transfers', 0)} transfers on-chain",
            str(item.get("explorer") or _onchain_url(str(item.get("address") or ""))),
            f"Contract {item.get('address')} moved {item.get('transfers', 0)} times to "
            f"{item.get('unique_receivers', 0)} distinct receivers in the sampled window.",
            address=str(item.get("address") or "").lower() or None,
            tool="chain_trending_tokens", score=0.75,
        )
        for item in tokens[:5]
    )
    return findings


async def onchain_search(query: str, depth: str = "quick") -> list[dict[str, Any]]:
    """Use native Robinhood Chain evidence for an address, observed ticker, or live trends.

    Ticker resolution is intentionally limited to the current on-chain transfer
    window. It never guesses a contract from an unauditable name lookup.
    """
    try:
        address, matched_symbol, initial_trends = await _resolve_address(query)
    except Exception as exc:
        return [_onchain_error_finding(None, "chain_trending_tokens", exc)]
    if not address:
        try:
            trending = initial_trends or await chain_tools.trending_tokens(blocks=600, limit=10)
            return _trend_findings(trending)
        except Exception as exc:
            return [_onchain_error_finding(None, "chain_trending_tokens", exc)]

    try:
        overview = await chain_tools.token_overview(address)
        if not isinstance(overview, dict):
            raise RuntimeError("token overview returned an invalid response")
    except Exception as exc:
        return [_onchain_error_finding(address, "chain_token_overview", exc)]

    if not overview.get("is_contract"):
        try:
            wallet = await chain_tools.wallet_report(address)
            if not isinstance(wallet, dict):
                raise RuntimeError("wallet report returned an invalid response")
        except Exception as exc:
            return [
                _onchain_finding(
                    f"{address} holds no contract code",
                    _onchain_url(address, overview),
                    "This address is a wallet, not a token contract.",
                    address=address, tool="chain_token_overview",
                ),
                _onchain_error_finding(address, "chain_wallet_report", exc),
            ]
        return [
            _onchain_finding(
                f"Wallet overview · {address}",
                _onchain_url(address, wallet),
                "This address is a wallet, not a token contract. "
                f"Native balance={wallet.get('native_balance_eth')}; "
                f"transaction count={wallet.get('transaction_count')}.",
                address=address, tool="chain_wallet_report",
            )
        ]

    label = str(overview.get("symbol") or matched_symbol or address[:10])
    findings = [
        _onchain_finding(
            f"{label}: on-chain identity",
            _onchain_url(address, overview),
            f"{overview.get('name')} ({overview.get('symbol')}), {overview.get('decimals')} decimals, "
            f"total supply {overview.get('total_supply')}. Verified by reading the contract.",
            address=address, tool="chain_token_overview",
        )
    ]
    reads: list[tuple[str, Any]] = [
        ("chain_contract_audit", chain_tools.contract_audit),
        ("chain_token_age", chain_tools.token_age),
    ]
    if depth == "deep":
        reads.extend([
            ("chain_token_liquidity", chain_tools.token_liquidity),
            ("chain_token_holders", lambda token_address: chain_tools.token_holders(token_address, top=5)),
            ("chain_token_candles", chain_tools.token_candles),
        ])
    semaphore = asyncio.Semaphore(2)

    async def read(tool: str, handler: Any) -> tuple[str, dict[str, Any] | Exception]:
        try:
            async with semaphore:
                result = await handler(address)
            if not isinstance(result, dict):
                raise RuntimeError("native chain tool returned an invalid response")
            return tool, result
        except Exception as exc:  # Findings must show source failures rather than silently disappearing.
            return tool, exc

    for tool, result in await asyncio.gather(*(read(tool, handler) for tool, handler in reads)):
        if isinstance(result, Exception):
            findings.append(_onchain_error_finding(address, tool, result))
            continue
        if tool == "chain_contract_audit":
            notes = "; ".join(result.get("risk_notes") or []) or "No privileged-function risks detected."
            findings.append(_onchain_finding(
                f"{label}: contract risk surface", _onchain_url(address, result),
                f"Owner {result.get('owner')}, renounced: {result.get('ownership_renounced')}, "
                f"proxy: {result.get('is_proxy')}. {notes}",
                address=address, tool=tool,
            ))
        elif tool == "chain_token_age" and result.get("first_activity_block"):
            findings.append(_onchain_finding(
                f"{label}: age and first minter", _onchain_url(address, result),
                f"First activity at block {result.get('first_activity_block')}, roughly {result.get('age_days')} days old. "
                f"First minter observed as {result.get('first_minter')}. {result.get('note') or ''}",
                address=address, tool=tool,
            ))
        elif tool == "chain_token_liquidity" and result.get("pools"):
            pool = result["pools"][0]
            findings.append(_onchain_finding(
                f"{label}: DEX liquidity", str(pool.get("explorer") or _onchain_url(address, result)),
                f"{result.get('pools_found')} pool(s). Deepest holds {pool.get('token_reserve')} {label} against "
                f"{pool.get('paired_reserve')} {pool.get('paired_symbol')}; implied price {pool.get('price_in_paired')}.",
                address=address, tool=tool,
            ))
        elif tool == "chain_token_holders" and result.get("holder_count"):
            completeness = "History complete." if result.get("history_complete") else "History truncated; shares are a lower bound."
            findings.append(_onchain_finding(
                f"{label}: holder concentration", _onchain_url(address, result),
                f"{result.get('holder_count')} holders. Top holder {result.get('top1_share')} of supply, top ten "
                f"{result.get('top10_share')}. {completeness}",
                address=address, tool=tool,
            ))
        elif tool == "chain_token_candles" and result.get("pool"):
            candles = list(result.get("candles") or [])
            latest = candles[-1] if candles else None
            movement = (
                f" Latest candle open={latest.get('open')}, close={latest.get('close')}, "
                f"high={latest.get('high')}, low={latest.get('low')}."
                if latest else " No executed swap fell in the scanned window; live slot0 price is shown instead."
            )
            findings.append(_onchain_finding(
                f"{label}: executed-swap candles", _onchain_url(address, result),
                f"Pool={result.get('pool')}; quote={result.get('paired_symbol') or result.get('paired_with')}; "
                f"live price={result.get('live_price_in_paired')}; candles={len(candles)}; "
                f"swaps used={result.get('swaps_used')}. {movement}{result.get('note') or ''}",
                address=address, tool=tool,
            ))
    return findings


def _onchain_source_status(items: list[dict[str, Any]]) -> str:
    states = [str((item.get("provenance") or {}).get("status") or "") for item in items]
    failures = states.count("error")
    if failures:
        successful = states.count("ok")
        if successful:
            return f"partial: {failures} native tool(s) unavailable"
        return "temporarily-unavailable: native chain RPC"
    return "robinhood-chain"


async def run_research(
    query: str,
    sources: list[str],
    credentials: dict[str, dict[str, str | None]],
    depth: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    brave_key = (credentials.get("web") or {}).get("key")
    query_variants = [query]
    if depth == "deep":
        query_variants.extend(
            [
                f"{query} evidence data case study",
                f"{query} limitations criticism risks",
                f"{query} latest trends analysis",
            ]
        )

    async def web_batch(search_query: str, source: str, count: int) -> list[dict[str, Any]]:
        if brave_key:
            return await brave_search(search_query, str(brave_key), source, count)
        return await public_web_search(search_query, source, count)

    async def one(source: str):
        try:
            credential = credentials.get(source) or {}
            if source == "onchain":
                items = await onchain_search(query, depth)
                return source, items, _onchain_source_status(items)
            if source == "web":
                batches = await asyncio.gather(
                    *(web_batch(variant, source, 8 if depth == "deep" else 6) for variant in query_variants)
                )
                mode = "orbit-search" if brave_key else "public-web"
                return source, [item for batch in batches for item in batch], mode
            if source == "youtube" and credential.get("key"):
                batches = await asyncio.gather(
                    *(youtube_search(variant, str(credential["key"]), count=6) for variant in query_variants[:2])
                )
                return source, [item for batch in batches for item in batch], "orbit-search"
            if source == "tiktok" and credential.get("key"):
                return source, await tiktok_search(query, str(credential["key"]), count=30 if depth == "deep" else 10), "orbit-search"
            if source == "instagram" and credential.get("key") and credential.get("account_id"):
                return source, await instagram_search(
                    query,
                    str(credential["key"]),
                    str(credential["account_id"]),
                    count=25 if depth == "deep" else 8,
                ), "orbit-search"
            source_domains = {
                "youtube": ("youtube.com", "youtu.be"),
                "tiktok": ("tiktok.com",),
                "instagram": ("instagram.com",),
            }[source]
            domain = source_domains[0]
            items = await web_batch(f"site:{domain} {query}", source, 24 if depth == "deep" else 14)
            items = [item for item in items if _matches_domains(item.get("url", ""), source_domains)]
            return source, items, "public-web"
        except Exception as exc:
            return source, [], f"temporarily-unavailable: {str(exc)[:140]}"

    results = await asyncio.gather(*(one(source) for source in sources))
    raw_findings = [finding for _, items, _ in results for finding in items]
    unique: dict[str, dict[str, Any]] = {}
    for finding in raw_findings:
        key = _finding_identity(finding)
        if key not in unique or finding.get("score", 0) > unique[key].get("score", 0):
            unique[key] = finding
    findings = sorted(unique.values(), key=lambda item: item["score"], reverse=True)
    statuses = {
        source: {
            "status": status,
            "results": len({_finding_identity(item) for item in items}),
            "queries": len(query_variants) if source == "web" and depth == "deep" else 1,
        }
        for source, items, status in results
    }
    return findings, statuses


def build_report(query: str, findings: list[dict[str, Any]], statuses: dict[str, Any]) -> str:
    ru = any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in query)
    if not findings:
        return (
            f"# Deep Research: {query}\n\n"
            + (
                "Orbit не смог получить результаты прямо сейчас. Попробуйте повторить исследование позже или изменить формулировку запроса. API-ключи от пользователя не требуются."
                if ru
                else "Orbit could not retrieve results right now. Try again later or rephrase the query. No user API keys are required."
            )
        )
    top = findings[:20]
    source_counts: dict[str, int] = {}
    for item in findings:
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1
    source_index = {_finding_identity(item): f"S{index}" for index, item in enumerate(top, 1)}
    if ru:
        lines = [
            f"# Deep Research: {query}", "", "## Резюме исследования",
            f"Orbit собрал {len(findings)} релевантных материалов из {len(source_counts)} типов источников.",
            "", "## Карта источников",
            *[f"- {source}: {count} материалов ({statuses[source]['status']})" for source, count in source_counts.items()],
            "", "## Матрица доказательств",
        ]
    else:
        lines = [
            f"# Deep Research: {query}", "", "## Research summary",
            f"Orbit collected {len(findings)} relevant items from {len(source_counts)} source types.",
            "", "## Source map",
            *[f"- {source}: {count} items ({statuses[source]['status']})" for source, count in source_counts.items()],
            "", "## Evidence matrix",
        ]
    for item in top:
        citation = source_index[_finding_identity(item)]
        lines.extend([
            f"### [{citation}] {item['title']}",
            item["snippet"] or ("Описание отсутствует." if ru else "No description available."),
            (f"Источник: [{item['source']}]({item['url']}) · релевантность {item['score']:.0%}" if ru else f"Source: [{item['source']}]({item['url']}) · relevance {item['score']:.0%}"),
            "",
        ])
    lines.extend([
        "## Ограничения" if ru else "## Limitations",
        "- Web-результат требует проверки первичного источника перед важным решением." if ru else "- Verify the primary source before making a consequential decision.",
        "- Публичный поиск по социальным платформам не показывает закрытые метрики." if ru else "- Public social search does not expose private metrics.",
        "", "## Источники" if ru else "## Sources",
        *[
            f"- [{source_index[_finding_identity(item)]}] [{item['title']}]({item['url']})"
            for item in top
        ],
    ])
    return "\n".join(lines)
