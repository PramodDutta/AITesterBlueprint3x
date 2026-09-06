"""05 - Hallucination: does the answer contradict the reference facts?

Scored against the golden answer, not against what was retrieved. That is the
difference from test_03: a RAG system can be perfectly faithful to a chunk it
should never have retrieved, and only this test notices.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import HallucinationMetric
from deepeval.test_case import LLMTestCase

from datasets.rag_goldens import RAG_GOLDENS


@pytest.mark.rag
@pytest.mark.quality
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_hallucination(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(
        input=golden.input,
        actual_output=r.answer,
        context=[golden.expected_output],
    )
    assert_test(tc, [HallucinationMetric(
        threshold=0.7, model=judge, include_reason=True, async_mode=False)])
