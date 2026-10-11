# Output formats: what survives

Anonymizer can write several artifacts from one run. They are **not** equivalent for privacy.

| Output | How it is built | Original PDF/DOCX metadata, outline, revisions | Residual risk |
|--------|-----------------|------------------------------------------------|---------------|
| **Markdown** (`.anonymized.md` / `.md`) | New text file from extracted + redacted blocks + YAML front matter | **Does not survive** — source info dict, XMP, TOC, DOCX `core.xml` / `app.xml`, tracked changes, and relationship targets are **not** copied into the Markdown | Only what remains in the **extracted text** (and anything you put in front matter yourself). Source images/binaries are not embedded. |
| **Text PDF** (`.anonymized.text.pdf`) | **New** reflow PDF rendered from anonymized Markdown | **Does not survive** — fresh document, not a rewrite of the source PDF | Same text as Markdown; no source bookmarks/XMP. **Not** layout-faithful native redaction. |
| **Native PDF** (`.anonymized.pdf`) | Copy of source + content-stream redactions + scrubs + full save rewrite | **Can survive if a channel is missed** — we wipe document info/XMP, clear the outline/bookmarks, scrub links/widgets best-effort | Higher forensic surface. Check `native_clean` / residual warnings. |
| **Native DOCX** (`.anonymized.docx`) | Copy of source + in-package replace + property/rels scrub | **Can survive if a channel is missed** — tracked changes are accepted, revision authors / app props / matching hyperlink targets scrubbed | Same honesty model via an independent zip verifier. |

## Which should I use?

- Need **“no original container metadata”** and editable text → **Markdown** (and optionally **text PDF** for a clean shareable reflow).
- Need the file to **look like the original** (layout, letterhead geometry) → **native** PDF/DOCX, and **always read** `native_clean`, residual samples, and scrub-error warnings in the run summary / Markdown front matter.

## What `native_clean` means

`native_clean: true` means the **independent verifier** found **no mapped cleartext surfaces** in the **documented covered channels** for that format (see front matter `native_coverage`). It is **not** a legal warranty and does **not** cover:

- Text that exists only inside images (unless you enable letterhead/logo black-box options)
- Glyph splits / encodings that search cannot match
- Full tagged-PDF structure trees / OCG layer names (not claimed in 1.4.7)
- Charts, SmartArt, or exhaustive alt-text catalogues in DOCX

Prefer `--fail-on-native-miss` when a pipeline must refuse non-clean native output.
