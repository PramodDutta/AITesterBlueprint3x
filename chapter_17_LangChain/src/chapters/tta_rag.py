"""A very small local RAG over the TTACart test-case library.

No server, no database, no API key. 20 test cases in a JSON file, embedded once
with fastembed (ONNX, ~130MB model, downloads on first run) and cached to disk as
a .npy matrix. Retrieval is a cosine dot product over 20 rows, which is instant.

Why this is enough: RAG is retrieval + generation. At 20 documents a vector
"database" is a numpy array, and anything heavier is ceremony. Swap the search()
body for a Qdrant call when the corpus outgrows memory, the interface is the same.

If fastembed is missing the module degrades to keyword overlap scoring, so a
class demo still works offline with no install.
"""

import hashlib
import json
import re
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "rag_corpus" / "tta_testcases.json"
INDEX_PATH = Path(__file__).parent / "rag_corpus" / ".index.npz"
MODEL_NAME = "BAAI/bge-small-en-v1.5"      # 384 dims, ~130MB


def _document(case: dict) -> str:
    """What actually gets embedded. Title and tags carry most of the signal."""
    return (f"{case['title']}. Area: {case['area']}. Type: {case['type']} test case. "
            f"Tags: {', '.join(case['tags'])}. "
            f"Steps: {' '.join(case['steps'])} Expected: {case['expected']}")


class TestCaseRAG:
    def __init__(self, corpus_path: Path = CORPUS_PATH):
        self.cases: list[dict] = json.loads(corpus_path.read_text())
        self.docs = [_document(c) for c in self.cases]
        self._vectors = None
        self.backend = "keyword"
        self._try_load_vectors()

    # ---------------------------------------------------------------- index
    def _corpus_fingerprint(self) -> str:
        return hashlib.sha256("\n".join(self.docs).encode()).hexdigest()[:16]

    def _try_load_vectors(self) -> None:
        try:
            import numpy as np
            from fastembed import TextEmbedding
        except ImportError:
            return                                    # stay on keyword scoring

        fp = self._corpus_fingerprint()
        if INDEX_PATH.exists():
            cached = np.load(INDEX_PATH, allow_pickle=False)
            if str(cached["fingerprint"]) == fp:      # corpus unchanged -> reuse
                self._vectors, self.backend = cached["vectors"], f"embeddings ({MODEL_NAME}, cached)"
                return

        model = TextEmbedding(model_name=MODEL_NAME)
        vectors = np.array(list(model.embed(self.docs)), dtype="float32")
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)   # unit -> dot == cosine
        np.savez(INDEX_PATH, vectors=vectors, fingerprint=fp)
        self._vectors, self.backend = vectors, f"embeddings ({MODEL_NAME}, built)"

    # --------------------------------------------------------------- search
    def search(self, query: str, k: int = 5) -> list[tuple[float, dict]]:
        """Return the k most similar test cases as (score, case), best first."""
        if self._vectors is None:
            return self._keyword_search(query, k)
        import numpy as np
        from fastembed import TextEmbedding
        q = np.array(next(iter(TextEmbedding(model_name=MODEL_NAME).embed([query]))), dtype="float32")
        q /= np.linalg.norm(q)
        scores = self._vectors @ q
        order = np.argsort(-scores)[:k]
        return [(float(scores[i]), self.cases[i]) for i in order]

    def _keyword_search(self, query: str, k: int) -> list[tuple[float, dict]]:
        """Jaccard overlap fallback. Crude, but it never fails to install."""
        def toks(s: str) -> set[str]:
            return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}
        q = toks(query)
        scored = [(len(q & toks(d)) / max(len(q | toks(d)), 1), c)
                  for d, c in zip(self.docs, self.cases)]
        return sorted(scored, key=lambda x: -x[0])[:k]


def format_for_prompt(hits: list[tuple[float, dict]]) -> str:
    """Render retrieved cases as context the planner can cite by id."""
    if not hits:
        return "No existing test cases matched."
    out = []
    for score, c in hits:
        out.append(
            f"[{c['id']}] ({c['type'].upper()}, {c['priority']}, {c['area']}, "
            f"{c['status']}, last run: {c['last_result']}, similarity {score:.3f})\n"
            f"  {c['title']}\n"
            f"  Expected: {c['expected']}\n"
            f"  Tags: {', '.join(c['tags'])}")
    return "\n".join(out)


if __name__ == "__main__":
    rag = TestCaseRAG()
    print(f"corpus: {len(rag.cases)} cases | backend: {rag.backend}\n")
    for q in ["SSO and passkey login buttons",
              "wrong password shows an error",
              "tax and total calculation at checkout"]:
        print(f"QUERY: {q}")
        for s, c in rag.search(q, 3):
            print(f"   {s:.3f}  {c['id']}  {c['title']}")
        print()
