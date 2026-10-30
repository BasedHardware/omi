import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Home's "Connect Google Calendar?" card: the connections that make Omi useful (calendar, mail,
/// Apple Health), one at a time while the account is new or nothing is connected yet. "Connect"
/// signs in right here; "Not now" hides that one for good (Settings › Apps & integrations still
/// has it).
@MainActor
enum ConnectSuggestion {
    /// Most useful first.
    static let order = ["google_calendar", "gmail", AppleHealthStore.key]
    /// Days after the first Home visit in which the card is offered while something is connected.
    static let newAccountDays = 14

    /// What to suggest now: unconnected, not dismissed, and only early on (or while nothing at all
    /// is connected).
    static func ids(
        connected: Set<String>, dismissed: Set<String>, firstSeen: Date?, now: Date = .now
    ) -> [String] {
        let isNew = firstSeen.map { now.timeIntervalSince($0) < Double(newAccountDays) * 86400 } ?? true
        guard isNew || connected.isEmpty else { return [] }
        return order.filter { !connected.contains($0) && !dismissed.contains($0) }
    }

    /// `ids(connected:…)` from the stores and Home's stored state.
    static func ids(_ capabilities: CapabilitiesStore, _ health: AppleHealthStore, dismissed: String, firstHomeAt: Double) -> [String] {
        let connected = capabilities.integrations.filter(\.isConnected).map(\.id) + (health.isConnected ? [AppleHealthStore.key] : [])
        return ids(
            connected: Set(connected), dismissed: Set(dismissed.split(separator: ",").map(String.init)),
            firstSeen: firstHomeAt == 0 ? nil : Date(timeIntervalSince1970: firstHomeAt)
        )
    }

    /// Notes the first Home visit and refreshes what is connected.
    static func prepare(_ capabilities: CapabilitiesStore, _ health: AppleHealthStore, firstHomeAt: Binding<Double>) async {
        if firstHomeAt.wrappedValue == 0 { firstHomeAt.wrappedValue = Date.now.timeIntervalSince1970 }
        async let apps: Void = capabilities.load()
        async let healthState: Void = health.load()
        _ = await (apps, healthState)
    }

    static func name(_ id: String) -> String {
        id == AppleHealthStore.key ? "Apple Health" : CapabilitiesList.name(id)
    }

    static func purpose(_ id: String) -> String {
        id == AppleHealthStore.key ? L("nativeCapabilityHealth") : L(CapabilitiesList.purposeKey(id))
    }
}

/// The card itself: kicker, the question, why it helps (or why connecting did not work), and
/// Connect / Not now.
struct ConnectSuggestionCard: View {
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(AppleHealthStore.self) private var health
    @Environment(\.webAuthenticationSession) private var webAuthentication
    let id: String
    let onDismiss: () -> Void

    var body: some View {
        DecisionCard(
            kicker: DecisionCard.Kicker(symbol: "link", text: L("nativeForYouConnect"), color: DS.Palette.agent),
            title: L("nativeForYouConnectTitle", ConnectSuggestion.name(id)),
            subtitle: subtitle,
            pulses: isConnecting,
            pills: [
                DecisionCard.Pill(title: L("nativeConnect"), isPrimary: true) { Task { await connect() } },
                DecisionCard.Pill(title: L("notNow"), action: onDismiss),
            ],
            // The card itself connects too (no dead tap).
            onTap: { Task { await connect() } }
        )
    }

    private var isConnecting: Bool {
        id == AppleHealthStore.key ? health.phase == .connecting : capabilities.connecting == id
    }

    private var subtitle: String {
        if id != AppleHealthStore.key, let failure = capabilities.failures[id], !isConnecting {
            return CapabilitiesList.message(failure, name: ConnectSuggestion.name(id))
        }
        return ConnectSuggestion.purpose(id)
    }

    private func connect() async {
        if id == AppleHealthStore.key {
            await health.connect()
        } else if let integration = capabilities.integrations.first(where: { $0.id == id }) {
            await CapabilitiesList.connect(integration, store: capabilities, webAuthentication: webAuthentication)
        }
    }
}
