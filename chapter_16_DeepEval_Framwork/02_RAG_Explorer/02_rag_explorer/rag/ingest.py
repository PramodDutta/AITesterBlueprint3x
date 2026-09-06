"""Document loaders + chunker."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


@dataclass
class Document:
    source: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    id: str
    source: str
    index: int
    text: str
    char_start: int
    char_end: int


def load_text(path: str | Path) -> Document:
    p = Path(path)
    return Document(source=p.name, text=p.read_text(encoding="utf-8"))


def load_pdf(path: str | Path) -> Document:
    p = Path(path)
    reader = PdfReader(str(p))
    pages = [page.extract_text() or "" for page in reader.pages]
    return Document(
        source=p.name,
        text="\n\n".join(pages),
        metadata={"pages": len(pages)},
    )


def load_any(path: str | Path) -> Document:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return load_pdf(p)
    return load_text(p)


def load_directory(directory: str | Path) -> list[Document]:
    d = Path(directory)
    docs: list[Document] = []
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix.lower() in {".md", ".txt", ".pdf"}:
            docs.append(load_any(p))
    return docs


def chunk_document(
    doc: Document,
    chunk_size: int = 500,
    overlap: int = 60,
) -> list[Chunk]:
    """Split on paragraph then sliding window over characters."""
    text = re.sub(r"\n{3,}", "\n\n", doc.text).strip()
    chunks: list[Chunk] = []
    i = 0
    idx = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        # snap to nearest period or newline within last 80 chars to avoid mid-sentence cuts
        if end < n:
            window = text[max(end - 80, i):end]
            cut = max(window.rfind(". "), window.rfind("\n"))
            if cut != -1:
                end = max(end - 80, i) + cut + 1
        body = text[i:end].strip()
        if body:
            chunks.append(
                Chunk(
                    id=f"{doc.source}#{idx}",
                    source=doc.source,
                    index=idx,
                    text=body,
                    char_start=i,
                    char_end=end,
                )
            )
            idx += 1
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return chunks


def chunk_documents(docs: Iterable[Document], **kw) -> list[Chunk]:
    out: list[Chunk] = []
    for d in docs:
        out.extend(chunk_document(d, **kw))
    return out
