"""02 - Contextual Relevancy: how much of what we retrieved was on topic?

Precision asks about order, relevancy asks about noise. Pulling top_k=4 when
only one chunk matters still scores 1.0 on precision but poorly here, and
that wasted context is what you pay for on every single call.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import ContextualRelevancyMetric
from deepeval.test_case import LLMTestCase

from datasets.rag_goldens import RAG_GOLDENS


@pytest.mark.rag
@pytest.mark.retrieval
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_contextual_relevancy(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(
        input=golden.input,
        actual_output=r.answer,
        retrieval_context=r.retrieval_context,
    )
    assert_test(tc, [ContextualRelevancyMetric(
        threshold=0.5, model=judge, include_reason=True, async_mode=False)])
