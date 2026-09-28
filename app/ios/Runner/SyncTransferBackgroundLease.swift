import Foundation

/// Refcount-independent state for iOS's finite background-task grant.
///
/// Dart owns the logical refcount. This object owns the native grant and tells
/// Dart whenever iOS expires it (or refuses to create one), so the two sides
/// cannot remain split-brained.
final class SyncTransferBackgroundLease {
  typealias Begin = (@escaping () -> Void) -> Bool
  typealias End = () -> Void
  typealias NotifyExpired = (String) -> Void

  private let begin: Begin
  private let end: End
  private let notifyExpired: NotifyExpired
  private(set) var isActive = false

  init(begin: @escaping Begin, end: @escaping End, notifyExpired: @escaping NotifyExpired) {
    self.begin = begin
    self.end = end
    self.notifyExpired = notifyExpired
  }

  func start() {
    guard !isActive else { return }
    let admitted = begin { [weak self] in
      self?.expire(reason: "expired")
    }
    guard admitted else {
      notifyExpired("invalid")
      return
    }
    isActive = true
  }

  func stop() {
    guard isActive else { return }
    isActive = false
    end()
  }

  private func expire(reason: String) {
    guard isActive else { return }
    isActive = false
    end()
    notifyExpired(reason)
  }
}
