import re


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunking. Oversized paragraphs are split with overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(p) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            step = max_chars - overlap
            for i in range(0, len(p), step):
                chunks.append(p[i:i + max_chars])
            continue
        if len(cur) + len(p) + 2 <= max_chars:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks
