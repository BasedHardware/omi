import Foundation
import Combine

/// Persisted configuration for the AI Clone plugin service.
///
/// Three values, two of them stored in the macOS Keychain:
/// 1. Plugin service URL (e.g. https://my-omi-clone.example.com) — stored in
///    UserDefaults (non-secret; the URL is the destination, not a credential).
/// 2. Plugin bearer token — stored in Keychain via AICloneKeychain. Matches
///    the AI_CLONE_PLUGIN_TOKEN env var set on the plugin service. Sent as
///    `Authorization: Bearer <token>` on every request from desktop → plugin.
/// 3. The user's `omi_dev_...` developer API key — stored in Keychain via
///    AICloneKeychain. Forwarded to the plugin's `/setup` so the plugin can
///    call the backend persona chat endpoint on the user's behalf.
///
/// Why two stores: UserDefaults is a plaintext plist on disk readable by
/// any process running as the user. Storing the bearer token or the
/// developer API key there exposed them to other apps and to backup
/// exfiltration. Identified by maintainer security review on PR #8528 —
/// moved to Keychain (encrypted at rest, only this app's bundle id can
/// read). The plugin URL is non-secret and stays in UserDefaults.
///
/// Migration: a previous build stored both secrets in UserDefaults. On
/// first launch under this code, `migrateFromUserDefaultsIfNeeded()`
/// detects the old entries, copies them to Keychain, and deletes the
/// UserDefaults copy. Migration is idempotent — re-running on an already-
/// migrated machine is a no-op.
///
/// Display snapshot of the user-account plugin's rate-limit
/// state. Populated by polling /status (every ~30s) and
/// surfaced in the Connect sheet's "Reply as me" section.
/// plan §8: ban-warning + rate-limit visibility.
struct RateLimitDisplay: Equatable {
    var maxPerHour: Int = 30
    var inWindowCount: Int = 0
    var isBlocked: Bool = false
    var secondsUntilNextSlot: Int = 0

    static let empty = RateLimitDisplay()

    /// "3 / 30 sent this hour" -- what the user sees at a glance.
    var formatted: String {
        return "\(inWindowCount) / \(maxPerHour) sent this hour"
    }

    /// True when the user is approaching the cap (>= 80%) or
    /// currently blocked. Drives the warning banner color.
    var isNearCap: Bool {
        if isBlocked { return true }
        // cubic review 4618627789 P2: the previous
        // `Int(Double(maxPerHour) * 0.8)` truncates toward zero
        // and produces incorrect early warnings for small
        // maxPerHour values. For example, maxPerHour=1 yields
        // threshold 0 (permanently near-cap), maxPerHour=2
        // yields threshold 1 (50%, not 80%). Use integer
        // arithmetic: inWindowCount * 5 >= maxPerHour * 4
        // matches the documented ">= 80%" threshold exactly
        // for all positive maxPerHour values.
        return maxPerHour > 0 && inWindowCount * 5 >= maxPerHour * 4
    }
}

/// Published via @Published so SwiftUI views update reactively when these
/// change (e.g. when the user saves new values from a settings sheet).
@MainActor
final class AICloneConfig: ObservableObject {
    static let shared = AICloneConfig()

    /// Task that periodically polls the user-account plugin's
    /// /status endpoint to refresh rate-limit + daily-sent
    /// counters. Started by applyUserAccountDiscovery() when
    /// the user is signed in; cancelled by
    /// stopTelegramUserAccountStatusPoll() on sign-out.
    /// Accessible from tests to verify the poll lifecycle.
    internal var telegramStatusPollTask: Task<Void, Never>?
    /// Poll interval for the user-account plugin's /status
    /// endpoint. 30s is a reasonable balance between
    /// freshness and chatter (the badge changes are not
    /// time-critical -- the rolling 60-min cap means the
    /// user has plenty of warning time).
    private static let telegramStatusPollIntervalSeconds: UInt64 = 30

    /// Legacy UserDefaults keys. Kept here so the one-time migration
    /// can find them. New code reads/writes via AICloneKeychain.
    private enum LegacyDefaultsKeys {
        static let bearerToken = "ai_clone_plugin_bearer_token"
        static let devApiKey = "ai_clone_omi_dev_api_key"
    }

    private enum DefaultsKeys {
        static let pluginURL = "ai_clone_plugin_url"
        // On-disk state for the user-account plugin: whether the
        // user has finished the Telethon session setup and which
        // chats they have auto-reply enabled for. The session
        // string itself is NEVER stored in UserDefaults — it lives
        // in Keychain only (see setTelegramUserSession below).
        static let telegramAccountEnabled = "ai_clone.telegram_user_enabled"
    }

    private let defaults: UserDefaults

    @Published var pluginURL: String {
        didSet { defaults.set(pluginURL, forKey: DefaultsKeys.pluginURL) }
    }

    // MARK: - Telegram user-account plugin (plan §7)

    /// Whether the user has finished the Telethon session setup.
    /// `false` means the Connect sheet shows a "Generate session"
    /// button. `true` means the session is in Keychain and the
    /// user-account plugin is ready to use.
    ///
    /// The session string itself is NOT stored in this property;
    /// it lives in Keychain via setTelegramUserSession / get.
    @Published var telegramAccountEnabled: Bool = false {
        didSet {
            defaults.set(
                telegramAccountEnabled,
                forKey: DefaultsKeys.telegramAccountEnabled
            )
        }
    }

    /// Account metadata populated from Telethon's get_me() after
    /// the session is connected. Surfaced to the UI as a
    /// "logged in as Alice (+1...)" badge.
    @Published var telegramAccountMeta: [String: String] = [:]
    /// plan §8: rate-limit state surfaced from the user-account
    /// plugin's /status endpoint. The desktop uses this to show
    /// "X/30 messages sent this hour" + a warning when the
    /// account is blocked by a Telegram FLOOD_WAIT.
    @Published var telegramRateLimit: RateLimitDisplay = .empty
    /// Daily count of AI replies sent. plan §8: "Daily 'messages
    /// sent today' counter on the plugin card."
    @Published var telegramMessagesSentToday: Int = 0
    /// plan: desktop-side mirror of the user-account plugin's
    /// auto-reply state. Updated by the 30s /status poll (any-user-
    /// enabled flag from the plugin). Bound to the toggle in
    /// ConnectSheet.userAccountSection. The plugin is the source
    /// of truth (in simple_storage.users[].auto_reply_enabled);
    /// this is just the UI cache so the toggle reflects current
    /// state without a UI flicker on app launch.
    @Published var telegramAutoReplyEnabled: Bool = false
    /// True while a /toggle POST is in flight. Drives the spinner
    /// in the connect sheet's user-account section.
    @Published var telegramAutoReplyInFlight: Bool = false

    /// Set the Telethon session string (from session_string_generator.py
    /// subprocess stdout). The session lives in Keychain (encrypted
    /// at rest, only readable when the screen is unlocked). After
    /// setting, the desktop's Connect sheet can hand control to the
    /// user-account plugin.
    ///
    /// SECURITY (plan §7): the session string is a fully-compromising
    /// identity secret. It is NEVER written to UserDefaults, NEVER
    /// logged, and NEVER included in any HTTP response. The desktop
    /// holds it only in Keychain; the user-account plugin process
    /// receives it via a one-shot stdin pipe.
    func setTelegramUserSession(_ session: String) throws {
        if session.isEmpty {
            // Empty string: clear the keychain entry AND flip the
            // enabled flag off. Used by the "Sign out" path.
            //
            // SECURITY (cubic review 4615559812 P1): MUST NOT swallow
            // the Keychain delete failure with `try?`. If the OS
            // refuses the deletion (keychain locked, ACL denied,
            // disk full), the secret would remain while the UI
            // claims "signed out". On next launch, init() would
            // see the session still in Keychain, flip
            // `telegramAccountEnabled` back on, and the user
            // would think their session was signed out when
            // it actually wasn't. Propagate the error so callers
            // can retry or surface a clear failure to the user.
            do {
                try AICloneKeychain.delete(.telegramUserSession)
            } catch {
                log("AICloneConfig: failed to delete Telethon session from Keychain during sign-out: \(error)")
                throw error
            }
            telegramAccountEnabled = false
            telegramAccountMeta = [:]
            // cubic review 4618627789 P2: also clear the
            // rate-limit + daily-sent counters so the UI
            // doesn't show stale metrics from the previous
            // account.
            stopTelegramUserAccountStatusPoll()
            telegramRateLimit = .empty
            telegramMessagesSentToday = 0
            telegramAutoReplyEnabled = false
            telegramAutoReplyInFlight = false
            return
        }
        try AICloneKeychain.set(.telegramUserSession, session)
        telegramAccountEnabled = true
    }

    /// Read the Telethon session from Keychain. Returns nil if no
    /// session is stored. The user-account plugin's stack-runner
    /// reads this and pipes it into the plugin subprocess's stdin
    /// at startup.
    func getTelegramUserSession() throws -> String? {
        return try AICloneKeychain.get(.telegramUserSession)
    }

    /// Clear the Telethon session from Keychain. Used by the "Sign
    /// out" path. After this, the user-account plugin can't connect
    /// until a new session is generated.
    /// Clear the Telethon session from Keychain. Used by the "Sign
    /// out" path. After this, the user-account plugin can't connect
    /// until a new session is generated.
    ///
    /// cubic review 4615559812 P1: must propagate Keychain delete
    /// failures (do NOT swallow with `try?`). A failed delete leaves
    /// the credential on disk while the app reports signed-out, and
    /// the next launch's init() will flip `telegramAccountEnabled`
    /// back on. The UI must handle the thrown error.
    func clearTelegramUserSession() throws {
        do {
            try AICloneKeychain.delete(.telegramUserSession)
        } catch {
            log("AICloneConfig: failed to delete Telethon session from Keychain: \(error)")
            throw error
        }
        telegramAccountEnabled = false
        telegramAccountMeta = [:]
        // cubic review 4618627789 P2: also clear the
        // rate-limit + daily-sent counters so the UI
        // doesn't show stale metrics from the previous
        // account.
        stopTelegramUserAccountStatusPoll()
        telegramRateLimit = .empty
        telegramMessagesSentToday = 0
        telegramAutoReplyEnabled = false
        telegramAutoReplyInFlight = false
    }

    @Published var bearerToken: String {
        didSet {
            // Persist to Keychain. An empty string clears it.
            do {
                try AICloneKeychain.set(.pluginBearerToken, bearerToken)
            } catch {
                // Keychain failures are rare (the user has denied access
                // once) and shouldn't crash the app. Log and keep the
                // in-memory value — the user can retry on next save.
                NSLog("AICloneConfig: Keychain set failed: \(error)")
            }
        }
    }

    @Published var omiDevApiKey: String {
        didSet {
            do {
                try AICloneKeychain.set(.devApiKey, omiDevApiKey)
            } catch {
                NSLog("AICloneConfig: Keychain set failed: \(error)")
            }
        }
    }

    /// True if the current config was auto-discovered from the plugin's
    /// discovery file (rather than manually entered by the user).
    /// Drives the UI banner: "Plugin discovered automatically".
    @Published var isAutoDiscovered: Bool = false

    /// True when the plugin is running in dev mode (the discovery file
    /// said so). In dev mode, the dev API key is optional because the
    /// local mock persona doesn't validate it.
    @Published var pluginDevMode: Bool = false
    /// The backend URL the plugin uses for persona calls. When the
    /// plugin is local (localhost), the desktop creates the persona + API
    /// key on that backend instead of prod. Prevents persona_id mismatch.
    @Published var discoveryBackendURL: String? = nil

    /// The PUBLIC URL of the plugin (the tunnel / external address
    /// Telegram or Meta use to reach the plugin from outside). Used by
    /// the desktop's ConnectSheet as the `publicBaseUrl` payload to the
    /// plugin's /setup endpoint — Telegram's webhook must be reachable
    /// from the internet, so we can't pass the local `pluginURL`
    /// (loopback). Falls back to pluginURL when no tunnel is configured
    /// (same-machine-only testing, where Telegram isn't involved).
    @Published var publicBaseURL: String? = nil

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.pluginURL = defaults.string(forKey: DefaultsKeys.pluginURL) ?? ""
        // Default-initialize secrets to empty before calling any method
        // that uses self. Swift requires all stored properties set before
        // self is used.
        self.bearerToken = ""
        self.omiDevApiKey = ""

        // Migrate any legacy UserDefaults values BEFORE reading from
        // Keychain so that if a migration happens we read the moved
        // value rather than nil. Migration is best-effort and
        // idempotent; failures don't block init.
        migrateFromUserDefaultsIfNeeded(defaults: defaults)

        // Load current values from Keychain (may be empty).
        self.bearerToken = (try? AICloneKeychain.get(.pluginBearerToken)) ?? ""
        self.omiDevApiKey = (try? AICloneKeychain.get(.devApiKey)) ?? ""

        // Load the user-account plugin's state. The session string
        // itself is read from Keychain; the on/off flag from
        // UserDefaults. If the session is in Keychain but the flag
        // is off, we flip the flag on (the session is the more
        // authoritative source of truth).
        self.telegramAccountEnabled = defaults.bool(
            forKey: DefaultsKeys.telegramAccountEnabled
        )
        if let _ = try? AICloneKeychain.get(.telegramUserSession) {
            self.telegramAccountEnabled = true
        }

        // Discovery is now applied EXPLICITLY via applyDiscovery() —
        // called from app startup (OmiApp.swift), not from init. P2
        // (cubic): init() previously called applyDiscoveryIfAvailable()
        // unconditionally, which read ~/.config/omi/ai-clone-plugin.json
        // and mutated the injected UserDefaults + Keychain. That broke
        // the hermetic contract of `defaults` (any test using a stub
        // UserDefaults would have its state mutated by a real file on
        // the test machine) and made unit tests non-deterministic.
    }

    /// Read `~/.config/omi/ai-clone-plugin.json` and fill any empty
    /// fields (pluginURL, bearerToken). Called from app startup
    /// (OmiApp.swift), not from init, so unit tests can construct
    /// AICloneConfig without touching the real discovery file.
    ///
    /// For the dev API key: the discovery file doesn't contain it
    /// (it's user-specific). If `devMode == true` in the discovery
    /// file, the plugin is paired with a local mock persona that
    /// doesn't validate the key — so we leave the field empty and
    /// the UI will show a lighter "optional" indicator.
    func applyDiscovery() {
        let path = PluginDiscovery.filePath
        log("AICloneConfig: checking discovery file at \(path)")
        guard let discovery = PluginDiscovery.read() else {
            log("AICloneConfig: no discovery file found")
            return
        }

        // Use the LOCAL pluginURL (NOT the tunnel publicURL) for the
        // desktop client's API base URL. Desktop and plugin run on the
        // same machine, so /health, /setup, /status, /toggle should hit
        // the plugin directly over loopback / LAN. The publicURL (the
        // tunnel) is needed by Telegram/Meta to reach the plugin from
        // outside, but routing our own control traffic through the
        // tunnel adds latency and exposes control calls to a third
        // party. Falls back to pluginURL when publicURL is absent
        // (same-machine-only testing).
        //
        // P1 from cubic AI review (PR #8682): the previous code used
        // `discovery.publicURL ?? discovery.pluginURL`, which meant a
        // configured tunnel would silently route all desktop control
        // calls through the external tunnel. Switched to pluginURL.
        let discoveryURL = discovery.pluginURL

        var changed = false

        // Cubic review 4614064929 P1: previously, the in-memory
        // `self.pluginURL` and `self.bearerToken` were only updated
        // when the local copies were EMPTY. After the first auto-
        // discovery both fields are persisted and non-empty, so later
        // plugin restarts that change the local port or bearer
        // token are silently ignored in-memory. The desktop then
        // hits the OLD URL while passing NEW publicBaseURL/
        // pluginDevMode — a mixed-config bug.
        //
        // Fix: ALWAYS refresh the in-memory copies. The UserDefaults
        // (pluginURL) and Keychain (bearerToken) WRITES still gate
        // on `isEmpty` so we don't clobber a user's manual override
        // on disk. But the in-memory copy always reflects the live
        // plugin. If the user manually edits, their edit takes
        // effect for this session; on next launch, discovery
        // refreshes again.
        let isFirstDiscovery = self.pluginURL.isEmpty && self.bearerToken.isEmpty

        if isFirstDiscovery {
            // First run: persist the discovery values to disk so
            // they survive across launches.
            defaults.set(discoveryURL, forKey: DefaultsKeys.pluginURL)
            try? AICloneKeychain.set(.pluginBearerToken, discovery.bearerToken)
            changed = true
        }
        // Always refresh in-memory.
        self.pluginURL = discoveryURL
        self.bearerToken = discovery.bearerToken

        // Refresh the rest of the discovery-derived fields (publicBaseURL,
        // pluginDevMode, discoveryBackendURL) unconditionally so the
        // desktop always reflects the live plugin instance. (P2 cubic
        // review 4601373760.)
        self.publicBaseURL = discovery.publicURL ?? discovery.pluginURL
        self.pluginDevMode = discovery.devMode
        self.discoveryBackendURL = discovery.omiBaseURL

        if changed {
            // Use the app's log() function so it appears in /tmp/omi-dev.log
            // (NSLog goes to unified logging only, not the dev log file).
            log("AICloneConfig: auto-discovered plugin at \(discoveryURL) (type=\(discovery.pluginType), devMode=\(discovery.devMode))")
            self.isAutoDiscovered = true
        }
    }

    /// Apply the user-account plugin's discovery file. Called from
    /// app startup (OmiApp.swift) when the "Reply as me" mode is
    /// enabled. Distinct from `applyDiscovery()` (which handles the
    /// bot plugin's `ai-clone-plugin.json`) because the user-account
    /// plugin authenticates as the user's PERSONAL Telegram account
    /// and has a different discovery schema.
    func applyUserAccountDiscovery() {
        let path = PluginDiscovery.userAccountFilePath
        log("AICloneConfig: checking user-account discovery file at \(path)")
        guard let info = PluginDiscovery.readUserAccount() else {
            log("AICloneConfig: no user-account discovery file found")
            return
        }
        // Persist URL + bearer to disk (first-time only) and
        // ALWAYS refresh in-memory. Same pattern as applyDiscovery.
        let isFirstDiscovery = self.pluginURL.isEmpty && self.bearerToken.isEmpty
        if isFirstDiscovery {
            defaults.set(info.pluginURL, forKey: DefaultsKeys.pluginURL)
            try? AICloneKeychain.set(.pluginBearerToken, info.bearerToken)
        }
        self.pluginURL = info.pluginURL
        self.bearerToken = info.bearerToken
        // User-account plugin doesn't write publicURL/omiBaseURL to
        // its discovery file (no tunnel — runs locally; uses the
        // Omi backend at https://api.omi.me by default). These are
        // not relevant for the user-account plugin but we keep them
        // populated for any UI that reads them.
        self.publicBaseURL = nil
        self.pluginDevMode = false
        self.discoveryBackendURL = nil
        // Account metadata from the Telethon session's get_me().
        // Surfaced in the Connect sheet as "Logged in as Alice
        // (+1...)" so the user can confirm they're using the right
        // Telegram account.
        if let phone = info.phone, let name = info.name {
            self.telegramAccountMeta = [
                "phone": phone,
                "name": name,
                "device_label": info.deviceLabel ?? "Omi Desktop",
            ]
        }
        // The session is the source of truth. Flip the flag on if
        // the user-account discovery file exists.
        self.telegramAccountEnabled = true
        log("AICloneConfig: auto-discovered user-account plugin at \(info.pluginURL) (phone=\(info.phone ?? "?"), name=\(info.name ?? "?"))")
        // Start the periodic /status poll so the rate-limit
        // badge + daily-sent counter stay current. The poll
        // does a one-shot fetch first so the UI populates
        // immediately rather than waiting 30s for the first
        // tick.
        startTelegramUserAccountStatusPoll()
    }

    /// Begin polling the user-account plugin's /status
    /// endpoint every 30s. Updates telegramRateLimit and
    /// telegramMessagesSentToday on each successful poll.
    /// Replaces any existing poll (idempotent).
    func startTelegramUserAccountStatusPoll() {
        // Idempotent: cancel any in-flight poll first.
        stopTelegramUserAccountStatusPoll()
        let pollInterval = Self.telegramStatusPollIntervalSeconds
        telegramStatusPollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollTelegramUserAccountStatus()
                // Sleep with cancellation check.
                do {
                    try await Task.sleep(nanoseconds: pollInterval * 1_000_000_000)
                } catch {
                    return  // Task was cancelled during sleep
                }
            }
        }
    }

    /// Stop polling the user-account plugin's /status
    /// endpoint. Safe to call when no poll is active.
    func stopTelegramUserAccountStatusPoll() {
        telegramStatusPollTask?.cancel()
        telegramStatusPollTask = nil
    }

    /// One poll iteration. Fetches /status, decodes the
    /// rate-limit + daily-sent fields, and updates the
    /// @Published state. Errors are swallowed (logged) so
    /// the poll survives transient network blips.
    private func pollTelegramUserAccountStatus() async {
        guard telegramAccountEnabled,
              !pluginURL.isEmpty,
              !bearerToken.isEmpty
        else {
            return  // not configured -- nothing to poll
        }
        do {
            let resp = try await AICloneClient.shared.status(
                baseURL: pluginURL, bearerToken: bearerToken
            )
            // Update @Published state on the main actor.
            // (We're already @MainActor-isolated.)
            // cubic review 4619143030 P2: nested RateLimitState
            // fields are optional. We only update the @Published
            // state for fields the plugin actually reported;
            // missing fields are KEPT at their current value
            // rather than reset to .empty / 0. This avoids
            // flapping the badge if a partial /status response
            // arrives (e.g. a transient decode error on the
            // plugin side, or a graceful degradation during
            // a reload).
            if let rl = resp.rateLimit {
                let new = RateLimitDisplay(
                    maxPerHour: rl.maxPerHour ?? telegramRateLimit.maxPerHour,
                    inWindowCount: rl.inWindowCount ?? telegramRateLimit.inWindowCount,
                    isBlocked: rl.isBlocked ?? telegramRateLimit.isBlocked,
                    secondsUntilNextSlot: rl.secondsUntilNextSlot ?? telegramRateLimit.secondsUntilNextSlot,
                )
                telegramRateLimit = new
            }
            if let count = resp.messagesSentToday {
                telegramMessagesSentToday = count
            }
            // plan: /status exposes auto_reply_enabled (any-user-
            // enabled aggregate). Update the toggle's UI cache
            // so it reflects plugin state without a flicker.
            // If the field is missing from the response (older
            // plugin version), we KEEP the current value rather
            // than resetting to false.
            if let enabled = resp.autoReplyEnabled {
                telegramAutoReplyEnabled = enabled
            }
        } catch {
            // Transient failures are expected (the plugin
            // may be restarting). Log at debug level so the
            // log isn't spammed; the next tick will retry.
            log("AICloneConfig: /status poll failed (will retry): \(error.localizedDescription)")
        }
    }

    /// Move legacy UserDefaults-stored secrets into the Keychain.
    /// Called once at init; idempotent.
    private func migrateFromUserDefaultsIfNeeded(defaults: UserDefaults) {
        // Cubic review 4614064929 P1: the previous `try?` swallowed
        // BOTH the keychain-write failure AND the subsequent
        // UserDefaults-remove step. If the keychain write fails
        // (e.g. user denied keychain access), the legacy plaintext
        // secret stays in UserDefaults indefinitely — a security
        // regression masked by silent failure.
        //
        // Fix: separate the two steps. Always delete the legacy
        // UserDefaults entry, even if the keychain write fails. The
        // keychain write is best-effort but logged. This way the
        // plaintext exposure window is closed as soon as the
        // migration runs, regardless of subsequent failure.
        migrateLegacySecret(
            .pluginBearerToken,
            defaultsKey: LegacyDefaultsKeys.bearerToken,
            defaults: defaults,
        )
        migrateLegacySecret(
            .devApiKey,
            defaultsKey: LegacyDefaultsKeys.devApiKey,
            defaults: defaults,
        )
    }

    private func migrateLegacySecret(
        _ keychainKey: AICloneKeychain.Key,
        defaultsKey: String,
        defaults: UserDefaults,
    ) {
        do {
            try AICloneKeychain.migrateFromUserDefaults(
                keychainKey,
                defaultsKey: defaultsKey,
                defaults: defaults
            )
        } catch {
            // Keychain write failed. Still delete the legacy
            // plaintext entry — the keychain set is best-effort
            // and we don't want the secret lingering in
            // UserDefaults if the keychain is broken. Log the
            // failure so the operator knows migration didn't
            // complete cleanly.
            NSLog(
                "AICloneConfig: keychain migration for \(defaultsKey) failed: \(error). Will remove plaintext entry anyway."
            )
        }
        // Delete the plaintext entry unconditionally. If the
        // keychain write succeeded, this is the second half of the
        // migration. If it failed, this is the security-mitigation
        // half — better to have no secret than a plaintext one.
        defaults.removeObject(forKey: defaultsKey)
    }

    /// True if the plugin URL is set and at least looks like a URL.
    var isPluginURLConfigured: Bool {
        guard !pluginURL.isEmpty else { return false }
        guard let url = URL(string: pluginURL) else { return false }
        return url.scheme?.lowercased() == "http" || url.scheme?.lowercased() == "https"
    }

    /// True if the bearer token is set (non-empty).
    var isBearerTokenConfigured: Bool { !bearerToken.isEmpty }

    /// True if the dev API key is set (non-empty).
    var isDevApiKeyConfigured: Bool { !omiDevApiKey.isEmpty }

    /// True if the plugin service is reachable (URL + bearer configured).
    /// The dev API key is NOT required for this check — it's only needed
    /// at /setup time (inside the Connect sheet). The Connect button is
    /// gated on this property, so requiring the dev API key here would
    /// prevent the user from even opening the Connect sheet.
    var isPluginReady: Bool {
        isPluginURLConfigured && isBearerTokenConfigured
    }

    /// True if all values needed to call the plugin are present,
    /// INCLUDING the dev API key. Used for the status indicator in
    /// PluginURLCard (shows whether the user still needs to provide
    /// the dev API key), NOT for gating the Connect button.
    ///
    /// In dev mode (plugin paired with local mock persona), the dev API
    /// key is optional — the mock doesn't validate it.
    var isFullyConfigured: Bool {
        if pluginDevMode {
            return isPluginReady
        }
        return isPluginReady && isDevApiKeyConfigured
    }
}