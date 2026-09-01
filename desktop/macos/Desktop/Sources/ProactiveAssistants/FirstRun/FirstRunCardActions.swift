import Foundation

enum FirstRunCardActionKind: Equatable {
  case focusReturn(projectTitle: String)
  case contextReminder(reminderID: String)
  case openSummary(conversationID: String)
}

enum FirstRunCardActions {
  static func make(_ kind: FirstRunCardActionKind) -> FloatingBarNotificationAction? {
    // MERGE-POINT: replace with FloatingBarNotificationAction cases from Task A
    // switch kind {
    // case .focusReturn(let projectTitle):
    //   return .firstRunFocusReturn(projectTitle: projectTitle)
    // case .contextReminder(let reminderID):
    //   return .contextReminder(reminderID: reminderID)
    // case .openSummary(let conversationID):
    //   return .firstRunOpenSummary(conversationID: conversationID)
    // }
    _ = kind
    return nil
  }
}
