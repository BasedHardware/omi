import Foundation
import OmiNetwork

/// The caller ID: verifying a number by a Twilio call with a code, deleting it, past calls, quota.
/// Flutter `phone_setup_number_page.dart`, `phone_setup_verify_page.dart`, `phone_call_settings_page.dart`.
public extension PhoneCallStore {
    struct Verification: Equatable, Sendable {
        public enum Status: Equatable, Sendable {
            case calling, inProgress
            /// Fifteen polls (30 s) without a code; polling goes on until the timeout.
            case missed
            case verified
            case timedOut
        }

        public let phoneNumber: String
        /// Typed on the keypad during Twilio's call; `nil`: follow the voice on the call.
        public let code: String?
        public internal(set) var status: Status
    }

    /// The number Twilio's verification call comes from (Flutter shows the same).
    static let verificationCallerID = "+1 (415) 723-4000"

    /// Numbers, then quota and past calls.
    func load() async {
        await loadNumbers()
        guard unavailable == nil else { return }
        async let quota: Void = loadQuota()
        async let history: Void = loadHistory()
        _ = await (quota, history)
    }

    func loadNumbers() async {
        do {
            numbers = try await api.verifiedPhoneNumbers()
            unavailable = nil
        } catch let APIError.http(status, body) where status == 402 || status == 403 {
            unavailable = PhoneCallErrorDetail(body: body) ?? .message("HTTP \(status)")
            numbers = []
        } catch {
            // Offline: keep what is shown.
        }
        numbersLoaded = true
    }

    func loadQuota() async {
        if let fresh = try? await api.phoneCallQuota() { quota = fresh }
    }

    func loadHistory() async {
        if let fresh = try? await api.phoneCallConversations(limit: 20, offset: 0) { history = fresh }
    }

    /// `false` when the number is still there (`deletePhoneNumber` refused).
    @discardableResult
    func deleteNumber(_ id: String) async -> Bool {
        do {
            try await api.deletePhoneNumber(id: id)
            numbers.removeAll { $0.id == id }
            return true
        } catch {
            return false
        }
    }

    /// Asks Twilio to call `phoneNumber` (E.164). `true`: the call is on its way (or the number was
    /// verified already); poll with `pollVerification()`.
    @discardableResult
    func startVerification(_ phoneNumber: String) async -> Bool {
        isStartingVerification = true
        verificationFailure = nil
        defer { isStartingVerification = false }
        do {
            let started = try await api.startPhoneVerification(phoneNumber: phoneNumber)
            let alreadyVerified = started.status == "verified"
            verification = Verification(
                phoneNumber: phoneNumber, code: started.validationCode, status: alreadyVerified ? .verified : .calling
            )
            if alreadyVerified { await loadNumbers() }
            return true
        } catch {
            verificationFailure = .server(Self.detail(of: error))
            return false
        }
    }

    /// Every 2 s for 60 s (the verify screen's task; leaving the screen cancels it). After two polls
    /// the call is in progress, after fifteen it counts as missed, after thirty it timed out.
    func pollVerification() async {
        guard let started = verification, started.status != .verified else { return }
        setVerification(.calling)
        for poll in 1 ... 31 {
            try? await Task.sleep(for: timing.verificationPoll)
            guard !Task.isCancelled, verification?.phoneNumber == started.phoneNumber else { return }
            if poll > 30 {
                setVerification(.timedOut)
                return
            }
            if poll == 2, verification?.status == .calling { setVerification(.inProgress) }
            if poll == 15, verification?.status == .inProgress { setVerification(.missed) }
            if (try? await api.checkPhoneVerification(phoneNumber: started.phoneNumber)) == true {
                setVerification(.verified)
                await loadNumbers()
                return
            }
        }
    }

    /// Try again after a missed call or a timeout: a new Twilio call, then polling.
    func retryVerification() async {
        guard let number = verification?.phoneNumber else { return }
        if await startVerification(number) {
            await pollVerification()
        } else {
            setVerification(.timedOut)
        }
    }

    func cancelVerification() {
        verification = nil
        verificationFailure = nil
    }

    private func setVerification(_ status: Verification.Status) {
        verification?.status = status
    }
}
