from __future__ import annotations

import json
import re
from typing import Any

import httpx


MAX_RECORDS = 500
MAX_CONTENT_CHARS = 120_000
NOTION_VERSION = "2026-03-11"
BITQUERY_GRAPHQL_URL = "https://streaming.bitquery.io/graphql"
BLOCKSCOUT_API_URL = "https://robinhoodchain.blockscout.com/api/v2"
_EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

CONNECTOR_CATALOG: dict[str, dict[str, Any]] = {
    "notion": {"name": "Notion", "base_url": "https://api.notion.com", "credential_label": "OAuth or integration token", "needs_identifier": False, "oauth": True},
    "slack": {"name": "Slack", "base_url": "https://slack.com/api", "credential_label": "OAuth token", "needs_identifier": False, "oauth": True},
    "google-drive": {"name": "Google Drive", "base_url": "https://www.googleapis.com/drive/v3", "credential_label": "Google OAuth", "needs_identifier": False, "oauth": True},
    "telegram": {"name": "Telegram", "base_url": "https://api.telegram.org", "credential_label": "Bot token", "needs_identifier": False, "oauth": False},
    "youtube": {"name": "YouTube", "base_url": "https://www.googleapis.com/youtube/v3", "credential_label": "Google OAuth or API key", "needs_identifier": True, "oauth": True},
    "bitquery": {
        "name": "Bitquery",
        "base_url": BITQUERY_GRAPHQL_URL,
        "credential_label": "Bitquery API key",
        "needs_identifier": True,
        "oauth": False,
    },
    "blockscout": {
        "name": "Blockscout",
        "base_url": BLOCKSCOUT_API_URL,
        "credential_label": "Blockscout API key (optional for the public Robinhood Chain endpoint)",
        "credential_required": False,
        "needs_identifier": True,
        "oauth": False,
    },
}


def connector_preset(connector: str) -> dict[str, Any]:
    preset = CONNECTOR_CATALOG.get(connector)
    if not preset:
        raise ValueError("Unsupported connector")
    return preset


def _json(response: httpx.Response, service: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError(f"{service} returned an invalid response") from exc
    if response.is_error:
        error = data.get("error") or data.get("message") or response.reason_phrase
        if isinstance(error, dict):
            error = error.get("message") or error.get("status") or "request rejected"
        raise ValueError(f"{service}: {error}")
    return data


def _plain_text(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "".join(str(item.get("plain_text") or "") for item in values if isinstance(item, dict)).strip()


def _notion_title(item: dict[str, Any]) -> str:
    properties = item.get("properties") or {}
    for value in properties.values():
        if isinstance(value, dict) and value.get("type") == "title":
            title = _plain_text(value.get("title"))
            if title:
                return title
    return str(item.get("url") or item.get("id") or "Untitled")


def _notion_block_text(block: dict[str, Any]) -> str:
    kind = str(block.get("type") or "")
    value = block.get(kind)
    if not isinstance(value, dict):
        return ""
    text = _plain_text(value.get("rich_text") or value.get("caption"))
    if kind == "to_do" and text:
        return f"[{'x' if value.get('checked') else ' '}] {text}"
    if kind.startswith("heading_") and text:
        return f"{'#' * int(kind[-1])} {text}"
    if kind in {"bulleted_list_item", "numbered_list_item"} and text:
        return f"- {text}"
    return text


async def _notion_children(client: httpx.AsyncClient, headers: dict[str, str], block_id: str, depth: int = 0) -> list[str]:
    if depth > 3:
        return []
    cursor: str | None = None
    lines: list[str] = []
    while len(lines) < 300:
        params: dict[str, Any] = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        data = _json(await client.get(f"https://api.notion.com/v1/blocks/{block_id}/children", headers=headers, params=params), "Notion")
        for block in data.get("results") or []:
            text = _notion_block_text(block)
            if text:
                lines.append(text)
            if block.get("has_children"):
                lines.extend(await _notion_children(client, headers, str(block["id"]), depth + 1))
        cursor = data.get("next_cursor") if data.get("has_more") else None
        if not cursor:
            break
    return lines


async def _fetch_notion(client: httpx.AsyncClient, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    profile = _json(await client.get("https://api.notion.com/v1/users/me", headers=headers), "Notion")
    cursor: str | None = None
    records: list[dict[str, Any]] = []
    while len(records) < MAX_RECORDS:
        body: dict[str, Any] = {"page_size": 100, "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
        if cursor:
            body["start_cursor"] = cursor
        data = _json(await client.post("https://api.notion.com/v1/search", headers=headers, json=body), "Notion")
        for item in data.get("results") or []:
            if item.get("object") != "page":
                continue
            lines = await _notion_children(client, headers, str(item["id"]))
            records.append({"id": item.get("id"), "title": _notion_title(item), "url": item.get("url"), "updated_at": item.get("last_edited_time"), "content": "\n".join(lines)[:20_000]})
            if len(records) >= MAX_RECORDS:
                break
        cursor = data.get("next_cursor") if data.get("has_more") else None
        if not cursor:
            break
    owner = profile.get("bot", {}).get("owner", {})
    label = profile.get("name") or ("Notion workspace" if owner.get("workspace") else "Notion")
    return {"label": str(label), "records": records, "summary": "Pages and readable block content shared with Orbit.", "cursor": cursor, "has_more": bool(cursor), "details": {"bot_id": profile.get("id"), "pages": len(records)}}


async def _slack_pages(client: httpx.AsyncClient, headers: dict[str, str], method: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = ""
    while len(results) < MAX_RECORDS:
        page_params = {**params, "limit": 100}
        if cursor:
            page_params["cursor"] = cursor
        data = _json(await client.get(f"https://slack.com/api/{method}", headers=headers, params=page_params), "Slack")
        if not data.get("ok"):
            raise ValueError(f"Slack: {data.get('error', 'request failed')}")
        results.extend(data.get("channels") or data.get("messages") or [])
        cursor = str((data.get("response_metadata") or {}).get("next_cursor") or "")
        if not cursor:
            break
    return results[:MAX_RECORDS]


async def _fetch_slack(client: httpx.AsyncClient, token: str, since: str | None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    auth = _json(await client.post("https://slack.com/api/auth.test", headers=headers), "Slack")
    if not auth.get("ok"):
        raise ValueError(f"Slack: {auth.get('error', 'authentication failed')}")
    channels = await _slack_pages(client, headers, "conversations.list", {"exclude_archived": "true", "types": "public_channel,private_channel"})
    records: list[dict[str, Any]] = []
    newest = since or "0"
    warnings: list[str] = []
    for channel in channels[:50]:
        try:
            messages = await _slack_pages(client, headers, "conversations.history", {"channel": channel["id"], "oldest": since or "0", "inclusive": "false", "limit": 15})
        except ValueError as exc:
            warnings.append(f"#{channel.get('name')}: {exc}")
            continue
        for message in messages:
            text = str(message.get("text") or "").strip()
            if text:
                ts = str(message.get("ts") or "0")
                newest = max(newest, ts, key=lambda value: float(value or 0))
                records.append({"id": f"{channel['id']}:{ts}", "title": f"#{channel.get('name', channel['id'])}", "updated_at": ts, "content": text[:6000], "user": message.get("user")})
    return {"label": str(auth.get("team") or "Slack workspace"), "records": records[:MAX_RECORDS], "summary": "Messages from channels visible to the installed Slack app.", "cursor": newest, "has_more": False, "details": {"team_id": auth.get("team_id"), "user_id": auth.get("user_id"), "channels": len(channels), "warnings": warnings[:10]}}


async def _fetch_drive(client: httpx.AsyncClient, token: str, page_token: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    about = _json(await client.get("https://www.googleapis.com/drive/v3/about", headers=headers, params={"fields": "user(displayName,emailAddress)"}), "Google Drive")
    records: list[dict[str, Any]] = []
    cursor = page_token
    next_cursor: str | None = None
    while len(records) < MAX_RECORDS:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "modifiedTime desc", "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,size)", "q": "trashed = false"}
        if cursor:
            params["pageToken"] = cursor
        data = _json(await client.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=params), "Google Drive")
        for item in data.get("files") or []:
            content = ""
            mime = str(item.get("mimeType") or "")
            try:
                if mime == "application/vnd.google-apps.document":
                    response = await client.get(f"https://www.googleapis.com/drive/v3/files/{item['id']}/export", headers=headers, params={"mimeType": "text/plain"})
                    if not response.is_error:
                        content = response.text[:30_000]
                elif mime.startswith("text/") or mime in {"application/json", "application/xml"}:
                    response = await client.get(f"https://www.googleapis.com/drive/v3/files/{item['id']}", headers=headers, params={"alt": "media"})
                    if not response.is_error:
                        content = response.text[:30_000]
            except httpx.HTTPError:
                content = ""
            records.append({**{key: item.get(key) for key in ("id", "name", "mimeType", "modifiedTime", "webViewLink", "size")}, "title": item.get("name"), "updated_at": item.get("modifiedTime"), "content": content})
        next_cursor = data.get("nextPageToken")
        if not next_cursor:
            break
        cursor = next_cursor
    user = about.get("user", {})
    return {"label": str(user.get("displayName") or user.get("emailAddress") or "Google Drive"), "records": records, "summary": "Drive files with exported text for readable documents.", "cursor": next_cursor, "has_more": bool(next_cursor), "details": {"email": user.get("emailAddress"), "files": len(records), "content_files": sum(bool(item.get("content")) for item in records)}}


def telegram_record(update: dict[str, Any]) -> dict[str, Any] | None:
    message = update.get("message") or update.get("edited_message") or update.get("channel_post") or update.get("edited_channel_post")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    content = str(message.get("text") or message.get("caption") or "").strip()
    if not content:
        return None
    return {"id": str(update.get("update_id")), "title": str(chat.get("title") or chat.get("username") or chat.get("id") or "Telegram"), "updated_at": message.get("date"), "content": content[:6000], "author": sender.get("username") or sender.get("first_name"), "chat_id": chat.get("id")}


async def _fetch_telegram(client: httpx.AsyncClient, token: str, offset: int | None) -> dict[str, Any]:
    base = f"https://api.telegram.org/bot{token}"
    profile = _json(await client.get(f"{base}/getMe"), "Telegram")
    if not profile.get("ok"):
        raise ValueError(f"Telegram: {profile.get('description', 'authentication failed')}")
    webhook = _json(await client.get(f"{base}/getWebhookInfo"), "Telegram")
    records: list[dict[str, Any]] = []
    newest = offset or 0
    if not (webhook.get("result") or {}).get("url"):
        params: dict[str, Any] = {"limit": 100, "timeout": 0, "allowed_updates": json.dumps(["message", "edited_message", "channel_post", "edited_channel_post"])}
        if offset is not None:
            params["offset"] = offset
        updates = _json(await client.get(f"{base}/getUpdates", params=params), "Telegram")
        if not updates.get("ok"):
            raise ValueError(f"Telegram: {updates.get('description', 'getUpdates failed')}")
        for update in updates.get("result") or []:
            newest = max(newest, int(update.get("update_id") or 0) + 1)
            record = telegram_record(update)
            if record:
                records.append(record)
    bot = profile.get("result", {})
    return {"label": f"@{bot.get('username', 'telegram_bot')}", "records": records, "summary": "New messages delivered to this bot after it was connected; Telegram Bot API cannot import earlier chat history.", "cursor": newest, "has_more": False, "details": {"bot_id": bot.get("id"), "username": bot.get("username"), "webhook_active": bool((webhook.get("result") or {}).get("url")), "pending_updates": (webhook.get("result") or {}).get("pending_update_count", 0)}}


async def _fetch_youtube(client: httpx.AsyncClient, credential: str, identifier: str | None, oauth: bool) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {credential}"} if oauth else {}
    auth_params = {} if oauth else {"key": credential}
    channel_params: dict[str, Any] = {**auth_params, "part": "snippet,statistics,contentDetails"}
    if oauth and not identifier:
        channel_params["mine"] = "true"
    elif identifier:
        channel_params["forHandle"] = identifier.lstrip("@")
    else:
        raise ValueError("YouTube channel handle is required for API-key connections")
    channel_data = _json(await client.get("https://www.googleapis.com/youtube/v3/channels", headers=headers, params=channel_params), "YouTube")
    channels = channel_data.get("items") or []
    if not channels:
        raise ValueError("YouTube channel was not found")
    channel = channels[0]
    playlist = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    records: list[dict[str, Any]] = []
    page_token: str | None = None
    while playlist and len(records) < MAX_RECORDS:
        params = {**auth_params, "part": "snippet,contentDetails", "playlistId": playlist, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        data = _json(await client.get("https://www.googleapis.com/youtube/v3/playlistItems", headers=headers, params=params), "YouTube")
        for item in data.get("items") or []:
            snippet = item.get("snippet") or {}
            records.append({"id": (item.get("contentDetails") or {}).get("videoId"), "title": snippet.get("title"), "updated_at": snippet.get("publishedAt"), "url": f"https://youtube.com/watch?v={(item.get('contentDetails') or {}).get('videoId')}", "content": str(snippet.get("description") or "")[:12_000]})
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    snippet = channel.get("snippet") or {}
    return {"label": str(snippet.get("title") or identifier or "YouTube"), "records": records, "summary": "Channel profile and paginated upload titles and descriptions.", "cursor": page_token, "has_more": bool(page_token), "details": {"channel_id": channel.get("id"), "description": str(snippet.get("description") or "")[:3000], "statistics": channel.get("statistics") or {}, "uploads_playlist": playlist}}


def _evm_address(value: str, label: str = "EVM address") -> str:
    address = value.strip()
    if not _EVM_ADDRESS_RE.fullmatch(address):
        raise ValueError(f"{label} must be a 0x-prefixed, 40-character hexadecimal address")
    return address.lower()


def _bitquery_target(identifier: str | None) -> tuple[str, str]:
    value = (identifier or "").strip()
    if not value:
        raise ValueError("Bitquery requires token:0x… or wallet:0x…")
    kind, separator, address = value.partition(":")
    if not separator:
        return "token", _evm_address(value, "Token address")
    if kind not in {"token", "wallet"}:
        raise ValueError("Bitquery target must start with token: or wallet:")
    return kind, _evm_address(address, f"Bitquery {kind} address")


def _graphql_data(response: httpx.Response, service: str) -> dict[str, Any]:
    payload = _json(response, service)
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        raise ValueError(f"{service}: {str(first.get('message') or 'query rejected')[:300]}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"{service} returned no data")
    return data


def _short_address(address: str) -> str:
    return f"{address[:8]}…{address[-6:]}"


BITQUERY_DEX_TRADES_QUERY = """
query TokenDexTrades($token: String!, $since: DateTime) {
  EVM(network: robinhood, dataset: combined) {
    DEXTrades(
      limit: { count: 100 }
      orderBy: { descending: Block_Time }
      where: {
        Trade: { Buy: { Currency: { SmartContract: { is: $token } } } }
        Block: { Time: { since: $since } }
      }
    ) {
      Block { Number Time }
      Transaction { Hash From }
      Trade {
        Dex { ProtocolName ProtocolFamily SmartContract }
        Buy { Amount AmountInUSD PriceInUSD Currency { Name Symbol SmartContract } }
        Sell { Amount AmountInUSD PriceInUSD Currency { Name Symbol SmartContract } }
      }
    }
  }
}
"""


BITQUERY_WALLET_BALANCES_QUERY = """
query WalletBalances($address: String!) {
  EVM(network: robinhood, dataset: combined) {
    Balances(
      limit: { count: 100 }
      orderBy: { descending: Balance_Amount }
      where: { Balance: { Address: { is: $address } } }
    ) {
      Currency { Name Symbol SmartContract Decimals }
      Balance { Amount }
    }
  }
}
"""


async def get_dex_trades(
    client: httpx.AsyncClient, token: str, since: str | None, api_key: str
) -> list[dict[str, Any]]:
    """Return recent DEX swaps for a token through Bitquery's direct GraphQL API."""
    response = await client.post(
        BITQUERY_GRAPHQL_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={
            "query": BITQUERY_DEX_TRADES_QUERY,
            "variables": {"token": token, "since": since},
        },
    )
    data = _graphql_data(response, "Bitquery")
    trades = ((data.get("EVM") or {}).get("DEXTrades") or [])
    records: list[dict[str, Any]] = []
    for item in trades[:100]:
        if not isinstance(item, dict):
            continue
        trade = item.get("Trade") or {}
        buy, sell = trade.get("Buy") or {}, trade.get("Sell") or {}
        buy_currency, sell_currency = buy.get("Currency") or {}, sell.get("Currency") or {}
        block = item.get("Block") or {}
        transaction = item.get("Transaction") or {}
        dex = trade.get("Dex") or {}
        timestamp = str(block.get("Time") or "")
        transaction_hash = str(transaction.get("Hash") or "")
        buy_symbol = str(buy_currency.get("Symbol") or "token")
        sell_symbol = str(sell_currency.get("Symbol") or "asset")
        records.append(
            {
                "id": transaction_hash or f"{timestamp}:{len(records)}",
                "title": f"DEX trade · {buy_symbol}/{sell_symbol}",
                "updated_at": timestamp,
                "content": "\n".join(
                    part
                    for part in [
                        f"Time: {timestamp}" if timestamp else "",
                        f"DEX: {dex.get('ProtocolName') or dex.get('ProtocolFamily') or 'unknown'}",
                        f"Buy: {buy.get('Amount') or '—'} {buy_symbol} (${buy.get('AmountInUSD') or '—'})",
                        f"Sell: {sell.get('Amount') or '—'} {sell_symbol} (${sell.get('AmountInUSD') or '—'})",
                        f"Price USD: {buy.get('PriceInUSD') or sell.get('PriceInUSD') or '—'}",
                        f"Sender: {transaction.get('From')}" if transaction.get("From") else "",
                        f"Transaction: {transaction_hash}" if transaction_hash else "",
                    ]
                    if part
                ),
            }
        )
    return records


async def get_wallet_balances(
    client: httpx.AsyncClient, address: str, api_key: str
) -> list[dict[str, Any]]:
    """Return token balances for a wallet through Bitquery's direct GraphQL API."""
    response = await client.post(
        BITQUERY_GRAPHQL_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={
            "query": BITQUERY_WALLET_BALANCES_QUERY,
            "variables": {"address": address},
        },
    )
    data = _graphql_data(response, "Bitquery")
    balances = ((data.get("EVM") or {}).get("Balances") or [])
    records: list[dict[str, Any]] = []
    for item in balances[:100]:
        if not isinstance(item, dict):
            continue
        currency = item.get("Currency") or {}
        symbol = str(currency.get("Symbol") or "asset")
        contract = str(currency.get("SmartContract") or "native asset")
        balance = (item.get("Balance") or {}).get("Amount")
        records.append(
            {
                "id": f"{address}:{contract}",
                "title": f"Wallet balance · {symbol}",
                "content": f"Wallet: {address}\nBalance: {balance if balance is not None else '—'} {symbol}\nAsset: {currency.get('Name') or symbol}\nContract: {contract}",
            }
        )
    return records


async def get_token_holders(
    client: httpx.AsyncClient, address: str, api_key: str
) -> list[dict[str, Any]]:
    """Return the first holders page from Blockscout's direct REST API."""
    headers = {"X-API-KEY": api_key} if api_key else {}
    params = {"apikey": api_key} if api_key else None
    data = _json(
        await client.get(
            f"{BLOCKSCOUT_API_URL}/tokens/{address}/holders",
            headers=headers,
            params=params,
        ),
        "Blockscout",
    )
    holders = data.get("items") or []
    records: list[dict[str, Any]] = []
    for item in holders[:100]:
        if not isinstance(item, dict):
            continue
        holder = item.get("address_hash") or item.get("address") or {}
        holder_address = holder.get("hash") if isinstance(holder, dict) else holder
        holder_address = str(holder_address or "unknown")
        records.append(
            {
                "id": holder_address,
                "title": f"Token holder · {_short_address(holder_address) if _EVM_ADDRESS_RE.fullmatch(holder_address) else holder_address}",
                "content": "\n".join(
                    part
                    for part in [
                        f"Token: {address}",
                        f"Holder: {holder_address}",
                        f"Balance (raw units): {item.get('value') or '—'}",
                        "Contract address" if isinstance(holder, dict) and holder.get("is_contract") else "",
                        f"Label: {holder.get('name')}" if isinstance(holder, dict) and holder.get("name") else "",
                    ]
                    if part
                ),
            }
        )
    return records


async def _fetch_bitquery(
    client: httpx.AsyncClient, api_key: str, identifier: str | None, since: str | None
) -> dict[str, Any]:
    target_type, address = _bitquery_target(identifier)
    if target_type == "wallet":
        records = await get_wallet_balances(client, address, api_key)
        return {
            "label": f"Wallet {_short_address(address)}",
            "records": records,
            "summary": "Current token balances from the Bitquery EVM API.",
            "cursor": None,
            "has_more": False,
            "details": {"target_type": target_type, "address": address, "balances": len(records)},
        }
    records = await get_dex_trades(client, address, since, api_key)
    timestamps = [str(item.get("updated_at")) for item in records if item.get("updated_at")]
    return {
        "label": f"Token {_short_address(address)}",
        "records": records,
        "summary": "Recent token DEX trades from the Bitquery EVM API.",
        "cursor": max(timestamps) if timestamps else since,
        "has_more": False,
        "details": {"target_type": target_type, "address": address, "trades": len(records)},
    }


async def _fetch_blockscout(
    client: httpx.AsyncClient, api_key: str, identifier: str | None
) -> dict[str, Any]:
    address = _evm_address(identifier or "", "Blockscout token address")
    records = await get_token_holders(client, address, api_key)
    return {
        "label": f"Token {_short_address(address)}",
        "records": records,
        "summary": "Token-holder snapshot from the Blockscout EVM API.",
        "cursor": None,
        "has_more": False,
        "details": {"token_address": address, "holders": len(records)},
    }


async def fetch_context_connector(connector: str, credential: str, identifier: str | None = None, *, cursor: Any = None, oauth: bool = False) -> dict[str, Any]:
    connector_preset(connector)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False) as client:
        if connector == "notion":
            result = await _fetch_notion(client, credential)
        elif connector == "slack":
            result = await _fetch_slack(client, credential, str(cursor) if cursor else None)
        elif connector == "google-drive":
            result = await _fetch_drive(client, credential)
        elif connector == "telegram":
            result = await _fetch_telegram(client, credential, int(cursor) if cursor is not None else None)
        elif connector == "bitquery":
            result = await _fetch_bitquery(client, credential, identifier, str(cursor) if cursor else None)
        elif connector == "blockscout":
            result = await _fetch_blockscout(client, credential, identifier)
        else:
            result = await _fetch_youtube(client, credential, identifier, oauth)
    result["item_count"] = len(result.get("records") or [])
    result["content_bytes"] = sum(len(str(item.get("content") or "").encode("utf-8")) for item in result.get("records") or [])
    return result


def connector_memory_markdown(connector: str, result: dict[str, Any]) -> str:
    preset = connector_preset(connector)
    lines = [f"<!-- source:connector-{connector} -->", f"## Connected source: {preset['name']}", f"- Account: {result['label']}", f"- Synced items: {result.get('item_count', 0)}", f"- Context: {result['summary']}"]
    details = result.get("details") or {}
    if connector == "telegram":
        lines.append("- Limitation: only updates received after the bot was connected are available; historical chats cannot be imported through Bot API.")
    if details.get("warnings"):
        lines.append(f"- Warnings: {'; '.join(map(str, details['warnings'][:5]))}")
    remaining = MAX_CONTENT_CHARS
    for record in result.get("records") or []:
        content = " ".join(str(record.get("content") or "").split())
        if not content:
            continue
        text = content[:6000]
        row = f"\n### {record.get('title') or 'Untitled'}\n{text}"
        if len(row) > remaining:
            break
        lines.append(row)
        remaining -= len(row)
    lines.append(f"<!-- /source:connector-{connector} -->")
    return "\n".join(lines)


async def configure_telegram_webhook(token: str, url: str, secret: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        data = _json(await client.post(f"https://api.telegram.org/bot{token}/setWebhook", json={"url": url, "secret_token": secret, "allowed_updates": ["message", "edited_message", "channel_post", "edited_channel_post"]}), "Telegram")
        if not data.get("ok"):
            raise ValueError(f"Telegram: {data.get('description', 'setWebhook failed')}")


async def remove_telegram_webhook(token: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(f"https://api.telegram.org/bot{token}/deleteWebhook", json={"drop_pending_updates": False})
