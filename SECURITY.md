# Security

Anonymizer is a **local** document tool. By default it does not send your files over the network.

## Expected behaviour

- Processing uses local libraries (spaCy, Presidio, PyMuPDF, etc.).
- Optional LLM (`--llm`) may send text to **local Ollama** or **remote xAI** only when you opt in.
- Map files (`--map`) contain original PII — treat them like the source document (written mode `0600` when the OS supports it).
- Config / template pack files under `~/.config/anonymizer/` may also be mode `0600`.
- Native PDF/DOCX redaction is **best-effort**, not a forensic wipe.
- Desktop GUIs (Mac droplet, Windows Tk) invoke the local CLI only; Mac Templates use `templates-io.sh` → offline Python (`templates_io`). No network from the GUI shell.

## Reporting a vulnerability

If you believe you have found a security issue in Anonymizer (for example unexpected network access, unsafe install scripts, or data exposure):

1. Prefer a **private** report via [GitHub Security Advisories](https://github.com/arcane-tl/anonymizer/security/advisories/new) if available, or contact the maintainer through [GitHub Sponsors / profile](https://github.com/arcane-tl).
2. Please include steps to reproduce and affected version/tag.
3. Avoid filing a public issue with exploit details until a fix is available.

We aim to acknowledge reports promptly and fix genuine issues in a timely release.
