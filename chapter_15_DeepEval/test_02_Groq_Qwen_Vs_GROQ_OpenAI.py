#Flow:
# 1. Send "What is 2+2?" to Groq Qwen3.8-27b (the model under test).
# 2. Capture the raw answer.
# 3. Hand input + answer + context to DeepEval.
# 4. openai/gpt-oss-120b as judge -> scores AnswerRelevancy + Hallucination.
#    Subject != judge on purpose: a judge scoring its own family inflates scores.

GROQ_MODEL = "qwen/qwen3.8-27b"
JUDGE_MODEL = "openai/gpt-oss-120b"

import os

from dotenv import load_dotenv
from openai import OpenAI

from deepeval.metrics import AnswerRelevancyMetric, HallucinationMetric
from deepeval.test_case import LLMTestCase
from deepeval import assert_test

load_dotenv()

# Groq speaks the OpenAI API, so the official openai SDK works unchanged:
# just point base_url at Groq. The key in .env is a Groq key (gsk_...) that
# lives under OPENAI_API_KEY because that is the name deepeval's
# set-local-model path reads when talking to an OpenAI-compatible endpoint.
groq = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)


def llm_response(question):
    """Ask GROQ_MODEL one question and return its raw answer text."""
    response = groq.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": question}],
        # temperature=0 keeps the answer stable so the score below is
        # reproducible. The judge is still non-deterministic; this only
        # pins the thing under test.
        temperature=0,
    )
    return response.choices[0].message.content.strip()

question = "What is 2+2? Reply with just the number."
answer = llm_response(question)
print(f"\n[Groq {GROQ_MODEL}] → {answer!r}\n")



def test_l4_with_judge_qwen():
    case = LLMTestCase(
        input=question,
        actual_output=answer,
        expected_output="4",
        # HallucinationMetric scores actual_output against this grounding text.
        context=["Basic arithmetic fact: 2 + 2 = 4"],
    )

    metrics = [
        AnswerRelevancyMetric(threshold=0.8, model=JUDGE_MODEL),
        HallucinationMetric(threshold=0.3, model=JUDGE_MODEL),
    ]
    assert_test(case, metrics)