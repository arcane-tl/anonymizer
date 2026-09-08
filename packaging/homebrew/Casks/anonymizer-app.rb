# Homebrew Cask — installs Anonymizer.app into /Applications
#
# Token is anonymizer-app (not anonymizer) so the formula can link the CLI.
# Homebrew skips formula linking when a cask shares the same token.
#
#   brew install --cask anonymizer-app   # app + CLI (depends on formula)
#   brew install anonymizer              # CLI only
#
# Finder name is always Anonymizer.app.
# Release zip: packaging/macos/release-app.sh (Developer ID + notarized).

cask "anonymizer-app" do
  # update-for-release.sh rewrites version/sha256 at publish time.
  version "1.4.5"
  sha256 "fb01007d8b67fbacbca80d65c7b44ae455aaf0ad1915e164a528da22be1d8fef"

  url "https://github.com/arcane-tl/anonymizer/releases/download/v#{version}/Anonymizer-#{version}.zip"
  name "Anonymizer"
  desc "Drag-and-drop document anonymizer (uses anonymize CLI)"
  homepage "https://github.com/arcane-tl/anonymizer"

  depends_on formula: "anonymizer"
  # Homebrew 6+ disabled `depends_on macos: :catalina` (no replacement).
  app "Anonymizer.app"

  # Clear quarantine attrs if Gatekeeper marks the notarized zip oddly.
  # Use install-steps DSL (Homebrew 6 deprecates Ruby `postflight` blocks).
  postflight_steps do
    run "/usr/bin/xattr",
        args:           ["-cr", "/Applications/Anonymizer.app"],
        writable_paths: ["/Applications/Anonymizer.app"]
  end

  zap trash: [
    "~/Library/Caches/com.apple.iconservices.store",
  ]

  caveats <<~EOS
    Applications name: Anonymizer.app
    CLI: anonymize (formula anonymizer — linked on PATH)

    Install / upgrade both:
      brew install --cask anonymizer-app
      brew upgrade anonymizer anonymizer-app

    Migrating from the old cask token "anonymizer":
      brew uninstall --cask --force anonymizer
      # if still stuck: rm -rf "$(brew --prefix)/Caskroom/anonymizer"
      brew install --cask anonymizer-app
      brew link --overwrite anonymizer && hash -r

    If macOS says the app is "damaged":
      brew reinstall --cask anonymizer-app
    or:
      xattr -cr /Applications/Anonymizer.app
  EOS
end
