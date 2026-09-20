from __future__ import annotations

from orchestrator import verdict


def test_parses_a_plain_json_reply():
    parsed = verdict.parse_verdict(
        """{"verdict": "SKIP", "confidence": 82,
            "rationale": "Ownership is live and can mint.",
            "scores": {"research": 7, "audit": 2, "narrative": 5, "timing": 4},
            "blocking_risks": ["Owner can mint unlimited supply"],
            "conditions": ["Ownership renounced"],
            "evidence": ["chain_contract_audit: mint(address,uint256) present"]}"""
    )
    assert parsed["verdict"] == "SKIP"
    assert parsed["confidence"] == 82
    assert parsed["scores"] == {"research": 7, "audit": 2, "narrative": 5, "timing": 4}
    assert parsed["blocking_risks"] == ["Owner can mint unlimited supply"]
    assert parsed["extraction"] == "model"


def test_parses_json_wrapped_in_fences_and_prose():
    parsed = verdict.parse_verdict(
        'Here is the verdict:\n```json\n{"verdict": "enter", "scores": {"audit": 9}}\n```\nDone.'
    )
    assert parsed["verdict"] == "ENTER"
    assert parsed["scores"]["audit"] == 9


def test_braces_inside_strings_do_not_truncate_the_object():
    parsed = verdict.parse_verdict(
        '{"verdict": "WATCH", "rationale": "the crew wrote {nested} braces", "scores": {}}'
    )
    assert parsed["verdict"] == "WATCH"
    assert "{nested}" in parsed["rationale"]


def test_unassessed_dimensions_stay_unknown_instead_of_zero():
    parsed = verdict.parse_verdict('{"verdict": "WATCH", "scores": {"research": 6}}')
    assert parsed["scores"]["research"] == 6
    assert parsed["scores"]["audit"] is None
    assert parsed["scores"]["timing"] is None


def test_scores_are_clamped_and_junk_is_discarded():
    parsed = verdict.parse_verdict(
        '{"verdict": "ENTER", "scores": {"research": 42, "audit": -5, "narrative": "n/a", "timing": true}}'
    )
    assert parsed["scores"]["research"] == 10
    assert parsed["scores"]["audit"] == 0
    assert parsed["scores"]["narrative"] is None
    assert parsed["scores"]["timing"] is None


def test_lists_are_capped_and_blank_entries_dropped():
    parsed = verdict.parse_verdict(
        '{"verdict": "SKIP", "blocking_risks": ["a", "", "  ", "b", "c", "d", "e", "f", "g"]}'
    )
    assert parsed["blocking_risks"] == ["a", "b", "c", "d", "e", "f"]


def test_a_string_where_a_list_was_expected_is_accepted():
    parsed = verdict.parse_verdict('{"verdict": "SKIP", "conditions": "liquidity above 10 ETH"}')
    assert parsed["conditions"] == ["liquidity above 10 ETH"]


def test_unusable_replies_return_none_so_the_caller_can_fall_back():
    assert verdict.parse_verdict("no json here at all") is None
    assert verdict.parse_verdict('{"verdict": "MAYBE"}') is None
    assert verdict.parse_verdict('{"verdict": "ENTER"') is None
    assert verdict.parse_verdict("") is None


def test_heuristic_reads_the_closing_call_not_the_first_mention():
    text = (
        "Early on the narrative suggested we ENTER without checking anything.\n"
        "The auditor disagreed.\n"
        "Final call: SKIP."
    )
    fallback = verdict.heuristic_verdict(text)
    assert fallback["verdict"] == "SKIP"
    assert fallback["extraction"] == "heuristic"


def test_heuristic_ignores_a_negated_decision():
    fallback = verdict.heuristic_verdict("Given the mint function we do not ENTER here.")
    assert fallback["verdict"] != "ENTER"


def test_heuristic_leaves_unstated_scores_unknown():
    fallback = verdict.heuristic_verdict("Audit: 3/10. Everything else was not assessed. SKIP")
    assert fallback["scores"]["audit"] == 3
    assert fallback["scores"]["research"] is None
    assert fallback["scores"]["narrative"] is None


def test_heuristic_defaults_to_watch_when_nothing_is_declared():
    fallback = verdict.heuristic_verdict("The crew could not reach a conclusion.")
    assert fallback["verdict"] == "WATCH"
    assert fallback["confidence"] is None


def test_both_paths_agree_on_shape():
    model = verdict.parse_verdict('{"verdict": "ENTER"}')
    fallback = verdict.heuristic_verdict("ENTER")
    assert set(model) == set(fallback)
    assert set(model["scores"]) == set(verdict.DIMENSIONS)
