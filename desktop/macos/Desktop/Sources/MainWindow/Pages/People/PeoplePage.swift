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
        case (let l?, let r?) where l != r: return l > r
        case (.some, .none): return true
        case (.none, .some): return false
        default: return lhs.person.name.localizedCaseInsensitiveCompare(rhs.person.name) == .orderedAscending
        }
      }
  }

  /// Nil when no voice is known: the row says nothing rather than nagging.
  static func voiceCaption(_ voice: LocalSpeakerDiarizer.VoiceSummary?) -> String? {
    guard let voice else { return nil }
    let minutes = Int(voice.speechSeconds / 60)
    let amount = minutes >= 1 ? "\(minutes) min heard" : "\(Int(voice.speechSeconds)) s heard"
    let clips =
      voice.sampleURLs.isEmpty ? "" : " · \(voice.sampleURLs.count) clip\(voice.sampleURLs.count == 1 ? "" : "s")"
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

/// One saved clip of a voice: what the person sounds like.
struct VoiceSnippet: Identifiable, Equatable {
  let url: URL
  let durationSeconds: Double
  let recordedAt: Date?

  var id: URL { url }

  /// Clip files are named by their millisecond timestamp (`LocalVoiceprintStore.addSample`).
  static func recordedAt(from url: URL) -> Date? {
    guard let millis = Double(url.deletingPathExtension().lastPathComponent) else { return nil }
    return Date(timeIntervalSince1970: millis / 1000)
  }

  static func caption(durationSeconds: Double, recordedAt: Date?, now: Date = Date()) -> String {
    let seconds = max(1, Int(durationSeconds.rounded()))
    guard let recordedAt else { return "\(seconds)s" }
    let formatter = RelativeDateTimeFormatter()
    formatter.unitsStyle = .short
    return "\(seconds)s · \(formatter.localizedString(for: recordedAt, relativeTo: now))"
  }

  /// Read each clip's length; a clip that cannot be opened is left out.
  static func load(_ urls: [URL]) -> [VoiceSnippet] {
    urls.compactMap { url in
      guard let file = try? AVAudioFile(forReading: url), file.fileFormat.sampleRate > 0 else { return nil }
      return VoiceSnippet(
        url: url,
        durationSeconds: Double(file.length) / file.fileFormat.sampleRate,
        recordedAt: recordedAt(from: url))
    }
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
  @State private var editingPersonId: String?
  @State private var editedName = ""
  @FocusState private var nameFieldFocused: Bool
  /// Who was talked to according to the backend's conversations (from the last Refresh),
  /// merged with the local transcript store.
  @State private var remoteActivity: [String: PersonActivity] = [:]
  @State private var isRefreshing = false
  @State private var refreshStatus: String?
  /// Clips per voice owner ("user" or the person id), loaded with the summaries.
  @State private var snippets: [String: [VoiceSnippet]] = [:]
  @StateObject private var samplePlayer = VoiceSamplePlayer()

  private var rows: [PersonOverview] {
    let merged = PeopleRebuildPlanner.merge(activity, remoteActivity)
    let all = PersonOverview.ordered(people: appState.people, activity: merged, voices: voices)
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
          placeholder: "Search people",
          searchSurface: .people
        )
      },
      content: {
        ScrollView {
          VStack(alignment: .leading, spacing: OmiSpacing.lg) {
            refreshRow
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

  // MARK: - Refresh

  /// Re-listens to recent conversations and rebuilds every remembered voice from them.
  private var refreshRow: some View {
    HStack(spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: 2) {
        Text(refreshStatus ?? "Rebuild people from your conversations")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .lineLimit(2)
        if refreshStatus == nil {
          Text(
            "Goes through recent transcripts, listens again to everyone you've named and to you, and refreshes their voices and clips."
          )
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.tertiary)
          .fixedSize(horizontal: false, vertical: true)
        }
      }
      Spacer(minLength: 0)
      Button {
        Task { await refreshPeople() }
      } label: {
        Text(isRefreshing ? "Rebuilding" : "Rebuild")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(GlassShell.controlLabel(isProminent: !isRefreshing))
          .padding(.horizontal, OmiSpacing.md)
          .frame(height: QueryShellLayout.chipHeight)
          .glassChip(isActive: isRefreshing)
      }
      .buttonStyle(.plain)
      .disabled(isRefreshing)
      .accessibilityIdentifier("people-rebuild")
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(Ink.rowFill)
    )
  }

  private func refreshPeople() async {
    guard !isRefreshing else { return }
    isRefreshing = true
    await appState.fetchPeople()
    let summary = await PeopleRebuilder.shared.run { progress in
      Task { @MainActor in refreshStatus = progress.message }
    }
    remoteActivity = summary.activity
    refreshStatus = summary.message
    isRefreshing = false
    await reload()
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
        nameField(row)
        Text(PersonOverview.conversationCaption(count: row.conversationCount, last: row.lastTalkedAt))
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        if let caption = PersonOverview.voiceCaption(row.voice) {
          Text(caption)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        snippetRow(owner: LocalVoiceprintStore.sampleOwner(row.id))
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
        .help(
          row.isFavorite ? "Unpin — this voice can be forgotten when space runs out" : "Pin — never forget this voice"
        )
        .accessibilityIdentifier("people-favorite-\(row.id)")
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

  /// The name, editable in place: click it to type, Return saves, Escape cancels.
  @ViewBuilder
  private func nameField(_ row: PersonOverview) -> some View {
    if editingPersonId == row.id {
      TextField("Name", text: $editedName)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)
        .focused($nameFieldFocused)
        .onSubmit { Task { await commitRename(row) } }
        .onExitCommand { editingPersonId = nil }
        .onChange(of: nameFieldFocused) { _, focused in
          if !focused, editingPersonId == row.id { Task { await commitRename(row) } }
        }
        .frame(maxWidth: 260)
        .accessibilityIdentifier("people-name-field-\(row.id)")
    } else {
      Button {
        editedName = row.person.name
        editingPersonId = row.id
        nameFieldFocused = true
      } label: {
        Text(row.person.name)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
      }
      .buttonStyle(.plain)
      .help("Click to rename")
      .accessibilityIdentifier("people-name-\(row.id)")
    }
  }

  private func commitRename(_ row: PersonOverview) async {
    guard editingPersonId == row.id else { return }
    editingPersonId = nil
    let name = editedName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !name.isEmpty, name != row.person.name else { return }
    _ = await appState.renamePerson(id: row.id, name: name)
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

  /// What this voice sounds like: one chip per saved clip, newest first.
  @ViewBuilder
  private func snippetRow(owner: String) -> some View {
    if let clips = snippets[owner], !clips.isEmpty {
      FlowLayout(spacing: OmiSpacing.xs) {
        ForEach(clips) { clip in
          snippetChip(clip, owner: owner)
        }
      }
      .padding(.top, OmiSpacing.xxs)
      .accessibilityIdentifier("people-snippets-\(owner)")
    }
  }

  private func snippetChip(_ clip: VoiceSnippet, owner: String) -> some View {
    let isPlaying = samplePlayer.playingURL == clip.url
    return Button {
      samplePlayer.toggle(clip.url)
    } label: {
      HStack(spacing: 4) {
        Image(systemName: isPlaying ? "stop.fill" : "play.fill")
          .scaledFont(size: OmiType.micro, weight: .semibold)
        Text(VoiceSnippet.caption(durationSeconds: clip.durationSeconds, recordedAt: clip.recordedAt))
          .scaledFont(size: OmiType.micro, weight: .medium)
          .monospacedDigit()
      }
      .foregroundColor(isPlaying ? Ink.surface : Ink.secondary)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, 3)
      .background(Capsule().fill(isPlaying ? Ink.primary : Ink.rowFillHover))
    }
    .buttonStyle(.plain)
    .help(isPlaying ? "Stop" : "Hear what this voice sounds like")
    .accessibilityIdentifier("people-snippet-\(owner)-\(clip.url.lastPathComponent)")
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
    var loaded: [String: [VoiceSnippet]] = [:]
    for voice in voices {
      loaded[LocalVoiceprintStore.sampleOwner(voice.personId)] = VoiceSnippet.load(voice.sampleURLs)
    }
    snippets = loaded
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
