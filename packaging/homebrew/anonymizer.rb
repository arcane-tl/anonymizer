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
  url "https://github.com/arcane-tl/anonymizer/archive/refs/tags/v1.3.2.tar.gz"
  sha256 "d66ab95d7fd83940604ab56b505f067a7b355ac24031bbfed602ccbf1cbfbb80"
  version "1.3.2"
  # rev2: spaCy models via GitHub release wheels (not bare PyPI names)
  revision 2

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
    # Homebrew formula python (has pip). The formula venv is often created
    # --without-pip, so model installs must use: python -m pip --python=venv …
    Formula["python@3.12"].opt_libexec/"bin/python"
  end

  def install
    # Create a venv under libexec. Homebrew's Virtualenv#pip_install passes
    # --no-deps (for resource-based installs); we need full PyPI resolution.
    venv = virtualenv_create(libexec, "python3.12")
    # Drive pip against the venv interpreter so dependencies are installed.
    system host_python, "-m", "pip", "--python=#{venv_python}",
           "install", "--verbose", "--upgrade", buildpath.to_s
    # Entry point from pyproject [project.scripts]
    bin.install_symlink libexec/"bin/anonymize"
  end

  def model_loadable?(model)
    quiet_system venv_python, "-c",
                 "import spacy; spacy.load(#{model.inspect}); print('ok')"
  end

  def spacy_model_wheel_url(model)
    # spaCy models are NOT on PyPI as bare names (pip install en_core_web_lg → none).
    # Resolve the release wheel via the installed spaCy compatibility table.
    out = Utils.safe_popen_read(
      venv_python, "-c",
      <<~PY
        import sys
        model = #{model.inspect}
        try:
            from spacy.cli.download import get_compatibility, get_version
            from spacy.about import __download_url__ as base
            ver = get_version(model, get_compatibility())
            print(f"{base}/{model}-{ver}/{model}-{ver}-py3-none-any.whl")
        except Exception as e:
            print(f"ERR:{e}", file=sys.stderr)
            sys.exit(1)
      PY
    ).strip
    return if out.empty? || out.start_with?("ERR:")

    out
  end

  def install_spacy_model(model)
    return true if model_loadable?(model)

    url = spacy_model_wheel_url(model)
    if url
      ohai "Installing spaCy model #{model} from #{url}"
      if system host_python, "-m", "pip", "--python=#{venv_python}",
               "install", "--upgrade", url
        return true if model_loadable?(model)
      end
      opoo "pip install from wheel URL failed for #{model}"
    else
      opoo "Could not resolve wheel URL for #{model} (spaCy compatibility lookup)"
    end

    # Fallback: ensure pip exists in the venv, then spaCy CLI download
    system host_python, "-m", "pip", "--python=#{venv_python}",
           "install", "--upgrade", "pip", "setuptools", "wheel"
    ohai "Retry: #{venv_python} -m spacy download #{model}"
    if system venv_python, "-m", "spacy", "download", model
      return true if model_loadable?(model)
    end

    false
  end

  def post_install
    # Quality-first: large EN+FI models. Fall back md→sm. Always try *both*
    # languages (do not abort after English fails — that left FI missing).
    chains = {
      "English" => %w[en_core_web_lg en_core_web_md en_core_web_sm],
      "Finnish"  => %w[fi_core_news_lg fi_core_news_md fi_core_news_sm],
    }
    failures = []
    chains.each do |label, chain|
      ok = false
      chain.each do |model|
        if install_spacy_model(model)
          ohai "Using spaCy model #{model} (#{label})"
          ok = true
          break
        end
        opoo "Failed #{model} (#{label}) — trying next fallback if any"
      end
      failures << label unless ok
    end

    return if failures.empty?

    odie <<~EOS
      Could not install spaCy models for: #{failures.join(", ")}.
      Retry:
        brew postinstall anonymizer
      Or install wheels into the formula venv (example for spaCy 3.8.x):
        #{host_python} -m pip --python=#{venv_python} install \\
          https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl \\
          https://github.com/explosion/spacy-models/releases/download/fi_core_news_lg-3.8.0/fi_core_news_lg-3.8.0-py3-none-any.whl
      Then: anonymize doctor
    EOS
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

      spaCy models (default): en_core_web_lg, fi_core_news_lg
        (best NER quality; first install may take several minutes)
        Models are installed from GitHub release wheels (not bare PyPI names).

      If doctor reports missing models after install:
        brew update && brew reinstall anonymizer
        # or:
        brew postinstall anonymizer

      Manual install (spaCy 3.8.x wheels — adjust version if needed):
        #{host_python} -m pip --python=#{venv_python} install \\
          https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl \\
          https://github.com/explosion/spacy-models/releases/download/fi_core_news_lg-3.8.0/fi_core_news_lg-3.8.0-py3-none-any.whl

      Optional Swedish:
        #{host_python} -m pip --python=#{venv_python} install \\
          https://github.com/explosion/spacy-models/releases/download/sv_core_news_lg-3.8.0/sv_core_news_lg-3.8.0-py3-none-any.whl
        anonymize doc.pdf --lang sv

      Model guide: https://github.com/arcane-tl/anonymizer/blob/main/docs/models.md

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
