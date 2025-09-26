import SwiftUI

struct FloatingChatMessageBubble: View {
    
    enum BubbleType {
        case user
        case ai
    }
    
    let message: String
    let attachmentURL: URL?
    let type: BubbleType
    
    var body: some View {
        HStack {
            if type == .user {
                Spacer()
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(message)
                    .font(.system(size: 14))
                    .foregroundColor(type == .user ? .white : .primary)
                    .textSelection(.enabled)
                
                if let url = attachmentURL {
                    Text("📎 \(url.lastPathComponent)")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(type == .user ? .white.opacity(0.8) : .secondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                Group {
                    if #available(macOS 26.0, *) {
                        if type == .user {
                            RoundedRectangle(cornerRadius: 15)
                                .fill(Color.blue)
                        } else {
                            RoundedRectangle(cornerRadius: 15)
                                .fill(Color.clear)
                                .glassEffect(in: RoundedRectangle(cornerRadius: 15))
                        }
                    } else {
                        RoundedRectangle(cornerRadius: 15)
                            .fill(type == .user ? Color.blue : Color(NSColor.controlBackgroundColor))
                    }
                }
            )
            .frame(maxWidth: .infinity * 0.75, alignment: type == .user ? .trailing : .leading)
            
            if type == .ai {
                Spacer()
            }
        }
        .accessibilityLabel(accessibilityMessage)
    }
    
    private var accessibilityMessage: String {
        let sender = type == .user ? "You" : "Omi"
        var accessibilityMessage = "Message from \(sender): \(message)"
        if let url = attachmentURL {
            accessibilityMessage += " with attachment \(url.lastPathComponent)"
        }
        return accessibilityMessage
    }
}
