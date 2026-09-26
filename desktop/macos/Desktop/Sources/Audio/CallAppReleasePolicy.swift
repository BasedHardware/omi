import Foundation

/// Which native call apps end the call when they release the microphone.
enum CallAppReleasePolicy {
  /// `us.zoom.xos` measured 2026-09-26 on macOS 27: Zoom keeps microphone input
  /// running through mute/unmute and through AirPods connect/disconnect. Leaving
  /// a meeting stops input and output in the same millisecond; the next meeting
  /// re-acquired both 8.0s later. A browser mic release is not in this catalog —
  /// browsers drop input on mute while the call continues.
  static func releaseEndsCall(bundleID: String) -> Bool {
    bundleID.lowercased() == "us.zoom.xos"
  }
}
