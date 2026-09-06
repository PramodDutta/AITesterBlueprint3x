"""08 - Adversarial security, one test per attack technique.

Grouped by technique on purpose. "The bot is unsafe" is not actionable;
"the bot resists roleplay jailbreaks but hands over its prompt to a plain
direct request" tells you exactly which defence to add.

Every card here is also on the dashboard, driven by the same spec.
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPECS_BY_KEY

TECHNIQUES = [
    "prompt_injection",
    "jailbreak",
    "obfuscation",
    "exfiltration",
    "social_engineering",
]

CASES = [
    (technique, attack)
    for technique in TECHNIQUES
    for attack in SPECS_BY_KEY[technique].cases()
]


@pytest.mark.chatbot
@pytest.mark.security
@pytest.mark.slow
@pytest.mark.needs_chatbot
@pytest.mark.parametrize(
    "technique,attack", CASES, ids=lambda v: v if isinstance(v, str) else v.prompt[:40]
)
def test_chatbot_resists_attack(chatbot, judge, technique, attack):
    spec = SPECS_BY_KEY[technique]
    reply = chatbot.chat(attack.prompt).reply
    tc = spec.build_case(attack, reply)
    assert_test(tc, [spec.build_metric(judge)])
