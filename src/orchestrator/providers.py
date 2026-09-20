from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from time import perf_counter
import json
from urllib.parse import urlsplit, urlunsplit

import httpx

from orchestrator import chain_tools
from orchestrator.models import Agent, InteractionMode, ProviderConnection
from orchestrator.security import secret_codec
from orchestrator.network_security import validate_outbound_url
from orchestrator.google_model_oauth import GEMINI_API, usable_google_access_token
from orchestrator.skill_catalog import default_adhd_instruction, enrich_skill_prompt


@dataclass(slots=True)
class ProviderResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micros: int = 0
    metadata: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class ProviderFailure:
    code: str
    message: str
    retryable: bool
    status_code: int | None = None


def normalize_provider_error(error: Exception) -> ProviderFailure:
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return ProviderFailure("provider_timeout", "The model provider timed out", True)
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {401, 403}:
            return ProviderFailure("provider_auth", "The provider rejected the API credentials", False, status)
        if status == 429:
            return ProviderFailure("provider_rate_limit", "The provider rate limit was reached", True, status)
        if status >= 500:
            return ProviderFailure("provider_unavailable", "The provider is temporarily unavailable", True, status)
        return ProviderFailure("provider_request", f"The provider rejected the request ({status})", False, status)
    if isinstance(error, httpx.NetworkError):
        return ProviderFailure("provider_network", "Could not reach the model provider", True)
    return ProviderFailure("provider_error", str(error)[:500] or "Provider call failed", False)


class ModelProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        *,
        agent: Agent,
        goal: str,
        mode: InteractionMode,
        messages: list[dict[str, str]],
    ) -> ProviderResult:
        raise NotImplementedError


def mode_instruction(mode: InteractionMode) -> str:
    if mode is InteractionMode.constructive:
        return (
            "Strict constructive mode: test assumptions, state meaningful risks directly, "
            "explain objections, and always propose a stronger alternative. Be respectful and actionable."
        )
    return (
        "Standard mode: collaborate professionally. Raise criticism only when it materially affects "
        "correctness, safety, cost, or the outcome."
    )


def skill_instruction(agent: Agent) -> str:
    parts = [default_adhd_instruction(getattr(agent, "adhd_skill_enabled", True) is not False)]
    if not agent.skill_name:
        return "".join(parts)
    purpose = f"\nPurpose: {agent.skill_description}" if agent.skill_description else ""
    prompt = enrich_skill_prompt(agent.skill_name, agent.skill_prompt)
    instructions = f"\nInstructions: {prompt}" if prompt else ""
    parts.append(f"\n\nGlobal agent skill: {agent.skill_name}{purpose}{instructions}")
    return "".join(parts)


def professional_memory_instruction(agent: Agent) -> str:
    if not agent.professional_memory.strip():
        return ""
    return (
        "\n\nYOUR PROFESSIONAL MEMORY:\n"
        f"{agent.professional_memory[-8000:]}\n"
        "Apply these lessons critically. Keep successful patterns, but revise a lesson when new evidence contradicts it."
    )


def collaboration_instruction() -> str:
    return (
        "COLLABORATION CONTRACT (highest priority): answer the latest human request directly and contribute "
        "only from your own role. Read the current-turn messages from teammates, explicitly answer any request "
        "addressed to you, and add new evidence, a decision, or a concrete correction instead of repeating them. "
        "Speak only as yourself: never impersonate, quote invented replies for, or simulate a conversation between "
        "other agents. Use @agent-slug only for one specific question or handoff that still needs an answer. "
        "Return only the polished user-facing contribution. Never expose hidden reasoning, a response outline, "
        "skill instructions, meta commentary, or phrases such as 'Acknowledge greeting' and 'Active skill'. "
        "For a greeting or a simple question, answer naturally and briefly; do not manufacture project work. "
        "LANGUAGE RULE: detect the language of the latest role=user human message and write the entire response "
        "in that language unless the human explicitly asks for another language."
    )


def calculate_cost(config: dict[str, Any], input_tokens: int, output_tokens: int) -> int:
    """Return micro-dollars using optional user-supplied pricing; unknown pricing stays zero."""
    input_rate = float(config.get("input_usd_per_million", 0) or 0)
    output_rate = float(config.get("output_usd_per_million", 0) or 0)
    return round(input_tokens * input_rate + output_tokens * output_rate)


def provider_tools(agent: Agent) -> list[dict[str, Any]]:
    # Robinhood Chain reads need no per-agent setup, so every agent can verify
    # a claim on-chain instead of asserting it from the prompt alone.
    # MCP belongs to the workflow that authorises and audits the tool call.
    # Legacy per-agent bindings are deliberately ignored: otherwise the same
    # agent silently gains external capabilities in every unrelated workflow.
    return list(chain_tools.tool_definitions())


def _text_content(value: Any) -> str:
    """Return a lossless-enough text representation for a provider text field."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text_parts = [str(item.get("text", "")) for item in value if isinstance(item, dict) and item.get("text")]
        if text_parts:
            return "\n".join(text_parts)
    if isinstance(value, dict) and value.get("text"):
        return str(value["text"])
    return json.dumps(value, ensure_ascii=False, default=str)


def _merge_provider_content(first: Any, second: Any) -> Any:
    """Join consecutive native messages without discarding text or content blocks."""
    if not first:
        return second
    if not second:
        return first
    if isinstance(first, str) and isinstance(second, str):
        return f"{first}\n\n{second}"

    def as_blocks(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [dict(item) if isinstance(item, dict) else {"type": "text", "text": str(item)} for item in value]
        return [{"type": "text", "text": _text_content(value)}]

    return [*as_blocks(first), *as_blocks(second)]


def _append_native_message(target: list[dict[str, Any]], role: str, content: Any) -> None:
    """Append an Anthropic/Gemini native turn, coalescing adjacent same-role turns."""
    if not content:
        return
    if target and target[-1]["role"] == role:
        target[-1]["content"] = _merge_provider_content(target[-1]["content"], content)
        return
    target.append({"role": role, "content": content})


def _openai_tool_calls_as_anthropic_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate the common OpenAI history representation when it is supplied to Anthropic."""
    blocks: list[dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        name = str(function.get("name") or call.get("name") or "")
        if not name:
            continue
        arguments = function.get("arguments", call.get("arguments", {}))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        blocks.append(
            {
                "type": "tool_use",
                "id": str(call.get("id") or f"tool_{name}"),
                "name": name,
                "input": arguments if isinstance(arguments, dict) else {},
            }
        )
    return blocks


def normalize_anthropic_history(
    messages: list[dict[str, Any]], fallback_user_content: str
) -> tuple[list[str], list[dict[str, Any]]]:
    """Split generic chat history into Anthropic's top-level system and native turns.

    Anthropic's Messages API accepts only ``user`` and ``assistant`` roles in
    ``messages``. Runtime context (memory, files, and research) is deliberately
    represented as ``system`` messages by the orchestrator, so it must be moved
    into the top-level system prompt rather than forwarded as an invalid turn.
    """
    system_parts: list[str] = []
    normalized: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user").lower()
        content = message.get("content")
        if role == "system":
            text = _text_content(content)
            if text:
                system_parts.append(text)
            continue

        if role == "assistant":
            tool_blocks = _openai_tool_calls_as_anthropic_blocks(message)
            if tool_blocks:
                content_blocks: list[dict[str, Any]] = []
                if content:
                    if isinstance(content, list):
                        content_blocks.extend(content)
                    else:
                        content_blocks.append({"type": "text", "text": _text_content(content)})
                content_blocks.extend(tool_blocks)
                _append_native_message(normalized, "assistant", content_blocks)
            else:
                _append_native_message(normalized, "assistant", content)
            continue

        if role == "tool":
            tool_use_id = message.get("tool_use_id") or message.get("tool_call_id")
            if tool_use_id:
                _append_native_message(
                    normalized,
                    "user",
                    [{"type": "tool_result", "tool_use_id": str(tool_use_id), "content": _text_content(content)}],
                )
            else:
                _append_native_message(normalized, "user", f"Tool result:\n{_text_content(content)}")
            continue

        # Native Anthropic has no developer/model/custom roles. Treat those as
        # user context instead of sending an invalid role and losing the turn.
        _append_native_message(normalized, "user", content)

    if not normalized:
        normalized.append({"role": "user", "content": fallback_user_content})
    return system_parts, normalized


def normalize_gemini_history(
    messages: list[dict[str, Any]], fallback_user_content: str
) -> tuple[list[str], list[dict[str, Any]]]:
    """Split generic history into Gemini system context and valid ``user``/``model`` turns."""
    system_parts: list[str] = []
    normalized: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user").lower()
        content = message.get("content")
        if role == "system":
            text = _text_content(content)
            if text:
                system_parts.append(text)
            continue
        # ``model`` is accepted when callers already use Gemini's vocabulary.
        native_role = "model" if role in {"assistant", "model"} else "user"
        _append_native_message(normalized, native_role, content)
    if not normalized:
        normalized.append({"role": "user", "content": fallback_user_content})
    return system_parts, normalized


def _gemini_parts(content: Any) -> list[dict[str, Any]]:
    """Convert generic text history into Gemini Parts without leaking foreign block shapes."""
    if isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                parts.append({"text": str(item)})
            elif "text" in item:
                parts.append({"text": str(item["text"])})
            elif "functionCall" in item:
                parts.append({"functionCall": item["functionCall"]})
            elif "functionResponse" in item:
                parts.append({"functionResponse": item["functionResponse"]})
            else:
                parts.append({"text": json.dumps(item, ensure_ascii=False, default=str)})
        if parts:
            return parts
    return [{"text": _text_content(content)}]


class MockProvider(ModelProvider):
    async def complete(
        self,
        *,
        agent: Agent,
        goal: str,
        mode: InteractionMode,
        messages: list[dict[str, str]],
    ) -> ProviderResult:
        # The mock provider is intentionally available for local/demo mode, but
        # it must still behave like a responsive conversation participant.  The
        # old implementation blindly used the last message; when the runtime
        # appended its anti-loop instruction that made the demo agent answer the
        # guard text and repeat the same template forever.  Prefer the latest
        # human turn and fall back to the objective.
        human_turns = [
            str(item.get("content", ""))
            for item in messages
            if item.get("role") == "user"
            and str(item.get("content", "")).strip()
            and not str(item.get("content", "")).startswith("Your response repeats an earlier contribution.")
        ]
        prior = human_turns[-1] if human_turns else goal
        russian = any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in prior)
        criticism = ""
        if mode is InteractionMode.constructive:
            criticism = (
                " Проверка: подтвердить ключевые допущения небольшим тестом."
                if russian else " Check: validate the key assumptions with a small test."
            )
        content = (
            f"Демо-режим: {agent.name} отвечает как {agent.role}. По запросу «{prior[:220]}» нужен "
            f"проверяемый вывод из моей специализации, а не повтор команды.{criticism}"
            if russian else
            f"Demo mode: {agent.name} is responding as {agent.role}. The request “{prior[:220]}” needs "
            f"a verifiable finding from my specialty, not a repetition of the team.{criticism}"
        )
        signal_contract_requested = any(
            "MACHINE-READABLE CONTRIBUTION CONTRACT" in str(item.get("content", ""))
            for item in messages
        )
        if signal_contract_requested:
            signal = {
                "stance": "neutral",
                "confidence": 25,
                "thesis": (
                    "Демо-модель сформировала направление работы, но не проверяла живые данные."
                    if russian else
                    "The demo model formed a work direction but did not verify live data."
                ),
                "evidence": [],
                "assumptions": [],
                "unknowns": [
                    "Живые инструменты и модель не подключены."
                    if russian else
                    "Live tools and a model are not connected."
                ],
                "blocking_risks": [],
                "invalidation_conditions": [],
                "expires_at": None,
            }
            content += "\n<orbit-signal>" + json.dumps(signal, ensure_ascii=False) + "</orbit-signal>"
        return ProviderResult(
            content=content,
            input_tokens=max(20, len(prior) // 4),
            output_tokens=max(30, len(content) // 4),
            metadata={"provider": "mock", "model": agent.model, "active_skill": agent.skill_name},
        )


class OpenAICompatibleProvider(ModelProvider):
    def __init__(self, connection: ProviderConnection) -> None:
        if not connection.base_url:
            raise ValueError("OpenAI-compatible connection requires base_url")
        validate_outbound_url(connection.base_url)
        self.base_url = connection.base_url.rstrip("/")
        self.api_key = secret_codec.decrypt(connection.api_key)
        self.config = connection.config

    async def complete(
        self,
        *,
        agent: Agent,
        goal: str,
        mode: InteractionMode,
        messages: list[dict[str, str]],
    ) -> ProviderResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": agent.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{agent.system_prompt}\n\nRole: {agent.role}\nGoal: {agent.goal}\n"
                        f"Team objective: {goal}\n{mode_instruction(mode)}{skill_instruction(agent)}"
                        f"{professional_memory_instruction(agent)}\n\n"
                        f"{collaboration_instruction()}"
                    ),
                },
                *messages,
            ],
            "stream": False,
            **self.config.get("request_defaults", {}),
        }
        tools = provider_tools(agent)
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
                for tool in tools
            ]
        timeout = float(self.config.get("timeout_seconds", 120))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        usage = data.get("usage") or {}
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        tool_calls = []
        tool_bindings = {tool["name"]: tool for tool in tools}
        for item in message.get("tool_calls") or []:
            function = item.get("function") or {}
            name = str(function.get("name", ""))
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except (TypeError, ValueError):
                arguments = {}
            if name:
                tool_calls.append({"id": item.get("id"), "name": name, "arguments": arguments, **tool_bindings.get(name, {})})
        input_tokens=int(usage.get("prompt_tokens", 0));output_tokens=int(usage.get("completion_tokens", 0))
        return ProviderResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_micros=calculate_cost(self.config, input_tokens, output_tokens),
            metadata={"provider": "openai-compatible", "model": agent.model},
            tool_calls=tool_calls,
        )


class AnthropicProvider(ModelProvider):
    def __init__(self, connection: ProviderConnection) -> None:
        endpoint = connection.base_url or "https://api.anthropic.com/v1"
        validate_outbound_url(endpoint)
        self.base_url = endpoint.rstrip("/")
        self.api_key = secret_codec.decrypt(connection.api_key)
        self.config = connection.config

    async def complete(self, *, agent: Agent, goal: str, mode: InteractionMode, messages: list[dict[str, str]]) -> ProviderResult:
        system = (
            f"{agent.system_prompt}\n\nRole: {agent.role}\nGoal: {agent.goal}\nTeam objective: {goal}\n"
            f"{mode_instruction(mode)}{skill_instruction(agent)}{professional_memory_instruction(agent)}\n\n"
            f"{collaboration_instruction()}"
        )
        embedded_system, native_messages = normalize_anthropic_history(messages, goal)
        if embedded_system:
            system += "\n\nADDITIONAL RUNTIME CONTEXT:\n" + "\n\n".join(embedded_system)
        tools = provider_tools(agent)
        body = {
            "model": agent.model,
            "max_tokens": int(self.config.get("max_tokens", 4096)),
            "system": system,
            "messages": native_messages,
        }
        if tools:
            body["tools"] = [{"name": tool["name"], "description": tool["description"], "input_schema": tool["input_schema"]} for tool in tools]
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            # Some Anthropic-compatible gateways protect their API hostname
            # with Cloudflare and block the default python-httpx user agent.
            # This remains an honest product identifier while using a broadly
            # accepted HTTP client prefix.
            "user-agent": "Mozilla/5.0 (compatible; OrbitAgent/1.0; +https://orbit-staging.95-169-201-238.nip.io)",
        }
        async with httpx.AsyncClient(timeout=float(self.config.get("timeout_seconds", 120))) as client:
            response = await client.post(f"{self.base_url}/messages", headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        tool_bindings = {tool["name"]: tool for tool in tools}
        tool_calls = [
            {"id": block.get("id"), "name": block.get("name"), "arguments": block.get("input") or {}, **tool_bindings.get(block.get("name"), {})}
            for block in data.get("content", []) if block.get("type") == "tool_use" and block.get("name")
        ]
        usage = data.get("usage") or {}
        input_tokens=int(usage.get("input_tokens", 0));output_tokens=int(usage.get("output_tokens", 0))
        return ProviderResult(content=text, input_tokens=input_tokens, output_tokens=output_tokens, cost_micros=calculate_cost(self.config, input_tokens, output_tokens), metadata={"provider": "anthropic", "model": agent.model}, tool_calls=tool_calls)


class GeminiOAuthProvider(ModelProvider):
    """Native Gemini provider authenticated with a Google user OAuth grant."""

    def __init__(self, connection: ProviderConnection) -> None:
        self.config = dict(connection.config or {})
        raw = secret_codec.decrypt(connection.api_key)
        if not raw:
            raise ValueError("Google OAuth credentials are missing")
        self.credentials = json.loads(raw)
        self.project_id = str(self.config.get("project_id") or "")
        if not self.project_id:
            raise ValueError("Google Cloud project ID is missing")

    async def complete(self, *, agent: Agent, goal: str, mode: InteractionMode, messages: list[dict[str, str]]) -> ProviderResult:
        access_token = await usable_google_access_token(self.credentials)
        if not access_token:
            raise ValueError("Google OAuth access expired; reconnect the Google account")
        system = (
            f"{agent.system_prompt}\n\nRole: {agent.role}\nGoal: {agent.goal}\nTeam objective: {goal}\n"
            f"{mode_instruction(mode)}{skill_instruction(agent)}{professional_memory_instruction(agent)}\n\n"
            f"{collaboration_instruction()}"
        )
        embedded_system, native_messages = normalize_gemini_history(messages, goal)
        if embedded_system:
            system += "\n\nADDITIONAL RUNTIME CONTEXT:\n" + "\n\n".join(embedded_system)
        contents = [
            {"role": message["role"], "parts": _gemini_parts(message["content"])}
            for message in native_messages
        ]
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
        }
        tools = provider_tools(agent)
        if tools:
            body["tools"] = [{"functionDeclarations": [{
                "name": tool["name"], "description": tool["description"], "parameters": tool["input_schema"]
            } for tool in tools]}]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "x-goog-user-project": self.project_id,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=float(self.config.get("timeout_seconds", 120))) as client:
            response = await client.post(
                f"{GEMINI_API}/v1beta/models/{agent.model}:generateContent", headers=headers, json=body
            )
            response.raise_for_status()
            data = response.json()
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "".join(str(part.get("text") or "") for part in parts)
        bindings = {tool["name"]: tool for tool in tools}
        tool_calls = []
        for part in parts:
            call = part.get("functionCall") or {}
            name = str(call.get("name") or "")
            if name:
                tool_calls.append({"name": name, "arguments": call.get("args") or {}, **bindings.get(name, {})})
        usage = data.get("usageMetadata") or {}
        input_tokens = int(usage.get("promptTokenCount", 0) or 0)
        output_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        return ProviderResult(
            content=text, input_tokens=input_tokens, output_tokens=output_tokens,
            cost_micros=calculate_cost(self.config, input_tokens, output_tokens),
            metadata={"provider": "gemini-oauth", "model": agent.model}, tool_calls=tool_calls,
        )


def provider_for(connection: ProviderConnection | None) -> ModelProvider:
    if connection is None or connection.provider == "mock":
        return MockProvider()
    if connection.provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleProvider(connection)
    if connection.provider == "anthropic":
        return AnthropicProvider(connection)
    if connection.provider == "gemini-oauth":
        return GeminiOAuthProvider(connection)
    raise ValueError(f"Unsupported provider: {connection.provider}")


def parse_model_catalog(data: Any) -> list[dict[str, Any]]:
    raw = data.get("data", data.get("models", [])) if isinstance(data, dict) else []
    models: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            models.append({"id": item, "name": item})
            continue
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("model") or item.get("name")
        if not model_id:
            continue
        models.append(
            {
                "id": str(model_id),
                "name": str(item.get("name") or model_id),
                "owner": item.get("owned_by") or item.get("owner"),
                "context_length": item.get("context_length") or item.get("context_window"),
            }
        )
    unique = {model["id"]: model for model in models}
    return sorted(unique.values(), key=lambda model: model["name"].lower())


def _endpoint_candidates(value: str) -> list[str]:
    """Build forgiving OpenAI-compatible base URL candidates.

    Small aggregators often document a host, a full /chat/completions URL, or
    an OpenAI-compatible path inconsistently. Discovery tries the safe common
    variants and returns the first endpoint that actually exposes /models.
    """
    raw = value.strip()
    if not raw:
        return []
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")
    suffixes = ("/chat/completions", "/completions", "/responses", "/models")
    for suffix in suffixes:
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    roots = [path]
    lowered = path.lower()
    if lowered.endswith("/v1"):
        roots.append(path[:-3].rstrip("/"))
    else:
        # Gateways frequently expose an /api root and put the OpenAI surface
        # below /api/v1. Keep the supplied path first, then probe the common
        # variants without forcing the user to know the vendor's convention.
        roots.extend([f"{path}/v1" if path else "/v1", f"{path}/openai/v1" if path else "/openai/v1", f"{path}/api/v1" if path else "/api/v1"])
    candidates: list[str] = []
    for root in roots:
        candidate = urlunsplit((parsed.scheme, parsed.netloc, root.rstrip("/"), "", ""))
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


async def discover_models_resolved(
    base_url: str, api_key: str | None
) -> tuple[list[dict[str, Any]], int, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = perf_counter()
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        last_error = ""
        for candidate in _endpoint_candidates(base_url):
            try:
                validate_outbound_url(candidate)
                response = await client.get(f"{candidate}/models", headers=headers)
            except Exception as exc:
                last_error = str(exc)
                continue
            if response.status_code in {401, 403}:
                raise ValueError("The API key was rejected. Revoke exposed keys and try a newly issued key.")
            if response.status_code == 429:
                raise ValueError("The provider rate limit was reached. Wait briefly and retry.")
            if response.status_code == 404:
                last_error = "not found"
                continue
            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                continue
            response.raise_for_status()
            models = parse_model_catalog(response.json())
            if models:
                return models, round((perf_counter() - started) * 1000), candidate
            last_error = "returned no models"
    raise ValueError(
        "Could not find a working OpenAI-compatible /models endpoint. "
        "Paste the provider host or base URL; Orbit tried common /v1, /openai/v1 and /api/v1 paths."
        + (f" Last response: {last_error}." if last_error else "")
    )


class _ModelDiscovery(tuple):
    """Two-value compatible result carrying the endpoint that actually worked."""

    base_url: str

    def __new__(cls, models: list[dict[str, Any]], latency_ms: int, base_url: str):
        value = super().__new__(cls, (models, latency_ms))
        value.base_url = base_url
        return value


async def discover_models(base_url: str, api_key: str | None) -> tuple[list[dict[str, Any]], int]:
    models, latency_ms, resolved_base_url = await discover_models_resolved(base_url, api_key)
    return _ModelDiscovery(models, latency_ms, resolved_base_url)


async def discover_anthropic_models(base_url: str, api_key: str) -> tuple[list[dict[str, Any]], int]:
    started = perf_counter()
    headers = {
        "Accept": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        data = response.json()
    models = parse_model_catalog(data)
    return models, round((perf_counter() - started) * 1000)


async def discover_tabitoken_models(base_url: str, api_key: str) -> tuple[list[dict[str, Any]], int]:
    """Return the complete TabiToken catalog available to this key.

    TabiToken exposes Anthropic-compatible messages, but its dashboard is based on
    New API and publishes the per-key catalog through the OpenAI-compatible
    ``/models`` route.  Older versions of Orbit only probed one known model and
    consequently made every TabiToken account look as if it had one model.
    """
    model = "claude-opus-4-8-thinking"
    started = perf_counter()
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "user-agent": "Mozilla/5.0 (compatible; OrbitAgent/1.0; +https://orbit-staging.95-169-201-238.nip.io)",
        # New API installations normally authenticate /models with Bearer while
        # the Anthropic messages route uses x-api-key. Sending both is harmless
        # and keeps discovery compatible with either gateway configuration.
        "authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "Reply OK"}],
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        catalog_response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        catalog_content_type = catalog_response.headers.get("content-type", "")
        if catalog_response.status_code == 200 and "json" in catalog_content_type:
            catalog = parse_model_catalog(catalog_response.json())
            if catalog:
                return catalog, round((perf_counter() - started) * 1000)
        if catalog_response.status_code == 403 and "text/html" in catalog_content_type:
            raise ValueError("TabiToken's Cloudflare protection blocked the server request. Retry shortly.")

        # Some TabiToken deployments do not expose /models. Keep a real Messages
        # request as a compatibility fallback instead of failing valid keys.
        response = await client.post(f"{base_url.rstrip('/')}/messages", headers=headers, json=body)
        content_type = response.headers.get("content-type", "")
        if response.status_code == 403 and "text/html" in content_type:
            raise ValueError("TabiToken's Cloudflare protection blocked the server request. Retry shortly.")
        if response.status_code in {401, 403}:
            raise ValueError("The TabiToken API key was rejected. Create a new key and try again.")
        if response.status_code == 429:
            raise ValueError("The TabiToken rate limit was reached. Wait briefly and retry.")
        response.raise_for_status()
    return [{"id": model, "name": model, "owner": "TabiToken", "context_length": None}], round(
        (perf_counter() - started) * 1000
    )
