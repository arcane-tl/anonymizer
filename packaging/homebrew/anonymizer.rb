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

  url "https://github.com/arcane-tl/anonymizer/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "952b6dd62ae4f1347e866331df6c390b9c3a799e979dd75c8f876a90477194d9"
  version "1.0.0"

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
      Verify the install:
        anonymize doctor
        anonymize --version

      A harmless linkage warning may appear for the lingua language-detection
      wheel during install; the CLI still runs. Prefer:
        $(brew --prefix)/opt/anonymizer/bin/anonymize --version

      If `anonymize` still points at ~/.local/bin (curl installer), either
      put Homebrew first on PATH or run:
        brew link --overwrite anonymizer

      spaCy models (installed by default): en_core_web_sm, fi_core_news_sm
      For higher accuracy (larger download):
        #{libexec}/bin/python -m spacy download en_core_web_lg
        #{libexec}/bin/python -m spacy download fi_core_news_lg

      Optional OCR (scanned PDFs): brew install tesseract tesseract-lang ocrmypdf

      Mac drag-and-drop GUI (optional):
        git clone https://github.com/arcane-tl/anonymizer.git
        cd anonymizer && ./packaging/macos/install-app.sh
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/anonymize --version")
    assert_match "anonymize", shell_output("#{bin}/anonymize --help")
  end
end
