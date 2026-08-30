LLM Eval -> How to do it -> Deepeval ( tool doesn't matter), concept matter -> Tool can be replaced!.



# Why LLM Eval?
Traditional QA isn't enough for LLM-powered systems. Here's what breaks  and why you need a new approach.

#### <u>Non-determinism</u>
Same prompt, different output. `<u>assertEquals</u>` breaks. You need probabilistic, score-based checks with thresholds.

#### <u>Open-ended outputs</u>
There's no single "correct" answer for "summarize this document." You measure quality along multiple axes instead.

#### <u>Hallucinations</u>
LLMs fabricate facts confidently. Fluent ≠ correct. You need faithfulness checks against a source of truth.

#### <u>Safety & bias</u>
Toxic, biased, or unsafe responses are failures. Jailbreaks and prompt injections are a new attack surface

#### Cost & latency
Quality is only one dimension. Token cost, p95 latency, and tool-call efficiency are first-class test signals.



![image.png](https://eraser.imgix.net/workspaces/xVHRtTGAqlpb3CtKgKii/WWS31TdyovhjTB1TVo9v2jWpPei1/image_RWDvswx-qOh-sO0a76cIW.png?ixlib=js-3.8.0 "image.png")

---

# Key Terms used in the LLM Evaluation
1. What is a prompt?
2. Completion and response.
3. Ground truth.
4. Golden dataset.
5. What is a judge or evaluator?
6. What is an LLM as a judge?
7. What is hallucination?
8. What is faithfulness and groundness?
9. What is the relevancy?
10. What is the context precision, and many more?
11. What are traces and span?
12. What is the eval and harness?
---

**<u>Prompt</u>**

The input to the LLM. Includes system instructions, user message, and often retrieved context<u>.</u>



**<u>Completion / Response</u>**

The LLM's output that we evaluate.



**<u>Ground Truth</u>** 

The "correct" or expected answer -> human-written, used as a reference.



**<u>Golden Dataset</u>**

A curated set of _input → expected output_ pairs. Your regression suite. ( TestData).



**<u>Evaluator / Judge (LLM, OR Human)</u>**

The component that scores a response. Can be rule-based, a model, or another LLM.



![image.png](https://eraser.imgix.net/workspaces/xVHRtTGAqlpb3CtKgKii/WWS31TdyovhjTB1TVo9v2jWpPei1/image_Es9BQ00wsnB9ZkbFtLKyH.png?ixlib=js-3.8.0 "image.png")

**<u>LLM-as-Judge</u>**

- Using a strong LLM (often GPT-4-class) to score another LLM's outputs on criteria like relevancy or correctness.


**<u>Hallucination</u>**

|  |
| ----- |
| <u>A fluent, confident statement that isn't grounded in facts or the provided context.</u> |


---

**<u>Relevancy</u>**

```
Does the answer actually address the user's question?
```
```
**Faithfulness - Does the answer stick to the retrieved context,
 without inventing things?**
```
```
Context Precision / Recall
```
---

