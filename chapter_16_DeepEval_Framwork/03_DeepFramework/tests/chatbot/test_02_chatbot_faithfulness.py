"""02 - Faithfulness: is every claim in the reply backed by the context?

Faithfulness reads `retrieval_context`. It asks a narrow question: of the
claims the bot made, how many are supported by the source it was given? A
reply can be perfectly faithful and still unhelpful, which is why this runs
alongside relevancy rather than instead of it.
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPEC_FAITHFULNESS

GOLDENS = SPEC_FAITHFULNESS.cases()


@pytest.mark.chatbot
@pytest.mark.quality
@pytest.mark.slow
@pytest.mark.needs_chatbot
@pytest.mark.parametrize("golden", GOLDENS, ids=lambda g: g.input[:45])
def test_chatbot_faithfulness(chatbot, judge, golden):
    reply = chatbot.chat(golden.input).reply
    tc = SPEC_FAITHFULNESS.build_case(golden, reply)
    assert_test(tc, [SPEC_FAITHFULNESS.build_metric(judge)])
