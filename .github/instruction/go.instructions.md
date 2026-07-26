---
applyTo: root/**
---

# AITesterBlueprint3x — Agent Instructions

## Custom Commands

### `go go go`

When the user says **"go go go"**, **"Go Go"**, **"go go"**, **"/go"**, or **"ship it"**, run the full document-commit-push workflow:

1. **Detect changes** — run `git status` and `git diff --stat` to find new/modified files.
2. **Update root `README.md`** — for every new or substantially changed module, add a section following the 6-block contract:
   - Section heading (`### NN — Topic Name`)
   - Concept (1–2 sentences)
   - Why (1 sentence)
   - Q&A — exactly 3 bullet points
   - Mermaid diagram (flowchart / sequenceDiagram / mindmap)
   - Runnable code sample (≤ 30 lines, real content)
   - Also update the TOC, curriculum mindmap, and repository tree if needed.
3. **Stage changed files** — `git add README.md` plus any new/modified source files.
4. **Commit** — Conventional Commits format, subject ≤ 50 chars. Strip any `Co-Authored-By` trailers.
5. **Push** — `git push origin main`.
6. **Report** — commit SHA + one-line summary.
