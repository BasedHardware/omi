import Foundation
import SwiftUI

/// Backing store for the Replies inbox: recent iMessage threads awaiting a reply.
@MainActor
final class IMessageInboxStore: ObservableObject {
  @Published var threads: [IMessageInboxThread] = []
  @Published var isLoading = false
  @Published var errorMessage: String?
  @Published var permissionNeeded = false

  func load() async {
    isLoading = true
    errorMessage = nil
    defer { isLoading = false }

    guard IMessagePermissionPolicy.fullDiskAccessGranted() else {
      permissionNeeded = true
      threads = []
      return
    }
    permissionNeeded = false

    do {
      threads = try await IMessageReaderService.shared.readInboxThreads()
    } catch {
      errorMessage = error.localizedDescription
    }
  }
}
