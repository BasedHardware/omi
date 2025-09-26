import SwiftUI

struct FloatingChatInputView: View {
    @State private var messageText: String = ""
    @State private var attachmentURL: URL?
    @State private var showingFilePicker = false
    
    var onSend: ((String, URL?) -> Void)?
    
    var body: some View {
        HStack(spacing: 8) {
            Button(action: attachmentButtonTapped) {
                Image(systemName: attachmentURL == nil ? "paperclip" : "doc.fill")
                    .foregroundColor(.secondary)
            }
            .buttonStyle(PlainButtonStyle())
            .frame(width: 24, height: 24)
            .accessibilityLabel(attachmentURL == nil ? "Attach file" : "File attached: \(attachmentURL?.lastPathComponent ?? "")")
            .help(attachmentURL?.lastPathComponent ?? "Attach file")
            
            TextField("Ask Omi...", text: $messageText)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .font(.system(size: 14))
                .accessibilityLabel("Message input")
                .onSubmit {
                    sendMessage()
                }
            
            Button("Send") {
                sendMessage()
            }
            .buttonStyle(.borderedProminent)
            .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .accessibilityLabel("Send message")
        }
        .padding(.horizontal, 10)
        .frame(minHeight: 50)
        .background(Color.clear)
        .fileImporter(
            isPresented: $showingFilePicker,
            allowedContentTypes: [.item],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first {
                    attachmentURL = url
                }
            case .failure(let error):
                print("File picker error: \(error)")
            }
        }
    }
    
    private func sendMessage() {
        let message = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !message.isEmpty {
            onSend?(message, attachmentURL)
            messageText = ""
            attachmentURL = nil
        }
    }
    
    private func attachmentButtonTapped() {
        if attachmentURL == nil {
            showingFilePicker = true
        } else {
            attachmentURL = nil
        }
    }
}
