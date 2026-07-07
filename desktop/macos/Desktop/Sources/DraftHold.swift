import Foundation

/// A tentative "hold" calendar event the backend created when an availability-aware
/// reply accepted a proposed meeting time. Surfaced in the Replies inbox so the user can
/// confirm (keep it) or discard (delete it). Shared across the iMessage/Telegram/WhatsApp
/// draft-reply payloads.
///
/// The APIClient decoder maps snake_case via explicit CodingKeys (no
/// `.convertFromSnakeCase`) and decodes ISO8601 date strings, so `startTime`/`endTime`
/// decode straight into `Date`.
struct DraftHold: Decodable, Equatable {
  let eventID: String
  let title: String
  let startTime: Date
  let endTime: Date
  let htmlLink: String?

  enum CodingKeys: String, CodingKey {
    case eventID = "event_id"
    case title
    case startTime = "start_time"
    case endTime = "end_time"
    case htmlLink = "html_link"
  }

  /// A short "Fri, Jul 10 · 1:00 PM" label for the banner.
  var whenLabel: String {
    let df = DateFormatter()
    df.dateFormat = "EEE, MMM d · h:mm a"
    return df.string(from: startTime)
  }
}
