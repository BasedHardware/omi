@preconcurrency import AVFoundation
import Combine
import SwiftUI
@preconcurrency import UserNotifications

@MainActor
extension AppState {
  func loadEnvironment() {
    BundleEnvironment.loadIfNeeded()
  }

}
