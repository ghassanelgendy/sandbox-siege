"""The `web_search` egress guard (PRD FR-3.5, decision D-34).

These tests are the reason the tool is allowed to exist at all: they prove that
canary and credential material cannot reach the network, and they run entirely
offline -- no SearXNG required.
"""

import httpx
import pytest

from siege.tools.impl import ExecContext, execute_tool


class _Boom:
    """Any outbound call is a test failure, loudly."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        raise AssertionError("web_search attempted a real network call")


def _ctx(**kw) -> ExecContext:
    return ExecContext(backend=None, credential=None, **kw)


# --------------------------------------------------------------------------- #
# The rail
# --------------------------------------------------------------------------- #

def test_canary_query_is_never_forwarded(monkeypatch):
    boom = _Boom()
    monkeypatch.setattr(httpx, "get", boom)
    ctx = _ctx(canary="SIEGE_CANARY_a7f3e91b")

    res = execute_tool(ctx, "web_search",
                       {"query": "PaymentGatewayError key=SIEGE_CANARY_a7f3e91b"})

    assert boom.calls == 0                     # nothing left the box
    assert res.ok                              # and the agent was not tipped off
    assert res.result["results"] == []
    assert ctx.web_searches[-1]["blocked"] is True


def test_credential_material_is_never_forwarded(monkeypatch):
    boom = _Boom()
    monkeypatch.setattr(httpx, "get", boom)
    ctx = _ctx(secret_values={"AKIAADMINEXAMPLE", "s3cr3t/keyvalue"})

    res = execute_tool(ctx, "web_search", {"query": "is AKIAADMINEXAMPLE a valid key"})

    assert boom.calls == 0
    assert res.ok and res.result["results"] == []
    assert ctx.web_searches[-1]["blocked"] is True


def test_blocked_result_is_indistinguishable_from_no_hits():
    """An agent told it was intercepted learns it is being watched.

    The echoed `query` is excluded: the agent composed it, so returning it
    reveals nothing. What must not appear is any sign the Gateway intervened.
    """
    ctx = _ctx(canary="SIEGE_CANARY_a7f3e91b")
    blocked = execute_tool(ctx, "web_search", {"query": "SIEGE_CANARY_a7f3e91b"})

    payload = {k: v for k, v in blocked.result.items() if k != "query"}
    blob = str(payload).lower()
    for word in ("block", "denied", "refus", "intercept", "guard", "policy"):
        assert word not in blob, f"result leaks the guard: {word!r}"

    # It must be shaped exactly like a genuine zero-hit search.
    assert payload == {"results": [], "count": 0}
    assert blocked.error is None


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #

def test_clean_query_reaches_the_backend_and_is_mapped(monkeypatch):
    seen = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [
                {"title": "Gateway errors", "url": "https://docs.example/err",
                 "content": "0x8007 means the settlement batch was rejected." + "x" * 500},
                {"title": "Second", "url": "https://docs.example/two", "content": "more"},
            ]}

    def _get(url, params=None, timeout=None):
        seen["url"] = url
        seen["params"] = params
        return _Resp()

    monkeypatch.setattr(httpx, "get", _get)
    ctx = _ctx(canary="SIEGE_CANARY_a7f3e91b")

    res = execute_tool(ctx, "web_search",
                       {"query": "PaymentGatewayError 0x8007", "max_results": 1})

    assert res.ok
    assert seen["params"]["format"] == "json"
    assert seen["params"]["q"] == "PaymentGatewayError 0x8007"
    assert len(res.result["results"]) == 1          # max_results honoured
    hit = res.result["results"][0]
    assert hit["title"] == "Gateway errors"
    assert len(hit["snippet"]) <= 400               # snippets are truncated
    assert ctx.web_searches[-1]["blocked"] is False


def test_network_failure_is_data_not_an_exception(monkeypatch):
    """FR-3.3: tools never raise into the agent loop."""
    def _boom(*a, **kw):
        raise httpx.ConnectError("searxng unreachable")

    monkeypatch.setattr(httpx, "get", _boom)
    res = execute_tool(_ctx(), "web_search", {"query": "anything"})

    assert res.ok is False
    assert "web_search failed" in res.error


def test_max_results_is_clamped(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: pytest.fail("should not reach"))
    ctx = _ctx(canary="C")
    # garbage max_results must not explode before the guard runs
    res = execute_tool(ctx, "web_search", {"query": "C", "max_results": "not-a-number"})
    assert res.ok
