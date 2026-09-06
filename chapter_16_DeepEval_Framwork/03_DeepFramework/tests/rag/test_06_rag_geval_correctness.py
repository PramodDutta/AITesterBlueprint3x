"""06 - Correctness (G-Eval): right facts, any wording.

The reference answers carry exact figures ($24.99, January 31, 3-5 business
days). The rubric lets the phrasing float and pins the numbers.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from datasets.rag_goldens import RAG_GOLDENS


def build(judge):
    return GEval(
        name="RAG Correctness",
        criteria="Is the actual output factually consistent with the expected output?",
        evaluation_steps=[
            "Compare every number, price, date and email address in the actual "
            "output against the expected output. A contradiction is a hard failure.",
            "Omitting a detail the expected output contains is a partial penalty.",
            "Different wording, ordering, markdown formatting and inline source "
            "citations are all acceptable. Do not penalise style.",
            "Award a HIGH score when the facts agree, a LOW score when they conflict.",
        ],
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT,
                           SingleTurnParams.EXPECTED_OUTPUT],
        threshold=0.7, model=judge, async_mode=False,
    )


@pytest.mark.rag
@pytest.mark.geval
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_geval_correctness(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(input=golden.input, actual_output=r.answer,
                     expected_output=golden.expected_output)
    assert_test(tc, [build(judge)])
