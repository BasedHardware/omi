import Foundation
import SwiftUI

/// The summary picker reads the account's installed apps independently of the
/// marketplace catalog shown elsewhere in conversation detail.
@MainActor
final class ConversationSummaryAppPicker: ObservableObject {
  enum Phase: Equatable {
    case idle
    case loading
    case ready
    case failed
  }

  typealias FetchPage = (_ offset: Int, _ limit: Int) async throws -> [OmiApp]

  @Published private(set) var apps: [OmiApp] = []
  @Published private(set) var phase: Phase = .idle
  @Published var searchText = ""

  private let fetchPage: FetchPage
  private var generation = 0
  private let pageSize = 100

  init(fetchPage: @escaping FetchPage) {
    self.fetchPage = fetchPage
  }

  convenience init() {
    self.init { offset, limit in
      try await APIClient.shared.searchApps(
        capability: "memories", installedOnly: true, limit: limit, offset: offset)
    }
  }

  var visibleApps: [OmiApp] {
    let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !query.isEmpty else { return apps }
    return apps.filter { $0.name.localizedStandardContains(query) || $0.author.localizedStandardContains(query) }
  }

  func reset() {
    generation &+= 1
    apps = []
    searchText = ""
    phase = .idle
  }

  func load() async {
    generation &+= 1
    let request = generation
    let ownerID = RuntimeOwnerIdentity.currentOwnerId()
    apps = []
    searchText = ""
    phase = .loading

    do {
      var installed: [OmiApp] = []
      var seenIDs = Set<String>()
      var offset = 0
      while true {
        let page = try await fetchPage(offset, pageSize)
        guard request == generation else { return }
        guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
          reset()
          return
        }
        for app in page where app.enabled && app.worksWithMemories {
          if seenIDs.insert(app.id).inserted {
            installed.append(app)
          }
        }
        guard page.count == pageSize else { break }
        offset += page.count
      }
      apps = installed
      phase = .ready
    } catch {
      guard request == generation else { return }
      guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
        reset()
        return
      }
      phase = .failed
    }
  }
}
