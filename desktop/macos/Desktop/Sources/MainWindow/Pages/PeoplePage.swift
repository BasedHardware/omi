import AppKit
import Combine
import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

// MARK: - People Intelligence Models
//
// Decoded from `~/Library/Application Support/Omi/users/<uid>/people_intelligence.json`,
// which the backend writes offline. The JSON mixes snake_case (`generated_at`) with
// camelCase (`lastTouch`, `openThreads`, `contactName`), so each type maps keys
// explicitly and tolerates missing/optional fields rather than trusting a global
// key-decoding strategy.

struct PeopleIntelligenceFile: Decodable, Sendable {
  let generatedAt: String?
  let stats: PeopleStats?
  let people: [PeopleIntelPerson]

  enum CodingKeys: String, CodingKey {
    case generatedAt = "generated_at"
    case stats
    case people
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    generatedAt = try c.decodeIfPresent(String.self, forKey: .generatedAt)
    stats = try c.decodeIfPresent(PeopleStats.self, forKey: .stats)
    people = (try c.decodeIfPresent([PeopleIntelPerson].self, forKey: .people)) ?? []
  }
}

struct PeopleStats: Decodable, Equatable, Sendable {
  let people: Int
  let featured: Int
  let multichannel: Int
  let channels: Int
  let dropped: Int

  enum CodingKeys: String, CodingKey {
    case people, featured, multichannel, channels, dropped
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    people = (try c.decodeIfPresent(Int.self, forKey: .people)) ?? 0
    featured = (try c.decodeIfPresent(Int.self, forKey: .featured)) ?? 0
    multichannel = (try c.decodeIfPresent(Int.self, forKey: .multichannel)) ?? 0
    channels = (try c.decodeIfPresent(Int.self, forKey: .channels)) ?? 0
    dropped = (try c.decodeIfPresent(Int.self, forKey: .dropped)) ?? 0
  }
}

struct PersonLastTouch: Decodable, Equatable, Sendable {
  let channel: String
  let date: String

  enum CodingKeys: String, CodingKey { case channel, date }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    channel = (try c.decodeIfPresent(String.self, forKey: .channel)) ?? ""
    date = (try c.decodeIfPresent(String.self, forKey: .date)) ?? ""
  }
}

/// LinkedIn appears in the JSON as either a bare URL string or an object
/// (`{url, company, position}`), so this decodes from both shapes.
struct PersonLinkedIn: Decodable, Equatable, Sendable {
  let url: String?
  let company: String?
  let position: String?

  enum CodingKeys: String, CodingKey { case url, company, position }

  init(from decoder: Decoder) throws {
    if let single = try? decoder.singleValueContainer(), let raw = try? single.decode(String.self) {
      url = raw
      company = nil
      position = nil
      return
    }
    let c = try decoder.container(keyedBy: CodingKeys.self)
    url = try c.decodeIfPresent(String.self, forKey: .url)
    company = try c.decodeIfPresent(String.self, forKey: .company)
    position = try c.decodeIfPresent(String.self, forKey: .position)
  }

  var subtitle: String? {
    switch (position, company) {
    case (let p?, let c?): return "\(p) · \(c)"
    default: return position ?? company
    }
  }

  var displayText: String? {
    subtitle ?? url
  }

  var isEmpty: Bool {
    (url?.isEmpty ?? true) && (company?.isEmpty ?? true) && (position?.isEmpty ?? true)
  }
}

struct PersonChannel: Decodable, Identifiable, Equatable, Sendable {
  let key: String
  let label: String
  let count: Int
  let last: String?

  var id: String { key }

  enum CodingKeys: String, CodingKey { case key, label, count, last }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    let decodedKey = (try c.decodeIfPresent(String.self, forKey: .key)) ?? ""
    key = decodedKey
    label = (try c.decodeIfPresent(String.self, forKey: .label)) ?? decodedKey
    count = (try c.decodeIfPresent(Int.self, forKey: .count)) ?? 0
    last = try c.decodeIfPresent(String.self, forKey: .last)
  }
}

/// A co-member of one of this person's groups/threads — the "who they know" edge.
/// `weight` is an unbounded co-occurrence score used only for the pre-sorted order
/// the pipeline writes; it is never rendered.
struct PersonConnection: Decodable, Identifiable, Equatable, Sendable {
  let id: String
  let name: String
  let weight: Double
  let sources: [String]

  enum CodingKeys: String, CodingKey { case id, name, weight, sources }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = (try c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
    name = (try c.decodeIfPresent(String.self, forKey: .name)) ?? ""
    weight = (try c.decodeIfPresent(Double.self, forKey: .weight)) ?? 0
    sources = (try c.decodeIfPresent([String].self, forKey: .sources)) ?? []
  }

  var initials: String {
    let parts = name.split(separator: " ").prefix(2).compactMap { $0.first }
    let joined = String(parts).uppercased()
    return joined.isEmpty ? "?" : joined
  }

  var firstName: String {
    name.split(separator: " ").first.map(String.init) ?? name
  }
}

/// The social cluster this person belongs to (label is a human-readable descriptor
/// derived from the cluster's most-central members).
struct PersonCircle: Decodable, Equatable, Sendable {
  let id: Int
  let label: String
  let size: Int

  enum CodingKeys: String, CodingKey { case id, label, size }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = (try c.decodeIfPresent(Int.self, forKey: .id)) ?? 0
    label = (try c.decodeIfPresent(String.self, forKey: .label)) ?? ""
    size = (try c.decodeIfPresent(Int.self, forKey: .size)) ?? 0
  }
}

struct PeopleIntelPerson: Decodable, Identifiable, Equatable, Sendable {
  let id: String
  let name: String
  let relationship: String
  let who: String
  let now: String
  let overall: String
  let closeness: Double
  let lastTouch: PersonLastTouch?
  let channels: [PersonChannel]
  let aliases: [String]
  let contactName: String?
  let linkedin: PersonLinkedIn?
  let activities: [String]
  let openThreads: [String]
  let facts: [String]
  let photoPath: String?
  let connections: [PersonConnection]?
  let circle: PersonCircle?

  enum CodingKeys: String, CodingKey {
    case id, name, relationship, who, now, overall, closeness
    case lastTouch, channels, aliases, contactName, linkedin, activities, openThreads, facts, photoPath
    case connections, circle
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = (try c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
    name = (try c.decodeIfPresent(String.self, forKey: .name)) ?? "Unknown"
    relationship = (try c.decodeIfPresent(String.self, forKey: .relationship)) ?? ""
    who = (try c.decodeIfPresent(String.self, forKey: .who)) ?? ""
    now = (try c.decodeIfPresent(String.self, forKey: .now)) ?? ""
    overall = (try c.decodeIfPresent(String.self, forKey: .overall)) ?? ""
    closeness = (try c.decodeIfPresent(Double.self, forKey: .closeness)) ?? 0
    lastTouch = try c.decodeIfPresent(PersonLastTouch.self, forKey: .lastTouch)
    channels = (try c.decodeIfPresent([PersonChannel].self, forKey: .channels)) ?? []
    aliases = (try c.decodeIfPresent([String].self, forKey: .aliases)) ?? []
    contactName = try c.decodeIfPresent(String.self, forKey: .contactName)
    linkedin = try c.decodeIfPresent(PersonLinkedIn.self, forKey: .linkedin)
    activities = (try c.decodeIfPresent([String].self, forKey: .activities)) ?? []
    openThreads = (try c.decodeIfPresent([String].self, forKey: .openThreads)) ?? []
    facts = (try c.decodeIfPresent([String].self, forKey: .facts)) ?? []
    photoPath = try c.decodeIfPresent(String.self, forKey: .photoPath)
    connections = try c.decodeIfPresent([PersonConnection].self, forKey: .connections)
    circle = try c.decodeIfPresent(PersonCircle.self, forKey: .circle)
  }

  var initials: String {
    let parts = name.split(separator: " ").prefix(2).compactMap { $0.first }
    let joined = String(parts).uppercased()
    return joined.isEmpty ? "?" : joined
  }
}

// MARK: - Channel palette (brand-ish dots — neutral only, per repo brand rule)

enum PeopleChannelPalette {
  /// Maps a channel key (may be prefixed, e.g. "screen_imessage") to a stable dot color.
  static func color(for key: String) -> Color {
    let k = key.lowercased()
    if k.contains("whatsapp") { return Color(red: 0.15, green: 0.78, blue: 0.44) }  // green
    if k.contains("imessage") || k.contains("messages") { return Color(red: 0.18, green: 0.72, blue: 0.72) }  // teal
    if k.contains("instagram") || k.contains("insta") { return Color(red: 0.91, green: 0.34, blue: 0.52) }  // rose
    if k.contains("email") || k.contains("gmail") || k.contains("mail") {
      return Color(red: 0.96, green: 0.62, blue: 0.10)
    }  // amber
    if k.contains("linkedin") { return Color(red: 0.42, green: 0.49, blue: 0.58) }  // slate
    if k.contains("call") || k.contains("phone") { return Color(red: 0.85, green: 0.66, blue: 0.16) }  // gold
    if k.contains("voice") || k.contains("audio") || k.contains("screen") {
      return Color(red: 0.25, green: 0.55, blue: 0.96)
    }  // blue
    if k.contains("telegram") { return Color(red: 0.20, green: 0.60, blue: 0.90) }  // blue
    return Color(red: 0.55, green: 0.58, blue: 0.62)  // neutral fallback
  }
}

// MARK: - Connection photo resolution

/// Resolves `~/Library/Application Support/Omi/users/<uid>/people_photos/<id>.jpg` —
/// the same on-device folder the person avatars load from (the person's own
/// `photoPath` points into it). Mirrors `PeopleViewModel.resolveFileURL()`: prefers the
/// signed-in uid, otherwise the one users dir that actually contains a photos folder.
enum PeoplePhotos {
  static func photoPath(forID id: String) -> String? {
    guard !id.isEmpty, let dir = photosDirectory() else { return nil }
    return dir.appendingPathComponent("\(id).jpg").path
  }

  private static func photosDirectory() -> URL? {
    let fm = FileManager.default
    guard let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    else { return nil }
    let usersDir = support.appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)

    let uid = UserDefaults.standard.string(forKey: .authUserId)
    if let uid, !uid.isEmpty {
      let candidate = usersDir.appendingPathComponent(uid, isDirectory: true)
        .appendingPathComponent("people_photos", isDirectory: true)
      if fm.fileExists(atPath: candidate.path) { return candidate }
    }
    if let entries = try? fm.contentsOfDirectory(
      at: usersDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
    {
      for entry in entries {
        let candidate = entry.appendingPathComponent("people_photos", isDirectory: true)
        if fm.fileExists(atPath: candidate.path) { return candidate }
      }
    }
    return nil
  }
}

// MARK: - Date helpers

enum PeopleDateFormat {
  // Formatters are only ever read (never mutated) after construction, matching the
  // repo's existing shared-ISO-formatter pattern (see DesktopDiagnosticsManager).
  nonisolated(unsafe) private static let isoFractional: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
  }()

  nonisolated(unsafe) private static let iso: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f
  }()

  private static let dayOnly: DateFormatter = {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.dateFormat = "yyyy-MM-dd"
    return f
  }()

  static func date(from raw: String?) -> Date? {
    guard let raw, !raw.isEmpty else { return nil }
    if let d = isoFractional.date(from: raw) { return d }
    if let d = iso.date(from: raw) { return d }
    if let d = dayOnly.date(from: String(raw.prefix(10))) { return d }
    return nil
  }

  static func relative(from raw: String?) -> String? {
    guard let d = date(from: raw) else { return nil }
    let formatter = RelativeDateTimeFormatter()
    formatter.unitsStyle = .abbreviated
    return formatter.localizedString(for: d, relativeTo: Date())
  }
}

// MARK: - People View Model

@MainActor
final class PeopleViewModel: ObservableObject {
  @Published var people: [PeopleIntelPerson] = []
  @Published var stats: PeopleStats?
  @Published var generatedAt: String?
  @Published var isLoading = false
  @Published var errorMessage: String?
  @Published var searchText = ""
  @Published var selectedID: String?

  private var hasLoaded = false

  var filteredPeople: [PeopleIntelPerson] {
    let trimmed = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !trimmed.isEmpty else { return people }
    return people.filter { person in
      if person.name.lowercased().contains(trimmed) { return true }
      if person.relationship.lowercased().contains(trimmed) { return true }
      if person.who.lowercased().contains(trimmed) { return true }
      if person.aliases.contains(where: { $0.lowercased().contains(trimmed) }) { return true }
      return false
    }
  }

  var multiChannelCount: Int {
    stats?.multichannel ?? people.filter { $0.channels.count > 1 }.count
  }

  var channelCount: Int {
    if let c = stats?.channels { return c }
    return Set(people.flatMap { $0.channels.map { $0.key } }).count
  }

  var totalPeopleCount: Int {
    stats?.people ?? people.count
  }

  func loadIfNeeded() {
    guard !hasLoaded else { return }
    load()
  }

  /// Force a fresh run of the on-device pipeline + reload. Used right after the user opts in to
  /// iMessage mapping so newly created people surface without leaving the tab.
  func reload() {
    hasLoaded = false
    load()
  }

  func load() {
    hasLoaded = true
    isLoading = true
    errorMessage = nil
    // Gated, fire-and-forget: self-guards on the `peopleIMessageExport` flag
    // (default off), so this is a no-op unless a developer opts in.
    IMessageExporter.exportIfRequested()
    // On-device social-graph engine: reads the exported iMessage aggregates and derives
    // edges / circles / communities locally, folding them into the People-tab data.
    // Self-gated on the `peopleGraphBuild` flag (default on) and runs off the main thread.
    PeopleGraphBuilder.rebuildIfNeeded(uid: UserDefaults.standard.string(forKey: .authUserId))
    Task { [weak self] in
      let outcome = await Self.loadOutcome()
      self?.apply(outcome)
    }
  }

  private func apply(_ outcome: LoadOutcome) {
    isLoading = false
    switch outcome {
    case .loaded(let file):
      // closeness is an unbounded relevance score (e.g. 991.2), so it is used
      // only for ordering — never rendered as a percentage.
      people = file.people.sorted { $0.closeness > $1.closeness }
      stats = file.stats
      generatedAt = file.generatedAt
      if let selected = selectedID, !people.contains(where: { $0.id == selected }) {
        selectedID = nil
      }
    case .missing:
      people = []
      stats = nil
      generatedAt = nil
    case .failed(let message):
      errorMessage = message
    }
  }

  // MARK: File resolution + decode (blocking read offloaded off the main actor)

  private enum LoadOutcome: Sendable {
    case loaded(PeopleIntelligenceFile)
    case missing
    case failed(String)
  }

  private nonisolated static func loadOutcome() async -> LoadOutcome {
    await withCheckedContinuation { (continuation: CheckedContinuation<LoadOutcome, Never>) in
      DispatchQueue.global(qos: .userInitiated).async {
        continuation.resume(returning: readAndDecode())
      }
    }
  }

  private nonisolated static func readAndDecode() -> LoadOutcome {
    guard let url = resolveFileURL() else { return .missing }
    do {
      let data = try Data(contentsOf: url)
      let file = try JSONDecoder().decode(PeopleIntelligenceFile.self, from: data)
      return .loaded(file)
    } catch {
      return .failed("Couldn't read people data: \(error.localizedDescription)")
    }
  }

  /// Resolves the people_intelligence.json path. Prefers the signed-in uid under the
  /// canonical Application Support base; otherwise scans `Omi/users/*/` for the one
  /// directory that contains the file.
  private nonisolated static func resolveFileURL() -> URL? {
    let fm = FileManager.default
    var bases: [URL] = []
    if let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first {
      bases.append(support.appendingPathComponent("Omi", isDirectory: true))
    }
    let uid = UserDefaults.standard.string(forKey: .authUserId)

    for base in bases {
      let usersDir = base.appendingPathComponent("users", isDirectory: true)
      if let uid, !uid.isEmpty {
        let candidate = usersDir.appendingPathComponent(uid, isDirectory: true)
          .appendingPathComponent("people_intelligence.json")
        if fm.fileExists(atPath: candidate.path) { return candidate }
      }
      if let entries = try? fm.contentsOfDirectory(
        at: usersDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
      {
        for entry in entries {
          let candidate = entry.appendingPathComponent("people_intelligence.json")
          if fm.fileExists(atPath: candidate.path) { return candidate }
        }
      }
    }
    return nil
  }
}

// MARK: - Connectors model (REAL status where a signal exists)

@MainActor
final class PeopleConnectorsModel: ObservableObject {
  @Published var fullDiskAccess = false
  @Published var xStatus: XConnectionStatus?
  @Published var xLoading = false
  @Published var xFailed = false
  @Published var linkedInCSVPath: String?
  /// Whether the user has explicitly opted in to on-device iMessage mapping. Backed by the
  /// `peopleIMessageExport` flag (default false) that gates `IMessageExporter`.
  @Published var imessageMappingEnabled = false

  init() {
    linkedInCSVPath = UserDefaults.standard.string(forKey: .peopleConnectorsLinkedInCSVPath)
    imessageMappingEnabled = UserDefaults.standard.bool(forKey: .peopleIMessageExport)
  }

  func refresh() {
    refreshFullDiskAccess()
    refreshX()
  }

  /// Explicit opt-in for reading Messages on-device. Flips the `peopleIMessageExport` gate on
  /// and kicks the export + graph rebuild immediately so the People list can populate without a
  /// backend. Nothing leaves the machine.
  func enableIMessageMapping() {
    UserDefaults.standard.set(true, forKey: .peopleIMessageExport)
    imessageMappingEnabled = true
    IMessageExporter.exportIfRequested()
    PeopleGraphBuilder.rebuildIfNeeded(uid: UserDefaults.standard.string(forKey: .authUserId))
  }

  /// Full Disk Access is a single global permission; reading `~/Library/Messages`
  /// proves it, and the same grant lets Omi read WhatsApp's container. Mirrors
  /// AppState.checkFullDiskAccess()'s file probe (TCC queries are unreliable on
  /// macOS 15+).
  func refreshFullDiskAccess() {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let protectedPaths = [
      "\(home)/Library/Messages",
      "\(home)/Library/Mail",
      "\(home)/Library/Safari",
    ]
    var granted = false
    for path in protectedPaths where FileManager.default.fileExists(atPath: path) {
      granted = (try? FileManager.default.contentsOfDirectory(atPath: path)) != nil
      break
    }
    fullDiskAccess = granted
  }

  func refreshX() {
    xLoading = true
    xFailed = false
    Task {
      do {
        let status = try await APIClient.shared.xConnectionStatus()
        self.xStatus = status
      } catch {
        self.xFailed = true
      }
      self.xLoading = false
    }
  }

  func openFullDiskAccessSettings() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
    {
      NSWorkspace.shared.open(url)
    }
  }

  /// Kicks off the backend-mediated X OAuth in the browser, then polls a few
  /// times so the card reflects the linked account without a manual refresh.
  func connectX() {
    Task {
      let redirect = "\(Self.appURLScheme())://x/callback"
      guard
        let resp = try? await APIClient.shared.xOAuthURL(successRedirectURL: redirect),
        resp.success, let authURL = resp.authUrl, let url = URL(string: authURL)
      else { return }
      NSWorkspace.shared.open(url)
      for _ in 0..<20 {
        try? await Task.sleep(for: .seconds(3))
        if let status = try? await APIClient.shared.xConnectionStatus() {
          self.xStatus = status
          if status.connected { break }
        }
      }
    }
  }

  func syncX() {
    Task {
      xLoading = true
      _ = try? await APIClient.shared.xSync()
      if let status = try? await APIClient.shared.xConnectionStatus() {
        self.xStatus = status
      }
      xLoading = false
    }
  }

  /// Honest LinkedIn stub: no backend yet, so we just record the picked CSV path.
  func uploadLinkedInCSV() {
    let panel = NSOpenPanel()
    panel.allowedContentTypes = [.commaSeparatedText]
    panel.allowsMultipleSelection = false
    panel.canChooseDirectories = false
    panel.canChooseFiles = true
    panel.prompt = "Choose CSV"
    if panel.runModal() == .OK, let picked = panel.url {
      linkedInCSVPath = picked.path
      UserDefaults.standard.set(picked.path, forKey: .peopleConnectorsLinkedInCSVPath)
    }
  }

  private static func appURLScheme() -> String {
    if let urlTypes = Bundle.main.infoDictionary?["CFBundleURLTypes"] as? [[String: Any]],
      let first = urlTypes.first,
      let schemes = first["CFBundleURLSchemes"] as? [String],
      let scheme = schemes.first
    {
      return scheme
    }
    return "omi-computer"
  }
}

// MARK: - People Page

struct PeoplePage: View {
  @ObservedObject var viewModel: PeopleViewModel
  @StateObject private var connectors = PeopleConnectorsModel()
  @Environment(\.sbTheme) private var sb

  var body: some View {
    VStack(spacing: 0) {
      // Fixed header + connectors + search
      VStack(alignment: .leading, spacing: 20) {
        header
        connectorSection
        searchField
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(.horizontal, 28)
      .padding(.top, 24)
      .padding(.bottom, 14)

      content
    }
    .background(Color.clear)
    .onAppear {
      viewModel.loadIfNeeded()
      connectors.refresh()
      NotificationCenter.default.post(name: .peoplePageDidLoad, object: nil)
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      connectors.refreshFullDiskAccess()
    }
    // Opting in to iMessage mapping runs the on-device pipeline; reload so its output surfaces.
    .onChange(of: connectors.imessageMappingEnabled) { _, enabled in
      if enabled { viewModel.reload() }
    }
  }

  // MARK: Header

  private var header: some View {
    HStack(alignment: .firstTextBaseline) {
      VStack(alignment: .leading, spacing: 6) {
        Text("People")
          .geist(size: 28, weight: .semibold, tracking: 28 * -0.02)
          .foregroundStyle(sb.ink)

        Text(statLine)
          .geistMono(size: 12.5, tracking: 0)
          .foregroundStyle(sb.ink(.w35))
      }

      Spacer(minLength: 12)
    }
  }

  private var statLine: String {
    let people = viewModel.totalPeopleCount
    let multi = viewModel.multiChannelCount
    let channels = viewModel.channelCount
    return "\(people.formatted()) people · \(multi.formatted()) multi-channel · \(channels.formatted()) channels"
  }

  // MARK: Connectors

  private var connectorSection: some View {
    VStack(alignment: .leading, spacing: 12) {
      SBSectionLabel(text: "Connect your apps")

      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 12) {
          imessageCard
          whatsappCard
          telegramCard
          xCard
          linkedInCard
        }
        .padding(.vertical, 1)
      }
    }
  }

  private var imessageCard: some View {
    let granted = connectors.fullDiskAccess
    let enabled = connectors.imessageMappingEnabled
    // Reading Messages is explicit opt-in: (a) grant FDA, (b) enable on-device mapping, (c) active.
    let statusText: String
    let actionTitle: String
    let action: () -> Void
    if !granted {
      statusText = "Needs Full Disk Access"
      actionTitle = "Grant"
      action = { connectors.openFullDiskAccessSettings() }
    } else if !enabled {
      statusText = "Reads Messages on-device only"
      actionTitle = "Enable"
      action = { connectors.enableIMessageMapping() }
    } else {
      statusText = "Mapping · on-device"
      actionTitle = "Open Settings"
      action = { connectors.openFullDiskAccessSettings() }
    }
    return ConnectorCard(
      name: "iMessage",
      systemIcon: "message.fill",
      tint: PeopleChannelPalette.color(for: "imessage"),
      isConnected: granted && enabled,
      statusText: statusText,
      actionTitle: actionTitle,
      actionEnabled: true,
      action: action
    )
  }

  // WhatsApp / Telegram: the on-device engine does not read either yet, so these are honestly
  // "Coming soon" — not "connected". Don't imply a signal we don't have.
  private var whatsappCard: some View {
    ConnectorCard(
      name: "WhatsApp",
      systemIcon: "bubble.left.and.bubble.right.fill",
      tint: PeopleChannelPalette.color(for: "whatsapp"),
      isConnected: false,
      statusText: "Coming soon",
      actionTitle: nil,
      actionEnabled: false,
      action: {}
    )
  }

  private var telegramCard: some View {
    ConnectorCard(
      name: "Telegram",
      systemIcon: "paperplane.fill",
      tint: PeopleChannelPalette.color(for: "telegram"),
      isConnected: false,
      statusText: "Coming soon",
      actionTitle: nil,
      actionEnabled: false,
      action: {}
    )
  }

  private var xCard: some View {
    let connected = connectors.xStatus?.connected ?? false
    let status: String
    if connectors.xLoading && connectors.xStatus == nil {
      status = "Checking…"
    } else if connectors.xFailed {
      status = "Couldn't check status"
    } else if connected {
      let handle = connectors.xStatus?.handle.map { "@\($0)" } ?? "Connected"
      if let synced = PeopleDateFormat.relative(from: connectors.xStatus?.lastSyncedAt) {
        status = "\(handle) · synced \(synced)"
      } else {
        status = handle
      }
    } else {
      status = "Not connected"
    }
    let actionTitle: String
    if connectors.xFailed {
      actionTitle = "Retry"
    } else if connected {
      actionTitle = "Sync now"
    } else {
      actionTitle = "Connect"
    }
    return ConnectorCard(
      name: "X",
      systemIcon: "at",
      tint: sb.ink(.w55),
      isConnected: connected,
      statusText: status,
      actionTitle: actionTitle,
      actionEnabled: !connectors.xLoading,
      action: {
        if connectors.xFailed {
          connectors.refreshX()
        } else if connected {
          connectors.syncX()
        } else {
          connectors.connectX()
        }
      }
    )
  }

  private var linkedInCard: some View {
    let filename = connectors.linkedInCSVPath.map { URL(fileURLWithPath: $0).lastPathComponent }
    return ConnectorCard(
      name: "LinkedIn",
      systemIcon: "briefcase.fill",
      tint: PeopleChannelPalette.color(for: "linkedin"),
      isConnected: false,
      statusText: filename.map { "CSV: \($0)" } ?? "Not connected",
      actionTitle: "Upload CSV",
      actionEnabled: true,
      action: { connectors.uploadLinkedInCSV() }
    )
  }

  // MARK: Search

  private var searchField: some View {
    HStack(spacing: 10) {
      Image(systemName: "magnifyingglass")
        .font(.system(size: 13, weight: .medium))
        .foregroundStyle(sb.ink(.w35))

      ZStack(alignment: .leading) {
        if viewModel.searchText.isEmpty {
          Text("Search people…")
            .geist(size: 14)
            .foregroundStyle(sb.ink(.w35))
        }
        TextField("", text: $viewModel.searchText)
          .textFieldStyle(.plain)
          .geist(size: 14)
          .foregroundStyle(sb.ink)
      }

      if !viewModel.searchText.isEmpty {
        Button {
          viewModel.searchText = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .font(.system(size: 13))
            .foregroundStyle(sb.ink(.w35))
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 10)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(sb.ink(.w06))
    )
    .overlay(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .stroke(sb.ink(.w12), lineWidth: 1)
    )
  }

  // MARK: Content

  @ViewBuilder
  private var content: some View {
    if viewModel.isLoading && viewModel.people.isEmpty {
      loadingState
    } else if let error = viewModel.errorMessage, viewModel.people.isEmpty {
      messageState(icon: "exclamationmark.triangle", title: "Couldn't load people", subtitle: error)
    } else if viewModel.people.isEmpty {
      messageState(
        icon: "person.2",
        title: "No people yet",
        subtitle: "Connect a source to start mapping your relationships."
      )
    } else if viewModel.filteredPeople.isEmpty {
      messageState(
        icon: "magnifyingglass", title: "No results", subtitle: "Try a different name or relationship.")
    } else {
      peopleList
    }
  }

  private var peopleList: some View {
    ScrollView {
      LazyVStack(spacing: 8) {
        ForEach(viewModel.filteredPeople) { person in
          PersonRowView(
            person: person,
            isSelected: viewModel.selectedID == person.id,
            onTap: {
              withAnimation(SBMotion.standard) {
                viewModel.selectedID = viewModel.selectedID == person.id ? nil : person.id
              }
            }
          )
        }
      }
      .padding(.horizontal, 28)
      .padding(.top, 6)
      .padding(.bottom, 32)
    }
  }

  private var loadingState: some View {
    VStack(spacing: 14) {
      ProgressView()
        .controlSize(.small)
      Text("Loading people…")
        .geist(size: 13.5)
        .foregroundStyle(sb.ink(.w45))
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func messageState(icon: String, title: String, subtitle: String) -> some View {
    VStack(spacing: 14) {
      Image(systemName: icon)
        .font(.system(size: 34, weight: .light))
        .foregroundStyle(sb.ink(.w25))
      Text(title)
        .geist(size: 16, weight: .semibold)
        .foregroundStyle(sb.ink(.w85))
      Text(subtitle)
        .geist(size: 13.5)
        .foregroundStyle(sb.ink(.w45))
        .multilineTextAlignment(.center)
        .lineSpacing(2)
        .frame(maxWidth: 360)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(.horizontal, 40)
  }
}

// MARK: - Connector Card

private struct ConnectorCard: View {
  let name: String
  let systemIcon: String
  let tint: Color
  let isConnected: Bool
  let statusText: String
  let actionTitle: String?
  let actionEnabled: Bool
  let action: () -> Void

  @Environment(\.sbTheme) private var sb

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        ZStack {
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(tint.opacity(0.16))
            .frame(width: 34, height: 34)
          Image(systemName: systemIcon)
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(tint)
        }
        Spacer(minLength: 6)
        Circle()
          .fill(isConnected ? Color(red: 0.15, green: 0.78, blue: 0.44) : sb.ink(.w18))
          .frame(width: 8, height: 8)
      }

      Text(name)
        .geist(size: 15, weight: .semibold)
        .foregroundStyle(sb.ink)

      Text(statusText)
        .geist(size: 12)
        .foregroundStyle(sb.ink(.w45))
        .lineLimit(2)
        .fixedSize(horizontal: false, vertical: true)

      Spacer(minLength: 0)

      if let actionTitle {
        Button(action: action) {
          Text(actionTitle)
            .geist(size: 12.5, weight: .medium)
            .foregroundStyle(actionEnabled ? sb.ink(.w85) : sb.ink(.w35))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 7)
            .background(
              RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(sb.ink(.w18), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(!actionEnabled)
      } else {
        Text("Coming soon")
          .geist(size: 12, weight: .medium)
          .foregroundStyle(sb.ink(.w25))
          .frame(maxWidth: .infinity)
          .padding(.vertical, 7)
      }
    }
    .padding(14)
    .frame(width: 176, height: 152, alignment: .topLeading)
    .sbCard(radius: 14)
  }
}

// MARK: - Person Row (with inline-expand detail)

private struct PersonRowView: View {
  let person: PeopleIntelPerson
  let isSelected: Bool
  let onTap: () -> Void

  @State private var isHovering = false
  @Environment(\.sbTheme) private var sb

  var body: some View {
    VStack(spacing: 0) {
      Button(action: onTap) {
        HStack(spacing: 14) {
          PersonAvatar(photoPath: person.photoPath, initials: person.initials)

          VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 8) {
              Text(person.name)
                .geist(size: 15, weight: .medium)
                .foregroundStyle(sb.ink)
                .lineLimit(1)

              if !person.relationship.isEmpty {
                RelationshipPill(text: person.relationship)
              }
            }

            HStack(spacing: 8) {
              ChannelDots(channels: person.channels)
              if let touch = lastTouchLine {
                Text(touch)
                  .geistMono(size: 11, tracking: 0)
                  .foregroundStyle(sb.ink(.w35))
                  .lineLimit(1)
              }
            }
          }

          Spacer(minLength: 8)

          Image(systemName: "chevron.right")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(sb.ink(.w35))
            .rotationEffect(.degrees(isSelected ? 90 : 0))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      if isSelected {
        PersonDetailView(person: person)
          .padding(.horizontal, 14)
          .padding(.bottom, 14)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(isSelected ? sb.ink(.w05) : (isHovering ? sb.ink(.w04) : Color.clear))
    )
    .overlay(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .stroke(sb.ink(isSelected ? .w12 : .w07), lineWidth: 1)
    )
    .onHover { hovering in
      isHovering = hovering
      if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
    }
  }

  private var lastTouchLine: String? {
    guard let touch = person.lastTouch else { return nil }
    let label = channelDisplayLabel(for: touch.channel)
    if let rel = PeopleDateFormat.relative(from: touch.date) {
      return label.isEmpty ? rel : "\(label) · \(rel)"
    }
    return label.isEmpty ? nil : label
  }

  private func channelDisplayLabel(for key: String) -> String {
    let k = key.lowercased()
    if k.contains("whatsapp") { return "WhatsApp" }
    if k.contains("imessage") || k.contains("messages") { return "iMessage" }
    if k.contains("instagram") || k.contains("insta") { return "Instagram" }
    if k.contains("email") || k.contains("gmail") || k.contains("mail") { return "Email" }
    if k.contains("linkedin") { return "LinkedIn" }
    if k.contains("call") || k.contains("phone") { return "Calls" }
    if k.contains("telegram") { return "Telegram" }
    if k.contains("voice") { return "Voice" }
    if k.contains("screen") { return "Screen" }
    return key.capitalized
  }
}

private struct InitialsAvatar: View {
  let initials: String
  @Environment(\.sbTheme) private var sb

  var body: some View {
    ZStack {
      Circle()
        .fill(sb.ink(.w08))
        .overlay(Circle().stroke(sb.ink(.w12), lineWidth: 1))
        .frame(width: 38, height: 38)
      Text(initials)
        .geist(size: 13, weight: .semibold)
        .foregroundStyle(sb.ink(.w7))
    }
  }
}

/// Shows a real contact/WhatsApp photo when one was matched on-device; otherwise initials.
private struct PersonAvatar: View {
  let photoPath: String?
  let initials: String
  @Environment(\.sbTheme) private var sb

  private var photo: NSImage? {
    guard let p = photoPath, FileManager.default.fileExists(atPath: p) else { return nil }
    return NSImage(contentsOfFile: p)
  }

  var body: some View {
    if let img = photo {
      Image(nsImage: img)
        .resizable()
        .aspectRatio(contentMode: .fill)
        .frame(width: 38, height: 38)
        .clipShape(Circle())
        .overlay(Circle().stroke(sb.ink(.w12), lineWidth: 1))
    } else {
      InitialsAvatar(initials: initials)
    }
  }
}

private struct RelationshipPill: View {
  let text: String
  @Environment(\.sbTheme) private var sb

  var body: some View {
    Text(text)
      .geistMono(size: 10.5, tracking: 0.2)
      .foregroundStyle(sb.ink(.w6))
      .padding(.horizontal, 8)
      .padding(.vertical, 2)
      .background(Capsule().fill(sb.ink(.w08)))
      .lineLimit(1)
  }
}

private struct ChannelDots: View {
  let channels: [PersonChannel]
  @Environment(\.sbTheme) private var sb

  var body: some View {
    HStack(spacing: 3) {
      ForEach(channels.prefix(6)) { channel in
        Circle()
          .fill(PeopleChannelPalette.color(for: channel.key))
          .frame(width: 7, height: 7)
      }
      if channels.count > 6 {
        Text("+\(channels.count - 6)")
          .geistMono(size: 9, tracking: 0)
          .foregroundStyle(sb.ink(.w35))
      }
    }
  }
}

// MARK: - Person Detail

private struct PersonDetailView: View {
  let person: PeopleIntelPerson
  @Environment(\.sbTheme) private var sb

  private var hasContactSection: Bool {
    if let contact = person.contactName, !contact.isEmpty { return true }
    if let linkedin = person.linkedin, !linkedin.isEmpty { return true }
    return false
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      if !person.who.isEmpty {
        Text(person.who)
          .geist(size: 13.5)
          .foregroundStyle(sb.ink(.w8))
          .lineSpacing(3)
          .textSelection(.enabled)
          .fixedSize(horizontal: false, vertical: true)
      }

      textSection("Now", person.now)
      textSection("Overall", person.overall)

      if !person.channels.isEmpty {
        VStack(alignment: .leading, spacing: 8) {
          SBSectionLabel(text: "Channels")
          VStack(alignment: .leading, spacing: 6) {
            ForEach(person.channels) { channel in
              HStack(spacing: 8) {
                Circle()
                  .fill(PeopleChannelPalette.color(for: channel.key))
                  .frame(width: 7, height: 7)
                Text(channel.label)
                  .geist(size: 12.5)
                  .foregroundStyle(sb.ink(.w75))
                Spacer(minLength: 8)
                Text("\(channel.count.formatted())")
                  .geistMono(size: 11.5, tracking: 0)
                  .foregroundStyle(sb.ink(.w45))
                if let last = PeopleDateFormat.relative(from: channel.last) {
                  Text("· \(last)")
                    .geistMono(size: 11, tracking: 0)
                    .foregroundStyle(sb.ink(.w35))
                }
              }
            }
          }
        }
      }

      if let connections = person.connections, !connections.isEmpty {
        VStack(alignment: .leading, spacing: 10) {
          SBSectionLabel(text: "Connected")
          if let circle = person.circle {
            ConnectionCircleChip(circle: circle)
          }
          ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 12) {
              ForEach(connections) { connection in
                ConnectionAvatarView(connection: connection)
              }
            }
            .padding(.vertical, 1)
          }
        }
      }

      bulletSection("Activities", person.activities)
      bulletSection("Open threads", person.openThreads)
      bulletSection("Facts", person.facts)

      if !person.aliases.isEmpty {
        VStack(alignment: .leading, spacing: 8) {
          SBSectionLabel(text: "Also known as")
          Text(person.aliases.joined(separator: ", "))
            .geist(size: 12.5)
            .foregroundStyle(sb.ink(.w6))
            .fixedSize(horizontal: false, vertical: true)
        }
      }

      if hasContactSection {
        VStack(alignment: .leading, spacing: 8) {
          SBSectionLabel(text: "Contact")
          if let contact = person.contactName, !contact.isEmpty {
            HStack(spacing: 8) {
              Image(systemName: "person.crop.circle")
                .font(.system(size: 12))
                .foregroundStyle(sb.ink(.w35))
              Text(contact)
                .geist(size: 12.5)
                .foregroundStyle(sb.ink(.w75))
                .textSelection(.enabled)
            }
          }
          if let linkedin = person.linkedin, !linkedin.isEmpty {
            HStack(spacing: 8) {
              Image(systemName: "briefcase")
                .font(.system(size: 12))
                .foregroundStyle(sb.ink(.w35))
              if let urlString = linkedin.url, let url = URL(string: urlString) {
                Link(linkedin.displayText ?? urlString, destination: url)
                  .geist(size: 12.5)
                  .foregroundStyle(sb.ink(.w75))
              } else if let text = linkedin.displayText {
                Text(text)
                  .geist(size: 12.5)
                  .foregroundStyle(sb.ink(.w75))
                  .textSelection(.enabled)
              }
            }
          }
        }
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(14)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(sb.ink(.w02))
    )
  }

  @ViewBuilder
  private func textSection(_ title: String, _ body: String) -> some View {
    if !body.isEmpty {
      VStack(alignment: .leading, spacing: 8) {
        SBSectionLabel(text: title)
        Text(body)
          .geist(size: 12.5)
          .foregroundStyle(sb.ink(.w7))
          .lineSpacing(2)
          .textSelection(.enabled)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  @ViewBuilder
  private func bulletSection(_ title: String, _ items: [String]) -> some View {
    if !items.isEmpty {
      VStack(alignment: .leading, spacing: 8) {
        SBSectionLabel(text: title)
        VStack(alignment: .leading, spacing: 6) {
          ForEach(Array(items.enumerated()), id: \.offset) { _, item in
            HStack(alignment: .top, spacing: 8) {
              Circle()
                .fill(sb.ink(.w25))
                .frame(width: 4, height: 4)
                .padding(.top, 6)
              Text(item)
                .geist(size: 12.5)
                .foregroundStyle(sb.ink(.w7))
                .lineSpacing(2)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
      }
    }
  }
}

// MARK: - Connected (social graph)

/// Subtle neutral chip summarizing the social cluster this person sits in.
private struct ConnectionCircleChip: View {
  let circle: PersonCircle
  @Environment(\.sbTheme) private var sb

  var body: some View {
    HStack(spacing: 8) {
      Image(systemName: "person.2.circle")
        .font(.system(size: 13))
        .foregroundStyle(sb.ink(.w45))
      VStack(alignment: .leading, spacing: 1) {
        Text("Inner circle · \(circle.size) \(circle.size == 1 ? "person" : "people")")
          .geist(size: 11.5, weight: .medium)
          .foregroundStyle(sb.ink(.w75))
        if !circle.label.isEmpty {
          Text(circle.label)
            .geistMono(size: 10, tracking: 0)
            .foregroundStyle(sb.ink(.w35))
            .lineLimit(1)
        }
      }
    }
    .padding(.horizontal, 10)
    .padding(.vertical, 6)
    .background(
      RoundedRectangle(cornerRadius: 9, style: .continuous)
        .fill(sb.ink(.w05))
    )
    .overlay(
      RoundedRectangle(cornerRadius: 9, style: .continuous)
        .stroke(sb.ink(.w08), lineWidth: 1)
    )
    .fixedSize(horizontal: true, vertical: false)
  }
}

/// A single "who they know" node: on-device photo when one exists, else initials,
/// with the connection's first name beneath. Photo lookup reuses the same
/// people_photos folder the person avatars load from (`<connection.id>.jpg`).
private struct ConnectionAvatarView: View {
  let connection: PersonConnection
  @Environment(\.sbTheme) private var sb

  private var photo: NSImage? {
    guard let path = PeoplePhotos.photoPath(forID: connection.id),
      FileManager.default.fileExists(atPath: path)
    else { return nil }
    return NSImage(contentsOfFile: path)
  }

  var body: some View {
    VStack(spacing: 6) {
      if let img = photo {
        Image(nsImage: img)
          .resizable()
          .aspectRatio(contentMode: .fill)
          .frame(width: 42, height: 42)
          .clipShape(Circle())
          .overlay(Circle().stroke(sb.ink(.w12), lineWidth: 1))
      } else {
        ZStack {
          Circle()
            .fill(sb.ink(.w08))
            .overlay(Circle().stroke(sb.ink(.w12), lineWidth: 1))
            .frame(width: 42, height: 42)
          Text(connection.initials)
            .geist(size: 13, weight: .semibold)
            .foregroundStyle(sb.ink(.w7))
        }
      }
      Text(connection.firstName)
        .geist(size: 10.5)
        .foregroundStyle(sb.ink(.w6))
        .lineLimit(1)
        .multilineTextAlignment(.center)
    }
    .frame(width: 60)
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    PeoplePage(viewModel: PeopleViewModel())
      .frame(width: 900, height: 640)
      .background(OmiColors.backgroundPrimary)
  }
#endif
