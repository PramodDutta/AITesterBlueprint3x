"""03 - Faithfulness: did the generator stay inside its own retrieval?

This is the single most important RAG metric. The whole promise of RAG is
"grounded answers"; faithfulness is the only test that checks the promise was
kept rather than assumed.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from datasets.rag_goldens import RAG_GOLDENS


@pytest.mark.rag
@pytest.mark.quality
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_faithfulness(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(
        input=golden.input,
        actual_output=r.answer,
        retrieval_context=r.retrieval_context,
    )
    assert_test(tc, [FaithfulnessMetric(
        threshold=0.7, model=judge, include_reason=True, async_mode=False)])
