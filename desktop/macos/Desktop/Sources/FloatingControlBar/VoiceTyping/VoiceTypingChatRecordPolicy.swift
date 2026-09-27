import Foundation

/// Whether a delivered dictation also enters Omi's chat context.
///
/// By the time this is asked the text has already been typed into the focused
/// app, so the only remaining question is what the turn does to the chat
/// transcript. Silent Type answers "nothing": dictation stays a typing tool and
/// never becomes chat history.
///
/// The two consequences travel together deliberately. A native source (terminal
/// OCR) is reserved under `voice:<uuid>` at turn start and is bound to the
/// journal row that records the turn; when there is no such row, the
/// reservation must be fenced instead, or a late extraction callback can invent
/// an admission for a turn that was never written.
enum VoiceTypingChatRecordPolicy {
  struct Decision: Equatable {
    /// Write the dictation to the chat transcript as a `realtime_voice` exchange.
    let journalsExchange: Bool
    /// Retire the native source reserved for this turn, because no producing
    /// journal row will ever exist for it to attach to.
    let retiresReservedEvidence: Bool
    /// Bar interrupted-turn recovery from resurrecting this turn's transcript.
    /// Recovery normally stands down because the turn already has an accepted
    /// persistence receipt; a turn that was never written has none, so without
    /// this a later provider failure would journal the very text the user asked
    /// to keep out of the chat.
    let suppressesJournalRecovery: Bool
  }

  static func decide(silentTypeEnabled: Bool) -> Decision {
    silentTypeEnabled
      ? Decision(
        journalsExchange: false, retiresReservedEvidence: true, suppressesJournalRecovery: true)
      : Decision(
        journalsExchange: true, retiresReservedEvidence: false, suppressesJournalRecovery: false)
  }
}
