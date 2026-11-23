# Rule: Vector-First Retrieval (Low Token, Max Quality)

To achieve maximum precision with minimal token consumption, agents must prioritize vector/hybrid chunk search over reading entire raw files.

## 1. The Vector-First Protocol
When searching for facts, code snippets, documentation, PDF pages, image details, or project history:
1. **Search First**: Call `search_memory(query=...)` or `POST /projects/{project}/search` with a targeted query.
2. **Evaluate Chunks**: Read the returned top chunks (`score`, `path`, `chunk`, `[Page X]` excerpt).
   - In most cases, the chunk snippet (up to 600 chars) contains the exact answer needed.
   - Answer or proceed using only the retrieved snippets.
3. **Targeted Read Only When Necessary**:
   - Only call `read_file` if the chunk snippet indicates more adjacent context is strictly required, or if you need to edit the file.
   - Never load large files, 50-page PDFs, or bulk binaries into the context window unprompted.

## 2. Token Efficiency Benefits
- Standard file read: 10,000 to 100,000+ tokens consumed.
- Vector chunk retrieval: ~100 to 200 tokens per snippet with exact page/section reference.
- Saves 95%+ of context budget while maintaining high accuracy and citation fidelity.
