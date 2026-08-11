# Screenshots

Product UI captures for the README and docs (synthetic sample contract only).

| File | Content |
|------|---------|
| `options-window.png` | Mac **Anonymizer.app** options (v1.4.0) with `tests/fixtures/contract_en.txt` |
| `review-window.png` | Document **review** UI (`strict` on the same fixture; **builtin packs only**, no user templates) |

Captured on macOS at native Retina resolution. Do not commit customer documents — regenerate from fixtures if you need new shots.

```bash
# Regenerating review shot without user/custom templates:
TMP=$(mktemp -d)
export XDG_CONFIG_HOME="$TMP" ANONYMIZER_CONFIG="$TMP/config.yaml"
printf '%s\n' 'templates_enabled: [en-field-labels, en-legal-boilerplate, fi-field-labels, fi-legal-boilerplate]' > "$ANONYMIZER_CONFIG"
anonymize strict tests/fixtures/contract_en.txt --review-window \
  --template en-field-labels,en-legal-boilerplate,fi-field-labels,fi-legal-boilerplate
```
