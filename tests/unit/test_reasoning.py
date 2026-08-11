import json
from types import SimpleNamespace

import pytest

from stockoutops.reasoning.deterministic_stub import DeterministicStubAdapter
from stockoutops.reasoning.openai_adapter import (
    INPUT_COST_PER_MILLION_USD,
    MAX_OUTPUT_TOKENS,
    MODEL_ID,
    OUTPUT_COST_PER_MILLION_USD,
    TIMEOUT_SECONDS,
    OpenAIResponsesAdapter,
)
from stockoutops.reasoning.schemas import validate_citations
from tests.unit.test_evidence import _bundle


class RecordingResponses:
    def __init__(self, output: dict[str, object]) -> None:
        self.request = None
        self.output = output
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        self.request = kwargs
        return SimpleNamespace(
            output_text=json.dumps(self.output),
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
        )


def test_deterministic_stub_is_reproducible_and_fully_cited() -> None:
    evidence = _bundle()
    first = DeterministicStubAdapter().reason(evidence)
    second = DeterministicStubAdapter().reason(evidence)
    assert first == second
    validate_citations(first.result, {item.evidence_id for item in evidence})
    assert first.result.root_cause_hypothesis.citations
    assert first.result.recommendation_draft.citations


def test_unknown_citation_fails_closed() -> None:
    result = DeterministicStubAdapter().reason(_bundle()).result
    result.recommendation_draft.citations = ["ev_" + "0" * 64]
    with pytest.raises(ValueError, match="unknown"):
        validate_citations(result, {item.evidence_id for item in _bundle()})


def test_openai_adapter_constructs_exact_bounded_request_without_network() -> None:
    expected = DeterministicStubAdapter().reason(_bundle()).result.model_dump(mode="json")
    responses = RecordingResponses(expected)
    adapter = OpenAIResponsesAdapter(SimpleNamespace(responses=responses))
    outcome = adapter.reason(_bundle())
    request = responses.request
    assert request["model"] == MODEL_ID == "gpt-4.1-mini-2025-04-14"
    assert request["store"] is False
    assert request["background"] is False
    assert request["stream"] is False
    assert request["tools"] == []
    assert request["max_output_tokens"] == MAX_OUTPUT_TOKENS == 1500
    assert request["timeout"] == TIMEOUT_SECONDS == 30.0
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["schema"]["additionalProperties"] is False
    assert (
        request["text"]["format"]["schema"]["properties"]["root_cause_hypothesis"][
            "additionalProperties"
        ]
        is False
    )
    assert (
        request["text"]["format"]["schema"]["properties"]["recommendation_draft"][
            "additionalProperties"
        ]
        is False
    )
    assert outcome.model_id == MODEL_ID
    assert (
        outcome.estimated_cost_usd
        == (100 * INPUT_COST_PER_MILLION_USD + 40 * OUTPUT_COST_PER_MILLION_USD) / 1_000_000
    )
    assert responses.calls == 1
