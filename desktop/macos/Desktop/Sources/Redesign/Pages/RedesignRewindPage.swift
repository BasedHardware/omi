import SwiftUI
import AppKit

/// Rewind, redesigned in the light "warm paper" Ink system — the mockup `rewind.html`.
///
/// Live-wired to the real `RewindViewModel` / `RewindStorage`: a real OCR + vector
/// search field, the main preview of the selected captured frame, a draggable timeline
/// scrubber, a filmstrip of the user's real thumbnails, and a "What I pulled from this"
/// side card that decodes the selected frame's extracted task(s) and on-screen OCR text.
///
/// Constructed from `PageContentView` where `appState`, `viewModelContainer`, and
/// `$selectedTabIndex` are in scope:
///
///     RedesignRewindPage(appState: appState, selectedIndex: $selectedTabIndex)
///
/// It owns its own `RewindViewModel` (the real one — no init args), exactly like the
/// existing `RewindPage`.
struct RedesignRewindPage: View {
  var appState: AppState? = nil
  @Binding var selectedIndex: Int

  @StateObject private var viewModel = RewindViewModel()

  /// Index into `viewModel.screenshots` (oldest-first / ASC) of the selected frame.
  @State private var currentIndex: Int = 0
  @State private var currentImage: NSImage? = nil
  @FocusState private var searchFocused: Bool

  // MARK: - Derived

  private var shots: [Screenshot] { viewModel.screenshots }

  private var selectedShot: Screenshot? {
    guard currentIndex >= 0, currentIndex < shots.count else { return nil }
    return shots[currentIndex]
  }

  /// Token that changes whenever the visible frame changes, driving `.task(id:)` reload.
  private var frameToken: String {
    "\(shots.count)|\(currentIndex)|\(selectedShot?.id ?? -1)"
  }

  private var frameCountLabel: String {
    let n = shots.count
    if viewModel.activeSearchQuery != nil {
      return "\(n) result\(n == 1 ? "" : "s")"
    }
    let day = viewModel.selectedDate
    let prefix = Calendar.current.isDateInToday(day) ? "Today" : Self.dayFormatter.string(from: day)
    return "\(prefix) · \(n) frame\(n == 1 ? "" : "s")"
  }

  // MARK: - Body

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        header
        searchField
          .padding(.top, InkSpace.s5)

        content
          .padding(.top, InkSpace.s6)

        footer
          .padding(.top, InkSpace.s6)
      }
      .frame(maxWidth: 1040, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .task { await viewModel.loadInitialData() }
    .task(id: frameToken) { await loadMainFrame() }
    .onChange(of: viewModel.screenshots) { old, new in
      reconcileSelection(old: old, new: new)
    }
  }

  // MARK: - Header

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 8) {
        Text("Rewind").inkEyebrow()
        Text("Everything you saw, kept.").inkH1()
      }
      Spacer()
      Text(frameCountLabel)
        .font(InkFont.mono(12))
        .foregroundColor(Ink.faint)
        .padding(.top, 4)
    }
  }

  // MARK: - Search

  private var searchField: some View {
    HStack(spacing: 10) {
      Image(systemName: "magnifyingglass")
        .font(.system(size: 14, weight: .medium))
        .foregroundColor(searchFocused ? Ink.ink : Ink.faint)

      ZStack(alignment: .leading) {
        if viewModel.searchQuery.isEmpty {
          Text("Find anything you saw — \u{201C}the lead CSV\u{201D}, \u{201C}that merge conflict\u{201D}, \u{201C}the PR\u{201D}")
            .font(InkFont.sans(15))
            .foregroundColor(Ink.faint)
        }
        TextField("", text: $viewModel.searchQuery)
          .textFieldStyle(.plain)
          .font(InkFont.sans(15))
          .foregroundColor(Ink.ink)
          .focused($searchFocused)
      }

      if viewModel.isSearching {
        ProgressView().progressViewStyle(.circular).scaleEffect(0.5).tint(Ink.faint)
      } else if !viewModel.searchQuery.isEmpty {
        Button { viewModel.searchQuery = "" } label: {
          Image(systemName: "xmark.circle.fill")
            .font(.system(size: 13))
            .foregroundColor(Ink.faint)
        }
        .buttonStyle(.plain)
      } else {
        Text("\u{2318}F")
          .font(InkFont.mono(11, .medium))
          .foregroundColor(Ink.faint)
          .padding(.horizontal, 7)
          .frame(height: 22)
          .background(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
              .fill(Ink.surface2)
              .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Ink.hair, lineWidth: 1)))
      }
    }
    .padding(.horizontal, 16)
    .frame(height: 48)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .strokeBorder(searchFocused ? Ink.hair2 : Ink.hair, lineWidth: 1)))
  }

  // MARK: - Content (two-pane grid)

  @ViewBuilder
  private var content: some View {
    if shots.isEmpty {
      emptyState
    } else {
      HStack(alignment: .top, spacing: 22) {
        VStack(alignment: .leading, spacing: 0) {
          framePreview
          scrubber.padding(.top, 14)
          timeRow.padding(.top, 12)
          filmstrip.padding(.top, 16)
        }
        .frame(maxWidth: .infinity, alignment: .leading)

        pulledCard
          .frame(width: 320)
      }
    }
  }

  // MARK: - Frame preview

  private var framePreview: some View {
    ZStack(alignment: .bottomLeading) {
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface2)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1))

      if let image = currentImage, image.size.width > 0, image.size.height > 0 {
        Image(nsImage: image)
          .resizable()
          .aspectRatio(contentMode: .fit)
          .padding(1)
      } else if viewModel.isLoading {
        ProgressView().progressViewStyle(.circular).scaleEffect(0.8).tint(Ink.faint)
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        VStack(spacing: 8) {
          Image(systemName: "photo").font(.system(size: 22)).foregroundColor(Ink.faint)
          Text("No frame").inkCaption()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }

      // App / window context pill over the frame
      if let shot = selectedShot {
        HStack(spacing: 6) {
          Image(systemName: "display").font(.system(size: 11))
          Text(contextTitle(for: shot))
            .font(InkFont.sans(12, .medium))
            .lineLimit(1)
        }
        .foregroundColor(Ink.body)
        .padding(.horizontal, 11)
        .frame(height: 26)
        .background(
          Capsule().fill(Ink.surface.opacity(0.94))
            .overlay(Capsule().strokeBorder(Ink.hair, lineWidth: 1)))
        .padding(14)
      }
    }
    .frame(height: 320)
    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
  }

  // MARK: - Scrubber

  private var scrubber: some View {
    GeometryReader { geo in
      let count = shots.count
      let frac: CGFloat = count > 1 ? CGFloat(currentIndex) / CGFloat(count - 1) : 0
      let w = geo.size.width
      ZStack(alignment: .leading) {
        Capsule().fill(Ink.hair).frame(height: 3)
        Capsule().fill(Ink.accent).frame(width: max(0, w * frac), height: 3)
        Circle()
          .fill(Ink.accent)
          .frame(width: 13, height: 13)
          .overlay(Circle().strokeBorder(Ink.surface, lineWidth: 2))
          .shadow(color: Ink.shadow, radius: 3, y: 1)
          .offset(x: min(max(0, w * frac - 6.5), w - 13))
      }
      .frame(height: 13)
      .contentShape(Rectangle())
      .gesture(
        DragGesture(minimumDistance: 0).onChanged { v in
          guard count > 1, w > 0 else { return }
          let f = min(max(0, v.location.x / w), 1)
          currentIndex = Int((f * CGFloat(count - 1)).rounded())
        })
    }
    .frame(height: 13)
  }

  private var timeRow: some View {
    HStack {
      Text(shots.first.map { Self.timeFormatter.string(from: $0.timestamp) } ?? "")
        .font(InkFont.mono(12)).foregroundColor(Ink.faint)
      Spacer()
      if let shot = selectedShot {
        Text("Selected · \(Self.selectedFormatter.string(from: shot.timestamp))")
          .font(InkFont.sans(12)).foregroundColor(Ink.body)
      }
      Spacer()
      Text(shots.last.map { Self.timeFormatter.string(from: $0.timestamp) } ?? "")
        .font(InkFont.mono(12)).foregroundColor(Ink.faint)
    }
  }

  // MARK: - Filmstrip

  private var filmstrip: some View {
    ScrollViewReader { proxy in
      ScrollView(.horizontal, showsIndicators: false) {
        LazyHStack(spacing: 10) {
          ForEach(Array(shots.enumerated()), id: \.offset) { idx, shot in
            RewindFilmstripThumb(
              screenshot: shot,
              isSelected: idx == currentIndex,
              onTap: { currentIndex = idx })
            .id(idx)
          }
        }
        .padding(.vertical, 2)
      }
      .onChange(of: currentIndex) { _, i in
        withAnimation(.easeInOut(duration: 0.2)) { proxy.scrollTo(i, anchor: .center) }
      }
      .onAppear { proxy.scrollTo(currentIndex, anchor: .center) }
    }
    .frame(height: 66)
  }

  // MARK: - "What I pulled from this" card

  private var pulledCard: some View {
    InkCard(padding: 20) {
      VStack(alignment: .leading, spacing: 0) {
        Text("What I pulled from this").inkEyebrow()

        if let shot = selectedShot {
          let tasks = extractedTasks(for: shot)
          let text = cleanedOCR(shot.ocrText)
          let hasAny = !tasks.isEmpty || text != nil

          VStack(alignment: .leading, spacing: 0) {
            // Where it came from — always real (app + window).
            pulledItem {
              HStack(spacing: 7) {
                Image(systemName: "display").font(.system(size: 12)).foregroundColor(Ink.faint)
                Text("On screen").font(InkFont.sans(12, .medium)).foregroundColor(Ink.faint)
              }
              Text(contextTitle(for: shot))
                .font(InkFont.sans(14, .medium)).foregroundColor(Ink.ink)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 6)
            }

            // Extracted task(s) — decoded from the real extractedTasksJson.
            if let task = tasks.first {
              divider
              pulledItem {
                HStack(spacing: 7) {
                  Image(systemName: "checkmark.circle").font(.system(size: 12)).foregroundColor(Ink.faint)
                  Text("New task").font(InkFont.sans(12, .medium)).foregroundColor(Ink.faint)
                }
                Text(task.title)
                  .font(InkFont.sans(14, .medium)).foregroundColor(Ink.ink)
                  .fixedSize(horizontal: false, vertical: true)
                  .padding(.top, 6)
                if let deadline = task.inferredDeadline, !deadline.isEmpty {
                  Text("Due \(deadline)").inkCaption().padding(.top, 3)
                }
              }
            }

            // On-screen OCR text — the real captured text.
            if let text {
              divider
              pulledItem {
                Text("Text on screen").inkEyebrow()
                Text("\u{201C}\(text)\u{201D}")
                  .font(InkFont.mono(12))
                  .foregroundColor(Ink.muted)
                  .lineSpacing(3)
                  .lineLimit(6)
                  .fixedSize(horizontal: false, vertical: true)
                  .padding(.top, 6)
              }
            }

            if !hasAny {
              Text("Nothing extracted from this frame yet.")
                .inkSmall()
                .padding(.top, 14)
            }
          }
          .padding(.top, 4)

          InkButton(title: "Ask about this moment", systemImage: "sparkles", kind: .plain, size: .sm, fullWidth: true) {
            selectedIndex = 2  // Ask / Chat
          }
          .padding(.top, 16)
        } else {
          Text("Select a frame to see what I kept.")
            .inkSmall()
            .padding(.top, 12)
        }
      }
    }
  }

  @ViewBuilder
  private func pulledItem<C: View>(@ViewBuilder _ content: () -> C) -> some View {
    VStack(alignment: .leading, spacing: 0) { content() }
      .padding(.vertical, 14)
      .frame(maxWidth: .infinity, alignment: .leading)
  }

  private var divider: some View {
    Rectangle().fill(Ink.hair).frame(height: 1)
  }

  // MARK: - Footer

  private var footer: some View {
    HStack(spacing: 8) {
      Image(systemName: "lock").font(.system(size: 11)).foregroundColor(Ink.faint)
      Text("Frames stay on your Mac. Deleted after \(RewindSettings.shared.retentionDays) days unless you keep them.")
        .inkCaption()
    }
  }

  // MARK: - Empty state

  private var emptyState: some View {
    InkCard(padding: 28, recessed: true) {
      VStack(spacing: 8) {
        Image(systemName: "clock.arrow.circlepath")
          .font(.system(size: 26)).foregroundColor(Ink.faint)
        Text(emptyTitle)
          .font(InkFont.serif(19, .medium)).foregroundColor(Ink.ink).tracking(-0.3)
        Text(emptyBody).inkSmall().multilineTextAlignment(.center)
      }
      .frame(maxWidth: .infinity)
      .padding(.vertical, 8)
    }
  }

  private var emptyTitle: String {
    if appState?.hasScreenRecordingPermission == false { return "Screen Recording is off." }
    if viewModel.activeSearchQuery != nil { return "Nothing matched that." }
    return "Nothing captured yet."
  }

  private var emptyBody: String {
    if appState?.hasScreenRecordingPermission == false {
      return "Grant Screen Recording and I'll start keeping what you see."
    }
    if viewModel.activeSearchQuery != nil { return "Try a different search term." }
    return "Frames show up here as you use your Mac."
  }

  // MARK: - Frame loading

  private func loadMainFrame() async {
    guard let shot = selectedShot else {
      currentImage = nil
      return
    }
    viewModel.selectScreenshot(shot)
    do {
      let image = try await RewindStorage.shared.loadScreenshotImage(for: shot)
      if !Task.isCancelled { currentImage = image }
    } catch {
      if !Task.isCancelled { currentImage = nil }
    }
  }

  /// Keep the user pinned to the same frame across refreshes; otherwise jump to newest.
  private func reconcileSelection(old: [Screenshot], new: [Screenshot]) {
    if new.isEmpty {
      currentIndex = 0
      currentImage = nil
      return
    }
    if !old.isEmpty, currentIndex < old.count, let id = old[currentIndex].id,
      let idx = new.firstIndex(where: { $0.id == id }) {
      currentIndex = idx
    } else {
      currentIndex = new.count - 1  // newest (ASC order → last)
    }
  }

  // MARK: - Extraction helpers (decode the real per-frame JSON)

  private func extractedTasks(for shot: Screenshot) -> [ExtractedTask] {
    guard let json = shot.extractedTasksJson, let data = json.data(using: .utf8) else { return [] }
    if let arr = try? JSONDecoder().decode([ExtractedTask].self, from: data) { return arr }
    if let one = try? JSONDecoder().decode(ExtractedTask.self, from: data) { return [one] }
    return []
  }

  private func cleanedOCR(_ raw: String?) -> String? {
    guard let raw else { return nil }
    let collapsed = raw
      .replacingOccurrences(of: "\n", with: " · ")
      .replacingOccurrences(of: "  ", with: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !collapsed.isEmpty else { return nil }
    return collapsed.count > 240 ? String(collapsed.prefix(240)) + "\u{2026}" : collapsed
  }

  private func contextTitle(for shot: Screenshot) -> String {
    if let title = shot.windowTitle, !title.isEmpty { return "\(shot.appName) — \(title)" }
    return shot.appName
  }

  // MARK: - Formatters

  private static let timeFormatter: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "h:mm a"; return f
  }()
  private static let selectedFormatter: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "MMM d h:mm a"; return f
  }()
  private static let dayFormatter: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "MMM d"; return f
  }()
}

// MARK: - Filmstrip thumbnail (light Ink style, real captured frame)

private struct RewindFilmstripThumb: View {
  let screenshot: Screenshot
  let isSelected: Bool
  let onTap: () -> Void

  @State private var image: NSImage? = nil

  private static let timeFormatter: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "h:mm"; return f
  }()

  var body: some View {
    Button(action: onTap) {
      ZStack(alignment: .bottomLeading) {
        RoundedRectangle(cornerRadius: 9, style: .continuous)
          .fill(Ink.surface2)

        if let image {
          Image(nsImage: image)
            .resizable()
            .aspectRatio(contentMode: .fill)
        } else {
          Image(systemName: "photo")
            .font(.system(size: 14))
            .foregroundColor(Ink.faint)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }

        Text(Self.timeFormatter.string(from: screenshot.timestamp))
          .font(InkFont.mono(10))
          .foregroundColor(.white)
          .padding(.horizontal, 5)
          .padding(.vertical, 2)
          .background(RoundedRectangle(cornerRadius: 4).fill(Color.black.opacity(0.55)))
          .padding(6)
      }
      .frame(width: 104, height: 62)
      .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
      .overlay(
        RoundedRectangle(cornerRadius: 9, style: .continuous)
          .strokeBorder(isSelected ? Ink.accent : Ink.hair, lineWidth: isSelected ? 2 : 1))
      .overlay(
        RoundedRectangle(cornerRadius: 9, style: .continuous)
          .strokeBorder(isSelected ? Ink.accentTint : .clear, lineWidth: isSelected ? 3 : 0)
          .padding(-2))
    }
    .buttonStyle(.plain)
    .task(id: screenshot.id) { await load() }
  }

  private func load() async {
    do {
      let full = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
      let target = NSSize(width: 208, height: 124)
      let thumb = NSImage(size: target)
      thumb.lockFocus()
      full.draw(
        in: NSRect(origin: .zero, size: target),
        from: NSRect(origin: .zero, size: full.size),
        operation: .copy, fraction: 1.0)
      thumb.unlockFocus()
      if !Task.isCancelled { image = thumb }
    } catch {
      // Leave placeholder on failure (e.g. frame in an unfinalized chunk).
    }
  }
}
