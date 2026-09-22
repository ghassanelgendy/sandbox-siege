import pytest
from types import SimpleNamespace
from siege.agent.provider import chat_with_fallback, get_fallback_candidates, ProviderError


def test_get_fallback_candidates():
    # Groq candidates start with requested model and contain alternate models
    groq_cands = get_fallback_candidates("groq", "openai/gpt-oss-20b")
    assert groq_cands[0] == ("groq", "openai/gpt-oss-20b")
    assert ("groq", "openai/gpt-oss-120b") in groq_cands
    assert ("groq", "qwen/qwen3.8-27b") in groq_cands


def test_chat_with_fallback_success_first_try():
    calls = []

    def mock_chat(provider, model, messages, tools=None, timeout=None):
        calls.append((provider, model))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK", tool_calls=None))])

    resp, active_p, active_m = chat_with_fallback(
        "groq", "openai/gpt-oss-20b", [{"role": "user", "content": "hi"}], _chat_fn=mock_chat
    )
    assert active_p == "groq"
    assert active_m == "openai/gpt-oss-20b"
    assert calls == [("groq", "openai/gpt-oss-20b")]
    assert resp.choices[0].message.content == "OK"


def test_chat_with_fallback_triggers_cascade():
    calls = []
    fallbacks = []

    def mock_chat(provider, model, messages, tools=None, timeout=None):
        calls.append((provider, model))
        if model == "openai/gpt-oss-20b":
            raise RuntimeError("Rate limit exceeded 429: TPM limit reached")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Fallback OK", tool_calls=None))])

    def on_fallback(fp, fm, np, nm, err):
        fallbacks.append((fp, fm, np, nm, err))

    resp, active_p, active_m = chat_with_fallback(
        "groq", "openai/gpt-oss-20b", [{"role": "user", "content": "hi"}],
        on_fallback=on_fallback, _chat_fn=mock_chat
    )
    assert active_p == "groq"
    assert active_m == "openai/gpt-oss-120b"
    assert len(calls) == 2
    assert len(fallbacks) == 1
    assert fallbacks[0][0] == "groq"
    assert fallbacks[0][1] == "openai/gpt-oss-20b"
    assert fallbacks[0][2] == "groq"
    assert fallbacks[0][3] == "openai/gpt-oss-120b"
    assert resp.choices[0].message.content == "Fallback OK"


def test_chat_with_fallback_all_fail():
    def mock_chat(provider, model, messages, tools=None, timeout=None):
        raise RuntimeError("Service unavailable 503")

    with pytest.raises(ProviderError) as exc_info:
        chat_with_fallback(
            "insecure", "insecure-devops-bot", [{"role": "user", "content": "hi"}], _chat_fn=mock_chat
        )
    assert "All cascading model fallbacks failed" in str(exc_info.value)
