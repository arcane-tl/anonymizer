# Real-world fixture sources

Retrieved for precision / false-positive testing. Not customer data.

| File | Source | Notes |
|------|--------|--------|
| `en_sample_agreement.txt` | University of Maine “Publishing Agreement” sample PDF text extract + synthetic annex | Public institutional sample form body; `https://www.maine.edu/general-counsel/wp-content/uploads/sites/49/2019/12/PublishingAgreementStandard.pdf` (retrieved 2026-07-31). Annex mirrors `contract_en.txt` PII for recall. |
| `fi_sample_sopimus.txt` | Wikipedia FI article «Sopimus» (CC BY-SA) + synthetic commercial annex | Encyclopedic contract-law prose (external-link dump trimmed to reduce non-PII ORG noise) + fictional supplier fields for recall |
| `*.must_not_redact.txt` | Hand-curated precision lists | Boilerplate / form labels that must survive anonymization |

Also used historically for ad-hoc checks:

- Library of Congress sample Agreement of Purchase PDF  
  `https://www.loc.gov/static/programs/national-recording-preservation-plan/tools-and-resources/documents/Agreement-Purchase-MBRS-project.pdf`

Synthetic annex fields use the same fictional identifiers as `contract_en.txt` / `contract_fi.txt` (not real persons or companies).

## What counts as a good redaction

| Keep redacting | Do not redact |
|----------------|---------------|
| Person names, emails, phones, IBANs, IPs | Legal roles (Publisher, Author, Work) |
| Companies / brands, Y-tunnus, VAT, hetu | Form labels (Osoite, Y-tunnus:, Rekisterinumero/tunniste) |
| Streets, postcodes, cities | Legal titles (Letter of Intent, Manuscript) |
| URLs, plates | Country-level treaty boilerplate is optional LOCATION |

Country names (`United States`, `Canada`) and historical places (`Sumerissa`, `Vienna`) may still appear as LOCATION — low sensitivity, conservative geo policy.
