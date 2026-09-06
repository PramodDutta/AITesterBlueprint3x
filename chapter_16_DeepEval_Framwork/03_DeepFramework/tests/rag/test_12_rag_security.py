"""12 - The same attack library, aimed at the RAG pipeline.

RAG changes the threat model. The attacker is no longer only trying to move
the model off its instructions; they are trying to make retrieval hand over
the corpus. Exfiltration is the technique to watch on this target.
"""
import pytest
from deepeval import assert_test

from metrics_catalog import SPECS_BY_KEY

TECHNIQUES = [
    "prompt_injection_rag",
    "jailbreak_rag",
    "obfuscation_rag",
    "exfiltration_rag",
    "social_engineering_rag",
]

CASES = [
    (technique, attack)
    for technique in TECHNIQUES
    for attack in SPECS_BY_KEY[technique].cases()
]


@pytest.mark.rag
@pytest.mark.security
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize(
    "technique,attack", CASES, ids=lambda v: v if isinstance(v, str) else v.prompt[:40]
)
def test_rag_resists_attack(rag, judge, technique, attack):
    spec = SPECS_BY_KEY[technique]
    answer = rag.ask(attack.prompt).answer
    assert_test(spec.build_case(attack, answer), [spec.build_metric(judge)])
