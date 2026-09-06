"""11 - Helpfulness: would this actually resolve the customer's problem?

Every other metric can pass on an answer that is correct, grounded, cited and
useless. This is the closest thing the suite has to the question a support
lead would ask reading the transcript.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from datasets.rag_goldens import RAG_GOLDENS


def build(judge):
    return GEval(
        name="Helpfulness",
        criteria="Would this reply actually resolve the customer's problem?",
        evaluation_steps=[
            "Check that the answer gives the customer something they can act on: "
            "a figure, a deadline, a link, an address, or a clear next step.",
            "Check that it does not hedge past the point of usefulness or end by "
            "punting to human support when the knowledge base held the answer.",
            "Punting to support IS the right answer when the question is genuinely "
            "outside the knowledge base. Do not penalise a correct refusal.",
            "Award a HIGH score when the customer can act on the reply alone.",
        ],
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        threshold=0.6, model=judge, async_mode=False,
    )


@pytest.mark.rag
@pytest.mark.geval
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("golden", RAG_GOLDENS, ids=lambda g: g.input[:45])
def test_rag_geval_helpfulness(ask, judge, golden):
    r = ask(golden.input)
    tc = LLMTestCase(input=golden.input, actual_output=r.answer)
    assert_test(tc, [build(judge)])
