.PHONY: install install-dev uninstall test

install:
	./scripts/install.sh --yes

install-dev:
	./scripts/install.sh --yes --from-source --with-dev

uninstall:
	./scripts/uninstall.sh --yes

test:
	. .venv/bin/activate && pytest -q
