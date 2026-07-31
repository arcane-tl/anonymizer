# Test contract templates

Synthetic **text** contracts used for regression testing of the anonymizer.

| File | Language | Purpose |
|------|----------|---------|
| `contract_en.txt` | English | Full feature showcase as a two-party service agreement |
| `contract_fi.txt` | Finnish | Full feature showcase as a two-party toimitussopimus |
| `../contract_expected_pii.py` | — | Ground-truth strings that must disappear after anonymization |

## Covered use cases

- Person names  
- Companies with legal form (`OY` / `LTD` / `AB`), ALL CAPS and Title Case  
- Brand / trading names without legal form (multi-word capitals)  
- Email addresses  
- Phone numbers (US, UK, Finnish `+358` / `040…`)  
- Street addresses (EN + FI suffixes)  
- Finnish postal codes (exactly 5 digits; leading space or `:`; trailing space/punct)  
- Finnish registration plate (`ABC-123`)  
- Finnish henkilötunnus + Y-tunnus  
- URLs (`https://…`, `www.…`)  
- IBAN  
- IP address (EN template)

All personal and company data is **fictional**.

## Manual run

```bash
source .venv/bin/activate
anonymize tests/fixtures/contract_en.txt -o /tmp/contract_en.out.md --lang en
anonymize tests/fixtures/contract_fi.txt -o /tmp/contract_fi.out.md --lang fi
```

## Automated test

```bash
pytest tests/test_contract_templates.py -q
```
