# anonymizer-fm-check

Small Swift helper that calls Apple’s on-device **Foundation Models** for the
automatic AI redaction check.

## Build

```bash
./packaging/macos/fm-check/build.sh
# → packaging/macos/fm-check/anonymizer-fm-check
```

Requires macOS 26+ with Apple Intelligence enabled.

## Usage

```bash
./anonymizer-fm-check --available
# AVAILABLE

echo '{"prompt":"Return ONLY JSON: {\"ok\":true}"}' | ./anonymizer-fm-check
```

Python discovers the binary via `PATH`, `ANONYMIZER_FM_CHECK`, or the paths in
`anonymizer.anonymize.ai_check.find_fm_helper`.

`release-app.sh` should copy the binary into `Anonymizer.app/Contents/MacOS/`.
