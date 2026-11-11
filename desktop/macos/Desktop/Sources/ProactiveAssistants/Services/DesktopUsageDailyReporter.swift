import Foundation

struct DesktopUsageAccumulator: Codable, Equatable, Sendable {
  var records: [String: DesktopUsageDailyPayload] = [:]
  var dirtyDates: Set<String> = []

  mutating func sample(
    dateKey: String,
    timezone: String,
    clientDeviceID: String,
    watching: Bool,
    listening: Bool,
    intervalSeconds: Int = 60
  ) {
    ensureRecord(dateKey: dateKey, timezone: timezone, clientDeviceID: clientDeviceID)
    if watching { records[dateKey]?.watchingSeconds += intervalSeconds }
    if listening { records[dateKey]?.listeningSeconds += intervalSeconds }
    if watching || listening { dirtyDates.insert(dateKey) }
  }

  mutating func incrementShown(dateKey: String, timezone: String, clientDeviceID: String) {
    ensureRecord(dateKey: dateKey, timezone: timezone, clientDeviceID: clientDeviceID)
    records[dateKey]?.proactiveCardsShown += 1
    dirtyDates.insert(dateKey)
  }

  mutating func incrementActed(dateKey: String, timezone: String, clientDeviceID: String) {
    ensureRecord(dateKey: dateKey, timezone: timezone, clientDeviceID: clientDeviceID)
    records[dateKey]?.proactiveCardsActed += 1
    dirtyDates.insert(dateKey)
  }

  mutating func incrementPTT(dateKey: String, timezone: String, clientDeviceID: String) {
    ensureRecord(dateKey: dateKey, timezone: timezone, clientDeviceID: clientDeviceID)
    records[dateKey]?.pttTurns += 1
    dirtyDates.insert(dateKey)
  }

  mutating func markUploaded(_ dateKey: String) {
    dirtyDates.remove(dateKey)
  }

  mutating func retainLatestDays(_ count: Int) {
    let retained = Set(records.keys.sorted().suffix(max(0, count)))
    records = records.filter { retained.contains($0.key) }
    dirtyDates = dirtyDates.intersection(retained)
  }

  private mutating func ensureRecord(dateKey: String, timezone: String, clientDeviceID: String) {
    guard records[dateKey] == nil else { return }
    records[dateKey] = DesktopUsageDailyPayload(
      date: dateKey,
      timezone: timezone,
      clientDeviceID: clientDeviceID,
      watchingSeconds: 0,
      listeningSeconds: 0,
      proactiveCardsShown: 0,
      proactiveCardsActed: 0,
      pttTurns: 0)
  }
}

@MainActor
final class DesktopUsageDailyReporter {
  static let shared = DesktopUsageDailyReporter()

  static let persistedKey = "desktopUsageDailyRecords"
  private static let sampleInterval: TimeInterval = 60
  private static let uploadInterval: TimeInterval = 10 * 60

  private let defaults: UserDefaults
  private let now: () -> Date
  private let calendar: Calendar
  private let timezone: () -> TimeZone
  private let deviceID: () -> String
  private let ownerID: () -> String?
  private let uploadPayload: @Sendable (DesktopUsageDailyPayload) async throws -> Void
  private var isWatching: () -> Bool = { false }
  private var isListening: () -> Bool = { false }
  private var accumulator: DesktopUsageAccumulator
  private var sampleTimer: Timer?
  private var uploadTimer: Timer?
  private var lastDateKey: String?
  private var retryAttempts: [String: Int] = [:]
  private var retryAfter: [String: Date] = [:]
  private var testingAssumeAuthorized = false
  private var started = false
  nonisolated(unsafe) private var ownerObserver: NSObjectProtocol?
  private var boundOwnerID: String?

  init(
    defaults: UserDefaults = .standard,
    now: @escaping () -> Date = { Date() },
    calendar: Calendar = .current,
    timezone: @escaping () -> TimeZone = { .current },
    deviceID: @escaping () -> String = { ClientDeviceService.shared.clientDeviceId },
    ownerID: @escaping () -> String? = { RuntimeOwnerIdentity.currentOwnerId() },
    uploadPayload: @escaping @Sendable (DesktopUsageDailyPayload) async throws -> Void = {
      try await APIClient.shared.postDesktopUsageDaily($0)
    }
  ) {
    self.defaults = defaults
    self.now = now
    self.calendar = calendar
    self.timezone = timezone
    self.deviceID = deviceID
    self.ownerID = ownerID
    self.uploadPayload = uploadPayload
    boundOwnerID = ownerID()
    if let boundOwnerID, let data = defaults.data(forKey: Self.persistedKey + "." + boundOwnerID),
      var decoded = try? JSONDecoder().decode(DesktopUsageAccumulator.self, from: data)
    {
      decoded.retainLatestDays(7)
      accumulator = decoded
    } else {
      accumulator = DesktopUsageAccumulator()
    }
    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated { self?.resetForOwnerChange() }
    }
  }

  deinit {
    if let ownerObserver { NotificationCenter.default.removeObserver(ownerObserver) }
  }

  func start(isWatching: @escaping () -> Bool, isListening: @escaping () -> Bool) {
    self.isWatching = isWatching
    self.isListening = isListening
    guard !started else { return }
    reloadForCurrentOwner()
    guard boundOwnerID != nil else { return }
    started = true
    lastDateKey = dateKey(for: now())
    sampleTimer = Timer.scheduledTimer(withTimeInterval: Self.sampleInterval, repeats: true) {
      [weak self] _ in
      Task { @MainActor in self?.sampleNow() }
    }
    uploadTimer = Timer.scheduledTimer(withTimeInterval: Self.uploadInterval, repeats: true) {
      [weak self] _ in
      Task { @MainActor in await self?.uploadDirtyRecords() }
    }
    Task { await uploadDirtyRecords() }
  }

  func recordProactiveCardShown() {
    let date = now()
    accumulator.incrementShown(
      dateKey: dateKey(for: date),
      timezone: timezone().identifier,
      clientDeviceID: deviceID())
    persist()
  }

  func recordProactiveCardActed() {
    let date = now()
    accumulator.incrementActed(
      dateKey: dateKey(for: date),
      timezone: timezone().identifier,
      clientDeviceID: deviceID())
    persist()
  }

  func recordCompletedPTTTurn(repliedToCard: Bool) {
    let date = now()
    let key = dateKey(for: date)
    accumulator.incrementPTT(dateKey: key, timezone: timezone().identifier, clientDeviceID: deviceID())
    if repliedToCard {
      accumulator.incrementActed(dateKey: key, timezone: timezone().identifier, clientDeviceID: deviceID())
    }
    persist()
  }

  func sampleForTesting(watching: Bool, listening: Bool, at date: Date) {
    sample(watching: watching, listening: listening, at: date)
  }

  func snapshotForTesting() -> DesktopUsageAccumulator { accumulator }

  func assumeAuthorizedForTesting() {
    testingAssumeAuthorized = true
  }

  func uploadDirtyRecordsForTesting() async {
    await uploadDirtyRecords()
  }

  func retryAttemptsForTesting(_ dateKey: String) -> Int {
    retryAttempts[dateKey, default: 0]
  }

  func retryAfterForTesting(_ dateKey: String) -> Date? {
    retryAfter[dateKey]
  }

  private func sampleNow() {
    sample(watching: isWatching(), listening: isListening(), at: now())
  }

  private func sample(watching: Bool, listening: Bool, at date: Date) {
    let key = dateKey(for: date)
    let rolledOver = lastDateKey != nil && lastDateKey != key
    let priorDate = lastDateKey
    accumulator.sample(
      dateKey: key,
      timezone: timezone().identifier,
      clientDeviceID: deviceID(),
      watching: watching,
      listening: listening)
    accumulator.retainLatestDays(7)
    lastDateKey = key
    persist()
    if rolledOver, let priorDate {
      Task { await upload(dateKey: priorDate) }
    }
  }

  private func uploadDirtyRecords() async {
    for dateKey in accumulator.dirtyDates.sorted() {
      await upload(dateKey: dateKey)
    }
  }

  private func upload(dateKey: String) async {
    guard let payload = accumulator.records[dateKey], let boundOwnerID else { return }
    let authorization: RuntimeOwnerAuthorizationSnapshot?
    if testingAssumeAuthorized {
      authorization = nil
    } else if let captured = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
      expectedOwnerID: boundOwnerID),
      RuntimeOwnerIdentity.isAuthorizationCurrent(captured)
    {
      authorization = captured
    } else {
      log("DesktopUsageDailyReporter: owner authorization changed before usage upload")
      return
    }
    if let retry = retryAfter[dateKey], retry > now() { return }
    do {
      try await uploadPayload(payload)
      if !testingAssumeAuthorized {
        guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization),
          self.boundOwnerID == boundOwnerID
        else {
          log("DesktopUsageDailyReporter: owner authorization changed during usage upload")
          return
        }
      }
      if accumulator.records[dateKey] == payload {
        accumulator.markUploaded(dateKey)
      }
      retryAttempts.removeValue(forKey: dateKey)
      retryAfter.removeValue(forKey: dateKey)
      persist()
    } catch {
      let attempt = min(6, retryAttempts[dateKey, default: 0] + 1)
      retryAttempts[dateKey] = attempt
      retryAfter[dateKey] = now().addingTimeInterval(min(Self.uploadInterval, pow(2, Double(attempt)) * 15))
      logError("DesktopUsageDailyReporter: daily usage upload failed", error: error)
    }
  }

  private func dateKey(for date: Date) -> String {
    var components = calendar.dateComponents(in: timezone(), from: date)
    components.calendar = calendar
    return String(format: "%04d-%02d-%02d", components.year ?? 0, components.month ?? 0, components.day ?? 0)
  }

  private func persist() {
    guard let boundOwnerID, ownerID() == boundOwnerID,
      let data = try? JSONEncoder().encode(accumulator)
    else { return }
    defaults.set(data, forKey: Self.persistedKey + "." + boundOwnerID)
  }

  private func resetForOwnerChange() {
    sampleTimer?.invalidate()
    uploadTimer?.invalidate()
    sampleTimer = nil
    uploadTimer = nil
    started = false
    accumulator = DesktopUsageAccumulator()
    retryAttempts.removeAll()
    retryAfter.removeAll()
    lastDateKey = nil
    boundOwnerID = nil
  }

  private func reloadForCurrentOwner() {
    let currentOwner = ownerID()
    guard currentOwner != boundOwnerID else { return }
    boundOwnerID = currentOwner
    accumulator = DesktopUsageAccumulator()
    guard let currentOwner,
      let data = defaults.data(forKey: Self.persistedKey + "." + currentOwner),
      var decoded = try? JSONDecoder().decode(DesktopUsageAccumulator.self, from: data)
    else { return }
    decoded.retainLatestDays(7)
    accumulator = decoded
  }
}
