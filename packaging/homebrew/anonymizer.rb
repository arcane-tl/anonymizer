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
  desc "Local CLI: PDF/DOCX/text → anonymized Markdown (EN + FI)"
  homepage "https://github.com/arcane-tl/anonymizer"
  license "MIT"

  # update-for-release.sh rewrites url / sha256 / version at publish time.
  url "https://github.com/arcane-tl/anonymizer/archive/refs/tags/v1.3.5.tar.gz"
  sha256 "1dbf53bf81eccd92e1807844be45898ad0ce77f346e0e38026391a0631cbd856"
  version "1.3.5"

  head "https://github.com/arcane-tl/anonymizer.git", branch: "main"

  # lingua’s wheel uses @rpath; without this, brew fails to rewrite dylib IDs
  # (load commands do not fit) and prints "Failed to fix install linkage".
  preserve_rpath

  depends_on "python@3.12"
  # Required for --review-window / desktop app review (Homebrew python has no _tkinter alone)
  depends_on "python-tk@3.12"
  depends_on "tesseract" => :recommended

  def venv_python
    libexec/"bin/python"
  end

  def host_python
    Formula["python@3.12"].opt_libexec/"bin/python"
  end

  def install
    # Isolated venv WITH pip (no --system-site-packages) so spaCy models and
    # doctor status reflect this formula only — not a leftover global install.
    system host_python, "-m", "venv", libexec.to_s

    # Install package into the venv
    system host_python, "-m", "pip", "--python=#{venv_python}",
           "install", "--upgrade", "pip", "setuptools", "wheel"
    system host_python, "-m", "pip", "--python=#{venv_python}",
           "install", "--upgrade", buildpath.to_s

    # CLI entry point
    bin.install_symlink libexec/"bin/anonymize"
  end

  def models_ok?
    # Same criterion as doctor: can we load EN+FI models?
    quiet_system venv_python, "-m", "anonymizer.install_models",
                 "--check", "--langs", "en,fi"
  end

  def post_install
    # 1) Preemptive: if models already load, do not download or warn
    if models_ok?
      ohai "spaCy models already ready (EN+FI); skipping download"
      return
    end

    # 2) Install only when needed (module also prechecks per language)
    ohai "Installing spaCy models (English + Finnish, large; may take several minutes)"
    system venv_python, "-m", "anonymizer.install_models",
           "--langs", "en,fi", "--size", "lg", "--fallback"

    # 3) Trust final load check — not install exit code alone
    if models_ok?
      ohai "spaCy models ready"
    else
      opoo <<~EOS
        Required spaCy models are not loadable yet.
        One-time fix (not a full reinstall of the app or cask):

          #{venv_python} -m anonymizer.install_models --langs en,fi --size lg --fallback

        Then: anonymize doctor
      EOS
    end
  end

  def caveats
    <<~EOS
      Product: Anonymizer
      CLI command: anonymize (this formula)
      GUI cask: anonymizer-app → /Applications/Anonymizer.app

      Full product (one command — installs this formula + app):
        brew install --cask anonymizer-app

      Upgrade both:
        brew update && brew upgrade anonymizer anonymizer-app

      Verify:
        anonymize doctor
        anonymize --version

      spaCy models (default: EN + FI large for best PERSON/ORG quality):
        Installed during post_install via:
          #{venv_python} -m anonymizer.install_models --langs en,fi --size lg --fallback

      If doctor reports missing EN/FI models (not a full reinstall):
        #{venv_python} -m anonymizer.install_models --langs en,fi --size lg --fallback
        # or: brew postinstall anonymizer

      Smaller models:
        #{venv_python} -m anonymizer.install_models --langs en,fi --size sm

      Optional Swedish:
        #{venv_python} -m anonymizer.install_models --langs sv --size lg
        anonymize doc.pdf --lang sv

      Model guide: https://github.com/arcane-tl/anonymizer/blob/main/docs/models.md

      Document review window needs tkinter (python-tk@3.12, a formula dependency).
      Optional OCR: brew install tesseract tesseract-lang ocrmypdf
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/anonymize --version")
    assert_match "anonymize", shell_output("#{bin}/anonymize --help")
    system libexec/"bin/python", "-c", "from lingua import Language; print(Language.ENGLISH)"
    system libexec/"bin/python", "-c", "import anonymizer.install_models"
  end
end
