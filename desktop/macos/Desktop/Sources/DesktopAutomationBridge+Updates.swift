import Foundation

/// Version and update automation actions, grouped out of the main registry file.
///
/// They report and drive what the About and Settings > Updates panes show: bundle identity, the
/// running version and its update preferences, the bundled release-note catalog, and the disclosure
/// state behind the "What's New" list — the same state a click drives, so a flow can assert the
/// section rather than only that it rendered.
extension DesktopAutomationActionRegistry {
  func registerUpdatesActions() {
    register(
      name: "about_snapshot",
      summary: "Return About settings version/build/bundle metadata"
    ) { _ in
      let updater = UpdaterViewModel.shared
      return [
        "version": updater.currentVersion,
        "build": updater.buildNumber,
        "bundle_id": AppBuild.bundleIdentifier,
        "channel": updater.activeChannelLabel,
      ]
    }

    register(
      name: "settings_updates_snapshot",
      summary: "Return Updates settings state: version, channel, preferences, bundled release notes"
    ) { _ in
      let updater = UpdaterViewModel.shared
      let catalog = DesktopReleaseNotesCatalog.bundled
      let disclosure = ReleaseNotesDisclosure.shared
      return [
        "schema":
          "version,build,channel,auto_check,auto_install,release_note_count,latest_release_version,latest_release_change_count,has_notes_for_running_version,visible_release_count,expanded_versions",
        "version": updater.currentVersion,
        "build": updater.buildNumber,
        "channel": updater.activeChannelLabel,
        "auto_check": "\(updater.automaticallyChecksForUpdates)",
        "auto_install": "\(updater.automaticallyDownloadsUpdates)",
        "release_note_count": "\(catalog.releases.count)",
        "latest_release_version": catalog.releases.first?.version ?? "",
        "latest_release_change_count": "\(catalog.releases.first?.changes.count ?? 0)",
        "has_notes_for_running_version": "\(catalog.note(forVersion: updater.currentVersion) != nil)",
        "visible_release_count": "\(disclosure.visibleCount)",
        "expanded_versions": disclosure.expandedVersions.sorted().joined(separator: ","),
      ]
    }

    register(
      name: "settings_toggle_release_note",
      summary: "Open or close one older release in the Updates section's release-note list",
      params: ["version"]
    ) { params in
      guard let version = params["version"], !version.isEmpty else {
        throw DesktopAutomationActionError.invalidParams("version is required")
      }
      let disclosure = await MainActor.run { ReleaseNotesDisclosure.shared }
      await MainActor.run { disclosure.toggle(version) }
      let expanded = await MainActor.run { disclosure.expandedVersions.sorted() }
      return [
        "version": version,
        "expanded": "\(expanded.contains(version))",
        "expanded_versions": expanded.joined(separator: ","),
      ]
    }

    register(
      name: "settings_show_more_release_notes",
      summary: "Reveal the next page of releases in the Updates section"
    ) { _ in
      let total = DesktopReleaseNotesCatalog.bundled.releases.count
      let disclosure = await MainActor.run { ReleaseNotesDisclosure.shared }
      await MainActor.run { disclosure.showMore(total: total) }
      let visible = await MainActor.run { disclosure.visibleCount }
      return [
        "visible_release_count": "\(visible)",
        "total_release_count": "\(total)",
      ]
    }
  }
}
