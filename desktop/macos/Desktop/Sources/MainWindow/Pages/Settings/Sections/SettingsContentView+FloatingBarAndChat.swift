import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  var floatingBarSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "floatingbar.show") {
        HStack(spacing: OmiSpacing.lg) {
          Text("Show floating bar")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          Spacer()

          Toggle("", isOn: $showAskOmiBar)
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
            .onChange(of: showAskOmiBar) { _, newValue in
              if newValue {
                FloatingControlBarManager.shared.show()
              } else {
                FloatingControlBarManager.shared.hide()
              }
            }
        }
      }

      settingsCard(settingId: "floatingbar.background") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          Text("Background Style")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          HStack(spacing: OmiSpacing.lg) {
            Text("Transparent")
              .scaledFont(size: OmiType.body, weight: shortcutSettings.solidBackground ? .regular : .semibold)
              .foregroundColor(
                shortcutSettings.solidBackground ? OmiColors.textTertiary : OmiColors.textPrimary)

            Toggle("", isOn: $shortcutSettings.solidBackground)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()

            Text("Solid Dark")
              .scaledFont(size: OmiType.body, weight: shortcutSettings.solidBackground ? .semibold : .regular)
              .foregroundColor(
                shortcutSettings.solidBackground ? OmiColors.textPrimary : OmiColors.textTertiary)

            Spacer()
          }
        }
      }

      settingsCard(settingId: "floatingbar.draggable") {
        HStack(spacing: OmiSpacing.lg) {
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Draggable Floating Bar")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Allow repositioning the floating bar by dragging it.")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Toggle("", isOn: $shortcutSettings.draggableBarEnabled)
            .toggleStyle(OmiToggleStyle())
        }
      }

      settingsCard(settingId: "floatingbar.typedvoiceanswers") {
        HStack(spacing: OmiSpacing.lg) {
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Typed Questions")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Speak answers aloud when you submit a typed question from the floating bar.")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Toggle("", isOn: floatingBarTypedVoiceAnswersBinding)
            .toggleStyle(OmiToggleStyle())
        }
      }

      settingsCard(settingId: "floatingbar.screenshare") {
        HStack(spacing: OmiSpacing.lg) {
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Screen Sharing in Chat")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Let Ask Omi capture your screen when you ask about what's on it.")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Toggle("", isOn: $chatScreenshotSharingEnabled)
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
        }
      }

      voicePicker(settingId: "floatingbar.voice")
        .opacity(shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled ? 1 : 0.55)
        .disabled(!shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled)

      voiceSpeedSlider(settingId: "floatingbar.voicespeed")
        .opacity(shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled ? 1 : 0.55)
        .disabled(!shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled)
    }
  }

  func voicePicker(settingId: String) -> some View {
    settingsCard(settingId: settingId) {
      HStack(spacing: OmiSpacing.lg) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Voice")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(
            ShortcutSettings.voiceOption(for: shortcutSettings.selectedVoiceID).description
          )
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
        }
        Spacer()
        SettingsMenuPicker(selection: $shortcutSettings.selectedVoiceID) {
          ForEach(ShortcutSettings.availableVoices) { voice in
            Text(voice.name).tag(voice.id)
          }
        }
      }
    }
  }

  var shortcutsSection: some View {
    ShortcutsSettingsSection(highlightedSettingId: $highlightedSettingId)
  }

  var aiChatSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // AI Provider card
      settingsCard(settingId: "aichat.provider") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "cpu")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textTertiary)

            Text("AI Provider")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            SettingsMenuPicker(selection: $chatBridgeMode) {
              ForEach(AIProvider.all) { provider in
                Text(provider.displayName).tag(provider.bridgeModeRawValue)
              }
            }
            .onChange(of: chatBridgeMode) { _, newMode in
              if let mode = ChatProvider.BridgeMode(rawValue: newMode) {
                Task {
                  await chatProvider?.switchBridgeMode(to: mode)
                }
              }
            }
          }

          if let provider = AIProvider.from(bridgeMode: chatBridgeMode) {
            if let url = provider.attributionURL {
              Link(destination: url) {
                Text("\(provider.tagline) · \(url.host ?? "")")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }
            } else {
              Text(provider.tagline)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          if chatBridgeMode == "claudeCode" && chatProvider?.isClaudeConnected == true {
            Divider()

            HStack {
              Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .scaledFont(size: OmiType.caption)
              Text("Connected to Claude")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textSecondary)

              Spacer()

              Button("Disconnect") {
                Task {
                  await chatProvider?.disconnectClaude()
                }
              }
              .buttonStyle(.plain)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(.red)
            }
          }
        }
      }
      .onAppear {
        chatProvider?.checkClaudeConnectionStatus()
      }

      // Ask Mode card
      settingsCard(settingId: "aichat.askmode") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "bubble.left.and.bubble.right")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textTertiary)

            Text("Ask Mode")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $askModeEnabled)
              .toggleStyle(OmiToggleStyle())
              .controlSize(.small)
              .labelsHidden()
          }

          Text(
            "When enabled, shows an Ask/Act toggle in the chat. Ask mode restricts the AI to read-only actions. When disabled, the AI always runs in Act mode."
          )
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
        }
      }

      // Workspace card
      settingsCard(settingId: "aichat.workspace") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "folder")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textTertiary)

            Text("Workspace")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Button("Browse...") {
              let panel = NSOpenPanel()
              panel.canChooseFiles = false
              panel.canChooseDirectories = true
              panel.allowsMultipleSelection = false
              panel.message = "Select a project directory"
              if panel.runModal() == .OK, let url = panel.url {
                aiChatWorkingDirectory = url.path
                refreshAIChatConfig()
                // Update ChatProvider
                chatProvider?.aiChatWorkingDirectory = url.path
                Task { await chatProvider?.discoverClaudeConfig() }
                if chatProvider?.workingDirectory == nil {
                  chatProvider?.workingDirectory = url.path
                }
              }
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))

            if !aiChatWorkingDirectory.isEmpty {
              Button("Clear") {
                aiChatWorkingDirectory = ""
                refreshAIChatConfig()
                chatProvider?.aiChatWorkingDirectory = ""
                Task { await chatProvider?.discoverClaudeConfig() }
                chatProvider?.workingDirectory = nil
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            }
          }

          if !aiChatWorkingDirectory.isEmpty {
            Text(aiChatWorkingDirectory)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
              .truncationMode(.middle)

            Text("Project-level CLAUDE.md and skills will be discovered from this directory")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          } else {
            Text(
              "No workspace set. Set a project directory to discover project-level CLAUDE.md and skills."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
          }
        }
      }

      // CLAUDE.md card
      settingsCard(settingId: "aichat.claudemd") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "doc.text")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textTertiary)

            Text("CLAUDE.md")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()
          }

          Text("Reference only — CLAUDE.md content is never injected into chat instructions.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)

          // Global CLAUDE.md
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            HStack {
              Text("Global")
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.horizontal, OmiSpacing.xs)
                .padding(.vertical, OmiSpacing.hairline)
                .background(
                  RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                    .fill(OmiColors.backgroundPrimary.opacity(0.5))
                )

              Spacer()

              if aiChatClaudeMdContent != nil {
                Button("View") {
                  fileViewerTitle = "Global CLAUDE.md"
                  fileViewerContent = aiChatClaudeMdContent ?? ""
                  showFileViewer = true
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }

            if let path = aiChatClaudeMdPath, let content = aiChatClaudeMdContent {
              let sizeKB = Double(content.utf8.count) / 1024.0
              Text("\(path) (\(String(format: "%.1f", sizeKB)) KB)")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
                .lineLimit(1)
                .truncationMode(.middle)
            } else {
              Text("No CLAUDE.md found at ~/.claude/CLAUDE.md")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          // Project CLAUDE.md (only show if workspace is set)
          if !aiChatWorkingDirectory.isEmpty {
            Divider().opacity(0.3)

            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                Text("Project")
                  .scaledFont(size: OmiType.caption, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .padding(.horizontal, OmiSpacing.xs)
                  .padding(.vertical, OmiSpacing.hairline)
                  .background(
                    RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                      .fill(OmiColors.backgroundTertiary)
                  )

                Spacer()

                if aiChatProjectClaudeMdContent != nil {
                  Button("View") {
                    fileViewerTitle = "Project CLAUDE.md"
                    fileViewerContent = aiChatProjectClaudeMdContent ?? ""
                    showFileViewer = true
                  }
                  .buttonStyle(OmiButtonStyle(.primary, size: .compact))
                }
              }

              if let path = aiChatProjectClaudeMdPath, let content = aiChatProjectClaudeMdContent {
                let sizeKB = Double(content.utf8.count) / 1024.0
                Text("\(path) (\(String(format: "%.1f", sizeKB)) KB)")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
                  .lineLimit(1)
                  .truncationMode(.middle)
              } else {
                Text("No CLAUDE.md found at \(aiChatWorkingDirectory)/CLAUDE.md")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }
          }
        }
      }

      // Skills card
      settingsCard(settingId: "aichat.skills") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "sparkles")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textTertiary)

            if aiChatProjectDiscoveredSkills.isEmpty {
              Text("Skills (\(aiChatDiscoveredSkills.count) discovered)")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
            } else {
              Text(
                "Skills (\(aiChatDiscoveredSkills.count) global + \(aiChatProjectDiscoveredSkills.count) project)"
              )
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            }

            Spacer()

            Button(action: { refreshAIChatConfig() }) {
              Image(systemName: "arrow.clockwise")
                .scaledFont(size: OmiType.body)
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          }

          let allSkills: [(skill: (name: String, description: String, path: String), origin: String)] =
            aiChatDiscoveredSkills.map { ($0, "Global") }
            + aiChatProjectDiscoveredSkills.map { ($0, "Project") }

          if allSkills.isEmpty {
            Text("No skills found in ~/.claude/skills/")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          } else {
            Text("Skill descriptions are included in the AI chat system prompt")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)

            // Search field
            HStack(spacing: OmiSpacing.sm) {
              Image(systemName: "magnifyingglass")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)

              TextField("Search skills...", text: $skillSearchQuery)
                .textFieldStyle(.plain)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)

              if !skillSearchQuery.isEmpty {
                Button(action: { skillSearchQuery = "" }) {
                  Image(systemName: "xmark.circle.fill")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
              }
            }
            .padding(OmiSpacing.sm)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .fill(OmiColors.backgroundPrimary.opacity(0.5))
            )

            ScrollView {
              let filteredSkills = allSkills.enumerated().filter { _, item in
                skillSearchQuery.isEmpty
                  || item.skill.name.localizedStandardContains(skillSearchQuery)
                  || item.skill.description.localizedStandardContains(skillSearchQuery)
              }

              VStack(spacing: 0) {
                ForEach(filteredSkills, id: \.element.skill.path) { item in
                  let skill = item.element.skill
                  let origin = item.element.origin
                  HStack(spacing: OmiSpacing.sm) {
                    Toggle(
                      "Enable \(skill.name)",
                      isOn: Binding(
                        get: { !aiChatDisabledSkills.contains(skill.name) },
                        set: { enabled in
                          if enabled {
                            aiChatDisabledSkills.remove(skill.name)
                          } else {
                            aiChatDisabledSkills.insert(skill.name)
                          }
                          saveDisabledSkills()
                        }
                      )
                    )
                    .toggleStyle(.checkbox)
                    .labelsHidden()

                    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                      HStack(spacing: OmiSpacing.xs) {
                        Text(skill.name)
                          .scaledFont(size: OmiType.body, weight: .medium)
                          .foregroundColor(OmiColors.textPrimary)

                        Text(origin)
                          .scaledFont(size: OmiType.micro, weight: .medium)
                          .foregroundColor(
                            origin == "Project" ? OmiColors.textSecondary : OmiColors.textTertiary
                          )
                          .padding(.horizontal, OmiSpacing.xxs)
                          .padding(.vertical, OmiSpacing.hairline)
                          .background(
                            RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                              .fill(
                                origin == "Project"
                                  ? OmiColors.backgroundTertiary
                                  : OmiColors.backgroundPrimary.opacity(0.5))
                          )
                      }

                      if !skill.description.isEmpty {
                        Text(skill.description)
                          .scaledFont(size: OmiType.caption)
                          .foregroundColor(OmiColors.textTertiary)
                          .lineLimit(1)
                          .truncationMode(.tail)
                      }
                    }

                    Spacer()

                    Button("View") {
                      fileViewerTitle = "\(skill.name)/SKILL.md"
                      fileViewerContent =
                        (try? String(contentsOfFile: skill.path, encoding: .utf8))
                        ?? "Unable to read file"
                      showFileViewer = true
                    }
                    .buttonStyle(OmiButtonStyle(.primary, size: .compact))
                  }
                  .padding(.vertical, OmiSpacing.xs)
                  .padding(.horizontal, OmiSpacing.xxs)

                  if item.offset != filteredSkills.last?.offset {
                    Divider()
                      .opacity(0.3)
                  }
                }
              }
            }
            .frame(maxHeight: 300)
          }
        }
      }

      // Browser Extension card
      settingsCard(settingId: "aichat.browserextension") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "globe")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textTertiary)

            Text("Browser Extension")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            if !playwrightExtensionToken.isEmpty {
              HStack(spacing: OmiSpacing.xxs) {
                Circle()
                  .fill(Color.green)
                  .frame(width: 6, height: 6)
                Text("Connected")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }

            Toggle("", isOn: $playwrightUseExtension)
              .toggleStyle(OmiToggleStyle())
              .controlSize(.small)
              .labelsHidden()
              .onChange(of: playwrightUseExtension) { _, _ in
              }
          }

          Text("Lets the AI use your Chrome browser with all your logged-in sessions.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)

          if playwrightUseExtension {
            if playwrightExtensionToken.isEmpty {
              // No token — show "Set Up" button
              Button(action: {
                showBrowserSetup = true
              }) {
                HStack(spacing: OmiSpacing.xs) {
                  Image(systemName: "wrench.and.screwdriver")
                    .scaledFont(size: OmiType.caption)
                  Text("Set Up")
                    .scaledFont(size: OmiType.body, weight: .medium)
                }
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            } else {
              // Token is set — show compact view
              HStack(spacing: OmiSpacing.sm) {
                Text("Token")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)

                Text(String(playwrightExtensionToken.prefix(8)) + "...")
                  .scaledFont(size: OmiType.caption, weight: .medium)
                  .foregroundColor(OmiColors.textPrimary)
                  .font(.system(.body, design: .monospaced))

                Spacer()

                Button(action: {
                  showBrowserSetup = true
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "arrow.clockwise")
                      .scaledFont(size: OmiType.caption)
                    Text("Reconfigure")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))

                Button(action: {
                  playwrightExtensionToken = ""
                  UserDefaults.standard.set("", forKey: "playwrightExtensionToken")
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "xmark")
                      .scaledFont(size: OmiType.caption)
                    Text("Reset")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }
          }
        }
      }

      // Dev Mode card
      settingsCard(settingId: "aichat.devmode") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "hammer")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textTertiary)

            Text("Dev Mode")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $devModeEnabled)
              .toggleStyle(OmiToggleStyle())
              .controlSize(.small)
              .labelsHidden()
              .onChange(of: devModeEnabled) { _, newValue in
                AnalyticsManager.shared.settingToggled(setting: "dev_mode", enabled: newValue)
              }
          }

          Text("Let the AI modify the app's source code, rebuild it, and add custom features.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)

          if devModeEnabled {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "checkmark.circle.fill")
                  .foregroundColor(.green)
                  .scaledFont(size: OmiType.caption)
                Text("AI can modify UI, add features, create custom SQLite tables")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textSecondary)
              }
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "lock.fill")
                  .foregroundColor(.orange)
                  .scaledFont(size: OmiType.caption)
                Text("Backend API, auth, and sync logic are read-only")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textSecondary)
              }
            }
          }
        }
      }
    }
    .onAppear {
      refreshAIChatConfig()
      playwrightExtensionToken =
        UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
    }
    .sheet(isPresented: $showFileViewer) {
      fileViewerSheet
    }
    .sheet(isPresented: $showBrowserSetup) {
      BrowserExtensionSetup(
        onComplete: {
          showBrowserSetup = false
          playwrightExtensionToken =
            UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
        },
        onDismiss: {
          showBrowserSetup = false
          playwrightExtensionToken =
            UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
        },
        chatProvider: chatProvider
      )
      .fixedSize()
    }
  }

  var fileViewerSheet: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text(fileViewerTitle)
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button(action: { showFileViewer = false }) {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding(OmiSpacing.lg)

      Divider().opacity(0.3)

      // Content
      ScrollView {
        Text(fileViewerContent)
          .font(.system(size: 12, design: .monospaced))
          .foregroundColor(OmiColors.textSecondary)
          .textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(OmiSpacing.lg)
      }
    }
    .frame(width: 600, height: 500)
    .background(OmiColors.backgroundSecondary)
  }

  func refreshAIChatConfig() {
    // Pull skill and CLAUDE.md data directly from ChatProvider (already discovered at startup).
    // Fall back to reading from disk only when ChatProvider is unavailable.
    if let provider = chatProvider {
      aiChatClaudeMdContent = provider.claudeMdContent
      aiChatClaudeMdPath = provider.claudeMdPath
      aiChatDiscoveredSkills = provider.discoveredSkills
      aiChatProjectClaudeMdContent = provider.projectClaudeMdContent
      aiChatProjectClaudeMdPath = provider.projectClaudeMdPath
      aiChatProjectDiscoveredSkills = provider.projectDiscoveredSkills
      loadDisabledSkills()
      return
    }

    // Fallback: read from disk (used when Settings is shown before ChatProvider initializes)
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let claudeDir = "\(home)/.claude"

    let mdPath = "\(claudeDir)/CLAUDE.md"
    if FileManager.default.fileExists(atPath: mdPath),
      let content = try? String(contentsOfFile: mdPath, encoding: .utf8)
    {
      aiChatClaudeMdContent = content
      aiChatClaudeMdPath = mdPath
    } else {
      aiChatClaudeMdContent = nil
      aiChatClaudeMdPath = nil
    }

    var skills: [(name: String, description: String, path: String)] = []
    let skillsDir = "\(claudeDir)/skills"
    if let skillDirs = try? FileManager.default.contentsOfDirectory(atPath: skillsDir) {
      for dir in skillDirs.sorted() {
        let skillPath = "\(skillsDir)/\(dir)/SKILL.md"
        if FileManager.default.fileExists(atPath: skillPath),
          let content = try? String(contentsOfFile: skillPath, encoding: .utf8)
        {
          let desc = ChatProvider.extractSkillDescription(from: content)
          skills.append((name: dir, description: desc, path: skillPath))
        }
      }
    }
    aiChatDiscoveredSkills = skills

    let workspace = aiChatWorkingDirectory
    if !workspace.isEmpty, FileManager.default.fileExists(atPath: workspace) {
      let projectMdPath = "\(workspace)/CLAUDE.md"
      if FileManager.default.fileExists(atPath: projectMdPath),
        let content = try? String(contentsOfFile: projectMdPath, encoding: .utf8)
      {
        aiChatProjectClaudeMdContent = content
        aiChatProjectClaudeMdPath = projectMdPath
      } else {
        aiChatProjectClaudeMdContent = nil
        aiChatProjectClaudeMdPath = nil
      }

      var projectSkills: [(name: String, description: String, path: String)] = []
      let projectSkillsDir = "\(workspace)/.claude/skills"
      if let skillDirs = try? FileManager.default.contentsOfDirectory(atPath: projectSkillsDir) {
        for dir in skillDirs.sorted() {
          let skillPath = "\(projectSkillsDir)/\(dir)/SKILL.md"
          if FileManager.default.fileExists(atPath: skillPath),
            let content = try? String(contentsOfFile: skillPath, encoding: .utf8)
          {
            let desc = ChatProvider.extractSkillDescription(from: content)
            projectSkills.append((name: dir, description: desc, path: skillPath))
          }
        }
      }
      aiChatProjectDiscoveredSkills = projectSkills
    } else {
      aiChatProjectClaudeMdContent = nil
      aiChatProjectClaudeMdPath = nil
      aiChatProjectDiscoveredSkills = []
    }

    loadDisabledSkills()
  }

  func loadDisabledSkills() {
    let json = UserDefaults.standard.string(forKey: "disabledSkillsJSON") ?? ""
    guard let data = json.data(using: .utf8),
      let names = try? JSONDecoder().decode([String].self, from: data)
    else {
      aiChatDisabledSkills = []  // Default: nothing disabled = all enabled
      return
    }
    aiChatDisabledSkills = Set(names)
  }

  func saveDisabledSkills() {
    if let data = try? JSONEncoder().encode(Array(aiChatDisabledSkills)),
      let json = String(data: data, encoding: .utf8)
    {
      UserDefaults.standard.set(json, forKey: "disabledSkillsJSON")
    }
  }

  // MARK: - About Section

  // MARK: - Advanced Section

  struct UserStats {
    let conversations: Int
    let appsInstalled: Int
    let screenshotsTotal: Int
    let focusSessions: Int
    let tasksTodo: Int
    let tasksDone: Int
    let tasksDeleted: Int
    let goalsCount: Int
    let memoriesTotal: Int
  }

}
