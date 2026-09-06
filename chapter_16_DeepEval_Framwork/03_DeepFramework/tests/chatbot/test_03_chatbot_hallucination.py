"""03 - Hallucination: does the reply contradict known ground truth?

The difference from Faithfulness is the field it reads. Faithfulness scores
against `retrieval_context` (what the bot was handed). Hallucination scores
against `context` (what is actually true). A bot can be faithful to a bad
document and still hallucinate about the world.

Direction note: in DeepEval 4.x a HIGH score is a pass. 1.0 means "agrees
with ground truth". This flipped from 3.x, where the score counted violations.
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPEC_HALLUCINATION

GOLDENS = SPEC_HALLUCINATION.cases()


@pytest.mark.chatbot
@pytest.mark.quality
@pytest.mark.slow
@pytest.mark.needs_chatbot
@pytest.mark.parametrize("golden", GOLDENS, ids=lambda g: g.input[:45])
def test_chatbot_hallucination(chatbot, judge, golden):
    reply = chatbot.chat(golden.input).reply
    tc = SPEC_HALLUCINATION.build_case(golden, reply)
    assert_test(tc, [SPEC_HALLUCINATION.build_metric(judge)])
