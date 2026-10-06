# Knowledge Base — ingestion notes

_Generated: 2026-10-07 00:03_

## Sources

| File | Volume | License | Chunks |
|------|--------|---------|--------|
| `openstax_vol1.pdf` | University Physics Volume 1 | CC BY 4.0 | 4309 |
| `openstax_vol2.pdf` | University Physics Volume 2 | CC BY 4.0 | 3448 |
| `openstax_vol3.pdf` | University Physics Volume 3 | CC BY 4.0 | 2771 |

## Chunking parameters

- Embedding model: `all-MiniLM-L6-v2` (max 256 tokens)
- Chunk size: **220 tokens**
- Overlap: **32 tokens**
- Boundaries: sentences, then paragraphs (greedy sentence packing)
- Section structure: taken from PDF bookmarks (`PyMuPDF.get_toc()`)

## Statistics

- Total chunks: **10528**
- Mean tokens / chunk: **196.4**
- Min / max tokens: 2 / 220
- Chunks exceeding 256 tokens (would be truncated): **0** (target: 0)

## Excluded ToC entries

The following ToC entries are dropped entirely before chunking (matched case-insensitively against their titles):

- `^index$`
- `^answer key`
- `^answers to`
- `^appendix\b`
- `^references$`
- `^bibliography$`
- `^glossary$`
- `problems$`
- `^problems\b`
- `^exercises\b`
- `challenge problems`
- `^review\b`
- `^conceptual questions`
- `^additional problems`
- `^chapter review`
- `^about openstax`
- `^about this book`
- `^preface$`

## Attribution (CC BY 4.0)

This knowledge base contains text adapted from:

> OpenStax, *University Physics* (Volumes 1, 2, and 3). Authors: Samuel J. Ling, Jeff Sanny, William Moebs, et al. Houston, Texas: OpenStax. Access for free at https://openstax.org/details/books/university-physics-volume-1 (and corresponding links for volumes 2 and 3). Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0): https://creativecommons.org/licenses/by/4.0/

Modifications made for this thesis:
- Extracted plain text from the official PDF releases.
- Removed non-content sections (index, answer key, appendices, end-of-chapter problems/exercises).
- Split content into fixed-size overlapping chunks for retrieval.
- No modifications were made to the physics content itself.

Additional sources under NASA public-domain policy are listed with their original URL and access date in `Knowledge_base/sources/misc/*.txt`.