"""09 - Summarization: is the answer tight, or did it paste the chunks back?

The RAG prompt caps replies at 150 words. The common failure is dumping the
retrieved context nearly verbatim, which technically passes faithfulness and
still gives the user a wall of policy text.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from datasets.rag_goldens import RAG_GOLDENS


def build(judge):
    return GEval(
        name="Summarization Quality",
        criteria="Is the answer a concise summary rather than a context dump?",
        evaluation_steps=[
            "Check whether the actual output is meaningfully shorter and better "
            "organised than the retrieval context it came from.",
            "Check that it still carries the specific figures the question needed.",
            "Copying whole sentences verbatim from the context is acceptable in "
            "small amounts; reproducing most of a chunk is not.",
            "Award a HIGH score for a compact answer that keeps the key facts, a "
            "LOW score for a verbatim dump or for a summary that lost the numbers.",
        ],
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT,
                           SingleTurnParams.RETRIEVAL_CONTEXT],
        threshold=0.6, model=judge, async_mode=False,
    )


@pytest.mark.rag
@pytest.mark.geval
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_geval_summarization(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(input=golden.input, actual_output=r.answer,
                     retrieval_context=r.retrieval_context)
    assert_test(tc, [build(judge)])
