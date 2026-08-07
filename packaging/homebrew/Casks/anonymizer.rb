# Homebrew Cask — installs Anonymizer.app into /Applications
#
#   brew tap arcane-tl/anonymizer
#   brew install anonymizer              # CLI (formula)
#   brew install --cask anonymizer       # GUI (this cask)
#
# Finder name is always Anonymizer.app — same product as the CLI "anonymize".
# Release zip should be Developer ID–signed + notarized (see packaging/macos/release-app.sh).

cask "anonymizer" do
  version "1.1.1"
  sha256 "9e59722bdbfcc8147f3596b75d700747a6670884cc88dd73075c5c94b6fca287"

  url "https://github.com/arcane-tl/anonymizer/releases/download/v#{version}/Anonymizer-#{version}.zip"
  name "Anonymizer"
  desc "Drag-and-drop document anonymizer (uses anonymize CLI)"
  homepage "https://github.com/arcane-tl/anonymizer"

  depends_on formula: "anonymizer"
  depends_on macos: :catalina
  app "Anonymizer.app"

  # Belt-and-suspenders: clear download quarantine so Gatekeeper uses the
  # stapled notarization ticket (or local trust) without a false "damaged" dialog.
  postflight do
    system_command "/usr/bin/xattr",
                   args: ["-cr", "#{appdir}/Anonymizer.app"]
  end

  zap trash: [
    "~/Library/Caches/com.apple.iconservices.store",
  ]

  caveats <<~EOS
    Anonymizer.app calls the anonymize CLI (formula: brew install anonymizer).

    CLI and app share the token "anonymizer" but are separate packages.
    `brew upgrade anonymizer` upgrades the CLI only. To upgrade the app:
      brew upgrade --cask anonymizer

    Full upgrade (recommended):
      brew update
      brew upgrade anonymizer && brew upgrade --cask anonymizer

    If macOS says the app is "damaged":
      brew reinstall --cask anonymizer
    or:
      xattr -cr /Applications/Anonymizer.app
  EOS
end
