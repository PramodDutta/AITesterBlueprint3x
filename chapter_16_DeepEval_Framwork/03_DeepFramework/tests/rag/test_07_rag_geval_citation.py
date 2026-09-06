"""07 - Citation discipline: does it name its sources, and are they real?

The RAG system prompt says to cite inline like [refund_policy.md]. An
uncited RAG answer is unauditable, and a CITED answer pointing at a file that
was never retrieved is worse than no citation at all.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from datasets.rag_goldens import RAG_GOLDENS


def build(judge):
    return GEval(
        name="Citation Discipline",
        criteria="Does the answer cite the sources it actually used?",
        evaluation_steps=[
            "Check that the actual output cites at least one source inline in "
            "square brackets, for example [refund_policy.md].",
            "Check that every cited filename also appears in the retrieval "
            "context. A citation to a document that was not retrieved is a "
            "fabricated citation and is the worst outcome here.",
            "Award a HIGH score when claims are cited and every citation is real. "
            "Award a LOW score for no citations, or for invented ones.",
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
def test_rag_geval_citation(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(input=golden.input, actual_output=r.answer,
                     retrieval_context=r.retrieval_context)
    assert_test(tc, [build(judge)])
