import Foundation

// Backend origin handling, ported from `react-native/src/v5BackendOrigin.ts`.

public let CLOUD_BACKEND_ORIGIN = "https://api.omi.me"
public let LOCAL_BACKEND_ORIGIN = "http://127.0.0.1:8787"
public let V5_BACKEND_URL_ENV = "OMI_V5_BACKEND_URL"

public struct BackendOrigin: Equatable, Sendable {
    /// Lowercased hostname with IPv6 brackets stripped.
    public let hostname: String
    /// `scheme://host[:port]` with the default port elided.
    public let origin: String
    /// Port string, empty when the scheme default applies.
    public let port: String
    public let isSecure: Bool

    public init(
        hostname: String, origin: String, port: String, isSecure: Bool
    ) {
        self.hostname = hostname
        self.origin = origin
        self.port = port
        self.isSecure = isSecure
    }
}

/// Port of `parseOrigin`. Accepts exactly `http(s)://host[:port][/` —
/// bracketed IPv6 is limited to `::1`, ports to 1...65535, default ports are
/// elided. Returns nil for anything else.
public func parseOrigin(_ value: String) -> BackendOrigin? {
    let scheme: String
    if value.lowercased().hasPrefix("https:") {
        scheme = "https:"
    } else if value.lowercased().hasPrefix("http:") {
        scheme = "http:"
    } else {
        return nil
    }
    var rest = String(value.dropFirst(scheme.count))
    if !rest.hasPrefix("//") { return nil }
    rest = String(rest.dropFirst(2))
    // The TS regex allows a single trailing slash only.
    if rest.hasSuffix("/") {
        rest = String(rest.dropLast())
    }
    guard !rest.isEmpty else { return nil }
    guard
        !rest.contains("/"), !rest.contains("?"), !rest.contains("#"),
        !rest.contains("@")
    else { return nil }

    let rawHostname: String
    let rawPort: String?
    if rest.hasPrefix("[") {
        guard let close = rest.firstIndex(of: "]") else { return nil }
        rawHostname = String(rest[...close])
        let after = rest[rest.index(after: close)...]
        if after.isEmpty {
            rawPort = nil
        } else if after.hasPrefix(":") {
            rawPort = String(after.dropFirst())
        } else {
            return nil
        }
    } else if let colon = rest.firstIndex(of: ":") {
        rawHostname = String(rest[..<colon])
        rawPort = String(rest[rest.index(after: colon)...])
    } else {
        rawHostname = rest
        rawPort = nil
    }

    let isBracketed = rawHostname.hasPrefix("[")
    let hostname = rawHostname
        .trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        .lowercased()
    if isBracketed {
        // The validated v5 origin only ever stamps loopback IPv6.
        guard hostname == "::1" else { return nil }
    } else {
        guard !hostname.isEmpty else { return nil }
        for scalar in hostname.unicodeScalars {
            let ok =
                (scalar.value >= 97 && scalar.value <= 122)  // a-z
                || (scalar.value >= 48 && scalar.value <= 57)  // 0-9
                || scalar == "." || scalar == "-"
            guard ok else { return nil }
        }
    }

    var port = rawPort ?? ""
    if let rawPort {
        guard !rawPort.isEmpty, let portNumber = Int(rawPort),
            (1...65535).contains(portNumber)
        else { return nil }
        let isSecure = scheme == "https:"
        if (isSecure && portNumber == 443) || (!isSecure && portNumber == 80) {
            port = ""
        }
    }

    let host = isBracketed ? "[\(hostname)]" : hostname
    let origin = "\(scheme)//\(host)\(port.isEmpty ? "" : ":\(port)")"
    return BackendOrigin(
        hostname: hostname, origin: origin, port: port,
        isSecure: scheme == "https:"
    )
}

/// Port of `isLoopbackHostname`.
public func isLoopbackHostname(_ hostname: String) -> Bool {
    let normalized = hostname
        .trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        .lowercased()
    return normalized == "localhost" || normalized == "127.0.0.1"
        || normalized == "::1"
}
