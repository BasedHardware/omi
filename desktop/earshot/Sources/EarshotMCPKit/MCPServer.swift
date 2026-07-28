import EarshotCore
import Foundation

/// The stdio MCP server Claude Code and Claude Desktop talk to.
///
/// Transport is line-delimited JSON-RPC 2.0: one request object per line in, one response object per
/// line out. **The output handle carries the protocol** — nothing but response lines may ever reach
/// it, so every diagnostic in this file goes to stderr.
public final class MCPServer {
    public static let protocolVersion = "2024-11-05"
    public static let serverName = "earshot"
    public static let serverVersion = "1.0.0"

    private let store: EarshotStore?

    /// `store` is nil when nothing has been captured yet; the tools explain that in prose.
    public init(store: EarshotStore?) {
        self.store = store
    }

    // MARK: - Transport

    /// Reads lines from `input`, writes response lines to `output`. Returns when input closes.
    ///
    /// Reads incrementally through the handle rather than `readLine()`, which would bind this loop to
    /// the process's own stdin and make the class untestable with a pipe.
    public func run(input: FileHandle = .standardInput, output: FileHandle = .standardOutput) {
        var buffer = Data()
        while true {
            let chunk = input.availableData
            if chunk.isEmpty { break } // EOF: the client closed the pipe.
            buffer.append(chunk)
            while let newline = buffer.firstIndex(of: 0x0A) {
                let line = Data(buffer[buffer.startIndex..<newline])
                buffer.removeSubrange(buffer.startIndex...newline)
                respond(to: line, on: output)
            }
        }
        // A final frame with no trailing newline still deserves an answer.
        if !buffer.isEmpty {
            respond(to: buffer, on: output)
        }
    }

    private func respond(to lineData: Data, on output: FileHandle) {
        guard let raw = String(data: lineData, encoding: .utf8) else {
            write(RPC.error(id: nil, code: RPC.Code.parseError, message: "Parse error: line is not UTF-8"),
                  to: output)
            return
        }
        guard let response = handle(line: raw) else { return }
        write(response, to: output)
    }

    private func write(_ response: String, to output: FileHandle) {
        guard let data = (response + "\n").data(using: .utf8) else { return }
        do {
            try output.write(contentsOf: data)
        } catch {
            // A closed pipe is the client going away, not a crash.
            Self.note("write failed: \(error)")
        }
    }

    // MARK: - Dispatch

    /// Testable single-message path. Returns the response line, or nil for a notification.
    /// Never throws: a tool failure is reported to the model as a result, not as a crash.
    public func handle(line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }

        guard let frame = RPC.json(line: trimmed) else {
            return RPC.error(id: nil, code: RPC.Code.parseError, message: "Parse error")
        }
        guard let request = RPC.request(from: frame) else {
            return RPC.error(id: frame["id"], code: RPC.Code.invalidRequest, message: "Invalid Request")
        }
        // Notifications carry no id and take no reply — answering one desynchronizes the client.
        if request.isNotification || request.method.hasPrefix("notifications/") { return nil }

        switch request.method {
        case "initialize":
            return RPC.result(id: request.id, [
                "protocolVersion": .string(Self.protocolVersion),
                "capabilities": ["tools": [:]],
                "serverInfo": ["name": .string(Self.serverName), "version": .string(Self.serverVersion)],
            ])

        case "ping":
            return RPC.result(id: request.id, [:])

        case "tools/list":
            let tools = Tools.all.map { tool in
                JSONValue.object([
                    "name": .string(tool.name),
                    "description": .string(tool.description),
                    "inputSchema": tool.inputSchema,
                ])
            }
            return RPC.result(id: request.id, ["tools": .array(tools)])

        case "tools/call":
            return callTool(request)

        default:
            return RPC.error(id: request.id,
                             code: RPC.Code.methodNotFound,
                             message: "Method not found: \(request.method)")
        }
    }

    private func callTool(_ request: RPCRequest) -> String {
        guard let name = request.params?["name"]?.stringValue else {
            return RPC.error(id: request.id,
                             code: RPC.Code.invalidParams,
                             message: "tools/call requires a string \"name\"")
        }
        do {
            let text = try Tools.call(name: name, arguments: request.params?["arguments"], store: store)
            return RPC.result(id: request.id, Self.content(text, isError: false))
        } catch {
            // MCP models a tool failure as a *result* so the model can read the reason and recover;
            // a JSON-RPC error would be swallowed by the client instead.
            Self.note("tool \(name) failed: \(error)")
            return RPC.result(id: request.id, Self.content(Self.describe(error), isError: true))
        }
    }

    private static func content(_ text: String, isError: Bool) -> JSONValue {
        [
            "content": [["type": "text", "text": .string(text)]],
            "isError": .bool(isError),
        ]
    }

    private static func describe(_ error: Error) -> String {
        if let localized = error as? LocalizedError, let description = localized.errorDescription {
            return description
        }
        // `localizedDescription` on a bare Swift error is the useless "operation couldn't be
        // completed" boilerplate; the case name is what the model can actually act on.
        return String(describing: error)
    }

    /// Diagnostics go to stderr only. Anything printed to stdout corrupts the protocol stream and
    /// Claude drops the connection.
    static func note(_ message: String) {
        guard let data = "earshot: \(message)\n".data(using: .utf8) else { return }
        try? FileHandle.standardError.write(contentsOf: data)
    }
}
