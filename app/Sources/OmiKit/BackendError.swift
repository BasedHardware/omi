import Foundation

// Backend error taxonomy, ported from `chatClient.ts` (ChatBackendError,
// chatErrorCopy, chatSessionLost, chatHistoryErrorCopy) and
// `nativeTransportError.ts` (transport failure kinds). Client failures that
// mean "this session is no longer usable" are classified centrally so every
// surface reacts identically.

public struct ChatBackendError: Error, Sendable {
    public let status: Int
    public let backendCode: String
    public let retryable: Bool
    public let action: String
    public let retryAfterSeconds: Int?

    public init(
        status: Int, backendCode: String, retryable: Bool, action: String,
        retryAfterSeconds: Int?
    ) {
        self.status = status
        self.backendCode = backendCode
        self.retryable = retryable
        self.action = action
        self.retryAfterSeconds = retryAfterSeconds
    }
}

/// Transport-layer failures raised by `BackendTransport` implementations.
/// These mirror the native error codes the JS layer classified by string
/// (`OMI_HTTP_UNCONFIGURED`, `OMI_HTTP_UNAUTHORIZED`, `OMI_HTTP_TRANSPORT`).
public enum TransportFailure: Error, Sendable, Equatable {
    /// No usable native HTTP configuration (unauthenticated, no origin).
    case unconfigured
    /// The configured session is not authorized for the request.
    case unauthorized
    /// The request could not be carried (DNS, TLS, timeout, reset).
    case transportFailed
    /// The caller cancelled the request.
    case cancelled
}

public func chatErrorCopy(_ error: Error?) -> String {
    guard let error = error as? ChatBackendError else {
        return "Message not sent. Check your connection and try again."
    }
    if error.action == "reauthenticate" || error.status == 401 {
        return "Sign in again to continue."
    }
    if error.status == 403 || error.backendCode == "forbidden" {
        return "Chat is not available for this account."
    }
    if error.status == 429 {
        return error.retryAfterSeconds == nil
            ? "Too many requests. Try again shortly."
            : "Too many requests. Try again in \(error.retryAfterSeconds!) seconds."
    }
    if error.retryable || error.status == 503 {
        return "Omi is temporarily unavailable. Try again."
    }
    return "This request cannot be completed."
}

/// A chat failure that means "this client no longer holds a usable cloud
/// session": a backend 401 / reauthenticate action, or transport
/// credentials that never resolved.
public func chatSessionLost(_ error: Error) -> Bool {
    if let backendError = error as? ChatBackendError {
        return backendError.status == 401
            || backendError.action == "reauthenticate"
    }
    return error is TransportFailure && !isCancellation(error)
}

public func chatHistoryErrorCopy(_ error: Error) -> String {
    if let backendError = error as? ChatBackendError {
        return chatErrorCopy(backendError)
    }
    switch error {
    case TransportFailure.unconfigured, TransportFailure.unauthorized:
        return "Sign in again to continue."
    case TransportFailure.transportFailed:
        return "Omi is temporarily unavailable. Try again."
    default:
        return "Chat history could not be loaded. Check your connection and try again."
    }
}

public func isCancellation(_ error: Error) -> Bool {
    if let failure = error as? TransportFailure { return failure == .cancelled }
    return error is CancellationError
}
