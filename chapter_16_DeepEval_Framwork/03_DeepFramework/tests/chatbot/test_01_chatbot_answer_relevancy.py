"""01 - Answer Relevancy: does the reply address the question asked?

The first and cheapest signal. It does not check whether the answer is TRUE,
only whether it is on topic and complete. A confidently wrong answer scores
1.0 here, which is exactly why the other six tests exist.
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPEC_ANSWER_RELEVANCY

GOLDENS = SPEC_ANSWER_RELEVANCY.cases()


@pytest.mark.chatbot
@pytest.mark.quality
@pytest.mark.slow
@pytest.mark.needs_chatbot
@pytest.mark.parametrize("golden", GOLDENS, ids=lambda g: g.input[:45])
def test_chatbot_answer_relevancy(chatbot, judge, golden):
    reply = chatbot.chat(golden.input).reply
    tc = SPEC_ANSWER_RELEVANCY.build_case(golden, reply)
    assert_test(tc, [SPEC_ANSWER_RELEVANCY.build_metric(judge)])
