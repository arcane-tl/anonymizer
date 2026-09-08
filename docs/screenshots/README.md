# Screenshots

Product UI captures for the README and docs (synthetic sample contract only).

| File | Content |
|------|---------|
| `options-window.png` | Mac **Anonymizer.app** options (v1.4.x) with `tests/fixtures/contract_en.txt` — **Mode**, **Save as**, **Review** / **Open**, **More options** |
| `review-window.png` | Document **review** UI (`strict` on the same fixture; **builtin packs only**, no user templates) |

Panel layout evolved (Save as ticks, More options disclosure). Regenerate `options-window.png` when documenting UI changes; see main [README Use cases](../../README.md#use-cases).

Captured on macOS at native Retina resolution. Do not commit customer documents — regenerate from fixtures if you need new shots.

```bash
# Regenerating review shot without user/custom templates:
TMP=$(mktemp -d)
export XDG_CONFIG_HOME="$TMP" ANONYMIZER_CONFIG="$TMP/config.yaml"
printf '%s\n' 'templates_enabled: [en-field-labels, en-legal-boilerplate, fi-field-labels, fi-legal-boilerplate]' > "$ANONYMIZER_CONFIG"
anonymize strict tests/fixtures/contract_en.txt --review-window \
  --template en-field-labels,en-legal-boilerplate,fi-field-labels,fi-legal-boilerplate
```
