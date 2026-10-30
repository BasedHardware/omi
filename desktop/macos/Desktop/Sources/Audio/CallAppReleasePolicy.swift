import Foundation

/// Which native call apps end the call when they release the microphone.
///
/// Browsers are never listed: they drop mic input when a call is muted while the call continues.
/// Entries come from `desktop/macos/scripts/call-app-catalog/catalog.json`, which records the
/// evidence for each one. `score.py --apply` regenerates the block below from it (the weekly
/// scoring job proposes changes as a PR); `test_call_app_catalog.py` fails if they disagree.
enum CallAppReleasePolicy {
  // BEGIN GENERATED: call-app-catalog (desktop/macos/scripts/call-app-catalog/score.py)
  static let releaseEndsCallBundleIDs: Set<String> = [
    "us.zoom.xos"
  ]
  // END GENERATED: call-app-catalog

  /// `bundleID` is the app's catalog key: a native call app's resolved ID
  /// (`ConferencingApps.nativeCallAppID`), not one of its helper processes.
  static func releaseEndsCall(bundleID: String) -> Bool {
    releaseEndsCallBundleIDs.contains(bundleID.lowercased())
  }
}
