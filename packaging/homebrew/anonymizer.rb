# Homebrew formula for anonymizer (CLI: anonymize).
#
# Public install:
#   brew tap arcane-tl/anonymizer
#   brew install anonymizer
#
# Source of truth is mirrored to:
#   https://github.com/arcane-tl/homebrew-anonymizer
#
# Docs: packaging/homebrew/README.md

class Anonymizer < Formula
  include Language::Python::Virtualenv

  desc "Local CLI: PDF/DOCX/text → anonymized Markdown (EN + FI)"
  homepage "https://github.com/arcane-tl/anonymizer"
  license "MIT"

  url "https://github.com/arcane-tl/anonymizer/archive/refs/tags/v1.1.1.tar.gz"
  sha256 "45d9a5bc6f911d3628c0ef2c916c6d91726c8ba44c490da3f0eb5f07930f76da"
  version "1.1.1"

  head "https://github.com/arcane-tl/anonymizer.git", branch: "main"

  depends_on "python@3.12"
  depends_on "tesseract" => :recommended

  def install
    # Create a venv under libexec. Homebrew's Virtualenv#pip_install passes
    # --no-deps (for resource-based installs); we need full PyPI resolution.
    venv = virtualenv_create(libexec, "python3.12")
    python = Formula["python@3.12"].opt_libexec/"bin/python"
    # Drive pip against the venv interpreter so dependencies are installed.
    system python, "-m", "pip", "--python=#{libexec}/bin/python",
           "install", "--verbose", "--upgrade", buildpath.to_s
    # Entry point from pyproject [project.scripts]
    bin.install_symlink libexec/"bin/anonymize"
  end

  def post_install
    # Smaller models by default for a faster first brew install.
    python = libexec/"bin/python"
    %w[en_core_web_sm fi_core_news_sm].each do |model|
      ohai "Downloading spaCy model #{model}"
      system python, "-m", "spacy", "download", model
    end
  end

  def caveats
    <<~EOS
      Product: Anonymizer
      CLI command: anonymize

      Install full product (CLI + app):
        brew install --cask anonymizer

      Upgrade CLI and app separately (same name, two packages):
        brew update
        brew upgrade anonymizer
        brew upgrade --cask anonymizer

      If `anonymize` is missing after upgrade:
        brew link --overwrite anonymizer && hash -r
      Ensure $(brew --prefix)/bin is on your PATH.

      If `anonymize` is shadowed by ~/.local/bin:
        brew link --overwrite anonymizer
        # or put Homebrew first on PATH

      Verify:
        anonymize doctor
        anonymize --version

      spaCy models (default): en_core_web_sm, fi_core_news_sm
      Larger models:
        #{libexec}/bin/python -m spacy download en_core_web_lg
        #{libexec}/bin/python -m spacy download fi_core_news_lg

      Optional OCR: brew install tesseract tesseract-lang ocrmypdf

      A harmless linkage warning for the lingua wheel may appear; the CLI still works.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/anonymize --version")
    assert_match "anonymize", shell_output("#{bin}/anonymize --help")
  end
end
