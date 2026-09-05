# Exercise 1 (Basic): Answer Relevancy
# Level Basic : chatbot anwsers

# Exercise 1 (Basic): Answer Relevancy & Hallucination Detection
# Level Basic : chatbot anwsers

# Goal:
#     Learn the two most fundamental LLM evaluation metrics:
#     1. Answer Relevancy  — Does the chatbot answer the question asked?



# Setup: DeepEval needs a "judge" LLM to score the output. Pick one.
    # Groq (cheap, OpenAI-compatible endpoint -> registered as a local model):
    #   deepeval set-local-model --model openai/gpt-oss-120b \
    #       --base-url "https://api.groq.com/openai/v1" --format json --prompt-api-key
    # OpenAI:
    #   export OPENAI_API_KEY=your_key_here
    #   deepeval set-openai --model gpt-4o-mini
    # Note: `deepeval set-grok` is xAI's Grok, NOT Groq.com.
    # Run: pytest test_01_Anwser_Relevancy.py


from deepeval.test_case import LLMTestCase
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric

def test_hello_world():

    test = LLMTestCase(
        input="What is 2+2?",
        actual_output="4",
        expected_output="4",
        context=["Basic arithmetice perform and give result"]
    )
    metric = [     AnswerRelevancyMetric(threshold=0.9)]
    assert_test(test, metric)