import Foundation

enum SystemCalendarMeetingContextFeature {
  static let flagName = "system_calendar_meeting_context"
  private static let localOverrideName = "OMI_FORCE_SYSTEM_CALENDAR_MEETING_CONTEXT"

  /// The feature ships dark. Named/dev bundles require an explicit environment override;
  /// production-family bundles require an explicit true PostHog flag evaluation.
  @MainActor static var isEnabled: Bool {
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localOverrideName] == "1"
    }
    return PostHogManager.shared.isFeatureEnabled(flagName)
  }
}

enum OnDeviceMeetingIdentityFeature {
  static let flagName = "on_device_meeting_identity"
  private static let localOverrideName = "OMI_FORCE_ON_DEVICE_MEETING_IDENTITY"

  /// Independent dark launch: screen-derived identity does not require Calendar permission.
  @MainActor static var isEnabled: Bool {
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localOverrideName] == "1"
    }
    return PostHogManager.shared.isFeatureEnabled(flagName)
  }
}
