import Foundation

extension ChatProvider {
  /// Compose and present the personalized opener the instant Home appears after onboarding. Local
  /// facts make the first paint immediate; a connected calendar may enrich it afterward.
  func presentOnboardingOpener(proofReceipt: OnboardingProofReceipt? = nil) {
    let name = Self.onboardingFirstName(AuthService.shared.givenName)
    let mode: OnboardingOpenerComposer.ListeningMode =
      AssistantSettings.shared.audioRecordingMode == .always ? .always : .meetingsOnly
    let baseStarters = HomeSuggestionComposer.compose(
      personalized: HomeSuggestionsStore.shared.personalizedQuestions,
      onboarding: PostOnboardingPromptSuggestions.suggestions())

    let presentedOpener = OnboardingOpenerComposer.compose(
      name: name, mode: mode, meetings: [], now: Date(), baseStarters: baseStarters,
      proofReceipt: proofReceipt)
    onboardingOpener = presentedOpener
    let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot()

    Task { [weak self] in
      let meetings = await Self.todaysOnboardingMeetings()
      guard !meetings.isEmpty else { return }
      guard let self,
        let authorization,
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorization),
        self.onboardingOpener == presentedOpener
      else { return }
      self.onboardingOpener = OnboardingOpenerComposer.compose(
        name: name, mode: mode, meetings: meetings, now: Date(), baseStarters: baseStarters,
        proofReceipt: proofReceipt)
    }
  }

  func dismissOnboardingOpener() {
    onboardingOpener = nil
  }

  private static func onboardingFirstName(_ full: String) -> String {
    let trimmed = full.trimmingCharacters(in: .whitespaces)
    return trimmed.components(separatedBy: " ").first ?? trimmed
  }

  /// Today's remaining timed meetings, best-effort. Failure leaves the immediate local opener.
  private static func todaysOnboardingMeetings() async -> [OnboardingMeetingBrief] {
    guard
      let events = try? await CalendarReaderService.shared.readEvents(
        daysBack: 0, daysForward: 1, maxResults: 50)
    else { return [] }

    // Event offsets describe the user's day, so compare against a local—not UTC—date prefix.
    let localDayFormatter = ISO8601DateFormatter()
    localDayFormatter.timeZone = TimeZone.current
    let todayPrefix = localDayFormatter.string(from: Date()).prefix(10)
    let plain = ISO8601DateFormatter()
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    let timeFormatter = DateFormatter()
    timeFormatter.locale = Locale.current
    timeFormatter.setLocalizedDateFormatFromTemplate("jmm")
    let cutoff = Date().addingTimeInterval(-30 * 60)

    return
      events
      .filter { !$0.isAllDay && $0.startTime.prefix(10) == todayPrefix }
      .compactMap { event -> (Date, OnboardingMeetingBrief)? in
        guard let start = plain.date(from: event.startTime) ?? fractional.date(from: event.startTime),
          start >= cutoff
        else { return nil }
        let title = event.summary.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return nil }
        return (start, OnboardingMeetingBrief(title: title, time: timeFormatter.string(from: start)))
      }
      .sorted { $0.0 < $1.0 }
      .map(\.1)
  }
}
