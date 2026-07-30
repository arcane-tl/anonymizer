# Sample documents for manual testing

Sources used for local smoke tests (not committed outputs).

## English (`en/`)

| File | Source |
|------|--------|
| `loc_purchase_agreement.pdf` | Library of Congress sample purchase agreement (public) |
| `maine_publishing_agreement.pdf` | University of Maine standard publishing agreement (public) |
| `nd_contract_manual.pdf` | North Dakota AG contract drafting manual (public) |
| `service_agreement_sample.docx` | Synthetic commercial DOCX with fictional PII |
| `supplier_memo.md` | Synthetic memo + Wikipedia GDPR excerpt (CC BY-SA) |

## Finnish (`fi/`)

| File | Source |
|------|--------|
| `sopimus_esimerkki.md` | Synthetic commercial FI text + Wikipedia *Helsinki* / *Nokia* (CC BY-SA) |
| `hankintasopimus_testi.docx` | Same content as DOCX |
| `hankintamuistio.pdf` | Same content as PDF (text layer) |

Fictional identifiers used in FI samples (for redaction checks):

- Hetu: `131052-308T`
- Y-tunnus: `0737546-2`
- Names: Maija Korhonen, Pekka Nieminen, Liisa Virtanen
- Orgs: Karjalan Komponentit Oy, Pohjolan Kuljetus Oy, …

## Outputs

Run:

```bash
source .venv/bin/activate
anonymize samples/en/supplier_memo.md -o samples/out/en_supplier_memo.anonymized.md
anonymize samples/fi/sopimus_esimerkki.md -o samples/out/fi_sopimus.anonymized.md
```

`samples/out/` is gitignored (anonymized markdown).
