import asyncio
import json
from types import SimpleNamespace

from orchestrator import providers as providers_module
from orchestrator.providers import (
    AnthropicProvider,
    GeminiOAuthProvider,
    MockProvider,
    normalize_anthropic_history,
    parse_model_catalog,
)
from orchestrator.models import InteractionMode
from orchestrator.runtime import RuntimeManager
from orchestrator.config import get_settings
from orchestrator.network_security import validate_outbound_url


def test_parse_openai_model_catalog():
    models = parse_model_catalog(
        {
            "data": [
                {"id": "model-b", "owned_by": "provider"},
                {"id": "model-a", "name": "Model A", "context_length": 128000},
            ]
        }
    )
    assert [model["id"] for model in models] == ["model-a", "model-b"]
    assert models[0]["context_length"] == 128000


def test_parse_ollama_model_catalog():
    models = parse_model_catalog({"models": [{"name": "qwen:latest", "model": "qwen:latest"}]})
    assert models == [
        {
            "id": "qwen:latest",
            "name": "qwen:latest",
            "owner": None,
            "context_length": None,
        }
    ]


def test_constructive_review_distinguishes_certification_from_dissent():
    assert RuntimeManager._is_certification("СЕРТИФИКАЦИЯ: существенных возражений нет; проверены A, B, C")
    assert RuntimeManager._is_certification("No material objection. Checks: A, B, C")
    assert not RuntimeManager._is_certification("OBJECTION: the sample is too small and must be stress-tested")


def test_mock_provider_answers_latest_human_turn_instead_of_loop_guard():
    agent = SimpleNamespace(name="Priya Nair", role="On-Chain Scout", skill_name="On-Chain Researcher", model="mock-model")
    result = asyncio.run(
        MockProvider().complete(
            agent=agent,
            goal="Research the token",
            mode=InteractionMode.standard,
            messages=[
                {"role": "user", "content": "Find the holder concentration"},
                {"role": "assistant", "content": "Earlier answer"},
                {"role": "user", "content": "Your response repeats an earlier contribution. Produce new evidence."},
            ],
        )
    )
    assert "Demo mode" in result.content
    assert "Find the holder concentration" in result.content
    assert result.metadata["active_skill"] == "On-Chain Researcher"
    assert "Active skill" not in result.content


def test_production_outbound_url_guard_blocks_private_networks():
    settings = get_settings()
    previous = settings.app_env
    settings.app_env = "production"
    try:
        try:
            validate_outbound_url("http://127.0.0.1:11434/v1")
            assert False, "loopback endpoint must be blocked in production"
        except ValueError as error:
            assert "not allowed" in str(error)
    finally:
        settings.app_env = previous


def test_anthropic_history_moves_runtime_system_messages_and_preserves_tool_turns():
    system, messages = normalize_anthropic_history(
        [
            {"role": "system", "content": "MEMORY: prefer verified facts"},
            {"role": "user", "content": "Find the current status."},
            {
                "role": "assistant",
                "content": "I will query the source.",
                "tool_calls": [
                    {
                        "id": "call-status",
                        "function": {"name": "get_status", "arguments": '{"project":"orbit"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-status", "content": '{"state":"ready"}'},
            {"role": "system", "content": "ATTACHED FILE: project brief"},
            {"role": "user", "content": "Summarize it."},
        ],
        "Fallback goal",
    )

    assert system == ["MEMORY: prefer verified facts", "ATTACHED FILE: project brief"]
    assert [message["role"] for message in messages] == ["user", "assistant", "user"]
    assert all(message["role"] != "system" for message in messages)
    assert messages[1]["content"] == [
        {"type": "text", "text": "I will query the source."},
        {"type": "tool_use", "id": "call-status", "name": "get_status", "input": {"project": "orbit"}},
    ]
    assert messages[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "call-status", "content": '{"state":"ready"}'},
        {"type": "text", "text": "Summarize it."},
    ]


class _CapturedResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _CapturedAsyncClient:
    calls: list[dict] = []
    response_payload: dict = {}

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _CapturedResponse(self.response_payload)


def _provider_agent():
    return SimpleNamespace(
        model="test-model",
        system_prompt="You are a careful teammate.",
        role="Researcher",
        goal="Produce a useful result",
        skill_name=None,
        skill_description=None,
        skill_prompt=None,
        professional_memory="",
        tools=[
            {
                "type": "mcp",
                "connection_id": "tool-connection",
                "tools": [{"name": "search_sources", "description": "Search sources", "input_schema": {"type": "object"}}],
            }
        ],
    )


async def test_anthropic_provider_sends_embedded_system_context_at_top_level(monkeypatch):
    _CapturedAsyncClient.calls = []
    _CapturedAsyncClient.response_payload = {
        "content": [{"type": "text", "text": "Done"}],
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }
    monkeypatch.setattr(providers_module.httpx, "AsyncClient", _CapturedAsyncClient)
    connection = SimpleNamespace(base_url="https://anthropic.example/v1", api_key="dev-plain:key", config={})

    result = await AnthropicProvider(connection).complete(
        agent=_provider_agent(),
        goal="Team objective",
        mode=providers_module.InteractionMode.standard,
        messages=[
            {"role": "system", "content": "MEMORY: cite primary sources"},
            {"role": "user", "content": "Investigate this."},
        ],
    )

    assert result.content == "Done"
    payload = _CapturedAsyncClient.calls[0]["json"]
    assert "MEMORY: cite primary sources" in payload["system"]
    assert payload["messages"] == [{"role": "user", "content": "Investigate this."}]
    assert not any(tool["name"] == "search_sources" for tool in payload["tools"])
    # Native Robinhood Chain reads remain available; MCP is authorised by a workflow node.
    assert "chain_contract_audit" in {tool["name"] for tool in payload["tools"]}


async def test_gemini_provider_keeps_system_context_out_of_user_contents(monkeypatch):
    _CapturedAsyncClient.calls = []
    _CapturedAsyncClient.response_payload = {
        "candidates": [{"content": {"parts": [{"text": "Done"}]}}],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4},
    }

    async def fake_access_token(_credentials):
        return "google-access-token"

    monkeypatch.setattr(providers_module, "usable_google_access_token", fake_access_token)
    monkeypatch.setattr(providers_module.httpx, "AsyncClient", _CapturedAsyncClient)
    connection = SimpleNamespace(
        api_key="dev-plain:" + json.dumps({"refresh_token": "refresh"}),
        config={"project_id": "orbit-test-project"},
    )

    result = await GeminiOAuthProvider(connection).complete(
        agent=_provider_agent(),
        goal="Team objective",
        mode=providers_module.InteractionMode.standard,
        messages=[
            {"role": "system", "content": "MEMORY: cite primary sources"},
            {"role": "assistant", "content": "Earlier finding."},
            {"role": "user", "content": "Investigate this."},
        ],
    )

    assert result.content == "Done"
    payload = _CapturedAsyncClient.calls[0]["json"]
    assert "MEMORY: cite primary sources" in payload["systemInstruction"]["parts"][0]["text"]
    assert payload["contents"] == [
        {"role": "model", "parts": [{"text": "Earlier finding."}]},
        {"role": "user", "parts": [{"text": "Investigate this."}]},
    ]
