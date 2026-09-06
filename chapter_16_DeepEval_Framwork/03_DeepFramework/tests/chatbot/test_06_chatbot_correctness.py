"""06 - Correctness: a custom G-Eval rubric, not a string comparison.

This is the test that shows why assertEquals dies on generated text. The bot
may say "within 7 business days" or "7 business days after we receive it" -
both correct. G-Eval judges against the reference answer using written
criteria, so wording is free but the FIGURES must match.
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPEC_CORRECTNESS

GOLDENS = SPEC_CORRECTNESS.cases()


@pytest.mark.chatbot
@pytest.mark.quality
@pytest.mark.slow
@pytest.mark.needs_chatbot
@pytest.mark.parametrize("golden", GOLDENS, ids=lambda g: g.input[:45])
def test_chatbot_correctness(chatbot, judge, golden):
    reply = chatbot.chat(golden.input).reply
    tc = SPEC_CORRECTNESS.build_case(golden, reply)
    assert_test(tc, [SPEC_CORRECTNESS.build_metric(judge)])
