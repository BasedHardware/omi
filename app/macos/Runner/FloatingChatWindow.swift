import SwiftUI
import Cocoa

class FloatingChatWindow: NSWindow {
    
    let windowId: String
    var onClose: (() -> Void)?
    private var userDefaultsKey: String { "floatingChatWindowFrame_\(windowId)" }
    
    private var chatViewModel = FloatingChatViewModel()
    private var streamingMessageIds: Set<String> = []
    
    init(id: String) {
        self.windowId = id
        
        let savedFrame = UserDefaults.standard.string(forKey: "floatingChatWindowFrame_\(id)")
        var initialRect: NSRect?
        var centerWindow = false

        if let frameString = savedFrame {
            let savedRect = NSRectFromString(frameString)
            var isOnScreen = false
            for screen in NSScreen.screens {
                if screen.visibleFrame.intersects(savedRect) {
                    isOnScreen = true
                    break
                }
            }
            if isOnScreen {
                initialRect = savedRect
            } else {
                centerWindow = true
            }
        } else {
            centerWindow = true
        }

        if initialRect == nil {
            initialRect = NSRect(x: 0, y: 0, width: 400, height: 600)
        }

        super.init(contentRect: initialRect!, styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        
        if centerWindow {
            self.center()
        }
        self.minSize = NSSize(width: 300, height: 400)
        
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = true
        self.isMovableByWindowBackground = true
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.titleVisibility = .hidden
        self.titlebarAppearsTransparent = true
        self.standardWindowButton(.closeButton)?.isHidden = true
        self.standardWindowButton(.miniaturizeButton)?.isHidden = true
        self.standardWindowButton(.zoomButton)?.isHidden = true
        
        setupSwiftUIContent()
        
        NotificationCenter.default.addObserver(self, selector: #selector(windowWillCloseNotification(_:)), name: NSWindow.willCloseNotification, object: self)
        NotificationCenter.default.addObserver(self, selector: #selector(windowDidResize(_:)), name: NSWindow.didResizeNotification, object: self)
        NotificationCenter.default.addObserver(self, selector: #selector(windowDidMove(_:)), name: NSWindow.didMoveNotification, object: self)

        FloatingChatWindowManager.shared.requestHistoryForWindow(id: id)
    }
    
    private func setupSwiftUIContent() {
        let contentView = FloatingChatContentView(
            windowId: windowId,
            viewModel: chatViewModel,
            onClose: { [weak self] in
                self?.closeAction()
            },
            onSend: { [weak self] message, attachmentURL in
                self?.handleUserMessageSend(message: message, attachmentURL: attachmentURL)
            }
        )
        
        let hostingController = NSHostingController(rootView: contentView)
        self.contentViewController = hostingController
    }
    
    private func handleUserMessageSend(message: String, attachmentURL: URL?) {
        // Finalize any ongoing AI response before sending a new user message
        streamingMessageIds.removeAll()

        chatViewModel.addMessage(text: message, attachmentURL: attachmentURL, type: .user)
        
        var messagePayload: [String: Any] = ["text": message, "conversationId": windowId]
        if let attachmentURL = attachmentURL {
            messagePayload["attachmentPath"] = attachmentURL.path
        }
        
        FloatingChatWindowManager.shared.sendMessageToFlutter(
            id: windowId,
            message: messagePayload
        )
    }
    
    func updateAIResponse(messageId: String, message: String, isFinal: Bool) {
        if streamingMessageIds.contains(messageId) {
            chatViewModel.updateLastAIMessage(text: message)
        } else {
            chatViewModel.addMessage(text: message, attachmentURL: nil, type: .ai)
            streamingMessageIds.insert(messageId)
        }
        
        if isFinal {
            streamingMessageIds.remove(messageId)
        }
    }

    func displayHistory(messages: [[String: Any]]) {
        chatViewModel.displayHistory(messagesData: messages)
    }
    
    @objc private func windowWillCloseNotification(_ notification: Notification) {
        print("FloatingChatWindow is closing. Cleaning up resources.")
        onClose?()
        saveWindowFrame()
    }
    
    @objc private func windowDidResize(_ notification: Notification) {
        saveWindowFrame()
    }
    
    @objc private func windowDidMove(_ notification: Notification) {
        saveWindowFrame()
    }
    
    private func saveWindowFrame() {
        let frameString = NSStringFromRect(self.frame)
        UserDefaults.standard.set(frameString, forKey: userDefaultsKey)
    }

    public func resetPosition() {
        UserDefaults.standard.removeObject(forKey: userDefaultsKey)
        self.center()
    }
    
    @objc func closeAction() {
        self.orderOut(nil)
    }
    
    override var canBecomeKey: Bool {
        return true
    }
    
    override var canBecomeMain: Bool {
        return true
    }
    
    override func cancelOperation(_ sender: Any?) {
        self.close()
    }
    
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    deinit {
        NotificationCenter.default.removeObserver(self)
    }
}

class FloatingChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    
    func addMessage(text: String, attachmentURL: URL?, type: FloatingChatMessageBubble.BubbleType) {
        let newMessage = ChatMessage(text: text, attachmentURL: attachmentURL, type: type)
        messages.append(newMessage)
    }
    
    func updateLastAIMessage(text: String) {
        if let lastIndex = messages.lastIndex(where: { $0.type == .ai }) {
            messages[lastIndex] = ChatMessage(text: text, attachmentURL: messages[lastIndex].attachmentURL, type: .ai)
        }
    }
    
    func clearMessages() {
        messages.removeAll()
    }
    
    func displayHistory(messagesData: [[String: Any]]) {
        var newMessages: [ChatMessage] = []
        
        for messageData in messagesData {
            guard let text = messageData["text"] as? String,
                  let typeString = messageData["type"] as? String else {
                continue
            }
            
            let type: FloatingChatMessageBubble.BubbleType = (typeString == "user") ? .user : .ai
            let attachmentPath = messageData["attachmentPath"] as? String
            let attachmentURL = attachmentPath != nil ? URL(fileURLWithPath: attachmentPath!) : nil
            
            newMessages.append(ChatMessage(text: text, attachmentURL: attachmentURL, type: type))
        }
        
        messages = newMessages
    }
}

struct FloatingChatContentView: View {
    let windowId: String
    @ObservedObject var viewModel: FloatingChatViewModel
    let onClose: () -> Void
    let onSend: (String, URL?) -> Void
    
    private var content: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Omi")
                    .font(.system(size: 14, weight: .bold))
                
                Spacer()
                
                Button("Close") {
                    onClose()
                }
                .buttonStyle(.bordered)
            }
            .padding(.horizontal, 16)
            .frame(height: 40)
            
            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(viewModel.messages) { message in
                            FloatingChatMessageBubble(
                                message: message.text,
                                attachmentURL: message.attachmentURL,
                                type: message.type
                            )
                            .id(message.id)
                        }
                    }
                    .padding(10)
                }
                .accessibilityLabel("Chat messages")
                .onChange(of: viewModel.messages.count) { _ in
                    if let lastMessage = viewModel.messages.last {
                        withAnimation(.easeOut(duration: 0.3)) {
                            proxy.scrollTo(lastMessage.id, anchor: .bottom)
                        }
                    }
                }
            }
            
            // Separator
            Divider()
            
            // Input
            FloatingChatInputView(onSend: onSend)
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
    
    var body: some View {
        if #available(macOS 26.0, *) {
            GlassEffectContainer {
                content
                    .glassEffect(in: RoundedRectangle(cornerRadius: 16))
            }
        } else {
            content
                .background(
                    VisualEffectView(material: .popover, blendingMode: .behindWindow)
                )
        }
    }
}

/// A container view that enables glass effects on macOS 26+
@available(macOS 26.0, *)
struct GlassEffectContainer<Content: View>: View {
    let content: () -> Content
    
    init(@ViewBuilder content: @escaping () -> Content) {
        self.content = content
    }
    
    var body: some View {
        content()
    }
}
