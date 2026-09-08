import AVFoundation
import OmiTheme
import SwiftUI

/// One row of the People page, assembled from the backend's people list, the local transcript
/// store, and the voices the on-device diarizer remembers. Pure so the ordering and copy can be
/// unit-tested without a database or a model.
struct PersonOverview: Identifiable {
  let person: Person
  let activity: PersonActivity?
  let voice: LocalSpeakerDiarizer.VoiceSummary?

  var id: String { person.id }

  var conversationCount: Int { activity?.conversationCount ?? 0 }
  var lastTalkedAt: Date? { activity?.lastTalkedAt }
  var hasVoice: Bool { voice != nil }
  var isFavorite: Bool { voice?.isFavorite ?? false }
  var sampleURL: URL? { voice?.sampleURLs.first }

  /// Favorites first, then most recently talked to; never-heard people by name at the end.
  static func ordered(
    people: [Person],
    activity: [String: PersonActivity],
    voices: [LocalSpeakerDiarizer.VoiceSummary]
  ) -> [PersonOverview] {
    let voiceByPerson = Dictionary(
      voices.compactMap { voice in voice.personId.map { ($0, voice) } },
      uniquingKeysWith: { _, latest in latest })
    return
      people.map { PersonOverview(person: $0, activity: activity[$0.id], voice: voiceByPerson[$0.id]) }
      .sorted { lhs, rhs in
        if lhs.isFavorite != rhs.isFavorite { return lhs.isFavorite }
        switch (lhs.lastTalkedAt, rhs.lastTalkedAt) {
        case let (l?, r?) where l != r: return l > r
        case (.some, .none): return true
        case (.none, .some): return false
        default: return lhs.person.name.localizedCaseInsensitiveCompare(rhs.person.name) == .orderedAscending
        }
      }
  }

  static func voiceCaption(_ voice: LocalSpeakerDiarizer.VoiceSummary?) -> String {
    guard let voice else { return "No voice yet — name them in a live transcript" }
    let minutes = Int(voice.speechSeconds / 60)
    let amount = minutes >= 1 ? "\(minutes) min heard" : "\(Int(voice.speechSeconds)) s heard"
    let clips = voice.sampleURLs.isEmpty ? "" : " · \(voice.sampleURLs.count) clip\(voice.sampleURLs.count == 1 ? "" : "s")"
    return (voice.isEnrolled ? "Voice known · \(amount)" : "Voice guessed · \(amount)") + clips
  }

  static func conversationCaption(count: Int, last: Date?, now: Date = Date()) -> String {
    guard count > 0, let last else { return "Not heard in a conversation yet" }
    let noun = count == 1 ? "conversation" : "conversations"
    let formatter = RelativeDateTimeFormatter()
    formatter.unitsStyle = .short
    return "\(count) \(noun) · last \(formatter.localizedString(for: last, relativeTo: now))"
  }
}

/// Everyone Omi has heard you talk to, and the voices it remembers for them and for you.
///
/// The voices are what make on-device speaker labels stick: a person named once in a live
/// transcript is recognised by voice in the next conversation, and "You" follows the user's
/// own remembered print instead of a guess.
struct PeoplePage: View {
  @ObservedObject var appState: AppState
  let brainDestination: MemoryHubDestination
  let onSelectBrainDestination: (MemoryHubDestination) -> Void

  @State private var searchText = ""
  @State private var activity: [String: PersonActivity] = [:]
  @State private var voices: [LocalSpeakerDiarizer.VoiceSummary] = []
  @State private var personPendingDeletion: Person?
  @StateObject private var samplePlayer = VoiceSamplePlayer()

  private var userVoice: LocalSpeakerDiarizer.VoiceSummary? {
    voices.first { $0.personId == nil }
  }

  private var rows: [PersonOverview] {
    let all = PersonOverview.ordered(people: appState.people, activity: activity, voices: voices)
    let query = searchText.trimmingCharacters(in: .whitespaces)
    guard !query.isEmpty else { return all }
    return all.filter { $0.person.name.localizedCaseInsensitiveContains(query) }
  }

  var body: some View {
    BrainSectionPageLayout(
      selected: brainDestination,
      onSelect: onSelectBrainDestination,
      search: {
        QuerySearchBar(
          text: $searchText,
          accessibilityID: "people-search-field",
          placeholder: "Search people…",
          searchSurface: .people
        )
      },
      content: {
        ScrollView {
          VStack(alignment: .leading, spacing: OmiSpacing.lg) {
            youCard
            peopleSection
          }
          .padding(.horizontal, QueryShellLayout.panelPaddingHorizontal)
          .padding(.bottom, OmiSpacing.xl)
        }
      }
    )
    .task { await reload() }
    .confirmationDialog(
      "Delete \(personPendingDeletion?.name ?? "this person")?",
      isPresented: Binding(get: { personPendingDeletion != nil }, set: { if !$0 { personPendingDeletion = nil } }),
      titleVisibility: .visible
    ) {
      Button("Delete", role: .destructive) {
        guard let person = personPendingDeletion else { return }
        personPendingDeletion = nil
        Task {
          _ = await appState.deletePerson(id: person.id)
          await reload()
        }
      }
      Button("Cancel", role: .cancel) { personPendingDeletion = nil }
    } message: {
      Text("Removes them from your people, their speaker labels in future conversations, and the voice Omi remembered.")
    }
    .accessibilityIdentifier("people-page")
  }

  // MARK: - You

  private var youCard: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      avatar(initial: "Y", isUser: true)
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("You")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(userVoiceCaption)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        Text("Omi learns your voice from push-to-talk and from “This is me” on a live transcript bubble.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.tertiary)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: 0)
      if let url = userVoice?.sampleURLs.first {
        playButton(url: url, identifier: "people-play-user-voice")
      }
      if userVoice != nil {
        pillButton(title: "Forget my voice", identifier: "people-forget-user-voice") {
          await LocalSpeakerDiarizer.shared.forgetVoice(personId: nil)
        }
      }
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(Ink.rowFill)
    )
    .accessibilityIdentifier("people-you-card")
  }

  private var userVoiceCaption: String {
    guard let userVoice else { return "Voice not learned yet" }
    let minutes = Int(userVoice.speechSeconds / 60)
    let amount = minutes >= 1 ? "\(minutes) min" : "\(Int(userVoice.speechSeconds)) s"
    return userVoice.isEnrolled ? "Voice known · \(amount) heard" : "Voice guessed from who talks most · \(amount) heard"
  }

  // MARK: - People

  @ViewBuilder
  private var peopleSection: some View {
    if rows.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text(appState.people.isEmpty ? "No people yet" : "No one matches")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
        if appState.people.isEmpty {
          Text("Tap a speaker in a live transcript to name them. Omi remembers their voice for next time.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      }
      .padding(.vertical, OmiSpacing.lg)
      .accessibilityIdentifier("people-empty")
    } else {
      VStack(spacing: OmiSpacing.xs) {
        ForEach(rows) { row in
          personRow(row)
        }
      }
    }
  }

  private func personRow(_ row: PersonOverview) -> some View {
    HStack(alignment: .center, spacing: OmiSpacing.md) {
      avatar(initial: String(row.person.name.prefix(1)).uppercased(), isUser: false)
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(row.person.name)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
        Text(PersonOverview.conversationCaption(count: row.conversationCount, last: row.lastTalkedAt))
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        Text(PersonOverview.voiceCaption(row.voice))
          .scaledFont(size: OmiType.caption)
          .foregroundColor(row.hasVoice ? Ink.secondary : Ink.tertiary)
      }
      Spacer(minLength: 0)
      if row.hasVoice {
        Button {
          Task {
            await LocalSpeakerDiarizer.shared.setFavorite(personId: row.id, !row.isFavorite)
            await reload()
          }
        } label: {
          Image(systemName: row.isFavorite ? "star.fill" : "star")
            .scaledFont(size: OmiType.body)
            .foregroundColor(row.isFavorite ? Ink.primary : Ink.tertiary)
            .frame(width: 24, height: 24)
        }
        .buttonStyle(.plain)
        .help(row.isFavorite ? "Unpin — this voice can be forgotten when space runs out" : "Pin — never forget this voice")
        .accessibilityIdentifier("people-favorite-\(row.id)")
      }
      if let url = row.sampleURL {
        playButton(url: url, identifier: "people-play-\(row.id)")
      }
      if row.hasVoice {
        pillButton(title: "Forget voice", identifier: "people-forget-voice-\(row.id)") {
          await LocalSpeakerDiarizer.shared.forgetVoice(personId: row.id)
        }
      }
      Button {
        personPendingDeletion = row.person
      } label: {
        Image(systemName: "trash")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.tertiary)
          .frame(width: 24, height: 24)
      }
      .buttonStyle(.plain)
      .help("Delete this person")
      .accessibilityIdentifier("people-delete-\(row.id)")
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(Ink.rowFill)
    )
    .accessibilityIdentifier("people-row-\(row.id)")
  }

  private func avatar(initial: String, isUser: Bool) -> some View {
    Circle()
      .fill(isUser ? Ink.primary : Ink.rowFillHover)
      .frame(width: 36, height: 36)
      .overlay(
        Text(initial)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(isUser ? Ink.surface : Ink.primary)
      )
  }

  private func playButton(url: URL, identifier: String) -> some View {
    let isPlaying = samplePlayer.playingURL == url
    return Button {
      samplePlayer.toggle(url)
    } label: {
      Image(systemName: isPlaying ? "stop.circle" : "play.circle")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .frame(width: 24, height: 24)
    }
    .buttonStyle(.plain)
    .help(isPlaying ? "Stop" : "Play a clip of this voice")
    .accessibilityIdentifier(identifier)
  }

  private func pillButton(title: String, identifier: String, action: @escaping () async -> Void) -> some View {
    Button {
      Task {
        await action()
        await reload()
      }
    } label: {
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.xs)
        .background(Capsule().fill(Ink.rowFillHover))
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier(identifier)
  }

  private func reload() async {
    await appState.fetchPeople()
    voices = await LocalSpeakerDiarizer.shared.voiceSummaries()
    activity = (try? await TranscriptionStorage.shared.personActivity()) ?? [:]
  }
}

/// Plays one remembered voice clip at a time.
@MainActor
final class VoiceSamplePlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
  @Published private(set) var playingURL: URL?
  private var player: AVAudioPlayer?

  func toggle(_ url: URL) {
    if playingURL == url {
      stop()
      return
    }
    stop()
    do {
      let player = try AVAudioPlayer(contentsOf: url)
      player.delegate = self
      self.player = player
      playingURL = url
      player.play()
    } catch {
      logError("VoiceSamplePlayer: could not play clip", error: error)
    }
  }

  func stop() {
    player?.stop()
    player = nil
    playingURL = nil
  }

  nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
    Task { @MainActor in self.stop() }
  }
}
