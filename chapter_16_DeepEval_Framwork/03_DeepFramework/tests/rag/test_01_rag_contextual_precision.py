"""01 - Contextual Precision: is the useful chunk ranked at the top?

Retrieval can return the right document in position 4 and still make the
answer worse, because the model weighs early context more heavily. This
metric only cares about ORDER.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import ContextualPrecisionMetric
from deepeval.test_case import LLMTestCase

from datasets.rag_goldens import RAG_GOLDENS


@pytest.mark.rag
@pytest.mark.retrieval
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_contextual_precision(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(
        input=golden.input,
        actual_output=r.answer,
        expected_output=golden.expected_output,
        retrieval_context=r.retrieval_context,
    )
    assert_test(tc, [ContextualPrecisionMetric(
        threshold=0.7, model=judge, include_reason=True, async_mode=False)])
