import AppKit
import SwiftUI
import OmiTheme

enum ProofFirstDashboardPage: Int, CaseIterable, Identifiable {
  case home
  case connectData
  case features

  var id: Int { rawValue }

  var title: String {
    switch self {
    case .home: return "Home"
    case .connectData: return "Connect data"
    case .features: return "Features"
    }
  }

  var icon: OmiIconName {
    switch self {
    case .home: return .home
    case .connectData: return .link
    case .features: return .sliders
    }
  }
}

enum DashboardHeroTier: Equatable {
  case loading
  case recommendation
  case recentConversation
  case recentTask
  case dayZero
}

enum DashboardHeroCascadePolicy {
  static func resolve(
    hasSettled: Bool,
    hasRecommendation: Bool,
    mostRecentConversationAt: Date?,
    mostRecentTaskAt: Date?
  ) -> DashboardHeroTier {
    guard hasSettled else { return .loading }
    if hasRecommendation { return .recommendation }

    switch (mostRecentConversationAt, mostRecentTaskAt) {
    case let (.some(conversationAt), .some(taskAt)):
      return conversationAt >= taskAt ? .recentConversation : .recentTask
    case (.some, .none):
      return .recentConversation
    case (.none, .some):
      return .recentTask
    case (.none, .none):
      return .dayZero
    }
  }
}

struct DashboardHeroContent: Equatable {
  let icon: OmiIconName
  let eyebrow: String
  let title: String
  let context: String
  let action: String
  let prompt: String
}

struct DashboardDayZeroCard: Identifiable, Equatable {
  enum Kind: Equatable {
    case screen
    case calendar
    case email
  }

  let id: String
  let kind: Kind
  let icon: OmiIconName
  let text: String
  let action: String
  let prompt: String
}

enum DashboardDayZeroSourcePolicy {
  enum Presentation: Equatable {
    case setup
    case staticCard
    case rotating
  }

  static func presentation(sourceCount: Int) -> Presentation {
    switch sourceCount {
    case 0: return .setup
    case 1: return .staticCard
    default: return .rotating
    }
  }
}

@MainActor
final class DashboardDayZeroSourceStore: ObservableObject {
  typealias ScreenLoader = () async -> DashboardDayZeroCard?
  typealias CalendarLoader = (_ now: Date) async -> DashboardDayZeroCard?
  typealias EmailLoader = () async -> DashboardDayZeroCard?

  @Published private(set) var cards: [DashboardDayZeroCard] = []
  @Published private(set) var isLoading = false
  @Published private(set) var hasSettled = false

  private let screenLoader: ScreenLoader
  private let calendarLoader: CalendarLoader
  private let emailLoader: EmailLoader

  init(
    screenLoader: @escaping ScreenLoader = DashboardDayZeroSourceStore.loadScreenCard,
    calendarLoader: @escaping CalendarLoader = DashboardDayZeroSourceStore.loadCalendarCard,
    emailLoader: @escaping EmailLoader = DashboardDayZeroSourceStore.loadEmailCard
  ) {
    self.screenLoader = screenLoader
    self.calendarLoader = calendarLoader
    self.emailLoader = emailLoader
  }

  func load(connectedConnectorIDs: Set<String>, now: Date = Date()) async {
    guard !isLoading else { return }
    isLoading = true
    defer {
      isLoading = false
      hasSettled = true
    }

    async let screen = screenLoader()
    async let calendar = connectedConnectorIDs.contains("calendar") ? calendarLoader(now) : nil
    async let email = connectedConnectorIDs.contains("email") ? emailLoader() : nil
    cards = await [screen, calendar, email].compactMap { $0 }
  }

  static func screenCard(from payload: [String: Any]) -> DashboardDayZeroCard? {
    guard
      let screenNow = payload["screen_now"] as? [String: Any],
      screenNow["available"] as? Bool == true,
      let appName = normalized(screenNow["app_name"] as? String)
    else { return nil }

    let windowTitle = normalized(screenNow["window_title"] as? String)
    let text: String
    if let windowTitle {
      text = "You’re in \(appName) — “\(windowTitle).” Ask Omi to summarize it or plan the next step."
    } else {
      text = "You’re in \(appName). Ask Omi what matters on this screen."
    }

    return DashboardDayZeroCard(
      id: "screen:\(appName):\(windowTitle ?? "current")",
      kind: .screen,
      icon: .monitor,
      text: text,
      action: "Ask about this",
      prompt: windowTitle.map { "Help me with what’s on my screen in \(appName): \($0)" }
        ?? "Help me with what’s on my screen in \(appName)."
    )
  }

  static func calendarCard(from events: [CalendarEvent], now: Date) -> DashboardDayZeroCard? {
    let upcoming = events.compactMap { event -> (CalendarEvent, Date)? in
      guard let date = parseCalendarDate(event.startTime), date >= now else { return nil }
      return (event, date)
    }
    .min { $0.1 < $1.1 }

    guard let (event, start) = upcoming, let summary = normalized(event.summary) else { return nil }
    let when = relativeCalendarDate(start, now: now)
    return DashboardDayZeroCard(
      id: "calendar:\(event.id)",
      kind: .calendar,
      icon: .calendar,
      text: "\(summary) is \(when), from your connected calendar. Omi can prep notes before it starts.",
      action: "Prep notes",
      prompt: "Prepare me for \(summary) \(when)."
    )
  }

  static func emailCard(from emails: [GmailEmail]) -> DashboardDayZeroCard? {
    guard let email = emails.sorted(by: { $0.date > $1.date }).first,
          let subject = normalized(email.subject)
    else { return nil }

    let sender = normalized(email.from.components(separatedBy: "<").first) ?? "a recent sender"
    return DashboardDayZeroCard(
      id: "email:\(email.id)",
      kind: .email,
      icon: .mail,
      text: "“\(subject)” from \(sender) is in your connected Gmail. Ask Omi to summarize it or draft a reply.",
      action: "Ask about it",
      prompt: "Help me with the email “\(subject)” from \(sender)."
    )
  }

  private static func loadScreenCard() async -> DashboardDayZeroCard? {
    let payload = await ScreenContextWorkContextBuilder.payload(arguments: ["minutes": 10])
    return screenCard(from: payload)
  }

  private static func loadCalendarCard(now: Date) async -> DashboardDayZeroCard? {
    guard let events = try? await CalendarReaderService.shared.readEvents(
      daysBack: 0,
      daysForward: 14,
      maxResults: 30
    ) else { return nil }
    return calendarCard(from: events, now: now)
  }

  private static func loadEmailCard() async -> DashboardDayZeroCard? {
    guard let emails = try? await GmailReaderService.shared.readRecentEmails(
      maxResults: 5,
      query: "newer_than:7d"
    ) else { return nil }
    return emailCard(from: emails)
  }

  private static func parseCalendarDate(_ raw: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = fractional.date(from: raw) ?? ISO8601DateFormatter().date(from: raw) {
      return date
    }

    let day = DateFormatter()
    day.locale = Locale(identifier: "en_US_POSIX")
    day.calendar = Calendar(identifier: .gregorian)
    day.dateFormat = "yyyy-MM-dd"
    return day.date(from: raw)
  }

  private static func relativeCalendarDate(_ date: Date, now: Date) -> String {
    let calendar = Calendar.current
    let time = DateFormatter()
    time.timeStyle = .short
    time.dateStyle = .none
    if calendar.isDateInToday(date) {
      return "today at \(time.string(from: date))"
    }
    if calendar.isDateInTomorrow(date) {
      return "tomorrow at \(time.string(from: date))"
    }
    let full = DateFormatter()
    full.dateFormat = "EEEE 'at' h:mm a"
    return full.string(from: date)
  }

  private static func normalized(_ value: String?) -> String? {
    let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? nil : trimmed
  }
}

struct ProofFirstDashboardView: View {
  let heroTier: DashboardHeroTier
  let heroContent: DashboardHeroContent?
  let dayZeroCards: [DashboardDayZeroCard]
  let upNextTasks: [TaskActionItem]
  let connectorStatusStore: ImportConnectorStatusStore
  let onHeroAction: (String) -> Void
  let onConnectSetup: () -> Void
  let onToggleTask: (TaskActionItem) -> Void
  let onViewTasks: () -> Void
  let onSelectConnector: (ImportConnector) -> Void
  let onOpenShortcutSettings: () -> Void

  @State private var selectedPage: ProofFirstDashboardPage? = .home

  var body: some View {
    GeometryReader { proxy in
      ZStack(alignment: .topLeading) {
        ScrollView(.horizontal) {
          LazyHStack(spacing: 0) {
            homePage
              .frame(width: proxy.size.width, height: proxy.size.height)
              .id(ProofFirstDashboardPage.home)

            ConnectDataDashboardPage(
              connectorStatusStore: connectorStatusStore,
              onSelectConnector: onSelectConnector
            )
            .frame(width: proxy.size.width, height: proxy.size.height)
            .id(ProofFirstDashboardPage.connectData)

            FeaturesDashboardPage(onOpenShortcutSettings: onOpenShortcutSettings)
              .frame(width: proxy.size.width, height: proxy.size.height)
              .id(ProofFirstDashboardPage.features)
          }
          .scrollTargetLayout()
        }
        .scrollIndicators(.hidden)
        .scrollTargetBehavior(.paging)
        .scrollPosition(id: $selectedPage)

        DashboardPrimaryTabBar(selectedPage: pageBinding)
          .padding(.leading, 14)
          .padding(.top, 14)

        if selectedPage != .home {
          OverlayModalEscapeCatcher {
            selectPage(.home)
          }
        }
      }
    }
  }

  private var pageBinding: Binding<ProofFirstDashboardPage> {
    Binding(
      get: { selectedPage ?? .home },
      set: { selectPage($0) }
    )
  }

  private var homePage: some View {
    ScrollView(.vertical) {
      VStack(spacing: OmiSpacing.lg) {
        Text("omi.")
          .scaledFont(size: OmiType.hero, weight: .bold)
          .foregroundStyle(OmiColors.textPrimary)
          .tracking(-1.8)
          .shadow(color: OmiColors.textPrimary.opacity(0.14), radius: 28)

        Group {
          switch heroTier {
          case .loading:
            DashboardHeroLoadingCard()
          case .recommendation, .recentConversation, .recentTask:
            if let heroContent {
              DashboardHeroCard(content: heroContent) {
                onHeroAction(heroContent.prompt)
              }
            }
          case .dayZero:
            DashboardDayZeroHero(
              cards: dayZeroCards,
              onAction: onHeroAction,
              onConnectSetup: {
                selectPage(.connectData)
                onConnectSetup()
              }
            )
          }
        }
        .frame(maxWidth: 760)

        DashboardUpNextSection(
          tasks: upNextTasks,
          onToggleTask: onToggleTask,
          onViewTasks: onViewTasks
        )
        .frame(maxWidth: 760)
      }
      .frame(maxWidth: .infinity)
      .padding(.horizontal, 28)
      .padding(.top, 86)
      .padding(.bottom, 88)
    }
    .scrollIndicators(.hidden)
  }

  private func selectPage(_ page: ProofFirstDashboardPage) {
    OmiMotion.withGated(.spring(response: 0.42, dampingFraction: 0.88)) {
      selectedPage = page
    }
  }
}

private struct DashboardPrimaryTabBar: View {
  @Binding var selectedPage: ProofFirstDashboardPage

  var body: some View {
    HStack(spacing: OmiSpacing.xxs) {
      ForEach(ProofFirstDashboardPage.allCases) { page in
        Button {
          selectedPage = page
        } label: {
          HStack(spacing: OmiSpacing.xs) {
            OmiIcon(page.icon)
              .frame(width: 15, height: 15)
            Text(page.title)
              .scaledFont(size: OmiType.caption, weight: .semibold)
          }
          .foregroundStyle(selectedPage == page ? OmiColors.backgroundPrimary : OmiColors.textTertiary)
          .padding(.horizontal, OmiSpacing.md)
          .frame(minHeight: 44)
          .background(
            Capsule(style: .continuous)
              .fill(selectedPage == page ? OmiColors.textPrimary : Color.clear)
          )
          .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(.plain)
        .omiPointerCursor()
        .accessibilityLabel(page.title)
        .accessibilityAddTraits(selectedPage == page ? .isSelected : [])
      }
    }
    .padding(OmiSpacing.xxs)
    .background(OmiColors.backgroundSecondary.opacity(0.94), in: Capsule(style: .continuous))
    .overlay(
      Capsule(style: .continuous)
        .stroke(OmiColors.border.opacity(0.5), lineWidth: 1)
    )
    .shadow(color: .black.opacity(0.3), radius: 25, y: 14)
  }
}

private struct DashboardHeroLoadingCard: View {
  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      ProgressView()
        .controlSize(.small)
      Text("Finding what matters now…")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(OmiColors.textTertiary)
    }
    .frame(maxWidth: .infinity, minHeight: 190)
    .dashboardProofCard()
    .accessibilityElement(children: .combine)
  }
}

private struct DashboardHeroCard: View {
  let content: DashboardHeroContent
  let action: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(spacing: OmiSpacing.sm) {
        DashboardMomentIcon(icon: content.icon)
        Text(content.eyebrow)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(OmiColors.textTertiary)
      }

      Text(content.title)
        .scaledFont(size: OmiType.title, weight: .bold)
        .foregroundStyle(OmiColors.textPrimary)
        .tracking(-0.8)
        .padding(.top, OmiSpacing.sm)

      Text(content.context)
        .scaledFont(size: OmiType.subheading)
        .foregroundStyle(OmiColors.textSecondary)
        .lineSpacing(4)
        .padding(.top, OmiSpacing.md)

      DashboardPrimaryAction(title: content.action, action: action)
        .frame(maxWidth: .infinity)
        .padding(.top, OmiSpacing.xxl)
    }
    .dashboardProofCard()
  }
}

private struct DashboardDayZeroHero: View {
  let cards: [DashboardDayZeroCard]
  let onAction: (String) -> Void
  let onConnectSetup: () -> Void

  @State private var selectedIndex = 0
  @State private var isPaused = false

  private var presentation: DashboardDayZeroSourcePolicy.Presentation {
    DashboardDayZeroSourcePolicy.presentation(sourceCount: cards.count)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Text("Here’s what Omi can already do")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundStyle(OmiColors.textTertiary)

      if cards.isEmpty {
        setupState
      } else {
        let safeIndex = min(selectedIndex, cards.count - 1)
        let card = cards[safeIndex]

        HStack(alignment: .top, spacing: OmiSpacing.md) {
          DashboardMomentIcon(icon: card.icon)
          Text(card.text)
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundStyle(OmiColors.textPrimary)
            .lineSpacing(5)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .id(card.id)
        .transition(.asymmetric(
          insertion: .opacity.combined(with: .offset(y: 12)),
          removal: .opacity.combined(with: .offset(y: -8))
        ))
        .padding(.top, OmiSpacing.lg)

        DashboardPrimaryAction(title: card.action) {
          onAction(card.prompt)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, OmiSpacing.xxl)

        if presentation == .rotating {
          HStack(spacing: 2) {
            ForEach(cards.indices, id: \.self) { index in
              Button {
                selectCard(index)
              } label: {
                Capsule(style: .continuous)
                  .fill(index == safeIndex ? OmiColors.textPrimary : OmiColors.textQuaternary)
                  .frame(width: index == safeIndex ? 16 : 6, height: 6)
                  .frame(width: 40, height: 40)
              }
              .buttonStyle(.plain)
              .omiPointerCursor()
              .accessibilityLabel("Show source \(index + 1) of \(cards.count)")
              .accessibilityAddTraits(index == safeIndex ? .isSelected : [])
            }
          }
          .frame(maxWidth: .infinity)
          .padding(.top, OmiSpacing.xxs)
        }
      }
    }
    .dashboardProofCard()
    .onHover { isPaused = $0 }
    .task(id: rotationTaskID) {
      guard presentation == .rotating, !isPaused else { return }
      while !Task.isCancelled {
        try? await Task.sleep(for: .seconds(5))
        guard !Task.isCancelled, !isPaused, cards.count > 1 else { return }
        await MainActor.run {
          selectCard((selectedIndex + 1) % cards.count)
        }
      }
    }
    .onChange(of: cards.count) { _, count in
      if count == 0 { selectedIndex = 0 }
      else if selectedIndex >= count { selectedIndex = count - 1 }
    }
  }

  private var rotationTaskID: String {
    "\(cards.map(\.id).joined(separator: "|")):\(isPaused)"
  }

  private var setupState: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        DashboardMomentIcon(icon: .link)
        Text("Connect a source so Omi can show a useful, grounded first step here.")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundStyle(OmiColors.textPrimary)
          .lineSpacing(5)
      }

      DashboardPrimaryAction(title: "Connect data", action: onConnectSetup)
        .frame(maxWidth: .infinity)
    }
    .padding(.top, OmiSpacing.lg)
  }

  private func selectCard(_ index: Int) {
    guard cards.indices.contains(index), index != selectedIndex else { return }
    OmiMotion.withGated(.easeOut(duration: 0.26)) {
      selectedIndex = index
    }
  }
}

private struct DashboardMomentIcon: View {
  let icon: OmiIconName

  var body: some View {
    OmiIcon(icon)
      .foregroundStyle(OmiColors.textPrimary)
      .frame(width: 17, height: 17)
      .frame(width: 34, height: 34)
      .background(OmiColors.backgroundTertiary, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
      .overlay(
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .stroke(OmiColors.border.opacity(0.55), lineWidth: 1)
      )
  }
}

private struct DashboardPrimaryAction: View {
  let title: String
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.sm) {
        Text(title)
          .scaledFont(size: OmiType.subheading, weight: .bold)
        OmiIcon(.arrowRight)
          .frame(width: 18, height: 18)
      }
      .foregroundStyle(OmiColors.backgroundPrimary)
      .frame(maxWidth: 360, minHeight: 54)
      .background(
        Capsule(style: .continuous)
          .fill(isHovering ? OmiColors.textSecondary : OmiColors.textPrimary)
      )
      .shadow(color: .black.opacity(isHovering ? 0.36 : 0.25), radius: isHovering ? 17 : 12, y: 8)
      .contentShape(Capsule(style: .continuous))
    }
    .buttonStyle(.plain)
    .omiPointerCursor()
    .onHover { isHovering = $0 }
    .scaleEffect(isHovering ? 1.012 : 1)
    .omiAnimation(.easeOut(duration: 0.15), value: isHovering)
  }
}

private struct DashboardUpNextSection: View {
  let tasks: [TaskActionItem]
  let onToggleTask: (TaskActionItem) -> Void
  let onViewTasks: () -> Void

  var body: some View {
    VStack(spacing: 0) {
      HStack {
        Text("Up next")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(OmiColors.textSecondary)
        Spacer()
        Button("View tasks", action: onViewTasks)
          .buttonStyle(.plain)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(OmiColors.textQuaternary)
          .frame(minHeight: 40)
          .omiPointerCursor()
      }

      if tasks.isEmpty {
        Text("No open tasks right now.")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(OmiColors.textQuaternary)
          .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
      } else {
        ForEach(tasks.prefix(2)) { task in
          HStack(spacing: OmiSpacing.sm) {
            Button {
              onToggleTask(task)
            } label: {
              Circle()
                .stroke(OmiColors.border, lineWidth: 1)
                .frame(width: 18, height: 18)
                .frame(width: 40, height: 40)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .omiPointerCursor()
            .accessibilityLabel("Complete \(task.description)")

            VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
              Text(task.description)
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundStyle(OmiColors.textSecondary)
                .lineLimit(2)
              Text(taskMetadata(task))
                .scaledFont(size: OmiType.micro)
                .foregroundStyle(OmiColors.textQuaternary)
            }
            Spacer(minLength: 0)
          }
          .frame(minHeight: 48)
        }
      }
    }
    .padding(.top, OmiSpacing.sm)
    .overlay(alignment: .top) {
      Rectangle()
        .fill(OmiColors.border.opacity(0.45))
        .frame(height: 1)
    }
  }

  private func taskMetadata(_ task: TaskActionItem) -> String {
    if let dueAt = task.dueAt {
      let formatter = DateFormatter()
      formatter.dateStyle = .medium
      formatter.timeStyle = .none
      return "Due \(formatter.string(from: dueAt))"
    }
    if task.conversationId != nil { return "From a conversation" }
    if let source = task.source, !source.isEmpty {
      return source.replacingOccurrences(of: "_", with: " ").capitalized
    }
    return "Open task"
  }
}

private struct ConnectDataDashboardPage: View {
  @ObservedObject var connectorStatusStore: ImportConnectorStatusStore
  let onSelectConnector: (ImportConnector) -> Void

  private let connectors = ImportConnector.all.filter {
    ["calendar", "email", "local-files", "apple-notes"].contains($0.id)
  }

  var body: some View {
    ScrollView(.vertical) {
      VStack(alignment: .leading, spacing: 0) {
        Text("Connect data")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(OmiColors.textTertiary)
        Text("Bring your context into Omi.")
          .scaledFont(size: OmiType.title, weight: .bold)
          .foregroundStyle(OmiColors.textPrimary)
          .tracking(-0.8)
          .padding(.top, OmiSpacing.sm)
        Text("Connect the places where you work so Omi can ground memories, tasks, and answers in your real information.")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(OmiColors.textTertiary)
          .lineSpacing(3)
          .padding(.top, OmiSpacing.md)

        VStack(spacing: 0) {
          ForEach(connectors) { connector in
            ImportConnectorRow(
              connector: connector,
              snapshot: connectorStatusStore.snapshot(for: connector),
              action: { onSelectConnector(connector) }
            )
            Divider().overlay(OmiColors.border.opacity(0.45))
          }
        }
        .padding(.top, OmiSpacing.lg)
      }
      .padding(28)
      .dashboardProofCard()
      .frame(maxWidth: 860)
      .frame(maxWidth: .infinity)
      .padding(.horizontal, 28)
      .padding(.top, 86)
      .padding(.bottom, 88)
    }
    .scrollIndicators(.hidden)
  }
}

private struct FeaturesDashboardPage: View {
  let onOpenShortcutSettings: () -> Void

  @ObservedObject private var shortcutSettings = ShortcutSettings.shared
  @State private var floatingBarEnabled = FloatingControlBarManager.shared.isEnabled

  var body: some View {
    ScrollView(.vertical) {
      VStack(alignment: .leading, spacing: 0) {
        Text("Features")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(OmiColors.textTertiary)
        Text("Control what Omi does.")
          .scaledFont(size: OmiType.title, weight: .bold)
          .foregroundStyle(OmiColors.textPrimary)
          .tracking(-0.8)
          .padding(.top, OmiSpacing.sm)
        Text("Everyday controls stay close at hand. Advanced account and privacy options remain in Settings.")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(OmiColors.textTertiary)
          .lineSpacing(3)
          .padding(.top, OmiSpacing.md)

        VStack(spacing: 0) {
          featureRow(
            title: "Ask Omi shortcut",
            detail: "Open the floating Ask Omi bar from anywhere"
          ) {
            Button(shortcutSettings.askOmiEnabled ? shortcutSettings.askOmiShortcut.displayLabel : "Disabled") {
              onOpenShortcutSettings()
            }
            .buttonStyle(.plain)
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(OmiColors.textSecondary)
            .padding(.horizontal, OmiSpacing.md)
            .frame(minHeight: 40)
            .background(OmiColors.backgroundTertiary, in: Capsule(style: .continuous))
            .overlay(Capsule(style: .continuous).stroke(OmiColors.border.opacity(0.55), lineWidth: 1))
            .omiPointerCursor()
          }

          featureRow(
            title: "Show floating bar",
            detail: "Keep Ask Omi available over other apps"
          ) {
            Toggle("", isOn: Binding(
              get: { floatingBarEnabled },
              set: { enabled in
                floatingBarEnabled = enabled
                if enabled {
                  FloatingControlBarManager.shared.show()
                } else {
                  FloatingControlBarManager.shared.hide()
                }
              }
            ))
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
          }

          featureRow(
            title: "Background style",
            detail: "Choose glass transparency or a solid dark surface"
          ) {
            Picker("Background style", selection: $shortcutSettings.solidBackground) {
              Text("Transparent").tag(false)
              Text("Solid Dark").tag(true)
            }
            .labelsHidden()
            .pickerStyle(.segmented)
            .frame(width: 190)
          }
        }
        .padding(.top, OmiSpacing.lg)
      }
      .padding(28)
      .dashboardProofCard()
      .frame(maxWidth: 860)
      .frame(maxWidth: .infinity)
      .padding(.horizontal, 28)
      .padding(.top, 86)
      .padding(.bottom, 88)
    }
    .scrollIndicators(.hidden)
    .onAppear {
      floatingBarEnabled = FloatingControlBarManager.shared.isEnabled
    }
  }

  private func featureRow<Trailing: View>(
    title: String,
    detail: String,
    @ViewBuilder trailing: () -> Trailing
  ) -> some View {
    HStack(spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundStyle(OmiColors.textSecondary)
        Text(detail)
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(OmiColors.textQuaternary)
      }
      Spacer(minLength: OmiSpacing.lg)
      trailing()
    }
    .frame(minHeight: 68)
    .overlay(alignment: .bottom) {
      Rectangle()
        .fill(OmiColors.border.opacity(0.45))
        .frame(height: 1)
    }
  }
}

private extension View {
  func dashboardProofCard() -> some View {
    padding(26)
      .background(OmiColors.backgroundSecondary, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
      .overlay(
        RoundedRectangle(cornerRadius: 28, style: .continuous)
          .stroke(OmiColors.border.opacity(0.5), lineWidth: 1)
      )
      .shadow(color: .black.opacity(0.28), radius: 40, y: 22)
  }
}
