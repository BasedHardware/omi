import Foundation

/// One audio process that has a bundle id, as read from a single CoreAudio pass.
struct CallAudioProcessSnapshot: Sendable, Equatable {
  var bundleID: String
  var pid: Int32
  var isRunningInput: Bool
  var isRunningOutput: Bool
}

/// One off-main probe of call audio. The meeting detector derives "in a call"
/// and call identities from this instead of scanning CoreAudio twice.
struct CallAudioSnapshot: Sendable, Equatable {
  var processes: [CallAudioProcessSnapshot]
  /// `kAudioHardwarePropertyDefaultInputDevice`, or 0 when it cannot be read.
  var defaultInputDeviceID: UInt32
  /// On-screen browser window titles. Empty when this tick did not need them.
  var browserWindowTitles: [String]
}

/// When a tick should pay for `CGWindowList`. Titles are the muted-browser
/// fallback and the only signal on macOS 14.0–14.3; Always mode on 14.4+ only
/// needs them once a call surface is already holding the mic.
enum CallAudioBrowserTitles: Sendable {
  case always
  case whenCallSurfaceHoldsInput
}

enum CallAudioBrowserTitlePolicy {
  static func capture(
    mode: AssistantSettings.AudioRecordingMode,
    processInputAPIAvailable: Bool
  ) -> CallAudioBrowserTitles {
    if processInputAPIAvailable, mode != .onlyMeetings {
      return .whenCallSurfaceHoldsInput
    }
    return .always
  }
}
