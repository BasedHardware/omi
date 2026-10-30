import Observation
import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// What the detail page's newer actions have open: summary template, calendar link, recordings,
/// SMS sharing, the developer test prompt. One object, so the screen holds one piece of state.
@MainActor
@Observable
final class DetailExtras {
    var showsTemplates = false
    var linksEvent = false
    var showsEvent = false
    var showsRecordings = false
    var sharesBySMS = false
    var testsPrompt = false
    /// "Google Calendar Not Connected · Connect".
    var asksToConnectCalendar = false
    /// Another device's recording, opened from the recordings sheet.
    var openRecording: Conversation?
    /// Event Omi found, being added to the iPhone calendar (index into `events`).
    var addingEvent: Int?
    /// A short confirmation or failure, shown for a moment by the screen's toast.
    var notice: String?
    /// Debug: the templates sheet opens on "Create custom template".
    var debugCreatesTemplate = false

    /// Created on first use (they load from the backend).
    var templates: SummaryTemplatesStore?
    var feedback: SummaryFeedbackStore?
    var screenshots: ConversationScreenshotsStore?

    func templates(_ list: ConversationsStore) -> SummaryTemplatesStore {
        if let templates { return templates }
        let store = list.makeTemplatesStore()
        templates = store
        return store
    }

    func say(_ message: String) {
        notice = message
        Task {
            try? await Task.sleep(for: .seconds(2.5))
            if notice == message { notice = nil }
        }
    }

    /// Starts linking: the picker when Google Calendar is connected, else the offer to connect.
    func linkEvent(_ store: ConversationDetailStore) {
        Task {
            if await store.isCalendarConnected() {
                linksEvent = true
            } else {
                asksToConnectCalendar = true
            }
        }
    }
}

/// Every sheet and dialog the extras open, attached once to the detail screen.
struct DetailExtrasPresenter: ViewModifier {
    @Bindable var extras: DetailExtras
    let store: ConversationDetailStore
    let conversation: Conversation
    let onHandOver: (ActionItem) -> Void
    let onAskOmi: () -> Void
    @Environment(ConversationsStore.self) private var conversations
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(\.openURL) private var openURL

    func body(content: Content) -> some View {
        content
            .sheet(isPresented: $extras.showsTemplates) {
                SummaryTemplateSheet(templates: extras.templates(conversations), detail: store, creating: extras.debugCreatesTemplate)
            }
            .sheet(isPresented: $extras.linksEvent) {
                LinkEventSheet(store: store) { title in extras.say(L("linkedToEvent", title)) }
                    .presentationDetents([.medium, .large])
            }
            .sheet(isPresented: $extras.showsEvent) {
                if let event = store.detail?.calendarEvent {
                    CalendarEventSheet(event: event, store: store).presentationDetents([.medium])
                }
            }
            .sheet(isPresented: $extras.showsRecordings) {
                CaptureRecordingsSheet(store: store) { recording in
                    Task {
                        if let opened = await conversations.conversation(id: recording.id) {
                            extras.showsRecordings = false
                            extras.openRecording = opened
                        } else {
                            extras.say(L("captureRecordingOpenFailed"))
                        }
                    }
                }
                .presentationDetents([.medium, .large])
            }
            .sheet(isPresented: $extras.testsPrompt) { TestPromptSheet(store: store) }
            .sheet(item: addingEvent) { request in
                AddToCalendarView(event: request.event) { added in
                    extras.addingEvent = nil
                    if added { Task { await store.markEventAdded(request.index) } }
                }
                .ignoresSafeArea()
            }
            .modifier(ShareBySMS(isActive: $extras.sharesBySMS, conversation: conversation) { extras.say($0) })
            .alert(L("googleCalendarNotConnected"), isPresented: $extras.asksToConnectCalendar) {
                Button(L("cancel"), role: .cancel) {}
                Button(L("connect")) { connectCalendar() }
            } message: {
                Text(L("googleCalendarConnectPrompt"))
            }
            .task { await openForDebugging() }
            .navigationDestination(item: $extras.openRecording) { other in
                ConversationDetailScreen(
                    store: store.sibling(other), onHandOver: onHandOver, onAskOmi: onAskOmi
                )
            }
    }

    private var addingEvent: Binding<EventRequest?> {
        Binding(
            get: {
                guard let index = extras.addingEvent, let events = store.detail?.events, events.indices.contains(index) else { return nil }
                return EventRequest(index: index, event: events[index])
            },
            set: { if $0 == nil { extras.addingEvent = nil } }
        )
    }

    /// `-omiConversationSheet templates|createTemplate|linkEvent|event|recordings|testPrompt|sms|addEvent`
    /// opens that sheet once the page has loaded (scripted screenshots; Debug builds only).
    private func openForDebugging() async {
        #if DEBUG
            guard let sheet = UserDefaults.standard.string(forKey: "omiConversationSheet") else { return }
            try? await Task.sleep(for: .seconds(1.5))
            switch sheet {
            case "templates": extras.showsTemplates = true
            case "createTemplate":
                extras.debugCreatesTemplate = true
                extras.showsTemplates = true
            case "linkEvent": extras.linkEvent(store)
            case "event": extras.showsEvent = true
            case "recordings": extras.showsRecordings = true
            case "testPrompt": extras.testsPrompt = true
            case "sms": extras.sharesBySMS = true
            case "addEvent": extras.addingEvent = store.detail?.events.firstIndex { !$0.isCreated }
            default: break
            }
        #endif
    }

    private func connectCalendar() {
        Task {
            guard let integration = capabilities.integrations.first(where: { $0.id == "google_calendar" }),
                  let url = await capabilities.authorizationURL(for: integration) else { return }
            openURL(url)
        }
    }
}

/// A found event on its way into the iPhone calendar.
struct EventRequest: Identifiable {
    let index: Int
    let event: ConversationDetail.Event
    var id: Int {
        index
    }
}
