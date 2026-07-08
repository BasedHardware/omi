import SwiftUI

/// Redesigned Messages page (Ink design system, light mode).
///
/// Ported from `mockup/screens/messages-{imessage,telegram,whatsapp}.html`: a two-pane
/// messaging inbox. The left rail (≈320px on `Ink.soft`) holds a channel switcher
/// (iMessage / Telegram / WhatsApp with real colored brand logos), a search field,
/// attention filters, and the conversation list. The right pane shows the selected
/// thread — message bubbles plus omi's draft-reply surface: the dashed `.draft-compose`
/// box ("omi drafted this — review before it sends" · Send / Edit / Discard), a tentative
/// calendar hold, a "needs you" escalation, and an auto-reply note, depending on the thread.
///
/// **This branch has no real messaging stores yet.** Everything renders from the in-file
/// `MessagesSampleData` below, so the shell is visually complete today. When the messaging
/// update lands, swap `MessagesSampleData` for the real iMessage/Telegram/WhatsApp inbox
/// stores (see the note at the bottom of this file) — the views take plain value types and
/// don't care where they come from.
///
/// Parameterless, so it drops straight into `PageContentView` as `RedesignMessagesPage()`.
struct RedesignMessagesPage: View {
  @State private var channel: MessagingChannel = .iMessage
  @State private var selectedThreadID: String?
  @State private var query: String = ""
  @State private var filter: MessagesFilter = .all
  @State private var autoReplyOn: Bool = false
  /// Whether the right-side per-person "how omi messages them" card is open.
  @State private var showPersonCard: Bool = false

  // MARK: Derived

  private var threads: [MsgThread] { MessagesSampleData.threads(for: channel) }

  private var filteredThreads: [MsgThread] {
    var rows = threads
    switch filter {
    case .all: break
    case .needs: rows = rows.filter { $0.badge?.kind == .needs }
    case .drafts: rows = rows.filter { $0.badge?.kind == .draft }
    }
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !trimmed.isEmpty else { return rows }
    return rows.filter {
      $0.name.lowercased().contains(trimmed) || $0.preview.lowercased().contains(trimmed)
    }
  }

  private var needsCount: Int { threads.filter { $0.badge?.kind == .needs }.count }
  private var draftCount: Int { threads.filter { $0.badge?.kind == .draft }.count }

  private var selectedDetail: MsgDetail? {
    guard let id = selectedThreadID else { return nil }
    return MessagesSampleData.detail(for: channel, threadID: id)
  }

  var body: some View {
    HStack(spacing: 0) {
      leftPanel
        .frame(width: 320)
        .frame(maxHeight: .infinity)
        .background(Ink.soft)
        .overlay(alignment: .trailing) { Rectangle().fill(Ink.hair).frame(width: 1) }

      rightPane
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Ink.canvas)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear(perform: syncSelection)
    .onChange(of: channel) { _, _ in
      selectedThreadID = nil
      filter = .all
      syncSelection()
    }
    .onChange(of: selectedThreadID) { _, _ in
      autoReplyOn = selectedDetail?.autoReplyOn ?? false
    }
  }

  /// Default the selection to the channel's first thread.
  private func syncSelection() {
    if let id = selectedThreadID, threads.contains(where: { $0.id == id }) { return }
    selectedThreadID = threads.first?.id
    autoReplyOn = selectedDetail?.autoReplyOn ?? false
  }

  // MARK: - Left panel

  private var leftPanel: some View {
    VStack(alignment: .leading, spacing: 0) {
      VStack(alignment: .leading, spacing: 12) {
        HStack(alignment: .center) {
          Text("Messages").inkH2()
          Spacer()
          HStack(spacing: 6) {
            LiveDot(color: Ink.warn, size: 6)
            Text("Drafting").inkCaption()
          }
        }
        channelSwitcher
        searchField
        filterTabs
      }
      .padding(.horizontal, 16)
      .padding(.top, 18)
      .padding(.bottom, 8)

      Divider().overlay(Ink.hair)

      if filteredThreads.isEmpty {
        emptyRail
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 2) {
            ForEach(filteredThreads) { thread in
              ThreadRow(
                thread: thread,
                accent: channel.brand,
                railBackground: Ink.soft,
                isActive: thread.id == selectedThreadID
              )
              .contentShape(Rectangle())
              .onTapGesture { selectedThreadID = thread.id }
            }
          }
          .padding(.horizontal, 8)
          .padding(.vertical, 8)
        }
      }

      previewFooter
    }
  }

  private var channelSwitcher: some View {
    HStack(spacing: 4) {
      ForEach(MessagingChannel.allCases) { ch in
        ChannelTab(
          channel: ch,
          isActive: ch == channel,
          attention: MessagesSampleData.attentionCount(for: ch)
        )
        .contentShape(Rectangle())
        .onTapGesture { channel = ch }
      }
    }
    .padding(4)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(Ink.surface2)
        .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
    )
  }

  private var searchField: some View {
    HStack(spacing: 8) {
      Image(systemName: "magnifyingglass").font(.system(size: 13)).foregroundColor(Ink.faint)
      TextField("Search everyone", text: $query)
        .textFieldStyle(.plain)
        .font(InkFont.sans(13))
        .foregroundColor(Ink.ink)
      if !query.isEmpty {
        Button { query = "" } label: {
          Image(systemName: "xmark.circle.fill").font(.system(size: 13)).foregroundColor(Ink.faint)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, 11)
    .frame(height: 34)
    .background(
      RoundedRectangle(cornerRadius: 9, style: .continuous)
        .fill(Ink.surface)
        .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
    )
  }

  private var filterTabs: some View {
    HStack(spacing: 4) {
      FilterTab(title: "All", count: nil, countColor: nil, isActive: filter == .all)
        .onTapGesture { filter = .all }
      FilterTab(
        title: "Needs you", count: needsCount, countColor: Ink.warn, isActive: filter == .needs
      )
      .onTapGesture { filter = .needs }
      FilterTab(
        title: "Drafts", count: draftCount, countColor: Ink.accentStrong, isActive: filter == .drafts
      )
      .onTapGesture { filter = .drafts }
      Spacer(minLength: 0)
    }
  }

  private var emptyRail: some View {
    VStack(spacing: 8) {
      Image(systemName: "tray").font(.system(size: 24)).foregroundColor(Ink.faint.opacity(0.6))
      Text(query.isEmpty ? "Nothing here yet" : "No matches").inkSmall()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(.horizontal, 18)
  }

  private var previewFooter: some View {
    HStack(spacing: 8) {
      Image(systemName: "sparkles").font(.system(size: 11)).foregroundColor(Ink.faint)
      Text("Preview · your real inboxes connect in the messaging update")
        .font(InkFont.sans(11))
        .foregroundColor(Ink.faint)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.horizontal, 16)
    .padding(.vertical, 12)
    .overlay(alignment: .top) { Rectangle().fill(Ink.hair).frame(height: 1) }
  }

  // MARK: - Right pane

  @ViewBuilder
  private var rightPane: some View {
    if let detail = selectedDetail {
      HStack(spacing: 0) {
        VStack(spacing: 0) {
          threadHeader(detail)
          Divider().overlay(Ink.hair)
          ScrollView {
            VStack(alignment: .leading, spacing: 14) {
              Text("Today").inkCaption().frame(maxWidth: .infinity, alignment: .center)
              ForEach(detail.bubbles) { bubble in
                ChatBubbleRow(bubble: bubble)
              }
              inlineBlock(detail.inline)
            }
            .frame(maxWidth: 720, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 24)
            .padding(.vertical, 22)
          }
          composer(detail.composer)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)

        if showPersonCard, let id = selectedThreadID {
          PersonCard(
            personID: id,
            name: detail.name,
            initials: detail.initials,
            channelTitle: channel.title,
            relationship: relationship(from: detail.sub),
            brand: channel.brand,
            onClose: { withAnimation(.easeInOut(duration: 0.18)) { showPersonCard = false } }
          )
          .frame(width: 340)
          .frame(maxHeight: .infinity)
          .background(Ink.soft)
          .overlay(alignment: .leading) { Rectangle().fill(Ink.hair).frame(width: 1) }
          .transition(.move(edge: .trailing).combined(with: .opacity))
        }
      }
    } else {
      connectEmptyState
    }
  }

  /// Best-effort relationship label from a thread's subtitle (e.g. "iMessage · Omi team" → "Omi team").
  private func relationship(from sub: String) -> String {
    let parts = sub.components(separatedBy: " · ")
    if parts.count > 1 { return parts.dropFirst().joined(separator: " · ") }
    return "Contact"
  }

  private func threadHeader(_ detail: MsgDetail) -> some View {
    HStack(spacing: 12) {
      AvatarView(
        initials: detail.initials, seed: detail.name, size: 38,
        presence: channel.brand, borderColor: Ink.canvas
      )
      VStack(alignment: .leading, spacing: 2) {
        Text(detail.name).inkH3()
        Text(detail.sub).font(InkFont.sans(12)).foregroundColor(Ink.faint)
      }
      Spacer()
      HStack(spacing: 10) {
        Text("Auto-reply").font(InkFont.sans(12.5)).foregroundColor(Ink.body)
        InkToggle(isOn: $autoReplyOn)
        personButton
      }
    }
    .padding(.horizontal, 20)
    .padding(.vertical, 13)
  }

  /// Toggles the per-person "how omi sounds to them" card in the right rail.
  private var personButton: some View {
    Button {
      withAnimation(.easeInOut(duration: 0.18)) { showPersonCard.toggle() }
    } label: {
      Image(systemName: "person.crop.circle")
        .font(.system(size: 17, weight: .regular))
        .foregroundColor(showPersonCard ? Ink.ink : Ink.faint)
        .frame(width: 30, height: 30)
        .background(
          RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(showPersonCard ? Ink.surface2 : .clear)
            .overlay(
              RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(showPersonCard ? Ink.hair : .clear, lineWidth: 1))
        )
    }
    .buttonStyle(.plain)
    .help("How omi messages this person")
  }

  @ViewBuilder
  private func inlineBlock(_ block: MsgInline) -> some View {
    switch block {
    case .none:
      EmptyView()
    case let .hold(title, body):
      HoldBanner(title: title, message: body)
    case let .escalation(title, reason, options):
      EscalationBlock(title: title, reason: reason, options: options)
    case let .sentTag(time):
      SentTag(time: time)
    }
  }

  @ViewBuilder
  private func composer(_ composer: MsgComposer) -> some View {
    VStack(spacing: 0) {
      Divider().overlay(Ink.hair)
      Group {
        switch composer {
        case let .draft(label, text):
          DraftCompose(label: label, text: text)
        case let .plainInput(placeholder):
          PlainInput(placeholder: placeholder)
        case let .autoNote(text):
          AutoNote(text: text, isOn: $autoReplyOn)
        }
      }
      .padding(.horizontal, 18)
      .padding(.vertical, 14)
    }
    .background(Ink.soft)
  }

  private var connectEmptyState: some View {
    VStack(spacing: 14) {
      BuddyRing(diameter: 54, dot: 7, color: Ink.faint, spins: false)
      Text("Your messages, drafted for you").inkDisplay(24)
      Text(
        "omi will read your iMessage, Telegram, and WhatsApp threads, draft replies in your voice, and hand back anything that needs a real decision. Connect your inboxes in the messaging update."
      )
      .font(InkFont.sans(14))
      .foregroundColor(Ink.muted)
      .multilineTextAlignment(.center)
      .lineSpacing(4)
      .frame(maxWidth: 440)
      InkPill(text: "Coming in the messaging update", systemImage: "clock")
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(40)
  }
}

// MARK: - Filters

private enum MessagesFilter { case all, needs, drafts }

// MARK: - Channels

enum MessagingChannel: String, CaseIterable, Identifiable {
  case iMessage, telegram, whatsapp

  var id: String { rawValue }

  var title: String {
    switch self {
    case .iMessage: return "iMessage"
    case .telegram: return "Telegram"
    case .whatsapp: return "WhatsApp"
    }
  }

  /// Real brand color — the explicit exception to the monochrome-ink rule.
  var brand: Color {
    switch self {
    case .iMessage: return Color(red: 0.20, green: 0.85, blue: 0.31)  // iMessage green (#34DA50-ish)
    case .telegram: return Color(red: 0.13, green: 0.62, blue: 0.85)  // Telegram blue (#229ED9)
    case .whatsapp: return Color(red: 0.15, green: 0.83, blue: 0.40)  // WhatsApp green (#25D366)
    }
  }

  /// White glyph drawn on the brand-colored logo.
  var glyph: String {
    switch self {
    case .iMessage: return "message.fill"
    case .telegram: return "paperplane.fill"
    case .whatsapp: return "phone.fill"
    }
  }
}

/// A rounded brand logo: white glyph on the channel's real brand color.
private struct BrandLogo: View {
  let channel: MessagingChannel
  var size: CGFloat = 22

  var body: some View {
    RoundedRectangle(cornerRadius: size * 0.28, style: .continuous)
      .fill(channel.brand)
      .frame(width: size, height: size)
      .overlay(
        Image(systemName: channel.glyph)
          .font(.system(size: size * 0.5, weight: .semibold))
          .foregroundColor(.white)
      )
  }
}

// MARK: - Channel tab

private struct ChannelTab: View {
  let channel: MessagingChannel
  let isActive: Bool
  let attention: Int

  @State private var hovering = false

  var body: some View {
    // Logo only — names are omitted to keep the switcher clean; the unread
    // count sits as a badge on the corner of the brand logo.
    ZStack(alignment: .topTrailing) {
      BrandLogo(channel: channel, size: 26)
      if attention > 0 {
        Text("\(attention)")
          .font(InkFont.sans(10, .semibold))
          .foregroundColor(Ink.accentInk)
          .frame(minWidth: 15, minHeight: 15)
          .background(Circle().fill(Ink.accent))
          .overlay(Circle().strokeBorder(Ink.soft, lineWidth: 1.5))
          .offset(x: 6, y: -6)
      }
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 8)
    .padding(.horizontal, 6)
    .help(channel.title)
    .background(
      RoundedRectangle(cornerRadius: 8, style: .continuous)
        .fill(isActive ? Ink.surface : (hovering ? Ink.surface.opacity(0.6) : .clear))
        .overlay(
          RoundedRectangle(cornerRadius: 8, style: .continuous)
            .strokeBorder(isActive ? Ink.hair : .clear, lineWidth: 1))
    )
    .onHover { hovering = $0 }
  }
}

// MARK: - Filter tab

private struct FilterTab: View {
  let title: String
  let count: Int?
  let countColor: Color?
  let isActive: Bool

  var body: some View {
    HStack(spacing: 4) {
      Text(title).font(InkFont.sans(12, isActive ? .medium : .regular))
      if let count, count > 0, let countColor {
        Text("·\(count)").font(InkFont.sans(12, .semibold)).foregroundColor(countColor)
      }
    }
    .foregroundColor(isActive ? Ink.ink : Ink.faint)
    .padding(.horizontal, 10)
    .padding(.vertical, 5)
    .background(
      RoundedRectangle(cornerRadius: 7, style: .continuous)
        .fill(isActive ? Ink.surface : .clear)
        .overlay(
          RoundedRectangle(cornerRadius: 7, style: .continuous)
            .strokeBorder(isActive ? Ink.hair : .clear, lineWidth: 1))
    )
    .contentShape(Rectangle())
  }
}

// MARK: - Avatar

private struct AvatarView: View {
  let initials: String
  let seed: String
  var size: CGFloat = 38
  var presence: Color? = nil
  var borderColor: Color = Ink.soft

  var body: some View {
    Text(initials)
      .font(InkFont.sans(size * 0.37, .semibold))
      .foregroundColor(.white)
      .frame(width: size, height: size)
      .background(Circle().fill(Ink.avatarFill(for: seed)))
      .overlay(alignment: .bottomTrailing) {
        if let presence {
          Circle()
            .fill(presence)
            .frame(width: size * 0.3, height: size * 0.3)
            .overlay(Circle().strokeBorder(borderColor, lineWidth: 2))
            .offset(x: 1, y: 1)
        }
      }
  }
}

// MARK: - Thread row

private struct ThreadRow: View {
  let thread: MsgThread
  let accent: Color
  let railBackground: Color
  let isActive: Bool

  @State private var hovering = false

  var body: some View {
    HStack(alignment: .top, spacing: 11) {
      AvatarView(
        initials: thread.initials, seed: thread.name, size: 30,
        presence: accent, borderColor: railBackground
      )
      VStack(alignment: .leading, spacing: 2) {
        Text(thread.name)
          .font(InkFont.sans(14, .medium))
          .foregroundColor(Ink.ink)
          .lineLimit(1)
        Text(thread.preview)
          .font(InkFont.sans(12.5))
          .foregroundColor(Ink.muted)
          .lineLimit(1)
          .truncationMode(.tail)
        if let badge = thread.badge {
          InkBadge(text: badge.text, kind: badge.kind).padding(.top, 5)
        }
      }
      Spacer(minLength: 6)
      Text(thread.time).font(InkFont.sans(11)).foregroundColor(Ink.faint)
    }
    .padding(10)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(isActive ? Ink.surface : (hovering ? Ink.surface2 : .clear))
        .overlay(
          RoundedRectangle(cornerRadius: 11, style: .continuous)
            .strokeBorder(isActive ? Ink.hair : .clear, lineWidth: 1))
    )
    .onHover { hovering = $0 }
  }
}

// MARK: - Chat bubble

private struct ChatBubbleRow: View {
  let bubble: MsgBubble

  var body: some View {
    HStack {
      if bubble.outgoing { Spacer(minLength: 40) }
      Text(bubble.text)
        .font(InkFont.sans(13.5))
        .foregroundColor(bubble.outgoing ? Ink.accentInk : Ink.ink)
        .lineSpacing(2)
        .padding(.horizontal, 13)
        .padding(.vertical, 9)
        .background(bubbleBackground)
        .frame(maxWidth: 420, alignment: bubble.outgoing ? .trailing : .leading)
      if !bubble.outgoing { Spacer(minLength: 40) }
    }
    .frame(maxWidth: .infinity, alignment: bubble.outgoing ? .trailing : .leading)
  }

  @ViewBuilder
  private var bubbleBackground: some View {
    let shape = UnevenRoundedRectangle(
      topLeadingRadius: 16,
      bottomLeadingRadius: bubble.outgoing ? 16 : 5,
      bottomTrailingRadius: bubble.outgoing ? 5 : 16,
      topTrailingRadius: 16,
      style: .continuous
    )
    if bubble.outgoing {
      shape.fill(Ink.accent)
    } else {
      shape.fill(Ink.surface2).overlay(shape.strokeBorder(Ink.hair, lineWidth: 1))
    }
  }
}

// MARK: - Inline blocks

/// Tentative calendar hold (iMessage sample) — omi held a time but sent nothing.
private struct HoldBanner: View {
  let title: String
  let message: String

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 8) {
        Image(systemName: "calendar").font(.system(size: 13, weight: .semibold)).foregroundColor(Ink.body)
        Text(title).inkH3()
      }
      Text(message)
        .font(InkFont.sans(13))
        .foregroundColor(Ink.muted)
        .lineSpacing(3)
        .fixedSize(horizontal: false, vertical: true)
      HStack(spacing: 8) {
        InkButton(title: "Confirm the hold", systemImage: "checkmark", kind: .accent, size: .sm) {}
        InkButton(title: "Drop it", kind: .ghost, size: .sm) {}
      }
      .padding(.top, 5)
    }
    .padding(15)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 13, style: .continuous)
        .fill(Ink.surface2)
        .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
    )
  }
}

/// The "needs you" escalation (Telegram sample) — omi hands a decision back, warn-toned.
private struct EscalationBlock: View {
  let title: String
  let reason: String
  let options: [MsgOption]

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 9) {
        Image(systemName: "flag.fill").font(.system(size: 14)).foregroundColor(Ink.warn)
        Text(title).font(InkFont.sans(15, .semibold)).foregroundColor(Ink.ink)
      }
      Text(reason)
        .font(InkFont.sans(13.5))
        .foregroundColor(Ink.body)
        .lineSpacing(3)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: 560, alignment: .leading)
      VStack(spacing: 8) {
        ForEach(options) { option in
          HStack(spacing: 11) {
            VStack(alignment: .leading, spacing: 2) {
              Text(option.tag).inkEyebrow()
              Text(option.text).font(InkFont.sans(14)).foregroundColor(Ink.ink)
                .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            InkButton(title: option.cta, kind: option.ctaKind, size: .sm) {}
          }
          .padding(.horizontal, 14)
          .padding(.vertical, 12)
          .background(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
              .fill(Ink.surface)
              .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
          )
        }
      }
      .padding(.top, 6)
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 15, style: .continuous)
        .fill(Ink.warn.opacity(0.07))
        .overlay(RoundedRectangle(cornerRadius: 15, style: .continuous).strokeBorder(Ink.warn.opacity(0.4), lineWidth: 1))
    )
  }
}

/// The "sent by omi" tag with a quiet undo (WhatsApp sample).
private struct SentTag: View {
  let time: String

  var body: some View {
    HStack(spacing: 9) {
      Spacer(minLength: 0)
      InkBadge(text: "Sent by omi · \(time)", kind: .sent)
      HStack(spacing: 5) {
        Text("Not right?").font(InkFont.sans(12)).foregroundColor(Ink.faint)
        Text("Undo & edit").font(InkFont.sans(12, .medium)).foregroundColor(Ink.accentStrong)
      }
    }
    .frame(maxWidth: .infinity, alignment: .trailing)
  }
}

// MARK: - Composers

/// The hero omi draft-reply surface — dashed box, editable, never auto-sent.
private struct DraftCompose: View {
  let label: String
  let text: String

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 6) {
        Image(systemName: "sparkles").font(.system(size: 11, weight: .semibold))
        Text(label).font(InkFont.sans(11, .semibold)).tracking(1).textCase(.uppercase)
      }
      .foregroundColor(Ink.accentStrong)

      Text(text)
        .font(InkFont.sans(14))
        .foregroundColor(Ink.ink)
        .lineSpacing(3)
        .fixedSize(horizontal: false, vertical: true)

      HStack(spacing: 8) {
        InkButton(title: "Send it", systemImage: "paperplane.fill", kind: .accent, size: .sm) {}
        InkButton(title: "Edit", kind: .plain, size: .sm) {}
        InkButton(title: "Discard", kind: .ghost, size: .sm) {}
        Spacer(minLength: 8)
        Text("omi drafted this — review before it sends")
          .font(InkFont.sans(12))
          .foregroundColor(Ink.faint)
      }
    }
    .padding(14)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.accentTint)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(Ink.accent, style: StrokeStyle(lineWidth: 1, dash: [5, 4]))
        )
    )
  }
}

/// A plain message input (Telegram sample, when omi is staying out of it).
private struct PlainInput: View {
  let placeholder: String

  var body: some View {
    HStack(spacing: 10) {
      Text(placeholder).font(InkFont.sans(13.5)).foregroundColor(Ink.faint)
      Spacer()
      Text("↩")
        .font(InkFont.mono(12))
        .foregroundColor(Ink.faint)
        .frame(width: 22, height: 22)
        .background(
          RoundedRectangle(cornerRadius: 6, style: .continuous)
            .fill(Ink.surface2)
            .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1)))
    }
    .padding(.horizontal, 14)
    .frame(height: 42)
    .frame(maxWidth: .infinity)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(Ink.surface)
        .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
    )
  }
}

/// The "auto-reply is on" note (WhatsApp sample).
private struct AutoNote: View {
  let text: String
  @Binding var isOn: Bool

  var body: some View {
    HStack(spacing: 10) {
      Image(systemName: "bolt.fill").font(.system(size: 14)).foregroundColor(Ink.accentStrong)
      Text(text)
        .font(InkFont.sans(13))
        .foregroundColor(Ink.body)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
      InkButton(title: isOn ? "Turn off" : "Turn on", kind: .plain, size: .sm) { isOn.toggle() }
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 11)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(Ink.accentTint)
        .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(Ink.accent.opacity(0.25), lineWidth: 1))
    )
  }
}

// MARK: - Person card (per-person messaging personality)

/// How omi should sound to a specific person. Each control persists locally via
/// `@AppStorage` keyed by the person's id, so the choices stick between launches.
///
/// **Storage keys** (all prefixed `msgPersona.<personID>.`): `autoReply` (Bool),
/// `askBeforeSending` (Bool), `tone` (`PersonTone.rawValue`), `emoji` (`PersonEmoji.rawValue`),
/// `length` (`PersonLength.rawValue`), `soundNote` (String). The future messaging PR reads the
/// same keys — construct them the same way (`"msgPersona.\(id).<field>"`).
private struct PersonCard: View {
  let personID: String
  let name: String
  let initials: String
  let channelTitle: String
  let relationship: String
  let brand: Color
  var onClose: () -> Void

  @AppStorage private var autoReply: Bool
  @AppStorage private var askBeforeSending: Bool
  @AppStorage private var toneRaw: String
  @AppStorage private var emojiRaw: String
  @AppStorage private var lengthRaw: String
  @AppStorage private var soundNote: String

  init(
    personID: String, name: String, initials: String, channelTitle: String,
    relationship: String, brand: Color, onClose: @escaping () -> Void
  ) {
    self.personID = personID
    self.name = name
    self.initials = initials
    self.channelTitle = channelTitle
    self.relationship = relationship
    self.brand = brand
    self.onClose = onClose
    let base = "msgPersona.\(personID)."
    _autoReply = AppStorage(wrappedValue: false, base + "autoReply")
    _askBeforeSending = AppStorage(wrappedValue: true, base + "askBeforeSending")
    _toneRaw = AppStorage(wrappedValue: PersonTone.shortDirect.rawValue, base + "tone")
    _emojiRaw = AppStorage(wrappedValue: PersonEmoji.sometimes.rawValue, base + "emoji")
    _lengthRaw = AppStorage(wrappedValue: PersonLength.short.rawValue, base + "length")
    _soundNote = AppStorage(wrappedValue: "", base + "soundNote")
  }

  var body: some View {
    VStack(spacing: 0) {
      header
      Divider().overlay(Ink.hair)
      ScrollView {
        VStack(alignment: .leading, spacing: 20) {
          Text("How I message \(name)").inkEyebrow()

          toggleRow(
            "Auto-reply",
            "Let me answer the routine ones for you and mark them.",
            $autoReply)

          segmentGroup(
            "Tone", "How I carry myself with \(name).",
            options: PersonTone.allCases.map { ($0.rawValue, $0.label) },
            selection: $toneRaw)

          segmentGroup(
            "Emoji", "How often I reach for one.",
            options: PersonEmoji.allCases.map { ($0.rawValue, $0.label) },
            selection: $emojiRaw)

          segmentGroup(
            "Length", "How much I say by default.",
            options: PersonLength.allCases.map { ($0.rawValue, $0.label) },
            selection: $lengthRaw)

          toggleRow(
            "Always ask before sending",
            "I'll hold every draft for your OK — nothing goes out on its own.",
            $askBeforeSending)

          soundField
          samplePreview
        }
        .padding(16)
      }
    }
  }

  // MARK: Header

  private var header: some View {
    HStack(alignment: .top, spacing: 11) {
      AvatarView(initials: initials, seed: name, size: 42, presence: brand, borderColor: Ink.soft)
      VStack(alignment: .leading, spacing: 3) {
        Text(name).inkH3()
        HStack(spacing: 5) {
          Text(channelTitle).font(InkFont.sans(11.5, .medium)).foregroundColor(Ink.body)
          Text("·").foregroundColor(Ink.faint)
          Text(relationship).font(InkFont.sans(11.5)).foregroundColor(Ink.faint).lineLimit(1)
        }
      }
      Spacer(minLength: 6)
      Button(action: onClose) {
        Image(systemName: "xmark")
          .font(.system(size: 12, weight: .semibold))
          .foregroundColor(Ink.faint)
          .frame(width: 26, height: 26)
          .background(Circle().fill(Ink.surface2).overlay(Circle().strokeBorder(Ink.hair, lineWidth: 1)))
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 14)
  }

  // MARK: Controls

  private func toggleRow(_ title: String, _ sub: String, _ isOn: Binding<Bool>) -> some View {
    HStack(alignment: .top, spacing: 12) {
      VStack(alignment: .leading, spacing: 2) {
        Text(title).font(InkFont.sans(13.5, .medium)).foregroundColor(Ink.ink)
        Text(sub).inkCaption().fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: 8)
      InkToggle(isOn: isOn)
    }
  }

  private func segmentGroup(
    _ title: String, _ sub: String, options: [(String, String)], selection: Binding<String>
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      VStack(alignment: .leading, spacing: 2) {
        Text(title).font(InkFont.sans(13.5, .medium)).foregroundColor(Ink.ink)
        Text(sub).inkCaption()
      }
      InkSegmented(options: options, selection: selection)
    }
  }

  private var soundField: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text("How I should sound to \(name)").font(InkFont.sans(13.5, .medium)).foregroundColor(Ink.ink)
      TextField(
        "e.g. keep it casual, no work-speak, call me by my first name",
        text: $soundNote, axis: .vertical
      )
      .textFieldStyle(.plain)
      .font(InkFont.sans(13))
      .foregroundColor(Ink.ink)
      .lineLimit(2...5)
      .padding(EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 12))
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(Ink.surface)
          .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
      )
    }
  }

  // MARK: Live sample

  private var samplePreview: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 6) {
        Image(systemName: "sparkles").font(.system(size: 11, weight: .semibold))
        Text("Sample reply").font(InkFont.sans(11, .semibold)).tracking(1).textCase(.uppercase)
      }
      .foregroundColor(Ink.accentStrong)

      Text(sampleReply)
        .font(InkFont.sans(14))
        .foregroundColor(Ink.ink)
        .lineSpacing(3)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)

      Text("This is how a draft to \(name) would read with these settings.")
        .inkCaption()
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(14)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.accentTint)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(Ink.accent, style: StrokeStyle(lineWidth: 1, dash: [5, 4]))
        )
    )
  }

  /// Derives a plausible draft from the current settings — static/derived, no LLM.
  private var sampleReply: String {
    let tone = PersonTone(rawValue: toneRaw) ?? .shortDirect
    let emoji = PersonEmoji(rawValue: emojiRaw) ?? .sometimes
    let length = PersonLength(rawValue: lengthRaw) ?? .short

    var text: String
    switch tone {
    case .shortDirect:
      text = length == .short
        ? "on it — sending now."
        : "on it — I'll get that over to you now and follow up if anything's off."
    case .warm:
      text = length == .short
        ? "yes! on it right now"
        : "yes, happy to — I'll get that over to you now and shout if I need anything else."
    case .formal:
      text = length == .short
        ? "Certainly — I'll send that shortly."
        : "Of course. I'll have that sent over to you shortly and follow up if anything is unclear."
    }

    switch emoji {
    case .off:
      text = text.filter { !$0.isEmoji }.trimmingCharacters(in: .whitespaces)
    case .sometimes:
      if tone == .warm && !text.contains(where: { $0.isEmoji }) { text += " 🙂" }
    case .matchThem:
      if !text.contains(where: { $0.isEmoji }) { text += " 👍" }
    }
    return "\u{201C}" + text + "\u{201D}"
  }
}

/// Per-person tone preset. Raw values are the persisted `msgPersona.<id>.tone` strings.
private enum PersonTone: String, CaseIterable, Identifiable {
  case shortDirect, warm, formal
  var id: String { rawValue }
  var label: String {
    switch self {
    case .shortDirect: return "Short & direct"
    case .warm: return "Warm"
    case .formal: return "Formal"
    }
  }
}

/// Per-person emoji preference. Raw values are the persisted `msgPersona.<id>.emoji` strings.
private enum PersonEmoji: String, CaseIterable, Identifiable {
  case off, sometimes, matchThem
  var id: String { rawValue }
  var label: String {
    switch self {
    case .off: return "Off"
    case .sometimes: return "Sometimes"
    case .matchThem: return "Match them"
    }
  }
}

/// Per-person default length. Raw values are the persisted `msgPersona.<id>.length` strings.
private enum PersonLength: String, CaseIterable, Identifiable {
  case short, normal
  var id: String { rawValue }
  var label: String {
    switch self {
    case .short: return "Short"
    case .normal: return "Normal"
    }
  }
}

/// A compact Ink segmented control: pill track, active segment on `Ink.surface`.
private struct InkSegmented: View {
  let options: [(String, String)]  // (value, label)
  @Binding var selection: String

  var body: some View {
    HStack(spacing: 4) {
      ForEach(options, id: \.0) { value, label in
        let active = value == selection
        Text(label)
          .font(InkFont.sans(12.5, active ? .semibold : .regular))
          .foregroundColor(active ? Ink.ink : Ink.faint)
          .lineLimit(1)
          .minimumScaleFactor(0.85)
          .frame(maxWidth: .infinity)
          .padding(.vertical, 7)
          .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
              .fill(active ? Ink.surface : .clear)
              .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                  .strokeBorder(active ? Ink.hair : .clear, lineWidth: 1))
          )
          .contentShape(Rectangle())
          .onTapGesture { selection = value }
      }
    }
    .padding(4)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(Ink.surface2)
        .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
    )
  }
}

/// Emoji detection for the sample-reply derivation (no external deps).
extension Character {
  fileprivate var isEmoji: Bool {
    unicodeScalars.contains { $0.properties.isEmojiPresentation || $0.properties.isEmoji && $0.value > 0x238C }
  }
}

// MARK: - Sample data model

struct MsgBadge {
  let text: String
  let kind: InkBadgeKind
}

struct MsgThread: Identifiable {
  let id: String
  let name: String
  let initials: String
  let preview: String
  let time: String
  var badge: MsgBadge? = nil
}

struct MsgBubble: Identifiable {
  let id = UUID()
  let text: String
  let outgoing: Bool
}

struct MsgOption: Identifiable {
  let id = UUID()
  let tag: String
  let text: String
  let cta: String
  let ctaKind: InkButtonKind
}

enum MsgInline {
  case none
  case hold(title: String, body: String)
  case escalation(title: String, reason: String, options: [MsgOption])
  case sentTag(time: String)
}

enum MsgComposer {
  case draft(label: String, text: String)
  case plainInput(placeholder: String)
  case autoNote(text: String)
}

struct MsgDetail {
  let name: String
  let initials: String
  let sub: String
  let autoReplyOn: Bool
  let bubbles: [MsgBubble]
  let inline: MsgInline
  let composer: MsgComposer
}

// MARK: - Sample data
//
// FUTURE MESSAGING PR — inject real inbox data here.
// This enum is the single seam between the UI shell above and the (not-yet-existing)
// iMessage / Telegram / WhatsApp inbox stores. Replace these three functions with reads
// from the real stores (keyed by `MessagingChannel`) and map the store's rows/threads
// onto `MsgThread` / `MsgDetail`. Nothing in the views above needs to change — they take
// plain value types. Recommended shape: an `ObservableObject` per channel (or one
// `MessagingInboxStore` exposing `threads(for:)` / `detail(for:threadID:)`), passed into
// `RedesignMessagesPage` via `@ObservedObject` and read where these statics are read today.

enum MessagesSampleData {
  static func attentionCount(for channel: MessagingChannel) -> Int {
    threads(for: channel).filter { $0.badge?.kind == .needs || $0.badge?.kind == .draft }.count
  }

  static func threads(for channel: MessagingChannel) -> [MsgThread] {
    switch channel {
    case .iMessage:
      return [
        MsgThread(
          id: "im-nick", name: "Nick", initials: "N",
          preview: "blocked on your review — send the PR?", time: "9:48",
          badge: MsgBadge(text: "Draft ready", kind: .draft)),
        MsgThread(
          id: "im-maher", name: "Maher", initials: "M",
          preview: "You: grabbing groceries on the way back", time: "9:15",
          badge: MsgBadge(text: "Auto-reply on", kind: .hold)),
        MsgThread(
          id: "im-allison", name: "Allison", initials: "A",
          preview: "You: yes! Friday works for the dinner", time: "Tue",
          badge: MsgBadge(text: "Sent by omi", kind: .sent)),
        MsgThread(
          id: "im-david", name: "David", initials: "D",
          preview: "the EMOTIV refund — want me to dispute?", time: "Tue",
          badge: MsgBadge(text: "Needs you", kind: .needs)),
        MsgThread(
          id: "im-will", name: "Will", initials: "W",
          preview: "You: connecting you with the Clock Out lead", time: "Mon"),
        MsgThread(
          id: "im-shristi", name: "Shristi", initials: "S",
          preview: "haha no worries, next time", time: "Sun"),
      ]
    case .telegram:
      return [
        MsgThread(
          id: "tg-ben", name: "Ben", initials: "B",
          preview: "coworking deposit — send your half today?", time: "11:04",
          badge: MsgBadge(text: "Needs you", kind: .needs)),
        MsgThread(
          id: "tg-allison", name: "Allison", initials: "A",
          preview: "You: locked it in — see you Friday", time: "10:40",
          badge: MsgBadge(text: "Sent by omi", kind: .sent)),
        MsgThread(
          id: "tg-nick", name: "Nick", initials: "N",
          preview: "You: rebasing on main now", time: "9:58",
          badge: MsgBadge(text: "Draft ready", kind: .draft)),
        MsgThread(
          id: "tg-team", name: "Omi team", initials: "OT",
          preview: "Josh: standup in 10", time: "Tue",
          badge: MsgBadge(text: "Auto-reply on", kind: .hold)),
        MsgThread(
          id: "tg-aditya", name: "Aditya", initials: "A",
          preview: "You: haha yes let's do the dinner Friday", time: "Mon"),
        MsgThread(
          id: "tg-drew", name: "Drew", initials: "D",
          preview: "sent you the lead list", time: "Sun"),
      ]
    case .whatsapp:
      return [
        MsgThread(
          id: "wa-aditya", name: "Aditya", initials: "A",
          preview: "omi: On it — sending the dinner menu today", time: "9:41",
          badge: MsgBadge(text: "Sent by omi · handled", kind: .sent)),
        MsgThread(
          id: "wa-allison", name: "Allison", initials: "A",
          preview: "can we push our call to 4?", time: "9:20",
          badge: MsgBadge(text: "Draft ready", kind: .draft)),
        MsgThread(
          id: "wa-maher", name: "Maher", initials: "M",
          preview: "don't forget the rent split", time: "8:55",
          badge: MsgBadge(text: "Auto-reply on", kind: .hold)),
        MsgThread(
          id: "wa-satvik", name: "Satvik", initials: "S",
          preview: "You: sounds perfect, thank you!", time: "Tue",
          badge: MsgBadge(text: "Sent by omi", kind: .sent)),
        MsgThread(
          id: "wa-hong", name: "Hong", initials: "H",
          preview: "👍", time: "Mon"),
        MsgThread(
          id: "wa-gabe", name: "Gabe", initials: "G",
          preview: "You: next week works", time: "Sun"),
      ]
    }
  }

  static func detail(for channel: MessagingChannel, threadID: String) -> MsgDetail? {
    switch threadID {
    case "im-nick":
      return MsgDetail(
        name: "Nick", initials: "N", sub: "iMessage · Omi team", autoReplyOn: false,
        bubbles: [
          MsgBubble(text: "did the auto-reply fix land? I'm blocked on my review", outgoing: false),
          MsgBubble(text: "rebasing on main now — one sec", outgoing: true),
          MsgBubble(text: "🙏 drop the PR link when it's up", outgoing: false),
        ],
        inline: .hold(
          title: "Tentative hold — walkthrough, today 4:00 PM",
          body:
            "You said you'd walk Nick through it before standup. I held 4pm on your calendar — nothing's sent yet."
        ),
        composer: .draft(
          label: "Draft ready · from your GitHub tab + your standup note",
          text:
            "Here's the PR — rebased on main, summary's in the description. Want to hop on at 4 so I can walk you through it?"
        ))
    case "tg-ben":
      return MsgDetail(
        name: "Ben", initials: "B", sub: "Telegram · @ben", autoReplyOn: false,
        bubbles: [
          MsgBubble(
            text: "the coworking space needs the deposit before they hold our desks", outgoing: false),
          MsgBubble(text: "can you send your half ($2,400) today? I'll cover the rest", outgoing: false),
        ],
        inline: .escalation(
          title: "I didn't want to guess on this one.",
          reason:
            "It's money and a same-day deadline — that's your call, not mine. I pulled the context so you can decide fast. Here's how I'd reply:",
          options: [
            MsgOption(
              tag: "If yes", text: "\"Sending my half now — done in a few minutes.\"",
              cta: "Use this", ctaKind: .accent),
            MsgOption(
              tag: "If you need time",
              text: "\"Can we do it tomorrow morning? Moving some cash around.\"",
              cta: "Use this", ctaKind: .plain),
            MsgOption(
              tag: "Or", text: "Write it yourself — I'll stay out of it.",
              cta: "I've got it", ctaKind: .ghost),
          ]),
        composer: .plainInput(placeholder: "Message Ben…"))
    case "wa-aditya":
      return MsgDetail(
        name: "Aditya", initials: "A", sub: "WhatsApp · online", autoReplyOn: true,
        bubbles: [
          MsgBubble(
            text: "morning! can you share the menu for the August dinner before EOD?", outgoing: false),
          MsgBubble(text: "no rush, just locking in the headcount 🙂", outgoing: false),
          MsgBubble(
            text:
              "On it — I'll get the menu over today. How many are we planning for this round?",
            outgoing: true),
        ],
        inline: .sentTag(time: "9:41"),
        composer: .autoNote(
          text:
            "Auto-reply is on for Aditya. I answer the routine ones and mark them — and pull back the moment something needs a real decision."
        ))
    default:
      // Threads without a scripted detail fall back to a simple placeholder thread so the
      // shell never dead-ends. The messaging PR replaces this with the real thread read.
      guard let summary = threads(for: channel).first(where: { $0.id == threadID }) else {
        return nil
      }
      return MsgDetail(
        name: summary.name, initials: summary.initials, sub: "\(channel.title)", autoReplyOn: false,
        bubbles: [
          MsgBubble(text: summary.preview.replacingOccurrences(of: "You: ", with: ""), outgoing: false)
        ],
        inline: .none,
        composer: .draft(
          label: "Draft ready",
          text: "omi will draft a reply here once your \(channel.title) inbox is connected."))
    }
  }
}
