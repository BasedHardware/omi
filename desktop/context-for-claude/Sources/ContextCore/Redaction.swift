import Foundation

// MARK: - Redaction

/// Everything that must never reach the database in the clear.
///
/// Screen capture reads whatever the user is looking at, which sooner or later means an OAuth
/// callback URL, a `.env` file, a token pasted into a terminal, or a password field caught
/// mid-render. Every frame's text is indexed into FTS and handed to a model on request, so a
/// credential that lands here is not merely stored — it is quoted back, into every context that
/// asks, forever. The database has no encryption and no expiry for text.
///
/// Both halves of the defence live in `ContextCore` rather than in the capture code, because a
/// policy that can only be exercised by running the app and looking at a screen is a policy nobody
/// checks:
///
/// - ``scrub(_:)`` strips credential-shaped *values* out of text that is otherwise worth keeping.
/// - ``isSensitiveWindow(app:title:)`` refuses whole windows that exist to display secrets.
///
/// The bias throughout is to over-redact. A redacted value costs one search result; a leaked one is
/// permanent and unrecallable. What that bias does *not* license is redacting prose: the point of
/// this database is that its text stays searchable, so every rule below needs a credential *shape*
/// — a named field, a known key prefix, an auth scheme — and never a keyword alone. The word
/// "password" in a sentence is a word.
public enum Redaction {

    /// What replaces a credential.
    ///
    /// Deliberately readable rather than a blank: a human reading the timeline must be able to tell
    /// "the field was empty" from "this was a secret and we dropped it", and the sentence around it
    /// stays searchable — `?code=<redacted>` still tells Claude an OAuth callback happened.
    ///
    /// It is also what makes ``scrub(_:)`` idempotent: `<` and `>` are excluded from every value
    /// pattern, so a marker is never itself a candidate for redaction.
    public static let marker = "<redacted>"

    /// Replaces credential-shaped values in text with a marker, preserving surrounding context.
    ///
    /// Rules are applied in a fixed order and the order is load-bearing: contextual rules
    /// (`name=value`, `name: value`, `Bearer …`) run before standalone key-prefix rules, so a token
    /// that is both — `api_key=sk-…` — is replaced once as the value of its field rather than twice,
    /// leaving `api_key=<redacted>` instead of `api_key=sk-<redacted>` or a doubled marker.
    public static func scrub(_ text: String) -> String {
        guard !text.isEmpty else { return text }
        return redactionRules.reduce(text) { partial, rule in rule.applied(to: partial) }
    }
}

// MARK: - Rule engine

/// One pattern plus which part of it is the secret.
///
/// Matching is done with `NSRegularExpression` and applied by hand rather than through
/// `stringByReplacingMatches`, for two reasons: only one capture group is replaced (the value, never
/// the field name that gives it meaning), and some rules need evidence a regex cannot express —
/// ``requires`` is how "a bearer token contains a digit, an English word does not" is written.
private struct RedactionRule {
    let regex: NSRegularExpression
    /// Which capture group holds the secret. Group 0 — the whole match — when there is no
    /// surrounding context worth keeping.
    let group: Int
    /// Extra evidence before a match counts as a credential. Nil means the pattern is proof enough.
    let requires: (@Sendable (String) -> Bool)?

    init(
        _ pattern: String,
        group: Int = 1,
        options: NSRegularExpression.Options = [.caseInsensitive],
        requires: (@Sendable (String) -> Bool)? = nil
    ) {
        // `try!` on a literal pattern. A malformed one is a typo in this file that fails on the
        // first scrub of any run or test, loudly and identically every time; the alternative —
        // skipping a rule that failed to compile — ships a redactor that silently redacts nothing,
        // which is the exact failure this file exists to prevent.
        self.regex = try! NSRegularExpression(pattern: pattern, options: options)
        self.group = group
        self.requires = requires
    }

    func applied(to text: String) -> String {
        let subject = text as NSString
        let matches = regex.matches(
            in: text,
            options: [],
            range: NSRange(location: 0, length: subject.length)
        )
        guard !matches.isEmpty else { return text }

        var result = text
        // Back to front: replacing a later range cannot move an earlier one, so every remaining
        // range stays valid without recomputing a single offset.
        for match in matches.reversed() {
            let range = match.range(at: group)
            guard range.location != NSNotFound, range.length > 0 else { continue }
            if let requires, !requires(subject.substring(with: range)) { continue }
            guard let replaceable = Range(range, in: result) else { continue }
            result.replaceSubrange(replaceable, with: Redaction.marker)
        }
        return result
    }
}

// MARK: - Pattern vocabulary

/// Where a field name may start, and where it must end.
///
/// `_` and `-` are deliberately *not* in the lookbehind class, which is the whole trick: it lets the
/// interesting word be the tail of a longer name — `OPENAI_API_KEY`, `x-api-key`,
/// `stripe_secret_key` — while still refusing to find `code` inside `zipcode` or `barcode`. A
/// lookahead does the same at the other end, so `secretHandshake = …` is a camelCase identifier
/// rather than a field named `secret`.
///
/// Both are fixed-width assertions rather than an explicit `(?:[A-Za-z0-9]+[_-])*` prefix, and that
/// is a performance requirement, not a style choice: a repeated prefix group makes every start
/// position walk the rest of the line, which turned a 70 KB screen into a minute of CPU per frame.
private let keyStart = #"(?<![A-Za-z0-9])"#
private let keyEnd = #"(?![A-Za-z0-9])"#

/// How far a value extends. Stops at whitespace, at the delimiters that end a query parameter, a
/// JSON string, a shell word or a cookie pair — and at `<`, which is what makes the marker
/// un-redactable and ``Redaction/scrub(_:)`` idempotent.
private let credentialValue = #"[^\s"'`<>&,;)\]}]+"#

private let authScheme = #"(?:bearer|basic|token|digest)"#

/// Field names that mean "the next thing is a credential" when assigned with `=` — the shape of a
/// URL query, a form body, a cookie pair and a shell assignment.
///
/// `code` and `state` are here because of the confirmed leak: an OAuth callback URL, this app's own
/// loopback sign-in among them, stored whole. They are ordinary English words, which is survivable
/// only because `=` is a strong signal on its own; they are deliberately absent from
/// ``labeledKeys``, where `Status code: 404` would otherwise lose the 404.
private let assignedKeys = """
client[_-]?secret|access[_-]?token|refresh[_-]?token|id[_-]?token|auth[_-]?token|api[_-]?token|\
session[_-]?(?:id|key|token)|api[_-]?key|apikey|secret[_-]?key|private[_-]?key|app[_-]?secret|\
authorization|password|passwd|passphrase|pwd|secret|token|bearer|signature|session|state|code|auth|sig
"""

/// Field names that mean the same thing when labelled with `:` — JSON, YAML, HTTP headers, and the
/// `password: hunter2` line of a README.
///
/// Narrower than ``assignedKeys`` on purpose. A colon is how English writes a label, so every
/// ambiguous word (`code`, `state`, `session`, `auth`) is dropped from this list; what remains is
/// words that have no innocent reading in front of a colon. The residual cost is accepted: a page
/// titled "reset your password: a guide" loses one word.
private let labeledKeys = """
client[_-]?secret|access[_-]?token|refresh[_-]?token|id[_-]?token|auth[_-]?token|api[_-]?token|\
api[_-]?key|apikey|secret[_-]?key|private[_-]?key|app[_-]?secret|authorization|password|passwd|\
passphrase|pwd|secret|token|bearer
"""

/// True when a value carries a digit — the cheapest separator between a token and a word.
///
/// Used only by the bare-scheme rule, where the pattern alone would turn "Basic authentication is
/// enabled" into "Basic <redacted> is enabled". Real bearer credentials are base64 or hex and
/// effectively always contain a digit; a fourteen-letter English word does not.
private let containsDigit: @Sendable (String) -> Bool = { value in
    value.unicodeScalars.contains { CharacterSet.decimalDigits.contains($0) }
}

// MARK: - The rules

/// Ordered: contextual rules first, then standalone keys, then multi-line blocks.
///
/// What is deliberately *not* here is a generic entropy test. "Any long random-looking string" would
/// take every git SHA, UUID, base64 thumbnail, file hash and minified identifier on screen with it,
/// which is most of what a developer's screen contains — it would empty the database to catch a
/// class the prefix rules below already catch by name.
private let redactionRules: [RedactionRule] = [

    // `postgres://user:hunter2@host`, `https://x-access-token:ghp_…@github.com`. The password is the
    // only part removed; the scheme, the user and the host are what make the row worth having.
    // The value class excludes `/` and whitespace, so an ordinary URL followed by an email address
    // later in the text cannot be mistaken for one of these.
    RedactionRule(#"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+.-]*://[^\s:/@]+:([^\s:/@]+)@"#),

    // `?code=…&state=…`, `api_key=…`, `Cookie: session=…`, `export OPENAI_API_KEY=…`.
    RedactionRule(#"\#(keyStart)(?:\#(assignedKeys))\#(keyEnd)["']?\s*=\s*["']?(\#(credentialValue))"#),

    // `"api_key": "sk-…"`, `password: hunter2`, `Authorization: Bearer eyJ…`. The quotes on either
    // side and the auth scheme are matched but not captured, so a JSON pair keeps its shape and the
    // header still says which scheme it carried.
    RedactionRule(
        #"\#(keyStart)(?:\#(labeledKeys))\#(keyEnd)["']?\s*:\s*(?:\#(authScheme)\s+)?["']?(\#(credentialValue))"#
    ),

    // A bare `Bearer <token>` with no header name in front of it — how curl commands and API docs
    // on screen usually show one.
    RedactionRule(
        #"(?<![A-Za-z0-9])\#(authScheme)\s+([A-Za-z0-9\-._~+/=]{12,})"#,
        requires: containsDigit
    ),

    // Standalone keys. Each keeps its public prefix and loses everything after it: `sk-<redacted>`
    // tells a human which credential was on screen, which is the difference between a timeline they
    // can act on and one that just has a hole in it.
    RedactionRule(#"(?<![A-Za-z0-9])sk-(?:ant-)?([A-Za-z0-9_-]{12,})"#),
    RedactionRule(#"(?<![A-Za-z0-9])github_pat_([A-Za-z0-9_]{20,})"#),
    RedactionRule(#"(?<![A-Za-z0-9])gh[pousr]_([A-Za-z0-9]{16,})"#),
    RedactionRule(#"(?<![A-Za-z0-9])omi_mcp_([A-Za-z0-9_-]{8,})"#),
    RedactionRule(#"(?<![A-Za-z0-9])xox[abporse]-([A-Za-z0-9-]{10,})"#),
    RedactionRule(#"(?<![A-Za-z0-9])(?:sk|rk)_(?:live|test)_([A-Za-z0-9]{8,})"#),
    // Case-sensitive: `AIza`, `AKIA` and `eyJ` are fixed base64 prefixes, and matching them
    // case-insensitively would start taking ordinary words that happen to share the letters.
    RedactionRule(#"(?<![A-Za-z0-9])AIza([A-Za-z0-9_-]{20,})"#, options: []),
    RedactionRule(#"(?<![A-Za-z0-9])AKIA([0-9A-Z]{16})"#, options: []),

    // A JWT is replaced whole. Its header segment decodes to `{"alg":…}` and is not a secret, but it
    // is also not readable text — keeping it would leave a long base64 smear in the timeline for no
    // gain, unlike `sk-` where the prefix is the useful part.
    RedactionRule(
        #"(?<![A-Za-z0-9_-])(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?)"#,
        options: []
    ),

    // A PEM block: header and footer kept, body removed. When the footer is missing — OCR cut the
    // window off, the key scrolled — the body runs to the end of the text and all of it goes. That
    // is the right way round: a truncated private key is still a private key.
    RedactionRule(#"(-----BEGIN[^\n]*PRIVATE KEY-----)([\s\S]*?)(?:-----END[^\n]*-----|\z)"#, group: 2),
]

// MARK: - Window policy

extension Redaction {

    /// True when a window should never be captured at all.
    ///
    /// Redaction is a net with holes in it — a password field renders as dots, a secret can be
    /// displayed with no field name near it, and OCR mangles exactly the high-entropy strings the
    /// patterns above depend on. So the surfaces whose entire purpose is to show credentials are
    /// never read in the first place, and this is the check that decides which.
    ///
    /// This is the half of the gate the user cannot turn off. The half they configure lives in
    /// ``ExclusionSet``, and the two are composed in ``CapturePolicy/exclusion(for:using:)`` — call
    /// that rather than this, unless there is genuinely no exclusion state to hand.
    ///
    /// `app` is matched as **either** a bundle identifier or a display name: bundle ids drift across
    /// versions and rebrands while product names do not, and the caller usually has both. Callers
    /// with both should ask twice. `title` is matched on its own, because a credential surface is
    /// often an ordinary app on an extraordinary window — a browser on a sign-in page, System
    /// Settings on the passwords pane.
    public static func isSensitiveWindow(app: String?, title: String?) -> Bool {
        let app = normalized(app)
        let title = normalized(title)

        if let app {
            if foldedBundleIdentifiers.contains(app) { return true }
            if excludedNameFragments.contains(where: { app.contains($0) }) { return true }
            // System Settings is an ordinary app until the pane is one of these, and the pane is
            // only knowable from the title — so this rule stays gated on the app instead of
            // becoming a global "security" title fragment that would exclude every privacy policy
            // and security advisory the user ever reads.
            if settingsIdentifiers.contains(app),
                let title,
                sensitiveSettingsPanes.contains(where: { title.contains($0) })
            {
                return true
            }
        }

        if let title, sensitiveTitleFragments.contains(where: { title.contains($0) }) { return true }
        return false
    }

    // MARK: Excluded applications

    /// Surfaces that must never be read. Password managers are the reason this list exists at all —
    /// OCRing an unlocked vault would put real secrets in a plain-text database. The screenshot and
    /// screen-share tools are here because their windows are either our own capture UI reflected
    /// back or a picker showing someone else's screen.
    ///
    /// The membership itself lives in ``ExclusionCatalog`` rather than here, and that is load-bearing:
    /// the Settings pane shows the same password managers and the same login screen as excluded and
    /// *not user-removable*, and two copies of that list is how a checkbox the user cannot clear ends
    /// up meaning nothing. This file consumes the catalog; it does not keep a second opinion of it.
    private static let excludedBundleIdentifiers: Set<String> =
        Set(ExclusionCatalog.lockedApps.map(\.bundleID))
        .union(ExclusionCatalog.screenCaptureTools.map(\.bundleID))

    /// Bundle IDs drift between versions and rebrands; these product names do not.
    ///
    /// The password-manager fragments come from the catalog for the same reason as the identifiers
    /// above. The three added here are screen-capture tooling, which is refused unconditionally and
    /// deliberately never offered in Settings — nothing is gained by letting a user opt into
    /// recording their own screen recorder.
    private static let excludedNameFragments =
        ExclusionCatalog.lockedNameFragments + ["screenshot", "screen sharing", "snagit"]

    private static let settingsIdentifiers: Set<String> = [
        "com.apple.systempreferences", "com.apple.systemsettings",
        // The same app arriving as a display name rather than a bundle id.
        "system settings", "system preferences",
    ]

    /// System Settings is ordinary until the user is on a pane that shows credentials or the exact
    /// permission grants this app depends on. The pane is only knowable from the window title.
    ///
    /// The second row is the permission panes, and it is there because the live database contained
    /// OCR of **Screen & System Audio Recording** — the full list of which apps may watch this
    /// machine — while matching none of the words in the first row (`docs/ocr-quality.md` §7). Each
    /// of these panes is a list of what every app on the machine is allowed to see, which is not a
    /// credential but is the map to all of them. Over-matching costs nothing here: the whole list
    /// only applies when the front app is System Settings.
    private static let sensitiveSettingsPanes = [
        "password", "privacy", "security", "touch id", "users & groups", "login",
        "recording", "full disk", "accessibility", "automation", "camera", "microphone",
        "location", "passkey", "wallet", "apple id", "apple account",
    ]

    /// Titles that mean the window is a credential surface whatever app is drawing it.
    ///
    /// Every entry here is a deliberate over-exclusion: a developer with `login.ts` open loses those
    /// frames, and so does a tab reading about two-factor authentication. That is the trade this
    /// file is set up to make — the same list is what keeps a live sign-in form, a recovery phrase,
    /// and an API-key page out of the database, and those are unrecoverable in a way a missing
    /// frame never is.
    private static let sensitiveTitleFragments = [
        "password", "passphrase", "passcode", "keychain", "credential",
        "sign in", "sign-in", "signin", "log in", "log-in", "login",
        "2fa", "two-factor", "two factor", "otp", "verification code", "security code",
        "authenticator", "api key", "secret key", "private key", "access token",
        "seed phrase", "recovery phrase", "wallet",
    ]

    /// Case folded once here rather than per comparison: this runs on every capture tick for the
    /// life of the machine, and the literals above are kept in the casing Apple and each vendor
    /// actually ship so they can be checked against a real bundle.
    private static let foldedBundleIdentifiers = Set(
        excludedBundleIdentifiers.map { $0.lowercased() }
    )

    private static func normalized(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return trimmed.isEmpty ? nil : trimmed
    }
}
