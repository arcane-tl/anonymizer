import Foundation
import FoundationModels

/// anonymizer-fm-check — Apple Foundation Models helper for AI redaction check.
///
/// Usage:
///   anonymizer-fm-check --available     → prints AVAILABLE / UNAVAILABLE… (exit 0/2)
///   anonymizer-fm-check                 → read JSON {"prompt":"..."} from stdin,
///                                         print model text response on stdout

@available(macOS 26.0, *)
func availabilityLine() -> (ok: Bool, line: String) {
    let model = SystemLanguageModel.default
    switch model.availability {
    case .available:
        return (true, "AVAILABLE")
    case .unavailable(let reason):
        return (false, "UNAVAILABLE \(String(describing: reason))")
    @unknown default:
        return (false, "UNAVAILABLE unknown")
    }
}

@available(macOS 26.0, *)
func generate(prompt: String) async throws -> String {
    let model = SystemLanguageModel.default
    guard case .available = model.availability else {
        throw NSError(
            domain: "anonymizer-fm-check",
            code: 2,
            userInfo: [NSLocalizedDescriptionKey: "Foundation Model unavailable"]
        )
    }
    let session = LanguageModelSession(
        model: model,
        instructions: "You output JSON only for privacy redaction review. No markdown fences."
    )
    let response = try await session.respond(to: prompt)
    return response.content
}

@available(macOS 26.0, *)
@main
struct AnonymizerFMCheck {
    static func main() async {
        let args = Array(CommandLine.arguments.dropFirst())
        if args.contains("--available") || args.contains("-a") {
            let (ok, line) = availabilityLine()
            print(line)
            exit(ok ? 0 : 2)
        }

        let data = FileHandle.standardInput.readDataToEndOfFile()
        guard !data.isEmpty else {
            fputs("error: empty stdin; expected JSON {\"prompt\": \"...\"}\n", stderr)
            exit(1)
        }
        struct Req: Decodable { let prompt: String }
        let prompt: String
        do {
            if let obj = try? JSONDecoder().decode(Req.self, from: data) {
                prompt = obj.prompt
            } else if let s = String(data: data, encoding: .utf8) {
                prompt = s
            } else {
                fputs("error: could not decode stdin\n", stderr)
                exit(1)
            }
        }
        do {
            let out = try await generate(prompt: prompt)
            print(out)
        } catch {
            fputs("error: \(error)\n", stderr)
            exit(1)
        }
    }
}
