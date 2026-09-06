"""10 - Multi-turn RAG: does retrieval follow the conversation?

Turn two is "And how does that change if I paid by credit card?". On its own
that sentence retrieves nothing useful. A RAG pipeline has to carry the
earlier turn into the query, and this is the only test that notices when it
silently stops doing so.
"""
import pytest
from deepeval import assert_test
from deepeval.metrics import ConversationCompletenessMetric, KnowledgeRetentionMetric
from deepeval.test_case import ConversationalTestCase, Turn

from datasets.rag_goldens import RAG_CONVERSATIONS

METRICS = {
    "completeness": lambda j: ConversationCompletenessMetric(
        threshold=0.5, model=j, include_reason=True, async_mode=False),
    "retention": lambda j: KnowledgeRetentionMetric(
        threshold=0.5, model=j, include_reason=True, async_mode=False),
}


@pytest.mark.rag
@pytest.mark.conversational
@pytest.mark.slow
@pytest.mark.needs_rag
@pytest.mark.parametrize("metric_name", list(METRICS))
@pytest.mark.parametrize("convo", RAG_CONVERSATIONS, ids=lambda c: c[0][:40])
def test_rag_conversational(rag, judge, convo, metric_name):
    turns, history = [], []
    for user_msg in convo:
        answer = rag.ask(user_msg, history=history).answer
        turns += [Turn(role="user", content=user_msg),
                  Turn(role="assistant", content=answer)]
        history += [{"role": "user", "content": user_msg},
                    {"role": "assistant", "content": answer}]
    assert_test(ConversationalTestCase(turns=turns), [METRICS[metric_name](judge)])
