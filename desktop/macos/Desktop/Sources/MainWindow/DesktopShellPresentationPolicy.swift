enum DesktopShellPresentationPolicy {
  static func usesChatFirst(_ useLegacyHomeDesign: Bool, _ capabilityVariant: ChatFirstShellVariant) -> Bool {
    guard !useLegacyHomeDesign else { return false }
    if case .chatFirst = capabilityVariant { return true }
    return false
  }
}
