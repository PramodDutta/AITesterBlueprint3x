"""04 - Answer Relevancy: on-topic for the question that was asked?

A RAG system fails this in a distinctive way: it retrieves a chunk that is
adjacent to the question and then answers the chunk instead of the user.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

from datasets.rag_goldens import RAG_GOLDENS


@pytest.mark.rag
@pytest.mark.quality
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_answer_relevancy(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(input=golden.input, actual_output=r.answer)
    assert_test(tc, [AnswerRelevancyMetric(
        threshold=0.7, model=judge, include_reason=True, async_mode=False)])
