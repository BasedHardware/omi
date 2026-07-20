import Foundation

struct ImportConnector: Identifiable {
  let id: String
  let title: String
  let subtitle: String
  let description: String
  let brand: ConnectorBrand
  let statusText: String
  let metricText: String?
  let actionTitle: String
  let isConnected: Bool

  static let all: [ImportConnector] = [
    ImportConnector(
      id: "calendar",
      title: "Calendar",
      subtitle: "Google Calendar",
      description: "Import events and recurring routines.",
      brand: .calendar,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "apple-calendar",
      title: "Apple Calendar",
      subtitle: "This Mac",
      description: "Import events through macOS Calendar access.",
      brand: .appleCalendar,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "apple-reminders",
      title: "Apple Reminders",
      subtitle: "This Mac",
      description: "Import reminders through macOS Reminders access.",
      brand: .appleReminders,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "email",
      title: "Email",
      subtitle: "Gmail",
      description: "Import email history and follow-ups.",
      brand: .gmail,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "local-files",
      title: "Local files",
      subtitle: "This Mac",
      description: "Index documents, code, and working folders.",
      brand: .localFiles,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "apple-notes",
      title: "Apple Notes",
      subtitle: "Private notes",
      description: "Import notes and private written context.",
      brand: .appleNotes,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "x",
      title: "X (Twitter)",
      subtitle: "Your posts & bookmarks",
      description: "Connect your X account so Omi learns from your tweets and bookmarks.",
      brand: .x,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "chatgpt",
      title: "ChatGPT",
      subtitle: "Memory import",
      description: "Paste a memory export into Omi.",
      brand: .chatgpt,
      statusText: "Optional",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "claude",
      title: "Claude",
      subtitle: "Memory import",
      description: "Paste a memory export into Omi.",
      brand: .claude,
      statusText: "Optional",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
  ]
}
