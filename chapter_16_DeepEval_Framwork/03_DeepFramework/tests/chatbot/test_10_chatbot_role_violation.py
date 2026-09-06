"""10 - Role adherence across the whole attack library.

Runs every one of the 27 attacks through a single question: did the assistant
stop being ShopBot? It is the broadest and slowest test in the suite, and the
one closest to "would this embarrass us in a screenshot".
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPEC_ROLE_VIOLATION


@pytest.mark.chatbot
@pytest.mark.security
@pytest.mark.slow
@pytest.mark.needs_chatbot
@pytest.mark.parametrize("attack", SPEC_ROLE_VIOLATION.cases(), ids=lambda a: a.prompt[:40])
def test_chatbot_holds_its_role(chatbot, judge, attack):
    reply = chatbot.chat(attack.prompt).reply
    assert_test(
        SPEC_ROLE_VIOLATION.build_case(attack, reply),
        [SPEC_ROLE_VIOLATION.build_metric(judge)],
    )
