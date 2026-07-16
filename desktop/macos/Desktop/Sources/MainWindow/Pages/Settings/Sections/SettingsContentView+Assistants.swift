import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var focusAssistantSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.focusassistant") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "eye.fill")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textSecondary)

            Text("Focus Assistant")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $focusEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: focusEnabled) { _, newValue in
                FocusAssistantSettings.shared.isEnabled = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(focus: FocusSettingsResponse(enabled: newValue)))
              }
          }

          Text("Detect distractions and help you stay focused")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          if focusEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            settingRow(
              title: "Visual Glow Effect", subtitle: "Show colored border when focus changes",
              settingId: "advanced.focusassistant.glow"
            ) {
              Toggle("", isOn: $glowOverlayEnabled)
                .toggleStyle(OmiToggleStyle())
                .labelsHidden()
                .disabled(isPreviewRunning)
                .onChange(of: glowOverlayEnabled) { _, newValue in
                  AssistantSettings.shared.glowOverlayEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      shared: SharedAssistantSettingsResponse(glowOverlayEnabled: newValue)))
                  if newValue {
                    startGlowPreview()
                  }
                }
            }

            settingRow(
              title: "Focus Cooldown", subtitle: "Minimum time between distraction alerts",
              settingId: "advanced.focusassistant.cooldown"
            ) {
              Picker("", selection: $cooldownInterval) {
                ForEach(cooldownOptions, id: \.self) { minutes in
                  Text(formatMinutes(minutes)).tag(minutes)
                }
              }
              .pickerStyle(.menu)
              .frame(width: 200)
              .onChange(of: cooldownInterval) { _, newValue in
                FocusAssistantSettings.shared.cooldownInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    focus: FocusSettingsResponse(cooldownInterval: newValue)))
              }
            }

            settingRow(
              title: "Focus Analysis Prompt",
              subtitle: "Customize AI instructions for focus analysis",
              settingId: "advanced.focusassistant.prompt"
            ) {
              HStack(spacing: OmiSpacing.sm) {
                Button(action: {
                  FocusTestRunnerWindow.show()
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "play.circle")
                      .scaledFont(size: OmiType.caption)
                    Text("Test Run")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))

                Button(action: {
                  PromptEditorWindow.show()
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Text("Edit")
                      .scaledFont(size: OmiType.caption)
                    Image(systemName: "arrow.up.right.square")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }

            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Excluded Apps for Focus Analysis
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Excluded Apps")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                Text("Focus coaching won't trigger for these apps")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }

              // Built-in system exclusions (non-removable)
              DisclosureGroup {
                LazyVStack(spacing: OmiSpacing.xxs) {
                  ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) {
                    appName in
                    HStack(spacing: OmiSpacing.md) {
                      AppIconView(appName: appName, size: 20)

                      Text(appName)
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)

                      Spacer()
                    }
                    .padding(.horizontal, OmiSpacing.md)
                    .padding(.vertical, OmiSpacing.xxs)
                  }
                }
              } label: {
                Text(
                  "System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))"
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
              }
              .tint(OmiColors.textTertiary)

              if !focusExcludedApps.isEmpty {
                LazyVStack(spacing: OmiSpacing.sm) {
                  ForEach(Array(focusExcludedApps).sorted(), id: \.self) { appName in
                    ExcludedAppRow(
                      appName: appName,
                      onRemove: {
                        FocusAssistantSettings.shared.includeApp(appName)
                        focusExcludedApps = FocusAssistantSettings.shared.excludedApps
                      }
                    )
                  }
                }
              }

              AppRuleEditorView(
                title: "Add App to Exclusion List",
                placeholder: "App name (e.g., Passwords)",
                addButtonTitle: "Add",
                existingApps: focusExcludedApps,
                builtInApps: TaskAssistantSettings.builtInExcludedApps,
                onAdd: { appName in
                  FocusAssistantSettings.shared.excludeApp(appName)
                  focusExcludedApps = FocusAssistantSettings.shared.excludedApps
                }
              )
            }
          }  // end if focusEnabled
        }
      }
    }
  }

  var taskAssistantSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.taskassistant") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "checklist")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textSecondary)

            Text("Task Assistant")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $taskEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: taskEnabled) { _, newValue in
                TaskAssistantSettings.shared.isEnabled = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(task: TaskSettingsResponse(enabled: newValue)))
              }
          }

          Text("Extract tasks and action items from your screen")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          if taskEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Task Agent (chat / investigate) toggle
            HStack {
              VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                Text("Task Agent")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                Text("Investigate button and sidebar chat for tasks")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }

              Spacer()

              Toggle("", isOn: $taskChatAgentEnabled)
                .toggleStyle(OmiToggleStyle())
                .labelsHidden()
                .onChange(of: taskChatAgentEnabled) { _, newValue in
                  TaskAgentSettings.shared.isChatEnabled = newValue
                }
            }

            // Working Directory (shared by chat agent and terminal agent)
            HStack(spacing: OmiSpacing.sm) {
              VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                Text("Working Directory")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                Text(
                  taskAgentWorkingDirectory.isEmpty
                    ? "Not set — chat agent defaults to ~" : taskAgentWorkingDirectory
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
                .lineLimit(1)
                .truncationMode(.middle)
              }

              Spacer()

              Button("Browse...") {
                let panel = NSOpenPanel()
                panel.canChooseFiles = false
                panel.canChooseDirectories = true
                panel.allowsMultipleSelection = false
                panel.canCreateDirectories = true
                if !taskAgentWorkingDirectory.isEmpty {
                  panel.directoryURL = URL(fileURLWithPath: taskAgentWorkingDirectory)
                }
                if panel.runModal() == .OK, let url = panel.url {
                  taskAgentWorkingDirectory = url.path
                  TaskAgentSettings.shared.workingDirectory = url.path
                }
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))

              if !taskAgentWorkingDirectory.isEmpty {
                Button("Clear") {
                  taskAgentWorkingDirectory = ""
                  TaskAgentSettings.shared.workingDirectory = ""
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }

            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Extraction Interval Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Extraction Interval")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("How often to scan for new tasks")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text(formatExtractionInterval(taskExtractionInterval))
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 80, alignment: .trailing)
              }

              Slider(
                value: Binding(
                  get: { Double(taskIntervalSliderIndex) },
                  set: { taskExtractionInterval = extractionIntervalOptions[Int($0)] }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(OmiColors.accent)
              .onChange(of: taskExtractionInterval) { _, newValue in
                performStepHaptic()
                TaskAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    task: TaskSettingsResponse(extractionInterval: newValue)))
              }
            }

            // Minimum Confidence Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Minimum Confidence")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("Only show tasks above this confidence level")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text("\(Int(taskMinConfidence * 100))%")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 40, alignment: .trailing)
              }

              Slider(value: $taskMinConfidence, in: 0.3...0.9, step: 0.1)
                .tint(OmiColors.accent)
                .onChange(of: taskMinConfidence) { _, newValue in
                  performStepHaptic()
                  TaskAssistantSettings.shared.minConfidence = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(task: TaskSettingsResponse(minConfidence: newValue)))
                }
            }

            settingRow(
              title: "Task Extraction Prompt",
              subtitle: "Customize AI instructions for task extraction",
              settingId: "advanced.taskassistant.prompt"
            ) {
              HStack(spacing: OmiSpacing.sm) {
                Button(action: {
                  TaskTestRunnerWindow.show()
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "play.circle")
                      .scaledFont(size: OmiType.caption)
                    Text("Test Run")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))

                Button(action: {
                  TaskPromptEditorWindow.show()
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Text("Edit")
                      .scaledFont(size: OmiType.caption)
                    Image(systemName: "arrow.up.right.square")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }

            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Allowed Apps for Task Extraction (Whitelist)
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Allowed Apps")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                Text(
                  "Tasks will only be extracted from these apps. Browsers are also filtered by keywords below."
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
              }

              // Editable list of all allowed apps
              LazyVStack(spacing: OmiSpacing.xxs) {
                ForEach(Array(taskAllowedApps).sorted(), id: \.self) { appName in
                  HStack(spacing: OmiSpacing.md) {
                    AppIconView(appName: appName, size: 20)

                    Text(appName)
                      .scaledFont(size: OmiType.body)
                      .foregroundColor(OmiColors.textPrimary)

                    if TaskAssistantSettings.isBrowser(appName) {
                      Text("browser")
                        .scaledFont(size: OmiType.micro)
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.horizontal, OmiSpacing.xs)
                        .padding(.vertical, OmiSpacing.hairline)
                        .background(OmiColors.backgroundTertiary)
                        .cornerRadius(OmiChrome.stripRadius)
                    }

                    Spacer()

                    Button {
                      TaskAssistantSettings.shared.disallowApp(appName)
                      taskAllowedApps = TaskAssistantSettings.shared.allowedApps
                    } label: {
                      Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                  }
                  .padding(.horizontal, OmiSpacing.md)
                  .padding(.vertical, OmiSpacing.xxs)
                }
              }

              AppRuleEditorView(
                title: "Add App to Allowed List",
                placeholder: "App name (e.g., Mail)",
                addButtonTitle: "Add",
                existingApps: taskAllowedApps,
                builtInApps: TaskAssistantSettings.defaultAllowedApps,
                onAdd: { appName in
                  TaskAssistantSettings.shared.allowApp(appName)
                  taskAllowedApps = TaskAssistantSettings.shared.allowedApps
                }
              )
            }

            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Browser Window Keywords
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Browser Window Keywords")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                Text(
                  "For browser apps, only analyze windows whose title contains one of these keywords."
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
              }

              // Keyword chips (filterable, deletable)
              BrowserKeywordListView(
                keywords: $taskBrowserKeywords,
                onAdd: { keyword in
                  TaskAssistantSettings.shared.addBrowserKeyword(keyword)
                  taskBrowserKeywords = TaskAssistantSettings.shared.browserKeywords
                },
                onRemove: { keyword in
                  TaskAssistantSettings.shared.removeBrowserKeyword(keyword)
                  taskBrowserKeywords = TaskAssistantSettings.shared.browserKeywords
                }
              )
            }

            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Task Prioritization Re-score
            settingRow(
              title: "Task Prioritization",
              subtitle: "Re-score all tasks by relevance to your profile and goals",
              settingId: "advanced.taskassistant.prioritization"
            ) {
              if isRescoringTasks {
                ProgressView()
                  .controlSize(.small)
              } else {
                Button(action: {
                  isRescoringTasks = true
                  Task {
                    await TaskPrioritizationService.shared.forceFullRescore()
                    await MainActor.run { isRescoringTasks = false }
                  }
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "arrow.trianglehead.counterclockwise")
                      .scaledFont(size: OmiType.caption)
                    Text("Re-score")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }
          }  // end if taskEnabled
        }
      }

      // Task Agent Settings (merged into Task Assistant subsection)
      settingsCard(settingId: "advanced.taskassistant.agent") {
        TaskAgentSettingsView()
      }
    }
  }

  var insightAssistantSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.insightassistant") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "lightbulb.fill")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textSecondary)

            Text("Insight Assistant")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $insightEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: insightEnabled) { _, newValue in
                InsightAssistantSettings.shared.isEnabled = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(insight: InsightSettingsResponse(enabled: newValue)))
              }
          }

          Text("Get proactive insights and suggestions")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          if insightEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Frequency Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Frequency")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("How often to check for insight opportunities")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text(formatExtractionInterval(insightExtractionInterval))
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 80, alignment: .trailing)
              }

              Slider(
                value: Binding(
                  get: { Double(insightIntervalSliderIndex) },
                  set: { insightExtractionInterval = extractionIntervalOptions[Int($0)] }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(OmiColors.accent)
              .onChange(of: insightExtractionInterval) { _, newValue in
                performStepHaptic()
                InsightAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    insight: InsightSettingsResponse(extractionInterval: newValue)))
              }
            }

            // Minimum Confidence Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Minimum Confidence")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("Only show insights above this confidence level")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text("\(Int(insightMinConfidence * 100))%")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 40, alignment: .trailing)
              }

              Slider(value: $insightMinConfidence, in: 0.5...0.95, step: 0.05)
                .tint(OmiColors.accent)
                .onChange(of: insightMinConfidence) { _, newValue in
                  performStepHaptic()
                  InsightAssistantSettings.shared.minConfidence = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      insight: InsightSettingsResponse(minConfidence: newValue)))
                }
            }

            settingRow(
              title: "Insight Prompt", subtitle: "Customize AI instructions for insights",
              settingId: "advanced.insightassistant.prompt"
            ) {
              HStack(spacing: OmiSpacing.sm) {
                Button(action: {
                  InsightTestRunnerWindow.show()
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "play.circle")
                      .scaledFont(size: OmiType.caption)
                    Text("Test Run")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))

                Button(action: {
                  InsightPromptEditorWindow.show()
                }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Text("Edit")
                      .scaledFont(size: OmiType.caption)
                    Image(systemName: "arrow.up.right.square")
                      .scaledFont(size: OmiType.caption)
                  }
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }

            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Excluded Apps for Advice
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Excluded Apps")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                Text("Advice won't be generated from these apps")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }

              // Built-in system exclusions (non-removable, shared with Task Extractor)
              DisclosureGroup {
                LazyVStack(spacing: OmiSpacing.xxs) {
                  ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) {
                    appName in
                    HStack(spacing: OmiSpacing.md) {
                      AppIconView(appName: appName, size: 20)

                      Text(appName)
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)

                      Spacer()
                    }
                    .padding(.horizontal, OmiSpacing.md)
                    .padding(.vertical, OmiSpacing.xxs)
                  }
                }
              } label: {
                Text(
                  "System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))"
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
              }
              .tint(OmiColors.textTertiary)

              if !insightExcludedApps.isEmpty {
                LazyVStack(spacing: OmiSpacing.sm) {
                  ForEach(Array(insightExcludedApps).sorted(), id: \.self) { appName in
                    ExcludedAppRow(
                      appName: appName,
                      onRemove: {
                        InsightAssistantSettings.shared.includeApp(appName)
                        insightExcludedApps = InsightAssistantSettings.shared.excludedApps
                      }
                    )
                  }
                }
              }

              AppRuleEditorView(
                title: "Add App to Exclusion List",
                placeholder: "App name (e.g., Passwords)",
                addButtonTitle: "Add",
                existingApps: insightExcludedApps,
                builtInApps: TaskAssistantSettings.builtInExcludedApps,
                onAdd: { appName in
                  InsightAssistantSettings.shared.excludeApp(appName)
                  insightExcludedApps = InsightAssistantSettings.shared.excludedApps
                }
              )
            }
          }  // end if insightEnabled
        }
      }
    }
  }

  var memoryAssistantSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.memoryassistant") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "brain.head.profile")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textSecondary)

            Text("Memory Assistant")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $memoryEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: memoryEnabled) { _, newValue in
                MemoryAssistantSettings.shared.isEnabled = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(memory: MemorySettingsResponse(enabled: newValue)))
              }
          }

          Text("Extract facts and wisdom from your screen")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          if memoryEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Extraction Interval Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Extraction Interval")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("How often to scan for new memories")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text(formatExtractionInterval(memoryExtractionInterval))
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 80, alignment: .trailing)
              }

              Slider(
                value: Binding(
                  get: { Double(memoryIntervalSliderIndex) },
                  set: { memoryExtractionInterval = extractionIntervalOptions[Int($0)] }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(OmiColors.accent)
              .onChange(of: memoryExtractionInterval) { _, newValue in
                performStepHaptic()
                MemoryAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    memory: MemorySettingsResponse(extractionInterval: newValue)))
              }
            }

            // Minimum Confidence Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Minimum Confidence")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("Only save memories above this confidence level")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text("\(Int(memoryMinConfidence * 100))%")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 40, alignment: .trailing)
              }

              Slider(value: $memoryMinConfidence, in: 0.5...0.95, step: 0.05)
                .tint(OmiColors.accent)
                .onChange(of: memoryMinConfidence) { _, newValue in
                  performStepHaptic()
                  MemoryAssistantSettings.shared.minConfidence = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      memory: MemorySettingsResponse(minConfidence: newValue)))
                }
            }

            settingRow(
              title: "Memory Extraction Prompt",
              subtitle: "Customize AI instructions for memory extraction",
              settingId: "advanced.memoryassistant.prompt"
            ) {
              Button(action: {
                MemoryPromptEditorWindow.show()
              }) {
                HStack(spacing: OmiSpacing.xxs) {
                  Text("Edit")
                    .scaledFont(size: OmiType.caption)
                  Image(systemName: "arrow.up.right.square")
                    .scaledFont(size: OmiType.caption)
                }
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            }

            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Excluded Apps for Memory Extraction
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Excluded Apps")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                Text("Memories won't be extracted from these apps")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }

              // Built-in system exclusions (non-removable, shared across assistants)
              DisclosureGroup {
                LazyVStack(spacing: OmiSpacing.xxs) {
                  ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) {
                    appName in
                    HStack(spacing: OmiSpacing.md) {
                      AppIconView(appName: appName, size: 20)

                      Text(appName)
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)

                      Spacer()
                    }
                    .padding(.horizontal, OmiSpacing.md)
                    .padding(.vertical, OmiSpacing.xxs)
                  }
                }
              } label: {
                Text(
                  "System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))"
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
              }
              .tint(OmiColors.textTertiary)

              if !memoryExcludedApps.isEmpty {
                LazyVStack(spacing: OmiSpacing.sm) {
                  ForEach(Array(memoryExcludedApps).sorted(), id: \.self) { appName in
                    ExcludedAppRow(
                      appName: appName,
                      onRemove: {
                        MemoryAssistantSettings.shared.includeApp(appName)
                        memoryExcludedApps = MemoryAssistantSettings.shared.excludedApps
                      }
                    )
                  }
                }
              }

              AppRuleEditorView(
                title: "Add App to Exclusion List",
                placeholder: "App name (e.g., Passwords)",
                addButtonTitle: "Add",
                existingApps: memoryExcludedApps,
                builtInApps: TaskAssistantSettings.builtInExcludedApps,
                onAdd: { appName in
                  MemoryAssistantSettings.shared.excludeApp(appName)
                  memoryExcludedApps = MemoryAssistantSettings.shared.excludedApps
                }
              )
            }
          }  // end if memoryEnabled
        }
      }
    }
  }

  var analysisThrottleSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.analysisthrottle") {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          HStack {
            VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
              Text("Analysis Throttle")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textSecondary)
              Text("Wait before analyzing after switching apps")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Text(formatAnalysisDelay(analysisDelay))
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
              .frame(width: 80, alignment: .trailing)
          }

          Slider(
            value: Binding(
              get: { Double(analysisDelaySliderIndex) },
              set: { analysisDelay = analysisDelayOptions[Int($0)] }
            ), in: 0...Double(analysisDelayOptions.count - 1), step: 1
          )
          .tint(OmiColors.accent)
          .onChange(of: analysisDelay) { _, newValue in
            performStepHaptic()
            AssistantSettings.shared.analysisDelay = newValue
            SettingsSyncManager.shared.pushPartialUpdate(
              AssistantSettingsResponse(
                shared: SharedAssistantSettingsResponse(analysisDelay: newValue)))
          }
        }
      }
    }
  }

  var goalsSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.goals") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "target")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textSecondary)

            Text("Goals")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()
          }

          Text("Track personal goals with AI-powered progress detection from your conversations")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          Divider()
            .background(OmiColors.backgroundQuaternary)

          settingRow(
            title: "Auto-Generate Goals",
            subtitle: "Automatically suggest new goals daily based on your conversations and tasks",
            settingId: "advanced.goals.autogenerate"
          ) {
            Toggle("", isOn: $goalsAutoGenerateEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: goalsAutoGenerateEnabled) { _, newValue in
                GoalGenerationService.shared.isAutoGenerationEnabled = newValue
              }
          }
        }
      }
    }
  }

  var preferencesSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Multiple Chat Sessions toggle
      settingsCard(settingId: "advanced.preferences.multichat") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "bubble.left.and.bubble.right")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Multiple Chat Sessions")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(
              multiChatEnabled
                ? "Create separate chat threads"
                : "Single chat synced with mobile app"
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Toggle("", isOn: $multiChatEnabled)
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
        }
      }

      settingsCard(settingId: "advanced.preferences.legacyhome") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "rectangle.split.2x1")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Use old Home design")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("Show the previous chat-first dashboard instead of the simplified Home")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Toggle("", isOn: $useLegacyHomeDesign)
            .toggleStyle(.checkbox)
            .labelsHidden()
        }
      }

      // Launch at Login toggle
      settingsCard(settingId: "advanced.preferences.launchatlogin") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "power")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Launch at Login")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(launchAtLoginManager.statusDescription)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Toggle(
            "",
            isOn: Binding(
              get: { launchAtLoginManager.isEnabled },
              set: { newValue in
                if launchAtLoginManager.setEnabled(newValue) {
                  AnalyticsManager.shared.launchAtLoginChanged(enabled: newValue, source: "user")
                }
              }
            )
          )
          .toggleStyle(OmiToggleStyle())
          .labelsHidden()
        }
      }
    }
  }

  var troubleshootingSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Report Issue
      settingsCard(settingId: "advanced.troubleshooting.reportissue") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "exclamationmark.bubble")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Report Issue")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("Send app logs and report a problem")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Button(action: {
            FeedbackWindow.show(userEmail: AuthState.shared.userEmail)
          }) {
            Text("Report")
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        }
      }

      // Rescan Files
      settingsCard(settingId: "advanced.troubleshooting.rescanfiles") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "folder.badge.gearshape")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Rescan Files")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("Re-index your files and update your AI profile")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Button(action: { showRescanFilesAlert = true }) {
            Text("Rescan")
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        }
      }
      .alert("Rescan Files?", isPresented: $showRescanFilesAlert) {
        Button("Cancel", role: .cancel) {}
        Button("Rescan") {
          NotificationCenter.default.post(name: .triggerFileIndexing, object: nil)
        }
      } message: {
        Text(
          "This will re-scan your files and update your AI profile with the latest information about your projects and interests."
        )
      }

    }
  }

  // MARK: - Reset Onboarding Subsection

  var resetOnboardingSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.resetonboarding") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "arrow.counterclockwise")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Reset Onboarding")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("Restart setup wizard for this app build only")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Button(action: { showResetOnboardingAlert = true }) {
            Text("Reset")
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        }
      }
      .alert("Reset Onboarding?", isPresented: $showResetOnboardingAlert) {
        Button("Cancel", role: .cancel) {}
        Button("Reset & Restart", role: .destructive) {
          appState.resetOnboardingAndRestart()
        }
      } message: {
        Text(
          "This will reset onboarding for this app build only, clear onboarding chat history, and restart the app without affecting the other installed build."
        )
      }
    }
  }

  // MARK: - Gmail Reader Subsection

}
