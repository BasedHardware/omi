import OmiCore
import OmiService
import SwiftUI

/// Debug launch arguments that drive the shell without tapping (compiled for every build but
/// inert: `DebugLaunchOptions` is empty outside Debug).
struct DebugHooks: ViewModifier {
    @Environment(AppEnvironment.self) private var environment
    @Environment(DeepLinkRouter.self) private var deepLinks
    @Binding var path: NavigationPath
    @Binding var handOverTask: ActionItem?
    @Binding var showsAgent: Bool

    func body(content: Content) -> some View {
        content
            .task(id: environment.conversations.conversations.count) {
                guard let id = DebugLaunchOptions.current.openConversationID, path.isEmpty,
                      let match = environment.conversations.conversations.first(where: { $0.id == id }) else { return }
                path.append(MainTabView.Route.conversation(match))
            }
            .task(id: environment.conversations.recaps.count) {
                // -omiOpenRecap YES pushes the newest daily recap.
                guard UserDefaults.standard.bool(forKey: "omiOpenRecap"), path.isEmpty,
                      let recap = environment.conversations.recaps.first else { return }
                path.append(MainTabView.Route.recap(recap))
            }
            .task(id: environment.tasks.tasks.count) {
                guard let id = DebugLaunchOptions.current.handOverTaskID, handOverTask == nil,
                      let task = environment.tasks.tasks.first(where: { $0.id == id }) else { return }
                handOverTask = task
                // -omiHandOverPreview YES opens the sheet without starting the run.
                if !UserDefaults.standard.bool(forKey: "omiHandOverPreview") {
                    await environment.agent.takeOver(task, conversationTitle: nil)
                }
            }
            .task {
                // -omiDemoOmiAsks message|contacts|access shows an "Omi asks" card (Debug only).
                #if DEBUG
                    guard let kind = UserDefaults.standard.string(forKey: "omiDemoOmiAsks") else { return }
                    environment.agent.showDemoQuestion(Self.demoQuestion(kind))
                #endif
            }
            .task {
                // -omiOpenSearch YES (with -omiSearchQuery "anna") pushes Search.
                guard UserDefaults.standard.bool(forKey: "omiOpenSearch"), path.isEmpty else { return }
                path.append(MainTabView.Route.search)
            }
            .task {
                guard let link = DebugLaunchOptions.current.deepLink.flatMap(URL.init(string:)) else { return }
                deepLinks.open(DeepLink(url: link) ?? DeepLink(universalLink: link))
            }
            .task {
                guard let text = DebugLaunchOptions.current.chatMessage else { return }
                showsAgent = true
                environment.chat.send(text)
            }
            .task {
                guard DebugLaunchOptions.current.startsPhoneCapture else { return }
                await environment.capture.startPhone()
                if let seconds = DebugLaunchOptions.current.captureSeconds {
                    try? await Task.sleep(for: .seconds(seconds))
                    await environment.capture.stop()
                }
            }
    }

    private static func demoQuestion(_ kind: String) -> PendingDeviceTool {
        let anna = DeviceContact(
            id: "demo-anna", name: "Anna Schmidt", phoneNumbers: [.init(label: "mobile", value: "+49 170 1234567")],
            emailAddresses: [], preferredHandle: "+49 170 1234567"
        )
        let annabel = DeviceContact(id: "demo-annabel", name: "Annabel Lee", phoneNumbers: [], emailAddresses: [], preferredHandle: "")
        switch kind {
        case "contacts":
            return PendingDeviceTool(
                taskID: "demo", taskTitle: "Send Anna the Thursday follow-up",
                request: DeviceToolRequest(id: "demo-call", toolName: "search_contacts", query: "Anna"), matches: [anna, annabel]
            )
        case "access":
            return PendingDeviceTool(
                taskID: "demo", taskTitle: "Send Anna the Thursday follow-up",
                request: DeviceToolRequest(id: "demo-call", toolName: "search_contacts", query: "Anna"), needsContactsAccess: true
            )
        default:
            return PendingDeviceTool(
                taskID: "demo", taskTitle: "Send Anna the Thursday follow-up",
                request: DeviceToolRequest(
                    id: "demo-call", toolName: "propose_message", recipients: ["Anna Schmidt"],
                    text: "Hi Anna, following up on our roadmap chat: does Thursday at 7 pm still work for you?"
                )
            )
        }
    }
}
