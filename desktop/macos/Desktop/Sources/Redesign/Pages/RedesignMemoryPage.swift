import SwiftUI

/// The memory screen — mockup `memory.html`, live-wired to `MemoriesViewModel`.
///
/// Two panes: a flexible left list of remembered facts (grouped Today / This week /
/// Earlier) with a search field, and a fixed ~392px right panel on `Ink.soft` that
/// shows the profile omi uses ("What I know about you") plus a static brain-map preview.
struct RedesignMemoryPage: View {
  @ObservedObject var viewModel: MemoriesViewModel

  /// Backend id of the row currently expanded inline (accordion — one at a time).
  @State private var expandedMemoryId: String? = nil

  var body: some View {
    HStack(spacing: 0) {
      leftPane
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay(alignment: .trailing) {
          Rectangle().fill(Ink.hair).frame(width: 1)
        }
      rightPane
        .frame(width: 392)
        .frame(maxHeight: .infinity)
        .background(Ink.soft)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .task {
      await viewModel.loadMemoriesIfNeeded()
    }
  }

  // MARK: - Left pane (the list)

  private var keptCount: Int {
    viewModel.totalMemoriesCount > 0 ? viewModel.totalMemoriesCount : viewModel.memories.count
  }

  private var leftPane: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Header + search
      VStack(alignment: .leading, spacing: 12) {
        HStack(alignment: .firstTextBaseline) {
          Text("Memory").inkH2()
          Spacer()
          Text("\(formattedCount(keptCount)) kept")
            .font(InkFont.mono(12)).foregroundColor(Ink.faint)
        }
        searchField
      }
      .padding(.horizontal, 24)
      .padding(.top, 20)
      .padding(.bottom, 12)

      // Grouped list
      if viewModel.isLoading && viewModel.memories.isEmpty {
        loadingState
      } else if viewModel.filteredMemories.isEmpty {
        emptyState
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 0) {
            ForEach(groupedMemories, id: \.title) { group in
              Text(group.title)
                .font(InkFont.sans(11, .semibold))
                .foregroundColor(Ink.faint)
                .tracking(1.3)
                .textCase(.uppercase)
                .padding(.horizontal, 8)
                .padding(.top, 16)
                .padding(.bottom, 8)

              ForEach(group.memories) { memory in
                MemoryRow(
                  memory: memory,
                  viewModel: viewModel,
                  source: sourceCaption(for: memory),
                  fullDetail: fullDetailCaption(for: memory),
                  isExpanded: expandedMemoryId == memory.id,
                  onToggle: {
                    withAnimation(.easeInOut(duration: 0.18)) {
                      expandedMemoryId = (expandedMemoryId == memory.id) ? nil : memory.id
                    }
                  },
                  onDeleted: {
                    if expandedMemoryId == memory.id { expandedMemoryId = nil }
                  }
                )
                .onAppear {
                  Task { await viewModel.loadMoreIfNeeded(currentMemory: memory) }
                }
              }
            }

            if viewModel.isLoadingMore {
              HStack {
                Spacer()
                ProgressView().scaleEffect(0.7)
                Spacer()
              }
              .padding(.vertical, 16)
            }
          }
          .padding(.horizontal, 16)
          .padding(.bottom, 24)
          .padding(.top, 4)
        }
      }
    }
  }

  private var searchField: some View {
    HStack(spacing: 10) {
      Image(systemName: "magnifyingglass")
        .font(.system(size: 13)).foregroundColor(Ink.faint)
      TextField("Search everything I've seen and heard…", text: $viewModel.searchText)
        .textFieldStyle(.plain)
        .font(InkFont.sans(14))
        .foregroundColor(Ink.ink)
      if !viewModel.searchText.isEmpty {
        Button {
          viewModel.searchText = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .font(.system(size: 13)).foregroundColor(Ink.faint)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, 14)
    .frame(height: 40)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 11, style: .continuous)
            .strokeBorder(Ink.hair2, lineWidth: 1))
    )
  }

  @ViewBuilder private var loadingState: some View {
    VStack {
      Spacer()
      ProgressView()
      Spacer()
    }
    .frame(maxWidth: .infinity)
  }

  @ViewBuilder private var emptyState: some View {
    VStack(spacing: 8) {
      Spacer()
      Text(viewModel.searchText.isEmpty ? "Nothing kept yet." : "No matches.")
        .inkBody()
      Text(viewModel.searchText.isEmpty
        ? "Memories build up from your calls, screen, and messages."
        : "Try a different search.")
        .inkCaption()
      Spacer()
    }
    .frame(maxWidth: .infinity)
    .padding(.horizontal, 24)
  }

  // MARK: - Right pane (profile + brain map)

  private var rightPane: some View {
    VStack(alignment: .leading, spacing: 0) {
      VStack(alignment: .leading, spacing: 8) {
        Text("What I know about you").inkEyebrow()
        Text("The profile I use to help — edit any memory on the left and it sticks.")
          .font(InkFont.sans(13)).foregroundColor(Ink.body)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(.horizontal, 22)
      .padding(.top, 20)
      .padding(.bottom, 8)

      ScrollView {
        VStack(alignment: .leading, spacing: 0) {
          ForEach(profileFacts) { memory in
            FactRow(text: memory.content, meta: learnedFrom(for: memory))
          }

          HStack {
            Text("Your brain map")
              .font(InkFont.sans(11, .semibold))
              .foregroundColor(Ink.faint)
              .tracking(1.3)
              .textCase(.uppercase)
            Spacer()
            Text("Open full map →")
              .font(InkFont.sans(11, .semibold))
              .foregroundColor(Ink.ink)
          }
          .padding(.horizontal, 8)
          .padding(.top, 18)
          .padding(.bottom, 6)

          Button {
            NotificationCenter.default.post(
              name: .navigateToSidebarItem, object: nil, userInfo: ["rawValue": 24])
          } label: {
            BrainMapPreview(labels: brainMapLabels).padding(.horizontal, 8)
          }
          .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 20)
        .padding(.top, 6)
      }
    }
  }

  /// Facts to show as the profile: prefer "About You" (system) memories, then fill
  /// with the most recent memories so the panel is never empty.
  private var profileFacts: [ServerMemory] {
    let systemFacts = viewModel.memories.filter { $0.category == .system }
    let base = systemFacts.isEmpty ? viewModel.memories : systemFacts
    return Array(base.prefix(8))
  }

  private var brainMapLabels: [String] {
    // Short, distinctive words drawn from the top facts; padded to keep the graph full.
    let words = profileFacts.compactMap { firstProperNoun(in: $0.content) }
    var unique: [String] = []
    for w in words where !unique.contains(w) { unique.append(w) }
    return Array(unique.prefix(4))
  }

  // MARK: - Grouping

  private struct MemoryGroup { let title: String; let memories: [ServerMemory] }

  private var groupedMemories: [MemoryGroup] {
    let cal = Calendar.current
    var today: [ServerMemory] = []
    var week: [ServerMemory] = []
    var earlier: [ServerMemory] = []
    let weekAgo = cal.date(byAdding: .day, value: -7, to: Date()) ?? Date.distantPast
    for m in viewModel.filteredMemories {
      if cal.isDateInToday(m.createdAt) {
        today.append(m)
      } else if m.createdAt >= weekAgo {
        week.append(m)
      } else {
        earlier.append(m)
      }
    }
    var groups: [MemoryGroup] = []
    if !today.isEmpty { groups.append(MemoryGroup(title: "Today", memories: today)) }
    if !week.isEmpty { groups.append(MemoryGroup(title: "This week", memories: week)) }
    if !earlier.isEmpty { groups.append(MemoryGroup(title: "Earlier", memories: earlier)) }
    return groups
  }

  // MARK: - Formatting helpers

  private func formattedCount(_ n: Int) -> String {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    return f.string(from: NSNumber(value: n)) ?? "\(n)"
  }

  private func sourceCaption(for memory: ServerMemory) -> String {
    let name = memory.sourceName ?? "omi"
    return "\(name) · \(shortTime(memory.createdAt))"
  }

  /// Full, human date shown in the expanded detail (e.g. "Jul 7, 2026 at 3:14 PM").
  private func fullDetailCaption(for memory: ServerMemory) -> String {
    let f = DateFormatter()
    f.dateStyle = .medium
    f.timeStyle = .short
    return f.string(from: memory.createdAt)
  }

  private func shortTime(_ date: Date) -> String {
    let cal = Calendar.current
    let f = DateFormatter()
    if cal.isDateInToday(date) {
      f.dateFormat = "h:mm a"
    } else if let weekAgo = cal.date(byAdding: .day, value: -7, to: Date()), date >= weekAgo {
      f.dateFormat = "EEE"
    } else {
      f.dateFormat = "MMM d"
    }
    return f.string(from: date)
  }

  private func learnedFrom(for memory: ServerMemory) -> String {
    if memory.manuallyAdded { return "Confirmed by you" }
    if let name = memory.sourceName { return "Learned from \(name)" }
    return "Learned from your activity"
  }

  /// Grab the first capitalized word from a fact for the brain-map node pills.
  private func firstProperNoun(in text: String) -> String? {
    for raw in text.split(separator: " ") {
      let word = raw.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
      guard let first = word.first, first.isUppercase, word.count > 2 else { continue }
      return String(word.prefix(12))
    }
    return nil
  }
}

// MARK: - Left list row

/// A remembered fact. Tapping the row expands it inline to reveal the full
/// content, its provenance (source · full date · category · visibility), and the
/// real actions — Edit, change visibility, Delete — all wired to
/// `MemoriesViewModel` so changes persist.
private struct MemoryRow: View {
  let memory: ServerMemory
  @ObservedObject var viewModel: MemoriesViewModel
  let source: String
  let fullDetail: String
  let isExpanded: Bool
  let onToggle: () -> Void
  let onDeleted: () -> Void

  @State private var hovering = false
  @State private var isEditing = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Tappable summary (collapsed content clamps to two lines).
      Button(action: onToggle) {
        HStack(alignment: .top, spacing: 10) {
          VStack(alignment: .leading, spacing: 5) {
            Text(memory.content)
              .font(InkFont.sans(14)).foregroundColor(Ink.ink)
              .lineSpacing(2)
              .lineLimit(isExpanded ? nil : 2)
              .fixedSize(horizontal: false, vertical: true)
            Text(source)
              .font(InkFont.sans(12)).foregroundColor(Ink.faint)
          }
          Spacer(minLength: 0)
          Image(systemName: "chevron.down")
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(Ink.faint)
            .rotationEffect(.degrees(isExpanded ? 180 : 0))
            .opacity(hovering || isExpanded ? 1 : 0)
            .padding(.top, 3)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      if isExpanded {
        expandedDetail
          .padding(.top, 12)
      }
    }
    .padding(12)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(isExpanded ? Ink.surface : (hovering ? Ink.surface2 : .clear))
        .overlay(
          RoundedRectangle(cornerRadius: 11, style: .continuous)
            .strokeBorder(isExpanded ? Ink.hair2 : .clear, lineWidth: 1))
    )
    .onHover { hovering = $0 }
  }

  // MARK: - Expanded detail

  @ViewBuilder private var expandedDetail: some View {
    VStack(alignment: .leading, spacing: 12) {
      Rectangle().fill(Ink.hair).frame(height: 1)

      // Metadata chips
      HStack(spacing: 8) {
        metaChip(icon: memory.category.icon, text: memory.category.displayName)
        metaChip(
          icon: memory.isPublic ? "globe" : "lock",
          text: memory.isPublic ? "Public" : "Private")
        if memory.manuallyAdded {
          metaChip(icon: "checkmark.seal", text: "Added by you")
        }
      }

      Text(fullDetail)
        .font(InkFont.sans(12)).foregroundColor(Ink.faint)

      if isEditing {
        editor
      } else {
        actions
      }
    }
  }

  private func metaChip(icon: String, text: String) -> some View {
    HStack(spacing: 5) {
      Image(systemName: icon).font(.system(size: 10))
      Text(text).font(InkFont.sans(11.5, .medium))
    }
    .foregroundColor(Ink.body)
    .padding(.horizontal, 9).frame(height: 24)
    .background(
      Capsule().fill(Ink.surface2)
        .overlay(Capsule().strokeBorder(Ink.hair, lineWidth: 1)))
  }

  // MARK: - Actions row (wired to the real view model)

  private var actions: some View {
    HStack(spacing: 8) {
      rowButton(label: "Edit", systemImage: "square.and.pencil") {
        viewModel.editText = memory.content
        withAnimation(.easeInOut(duration: 0.15)) { isEditing = true }
      }

      rowButton(
        label: memory.isPublic ? "Make private" : "Make public",
        systemImage: memory.isPublic ? "lock" : "globe",
        disabled: viewModel.isTogglingVisibility
      ) {
        Task { await viewModel.toggleVisibility(memory) }
      }

      Spacer(minLength: 0)

      rowButton(label: "Delete", systemImage: "trash", tint: Ink.danger) {
        onDeleted()
        Task { await viewModel.deleteMemory(memory) }
      }
    }
  }

  // MARK: - Inline editor (wired to viewModel.editText + saveEditedMemory)

  private var editor: some View {
    VStack(alignment: .leading, spacing: 10) {
      TextField("Memory", text: $viewModel.editText, axis: .vertical)
        .textFieldStyle(.plain)
        .font(InkFont.sans(14)).foregroundColor(Ink.ink)
        .lineLimit(2...8)
        .padding(10)
        .background(
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(Ink.surface2)
            .overlay(
              RoundedRectangle(cornerRadius: 9, style: .continuous)
                .strokeBorder(Ink.hair2, lineWidth: 1)))

      HStack(spacing: 8) {
        Spacer(minLength: 0)
        rowButton(label: "Cancel", systemImage: nil) {
          viewModel.editText = ""
          withAnimation(.easeInOut(duration: 0.15)) { isEditing = false }
        }
        rowButton(
          label: "Save", systemImage: "checkmark", filled: true,
          disabled: viewModel.editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        ) {
          Task {
            await viewModel.saveEditedMemory(memory)
            withAnimation(.easeInOut(duration: 0.15)) { isEditing = false }
          }
        }
      }
    }
  }

  /// Compact pill button matching the Ink aesthetic (InkButton is too tall here).
  private func rowButton(
    label: String,
    systemImage: String?,
    tint: Color = Ink.ink,
    filled: Bool = false,
    disabled: Bool = false,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(spacing: 5) {
        if let systemImage { Image(systemName: systemImage).font(.system(size: 11, weight: .semibold)) }
        Text(label).font(InkFont.sans(12.5, .medium))
      }
      .foregroundColor(filled ? Ink.accentInk : tint)
      .padding(.horizontal, 12).frame(height: 30)
      .background(
        Capsule(style: .continuous)
          .fill(filled ? Ink.ink : Ink.surface)
          .overlay(Capsule(style: .continuous).strokeBorder(filled ? .clear : Ink.hair2, lineWidth: 1)))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .disabled(disabled)
    .opacity(disabled ? 0.5 : 1)
  }
}

// MARK: - Right panel fact row

private struct FactRow: View {
  let text: String
  let meta: String
  @State private var hovering = false

  var body: some View {
    HStack(alignment: .top, spacing: 10) {
      Circle().fill(Ink.accent).frame(width: 6, height: 6)
        .padding(.top, 7)
      VStack(alignment: .leading, spacing: 4) {
        Text(text)
          .font(InkFont.sans(13.5)).foregroundColor(Ink.ink)
          .lineSpacing(2)
          .fixedSize(horizontal: false, vertical: true)
        Text(meta)
          .font(InkFont.sans(11.5)).foregroundColor(Ink.faint)
      }
      Spacer(minLength: 0)
    }
    .padding(12)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(hovering ? Ink.surface : .clear))
    .onHover { hovering = $0 }
  }
}

// MARK: - Static brain-map preview

private struct BrainMapPreview: View {
  let labels: [String]

  // Fixed satellite slots (fractional positions inside the box), mockup-matched.
  private let slots: [(x: CGFloat, y: CGFloat, dim: Bool)] = [
    (0.14, 0.22, false),
    (0.72, 0.20, true),
    (0.80, 0.70, true),
    (0.18, 0.76, false),
  ]

  var body: some View {
    GeometryReader { geo in
      let w = geo.size.width
      let h = geo.size.height
      ZStack {
        // Faint connective lines from core to satellites.
        Path { path in
          let core = CGPoint(x: w * 0.44, y: h * 0.48)
          for (i, _) in labels.enumerated() where i < slots.count {
            path.move(to: core)
            path.addLine(to: CGPoint(x: w * slots[i].x + 24, y: h * slots[i].y + 10))
          }
        }
        .stroke(Ink.hair2, lineWidth: 1)

        // Satellite nodes
        ForEach(Array(labels.enumerated()), id: \.offset) { i, label in
          if i < slots.count {
            node(label, dim: slots[i].dim)
              .position(x: w * slots[i].x + 30, y: h * slots[i].y + 11)
          }
        }

        // Core node
        coreNode
          .position(x: w * 0.44 + 4, y: h * 0.48)
      }
    }
    .frame(height: 120)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1))
    )
    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
  }

  private var coreNode: some View {
    Text("omi")
      .font(InkFont.serif(13, .medium)).foregroundColor(Ink.accentInk)
      .padding(.horizontal, 12).frame(height: 26)
      .background(Capsule().fill(Ink.ink))
  }

  private func node(_ label: String, dim: Bool) -> some View {
    Text(label)
      .font(InkFont.sans(11.5, .medium))
      .foregroundColor(dim ? Ink.faint : Ink.body)
      .lineLimit(1)
      .padding(.horizontal, 10).frame(height: 24)
      .background(
        Capsule().fill(Ink.surface2)
          .overlay(Capsule().strokeBorder(Ink.hair, lineWidth: 1)))
  }
}
