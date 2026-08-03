import SwiftUI

/// A request to open a person's profile that survives the People page not being
/// mounted yet.
///
/// The automation action can fire while the user is on Home, so a bare
/// notification would be posted to nobody and silently do nothing — the call
/// still returns success, which is worse than failing. Holding the request until
/// the page appears mirrors `MainChatNavigationRequestStore`, which solves the
/// same ordering problem for chat.
@MainActor
enum PeopleOpenRequestStore {
  private static var pending: (personID: String?, name: String?)?

  static func request(personID: String?, name: String?) {
    let id = personID?.trimmingCharacters(in: .whitespacesAndNewlines)
    let named = name?.trimmingCharacters(in: .whitespacesAndNewlines)
    guard (id?.isEmpty == false) || (named?.isEmpty == false) else { return }
    pending = (id, named)
  }

  /// Returns the pending request once, then forgets it. Consuming on every
  /// appear means a request made from another page still lands.
  static func consume() -> (personID: String?, name: String?)? {
    defer { pending = nil }
    return pending
  }

  static func reset() { pending = nil }
}

extension View {
  /// Applies any pending "open this person" request, both when it arrives and
  /// when the People page appears.
  func peopleOpenRequests(_ apply: @escaping (String?, String?) -> Void) -> some View {
    onAppear {
      if let request = PeopleOpenRequestStore.consume() {
        apply(request.personID, request.name)
      }
    }
    .onReceive(NotificationCenter.default.publisher(for: .peopleOpenPerson)) { _ in
      if let request = PeopleOpenRequestStore.consume() {
        apply(request.personID, request.name)
      }
    }
  }
}
