# Homebrew Cask — installs Anonymizer.app into /Applications
#
#   brew tap arcane-tl/anonymizer
#   brew install anonymizer              # CLI (formula)
#   brew install --cask anonymizer       # GUI (this cask)
#
# Finder name is always Anonymizer.app — same product as the CLI "anonymize".

cask "anonymizer" do
  version "1.0.0"
  sha256 "c5b7ae96b9a70aa5fccb193a9933570d236ca2226a70901bb6a3f37d43e8dfcf"

  url "https://github.com/arcane-tl/anonymizer/releases/download/v#{version}/Anonymizer-#{version}.zip"
  name "Anonymizer"
  desc "Drag-and-drop document anonymizer (uses anonymize CLI)"
  homepage "https://github.com/arcane-tl/anonymizer"

  depends_on formula: "anonymizer"
  depends_on macos: ">= :catalina"

  app "Anonymizer.app"

  zap trash: [
    "~/Library/Caches/com.apple.iconservices.store",
  ]

  caveats <<~EOS
    Anonymizer.app calls the anonymize CLI (from: brew install anonymizer).
    Ensure `anonymize` works in Terminal before using drag-and-drop.
  EOS
end
