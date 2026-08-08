.PHONY: install install-dev uninstall test

# macOS: ./scripts/install.sh
# Windows: see packaging/windows/README.md (Setup.exe / install.ps1 / build-release.ps1)

install:
	./scripts/install.sh --yes

install-dev:
	./scripts/install.sh --yes --from-source --with-dev

uninstall:
	./scripts/uninstall.sh --yes

test:
	. .venv/bin/activate && pytest -q
