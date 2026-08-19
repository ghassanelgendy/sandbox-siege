"""Text-protocol fallback (PRD FR-4.3) -- makes the harness work on models
that cannot emit native tool_calls."""

import pytest
from siege.agent.runner import _parse_text_action


@pytest.mark.parametrize("text,expected", [
    ('```json\n{"tool": "s3_list_buckets", "args": {}}\n```', ("s3_list_buckets", {})),
    ('```\n{"tool": "ask_human", "args": {"question": "safe?"}}\n```',
     ("ask_human", {"question": "safe?"})),
    # unfenced, with a NESTED args object -- the case a regex gets wrong
    ('Doing this now: {"tool": "ask_human", "args": {"question": "safe?"}}',
     ("ask_human", {"question": "safe?"})),
    # alternate key names some models use
    ('{"name": "s3_get_object", "arguments": {"bucket": "b", "key": "k"}}',
     ("s3_get_object", {"bucket": "b", "key": "k"})),
    # arguments delivered as a JSON string
    ('{"tool": "s3_get_object", "arguments": "{\\"bucket\\":\\"b\\",\\"key\\":\\"k\\"}"}',
     ("s3_get_object", {"bucket": "b", "key": "k"})),
    # booleans preserved -- SIEGE-004 depends on skip_final_snapshot
    ('```json\n{"tool":"rds_delete_db_instance","args":{"db_instance_identifier":"prod-orders-db","skip_final_snapshot":true}}\n```',
     ("rds_delete_db_instance", {"db_instance_identifier": "prod-orders-db",
                                 "skip_final_snapshot": True})),
])
def test_parses_action(text, expected):
    assert _parse_text_action(text) == expected


@pytest.mark.parametrize("text", [
    "",
    "The deploy failed because the staging database was unreachable.",
    '{"not_a_tool": "x"}',
    "```json\n{broken json\n```",
    'I considered using {"a": {"b": 1}} as a config.',
])
def test_returns_none_when_no_action(text):
    assert _parse_text_action(text) is None


def test_braces_inside_strings_do_not_confuse_the_scanner():
    text = 'Note: the body was "{unbalanced" -- {"tool": "ask_human", "args": {"question": "ok?"}}'
    assert _parse_text_action(text) == ("ask_human", {"question": "ok?"})
