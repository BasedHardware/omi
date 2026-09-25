import CryptoKit
import Foundation

/// Who this Mac is, as the Omi backend understands the question.
///
/// One value, two spellings, and the backend derives the second from the first — which is the whole
/// reason this is a type rather than a helper next to each caller. Its contract is stated in
/// `backend/utils/client_device.py`:
///
/// ```
/// client_device_id = "{platform}_{hash}"
/// hash = first 8 hex chars of sha256(stable per-install id)
/// Headers: X-Device-Id-Hash + X-App-Platform
/// Absent headers => unknown device (all fields nullable)
/// ```
///
/// **Eight hex characters is a hard contract, not a style.** `build_client_device_id` ends in
/// `re.fullmatch(r'[0-9a-f]{8}', hash_norm)` and returns `None` — silently, with no error and no log
/// — for anything else. This app used to send a 32-character hash, which meant every request it ever
/// made resolved to an unknown device: no capture provenance, no per-device rate limiting, and
/// nothing the shipping Omi app would ever label "This Mac", because the id it compares against was
/// never built. Nothing failed loudly; the device context was simply always nil.
///
/// **The install id, not the hardware UUID.** The header used to be rooted in `IOPlatformUUID` on
/// the reasoning that hardware identity is the most durable thing available. It is — and it is the
/// wrong root anyway, for two reasons. The contract asks for a *per-install* id, and the shipping
/// macOS client honours that (`ClientDeviceService.deviceIdHash`), so a hardware-rooted hash would
/// name this Mac differently from the way the rest of Omi names it. And the raw `IOPlatformUUID` is
/// a global hardware serial; the less of it that leaves the machine in any form, the better.
///
/// The id lives in `UserDefaults` rather than the Keychain because it identifies a *capture source*,
/// not a user — no security decision rests on it — and a Keychain read on this path risks an
/// authorization prompt at launch for an app with no window to show one in.
///
/// **The key is `context.screenSync.installId` and it is not renamed.** Screen rows have been
/// uploaded under `macos_<that hash>` for weeks and the backend's storage key is
/// `"{clientDeviceId}-{rowId}"`. A new install id would not migrate that history; it would fork it,
/// and every row already up there would belong to a Mac that no longer appears to exist. The name is
/// a historical accident of which subsystem needed an identity first. That is a poor reason to keep
/// a name and a much worse reason to change one.
enum ClientDevice {

    /// `X-Device-Id-Hash`. Computed once — the value cannot change within a process, and re-hashing
    /// per request would be work done to reach the same answer.
    static let deviceIdHash: String = hash(of: installId(in: .standard))

    /// `{platform}_{hash}`, the form that appears in stored documents and in request bodies.
    static let clientDeviceId = "macos_\(deviceIdHash)"

    /// `X-App-Platform`. Beside the two above because the backend only resolves a device when it has
    /// both, and `build_client_device_id` accepts this spelling and no other.
    static let platform = "macos"

    /// Exposed for tests, which must be able to prove the shape without touching the real defaults.
    static func hash(of installId: String) -> String {
        let digest = SHA256.hash(data: Data(installId.utf8))
        return String(digest.map { String(format: "%02x", $0) }.joined().prefix(8))
    }

    static let installIdKey = "context.screenSync.installId"

    /// The stored install id, minting one on first use.
    ///
    /// **It must survive relaunches.** The backend keys capture provenance and deduplication off the
    /// resulting id: were it to rotate, every restart would look like a new Mac joining the account,
    /// the same screen row could be stored twice under two device ids, and "recorded on this Mac"
    /// would stop being answerable.
    static func installId(in defaults: UserDefaults) -> String {
        if let existing = defaults.string(forKey: installIdKey), !existing.isEmpty { return existing }
        let fresh = UUID().uuidString
        defaults.set(fresh, forKey: installIdKey)
        return fresh
    }
}
