"""09 - Out-of-domain misuse and regulated advice.

The failure here is not a jailbreak. The bot is asked a perfectly polite
question that it should not answer at all ("my chest hurts, what should I
do?") and helpfully answers it. DeepEval ships two built-ins for this, and
they disagree often enough to be worth running both.
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPEC_MISUSE, SPEC_NON_ADVICE

SPECS = {"misuse": SPEC_MISUSE, "non_advice": SPEC_NON_ADVICE}


@pytest.mark.chatbot
@pytest.mark.security
@pytest.mark.slow
@pytest.mark.needs_chatbot
@pytest.mark.parametrize("spec_key", list(SPECS))
@pytest.mark.parametrize("attack", SPEC_MISUSE.cases(), ids=lambda a: a.prompt[:40])
def test_chatbot_stays_in_domain(chatbot, judge, attack, spec_key):
    spec = SPECS[spec_key]
    reply = chatbot.chat(attack.prompt).reply
    assert_test(spec.build_case(attack, reply), [spec.build_metric(judge)])
