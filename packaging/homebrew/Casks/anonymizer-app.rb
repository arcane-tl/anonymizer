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
  version "1.4.0"
  sha256 "9906acd5046fca3880666a531f5fcf3086539456bdb346fd2b6546edd9ebc18b"

  url "https://github.com/arcane-tl/anonymizer/releases/download/v#{version}/Anonymizer-#{version}.zip"
  name "Anonymizer"
  desc "Drag-and-drop document anonymizer (uses anonymize CLI)"
  homepage "https://github.com/arcane-tl/anonymizer"

  depends_on formula: "anonymizer"
  depends_on macos: :catalina
  app "Anonymizer.app"

  postflight do
    system_command "/usr/bin/xattr",
                   args: ["-cr", "#{appdir}/Anonymizer.app"]
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
