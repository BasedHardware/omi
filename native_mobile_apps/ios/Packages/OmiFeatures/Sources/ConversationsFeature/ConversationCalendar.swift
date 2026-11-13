import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI
#if canImport(EventKitUI)
    import EventKit
    import EventKitUI
#endif

/// The Google Calendar event the conversation is linked to, as a card on the summary tab.
struct LinkedEventCard: View {
    let event: CalendarEventLink
    let onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            HStack(spacing: DS.Spacing.md) {
                Image(systemName: "calendar.badge.checkmark").foregroundStyle(DS.Palette.inkSecondary).frame(width: 22)
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(event.title).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink).lineLimit(2)
                    Text(CalendarEventSheet.timeRange(event.start, event.end))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                Spacer(minLength: 0)
            }
            .multilineTextAlignment(.leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("conversation.calendarEvent")
    }
}

/// A linked event: when, who, open it in Google Calendar, write to the attendees, unlink.
struct CalendarEventSheet: View {
    let event: CalendarEventLink
    let store: ConversationDetailStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label(Self.timeRange(event.start, event.end), systemImage: "clock")
                    if !event.attendees.isEmpty {
                        Label(event.attendees.map(Self.attendee).joined(separator: ", "), systemImage: "person.2")
                    }
                }
                Section {
                    if let link = event.htmlLink {
                        Button { openURL(link) } label: { Label(L("openInGoogleCalendar"), systemImage: "arrow.up.right.square") }
                    }
                    if let mail = event.shareURL(subject: L("meetingNotesSubject", event.title)) {
                        Button { openURL(mail) } label: { Label(L("shareWithAttendees"), systemImage: "envelope") }
                    }
                }
                Section {
                    Button(role: .destructive) {
                        Task {
                            await store.unlinkCalendarEvent()
                            dismiss()
                        }
                    } label: { Label(L("unlinkCalendarEvent"), systemImage: "calendar.badge.minus") }
                }
            }
            .navigationTitle(event.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("done")) { dismiss() } } }
        }
    }

    /// "Wed 7 Oct, 15:00 – 16:00".
    static func timeRange(_ start: Date, _ end: Date) -> String {
        let day = start.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute())
        return "\(day) – \(end.formatted(date: .omitted, time: .shortened))"
    }

    /// An email shows as its local part (Flutter `formatAttendeeName`).
    static func attendee(_ value: String) -> String {
        value.contains("@") ? String(value.prefix { $0 != "@" }) : value
    }
}

/// "Link Event": events around the conversation from Google Calendar, the best overlap marked
/// "Suggested" and first.
struct LinkEventSheet: View {
    let store: ConversationDetailStore
    let onLinked: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var events: [CalendarEventCandidate]?
    @State private var linking: String?
    @State private var failed = false

    var body: some View {
        NavigationStack {
            List {
                if let events {
                    if events.isEmpty {
                        Text(L("noCalendarEventsNearby")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                    }
                    ForEach(events) { row($0) }
                } else {
                    ProgressView().frame(maxWidth: .infinity)
                }
            }
            .navigationTitle(L("linkEvent"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } } }
            .task { await load() }
            .alert(L("failedToLinkCalendarEvent"), isPresented: $failed) { Button(L("ok"), role: .cancel) {} }
        }
    }

    private var suggested: CalendarEventCandidate? {
        CalendarEventCandidate.suggested(events ?? [], start: store.window.start, end: store.window.end)
    }

    private func row(_ event: CalendarEventCandidate) -> some View {
        Button {
            linking = event.id
            Task {
                if await store.linkCalendarEvent(event.id) != nil {
                    onLinked(event.title)
                    dismiss()
                } else {
                    failed = true
                }
                linking = nil
            }
        } label: {
            HStack(spacing: DS.Spacing.md) {
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    HStack(spacing: DS.Spacing.xs) {
                        Text(event.title.isEmpty ? L("untitledConversation") : event.title)
                            .font(DS.Typography.cardTitle)
                            .foregroundStyle(DS.Palette.ink)
                        if event.id == suggested?.id {
                            Text(L("suggestedEvent"))
                                .font(DS.Typography.micro)
                                .foregroundStyle(DS.Palette.agent)
                                .padding(.horizontal, DS.Spacing.xs + 2)
                                .padding(.vertical, 2)
                                .background(DS.Palette.agentSoft, in: Capsule())
                        }
                    }
                    Text(CalendarEventSheet.timeRange(event.start, event.end))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                Spacer(minLength: 0)
                if linking == event.id { ProgressView().controlSize(.small) }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(linking != nil)
    }

    private func load() async {
        let loaded = await store.calendarCandidates() ?? []
        let best = CalendarEventCandidate.suggested(loaded, start: store.window.start, end: store.window.end)
        events = loaded.sorted { lhs, rhs in
            if lhs.id == best?.id { return true }
            if rhs.id == best?.id { return false }
            return lhs.start < rhs.start
        }
    }
}

#if canImport(EventKitUI)
    /// The system "New Event" screen, filled with an event Omi found; the user saves or cancels
    /// (no calendar access needed: the editor runs outside the app).
    struct AddToCalendarView: UIViewControllerRepresentable {
        let event: ConversationDetail.Event
        let onFinish: (Bool) -> Void

        func makeCoordinator() -> Coordinator {
            Coordinator(onFinish: onFinish)
        }

        func makeUIViewController(context: Context) -> EKEventEditViewController {
            let store = EKEventStore()
            let draft = EKEvent(eventStore: store)
            draft.title = event.title
            draft.notes = event.description.isEmpty ? nil : event.description
            let start = event.start ?? .now
            draft.startDate = start
            draft.endDate = start.addingTimeInterval(TimeInterval(max(event.duration, 1) * 60))
            let controller = EKEventEditViewController()
            controller.eventStore = store
            controller.event = draft
            controller.editViewDelegate = context.coordinator
            return controller
        }

        func updateUIViewController(_: EKEventEditViewController, context _: Context) {}

        final class Coordinator: NSObject, EKEventEditViewDelegate {
            let onFinish: (Bool) -> Void

            init(onFinish: @escaping (Bool) -> Void) {
                self.onFinish = onFinish
            }

            func eventEditViewController(_: EKEventEditViewController, didCompleteWith action: EKEventEditViewAction) {
                onFinish(action == .saved)
            }
        }
    }
#else
    struct AddToCalendarView: View {
        let event: ConversationDetail.Event
        let onFinish: (Bool) -> Void
        var body: some View {
            EmptyView()
        }
    }
#endif
