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

  # update-for-release.sh rewrites url / sha256 / version at publish time.
  url "https://github.com/arcane-tl/anonymizer/archive/refs/tags/v1.3.1.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  version "1.3.1"

  head "https://github.com/arcane-tl/anonymizer.git", branch: "main"

  # lingua’s wheel uses @rpath; without this, brew fails to rewrite dylib IDs
  # (load commands do not fit) and prints "Failed to fix install linkage".
  preserve_rpath

  depends_on "python@3.12"
  # Required for --review-window / desktop app review (Homebrew python has no _tkinter alone)
  depends_on "python-tk@3.12"
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
      CLI command: anonymize (this formula)
      GUI cask: anonymizer-app → /Applications/Anonymizer.app

      Full product (one command — installs this formula + app):
        brew install --cask anonymizer-app

      Upgrade both (one command):
        brew update && brew upgrade anonymizer anonymizer-app

      Migrating from the old cask token "anonymizer" (same name blocked CLI link):
        brew uninstall --cask --force anonymizer
        # if uninstall still errors:
        #   rm -rf "$(brew --prefix)/Caskroom/anonymizer"
        #   rm -rf /Applications/Anonymizer.app
        brew install --cask anonymizer-app
        brew link --overwrite anonymizer && hash -r

      If `anonymize` is missing:
        brew link --overwrite anonymizer && hash -r
      Ensure $(brew --prefix)/bin is on PATH.

      If `~/.local/bin/anonymize` shadows Homebrew, put Homebrew first on PATH or:
        brew link --overwrite anonymizer

      Verify:
        anonymize doctor
        anonymize --version

      Document review window needs tkinter (via python-tk@3.12, a formula dependency).

      spaCy models (default): en_core_web_sm, fi_core_news_sm
      Larger models:
        #{libexec}/bin/python -m spacy download en_core_web_lg
        #{libexec}/bin/python -m spacy download fi_core_news_lg

      Optional OCR: brew install tesseract tesseract-lang ocrmypdf
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/anonymize --version")
    assert_match "anonymize", shell_output("#{bin}/anonymize --help")
    # Language detector extension must import (preserve_rpath keeps @rpath wheels usable)
    system libexec/"bin/python", "-c", "from lingua import Language; print(Language.ENGLISH)"
  end
end
