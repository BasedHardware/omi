import Foundation

/// Accept only the loopback auth endpoint's origin-form request target.
/// Query strings are allowed; path prefixes, encoded aliases, absolute URLs,
/// and fragments are not.
public func isLoopbackAuthCallbackRequestTarget(_ target: String) -> Bool {
    guard !target.contains("#") else { return false }
    let path = target.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false).first
    return path == "/callback"
}
