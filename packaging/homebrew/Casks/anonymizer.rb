# Homebrew Cask — installs Anonymizer.app into /Applications
#
#   brew tap arcane-tl/anonymizer
#   brew install anonymizer              # CLI (formula)
#   brew install --cask anonymizer       # GUI (this cask)
#
# Finder name is always Anonymizer.app — same product as the CLI "anonymize".
# Release zip should be Developer ID–signed + notarized (see packaging/macos/release-app.sh).

cask "anonymizer" do
  version "1.1.0"
  sha256 "f8bcd2f613c458d2fce27908b8297078a1c8d670a43aa17ab1ce377d10cb2e6f"

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
    Anonymizer.app calls the anonymize CLI (from: brew install anonymizer).
    Ensure `anonymize` works in Terminal before using drag-and-drop.

    If macOS says the app is "damaged" (old unsigned zip):
      brew reinstall --cask anonymizer
    or:
      xattr -cr /Applications/Anonymizer.app
  EOS
end
