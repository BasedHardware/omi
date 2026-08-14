import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  var taskAssistantSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.taskassistant") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "checklist")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            Text("Task Assistant")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)

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
            .foregroundColor(Ink.secondary)

          if taskEnabled {
            GlassSeparator()

            // Task Agent (chat / investigate) toggle
            HStack {
              VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                Text("Task Agent")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                Text("Investigate button and sidebar chat for tasks")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)
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
                  .foregroundColor(Ink.secondary)
                Text(
                  taskAgentWorkingDirectory.isEmpty
                    ? "Not set — chat agent defaults to ~" : taskAgentWorkingDirectory
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
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

            GlassSeparator()

            // Extraction Interval Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Extraction Interval")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(Ink.secondary)
                  Text("How often to scan for new tasks")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                }

                Spacer()

                Text(formatExtractionInterval(taskExtractionInterval))
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .frame(width: 80, alignment: .trailing)
              }

              Slider(
                value: Binding(
                  get: { Double(taskIntervalSliderIndex) },
                  set: {
                    if let step = SettingsControlMetrics.ladderValue(
                      at: Int($0), in: extractionIntervalOptions)
                    {
                      taskExtractionInterval = step
                    }
                  }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(Ink.accent)
              .onChange(of: taskExtractionInterval) { _, newValue in
                performStepHaptic()
                TaskAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    task: TaskSettingsResponse(extractionInterval: newValue)))
              }

              offLadderStepNote(for: taskExtractionInterval, in: extractionIntervalOptions)
            }

            // Minimum Confidence Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Minimum Confidence")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(Ink.secondary)
                  Text("Only show tasks above this confidence level")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                }

                Spacer()

                Text("\(Int(taskMinConfidence * 100))%")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .frame(width: 40, alignment: .trailing)
              }

              Slider(value: $taskMinConfidence, in: 0.3...0.9, step: 0.1)
                .tint(Ink.accent)
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

            GlassSeparator()

            // Allowed Apps for Task Extraction (Whitelist)
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Allowed Apps")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                Text(
                  "Tasks will only be extracted from these apps. Browsers are also filtered by keywords below."
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
              }

              // Editable list of all allowed apps
              LazyVStack(spacing: OmiSpacing.xxs) {
                ForEach(Array(taskAllowedApps).sorted(), id: \.self) { appName in
                  HStack(spacing: OmiSpacing.md) {
                    AppIconView(appName: appName, size: 20)

                    Text(appName)
                      .scaledFont(size: OmiType.body)
                      .foregroundColor(Ink.primary)

                    if TaskAssistantSettings.isBrowser(appName) {
                      Text("browser")
                        .scaledFont(size: OmiType.micro)
                        .foregroundColor(Ink.secondary)
                        .padding(.horizontal, OmiSpacing.xs)
                        .padding(.vertical, OmiSpacing.hairline)
                        .background(Ink.rowFill)
                        .cornerRadius(OmiChrome.stripRadius)
                    }

                    Spacer()

                    Button {
                      TaskAssistantSettings.shared.disallowApp(appName)
                      taskAllowedApps = TaskAssistantSettings.shared.allowedApps
                    } label: {
                      Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(Ink.secondary)
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

            GlassSeparator()

            // Browser Window Keywords
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Browser Window Keywords")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                Text(
                  "For browser apps, only analyze windows whose title contains one of these keywords."
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
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

            GlassSeparator()

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
            Image(systemName: ProactiveNotificationBadge.insightSystemImage)
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            Text("Insight Assistant")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)

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
            .foregroundColor(Ink.secondary)

          if insightEnabled {
            GlassSeparator()

            // Frequency Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Frequency")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(Ink.secondary)
                  Text("How often to check for insight opportunities")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                }

                Spacer()

                Text(formatExtractionInterval(insightExtractionInterval))
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .frame(width: 80, alignment: .trailing)
              }

              Slider(
                value: Binding(
                  get: { Double(insightIntervalSliderIndex) },
                  set: {
                    if let step = SettingsControlMetrics.ladderValue(
                      at: Int($0), in: extractionIntervalOptions)
                    {
                      insightExtractionInterval = step
                    }
                  }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(Ink.accent)
              .onChange(of: insightExtractionInterval) { _, newValue in
                performStepHaptic()
                InsightAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    insight: InsightSettingsResponse(extractionInterval: newValue)))
              }

              offLadderStepNote(for: insightExtractionInterval, in: extractionIntervalOptions)
            }

            // Minimum Confidence Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Minimum Confidence")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(Ink.secondary)
                  Text("Only show insights above this confidence level")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                }

                Spacer()

                Text("\(Int(insightMinConfidence * 100))%")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .frame(width: 40, alignment: .trailing)
              }

              Slider(value: $insightMinConfidence, in: 0.5...0.95, step: 0.05)
                .tint(Ink.accent)
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

            GlassSeparator()

            // Excluded Apps for Advice
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Excluded Apps")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                Text("Advice won't be generated from these apps")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)
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
                        .foregroundColor(Ink.secondary)

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
                .foregroundColor(Ink.secondary)
              }
              .tint(Ink.secondary)

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
              .foregroundColor(Ink.secondary)

            Text("Memory Assistant")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)

            Spacer()

            Toggle("", isOn: $memoryEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: memoryEnabled) { _, newValue in
                MemoryAssistantSettings.shared.applyUserSettingChange(.enabled, value: newValue)
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(memory: MemorySettingsResponse(enabled: newValue)))
              }
          }

          Text("Extract facts and wisdom from your screen")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)

          if memoryEnabled {
            GlassSeparator()

            // Extraction Interval Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Extraction Interval")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(Ink.secondary)
                  Text("How often to scan for new memories")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                }

                Spacer()

                Text(formatExtractionInterval(memoryExtractionInterval))
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .frame(width: 80, alignment: .trailing)
              }

              Slider(
                value: Binding(
                  get: { Double(memoryIntervalSliderIndex) },
                  set: {
                    if let step = SettingsControlMetrics.ladderValue(
                      at: Int($0), in: extractionIntervalOptions)
                    {
                      memoryExtractionInterval = step
                    }
                  }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(Ink.accent)
              .onChange(of: memoryExtractionInterval) { _, newValue in
                performStepHaptic()
                MemoryAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    memory: MemorySettingsResponse(extractionInterval: newValue)))
              }

              offLadderStepNote(for: memoryExtractionInterval, in: extractionIntervalOptions)
            }

            // Minimum Confidence Slider
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text("Minimum Confidence")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(Ink.secondary)
                  Text("Only save memories above this confidence level")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                }

                Spacer()

                Text("\(Int(memoryMinConfidence * 100))%")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .frame(width: 40, alignment: .trailing)
              }

              Slider(value: $memoryMinConfidence, in: 0.5...0.95, step: 0.05)
                .tint(Ink.accent)
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

            GlassSeparator()

            // Excluded Apps for Memory Extraction
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Excluded Apps")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                Text("Memories won't be extracted from these apps")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)
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
                        .foregroundColor(Ink.secondary)

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
                .foregroundColor(Ink.secondary)
              }
              .tint(Ink.secondary)

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
                .foregroundColor(Ink.secondary)
              Text("Wait before analyzing after switching apps")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
            }

            Spacer()

            Text(formatAnalysisDelay(analysisDelay))
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.secondary)
              .frame(width: 80, alignment: .trailing)
          }

          Slider(
            value: Binding(
              get: { Double(analysisDelaySliderIndex) },
              set: {
                if let step = SettingsControlMetrics.ladderValue(
                  at: Int($0), in: analysisDelayOptions)
                {
                  analysisDelay = step
                }
              }
            ), in: 0...Double(analysisDelayOptions.count - 1), step: 1
          )
          .tint(Ink.accent)
          .onChange(of: analysisDelay) { _, newValue in
            performStepHaptic()
            AssistantSettings.shared.analysisDelay = newValue
            SettingsSyncManager.shared.pushPartialUpdate(
              AssistantSettingsResponse(
                shared: SharedAssistantSettingsResponse(analysisDelay: newValue)))
          }

          offLadderStepNote(for: analysisDelay, in: analysisDelayOptions)
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
              .foregroundColor(Ink.secondary)

            Text("Goals")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)

            Spacer()
          }

          Text("Track personal goals with AI-powered progress detection from your conversations")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)

          GlassSeparator()

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
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Multiple Chat Sessions")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text(
              multiChatEnabled
                ? "Create separate chat threads"
                : "Single chat synced with mobile app"
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
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
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Use old Home design")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text("Show the previous chat-first dashboard instead of the simplified Home")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }

          Spacer()

          // Same card shape, same trailing slot, same kind of preference as the two rows it sits
          // between — an AppKit checkbox here is a second switch vocabulary in one stack.
          Toggle("", isOn: $useLegacyHomeDesign)
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
        }
      }

      settingsCard(settingId: "advanced.preferences.speaknotifications") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "speaker.wave.2")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Speak Notifications Aloud")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text("Read proactive notifications out loud when they arrive, using your chat voice")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }

          Spacer()

          Toggle("", isOn: $speakNotificationsAloud)
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
        }
      }

      // Launch at Login toggle
      settingsCard(settingId: "advanced.preferences.launchatlogin") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "power")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Launch at Login")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text(launchAtLoginManager.statusDescription)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
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
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Report Issue")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text("Send app logs and report a problem")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
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
        RescanFilesRow(showConfirmation: $showRescanFilesAlert)
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
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Reset Onboarding")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text("Restart setup wizard for this app build only")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }

          Spacer()

          // Raises the confirmation; `SettingsPage` presents it. `.alert` dims the *window*, and this
          // window is a transparent rectangle larger than the panels in it, so the system's backdrop
          // landed on the wallpaper — see `ShellConfirmationDialog`.
          Button(action: { showResetOnboardingConfirm = true }) {
            Text("Reset")
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        }
      }
    }
  }

  // MARK: - Gmail Reader Subsection

  /// Re-reads every assistant control from the store that owns it.
  ///
  /// These cards are seeded from their singletons once, in `SettingsContentView.init`. Opening
  /// Settings then runs `loadBackendSettings()`, which awaits `SettingsSyncManager.syncFromServer()`
  /// — server-authoritative by design, and it rewrites exactly those singletons underneath the pane.
  /// Nothing told the pane, so the switches, sliders and app lists kept painting the pre-sync values
  /// until the next relaunch: a per-device answer to a per-account question. The sync manager already
  /// announces itself with `.assistantSettingsDidSyncFromServer`; `advancedSection` subscribes, and
  /// this is what it runs. Same shape as
  /// `syncNotificationTogglesFromAssistantSettings()` in `SettingsContentView+NotificationsPrivacy`.
  ///
  /// A sync that agrees with the pane assigns nothing, so the common case does not re-enter the
  /// `onChange` handlers above. A sync that corrects the pane does, and each handler then writes the
  /// value the server just supplied back to the same singleton — a no-op write whose partial update
  /// restates the server's own value, and whose telemetry sees no change to report.
  func syncAssistantControlsFromSettings() {
    let values = AssistantControlValues.current()
    taskEnabled = values.taskEnabled
    taskExtractionInterval = values.taskExtractionInterval
    taskMinConfidence = values.taskMinConfidence
    taskAllowedApps = values.taskAllowedApps
    taskBrowserKeywords = values.taskBrowserKeywords
    insightEnabled = values.insightEnabled
    insightExtractionInterval = values.insightExtractionInterval
    insightMinConfidence = values.insightMinConfidence
    insightExcludedApps = values.insightExcludedApps
    memoryEnabled = values.memoryEnabled
    memoryExtractionInterval = values.memoryExtractionInterval
    memoryMinConfidence = values.memoryMinConfidence
    memoryExcludedApps = values.memoryExcludedApps
    analysisDelay = values.analysisDelay
  }

}

// MARK: - Assistant Control Projection

/// Everything the three assistant cards and the analysis throttle paint, read from the stores that
/// own them.
///
/// Naming the projection separately is what lets the account-sync path be asserted without standing
/// up a SwiftUI host: a test can apply a server snapshot through `SettingsSyncManager` and compare
/// this against it. It is deliberately only the settings `SettingsSyncManager.applyRemoteSettings`
/// can rewrite — the task agent's chat toggle and working directory are local to this Mac and are
/// not the account's to correct.
struct AssistantControlValues: Equatable {
  var taskEnabled: Bool
  var taskExtractionInterval: TimeInterval
  var taskMinConfidence: Double
  var taskAllowedApps: Set<String>
  var taskBrowserKeywords: [String]
  var insightEnabled: Bool
  var insightExtractionInterval: TimeInterval
  var insightMinConfidence: Double
  var insightExcludedApps: Set<String>
  var memoryEnabled: Bool
  var memoryExtractionInterval: TimeInterval
  var memoryMinConfidence: Double
  var memoryExcludedApps: Set<String>
  var analysisDelay: Int

  @MainActor
  static func current() -> AssistantControlValues {
    AssistantControlValues(
      taskEnabled: TaskAssistantSettings.shared.isEnabled,
      taskExtractionInterval: TaskAssistantSettings.shared.extractionInterval,
      taskMinConfidence: TaskAssistantSettings.shared.minConfidence,
      taskAllowedApps: TaskAssistantSettings.shared.allowedApps,
      taskBrowserKeywords: TaskAssistantSettings.shared.browserKeywords,
      insightEnabled: InsightAssistantSettings.shared.isEnabled,
      insightExtractionInterval: InsightAssistantSettings.shared.extractionInterval,
      insightMinConfidence: InsightAssistantSettings.shared.minConfidence,
      insightExcludedApps: InsightAssistantSettings.shared.excludedApps,
      memoryEnabled: MemoryAssistantSettings.shared.isEnabled,
      memoryExtractionInterval: MemoryAssistantSettings.shared.extractionInterval,
      memoryMinConfidence: MemoryAssistantSettings.shared.minConfidence,
      memoryExcludedApps: MemoryAssistantSettings.shared.excludedApps,
      analysisDelay: AssistantSettings.shared.analysisDelay
    )
  }
}

// MARK: - Rescan Files

/// What the Rescan Files row is allowed to claim, and the sentence it shows for it.
///
/// The row used to promise it would "update your AI profile", then post a notification whose only
/// listener runs `FileIndexerService.backgroundRescan()` — an incremental re-index of file
/// *metadata* that never touches the profile. (Regenerating the profile is the Advanced page's own
/// separate button.) It also gave no sign it had done anything: press Rescan, and every pixel on
/// the row stayed exactly as it was, whether the scan ran, finished, or never started. Claim and
/// evidence live here together so neither can drift without the other.
enum FileRescanState: Equatable {
  case idle
  case scanning
  case finished(indexedFiles: Int)

  var subtitle: String {
    switch self {
    case .idle:
      return "Re-index the files in your standard folders"
    case .scanning:
      return "Re-indexing files…"
    case .finished(let indexedFiles):
      // A zero is not evidence of an empty Mac: `getIndexedFileCount()` also answers 0 when the
      // local database could not be opened, so the count is only stated when there is one.
      guard indexedFiles > 0 else { return "Re-index finished" }
      return "Re-indexed — \(indexedFiles) file\(indexedFiles == 1 ? "" : "s") in the index"
    }
  }
}

/// Settings ▸ Advanced ▸ Troubleshooting ▸ Rescan Files.
///
/// A view of its own because the progress it now reports is per-row transient state, and
/// `SettingsContentView` is one struct shared by every settings section — its stored properties are
/// the wrong place for a flag that only this row can be in.
struct RescanFilesRow: View {
  @Binding var showConfirmation: Bool
  @State private var state: FileRescanState = .idle

  var body: some View {
    HStack(spacing: OmiSpacing.lg) {
      Image(systemName: "folder.badge.gearshape")
        .scaledFont(size: OmiType.subheading)
        .foregroundColor(Ink.secondary)
        .frame(width: 24, height: 24)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Rescan Files")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Text(state.subtitle)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
      }

      Spacer()

      if state == .scanning {
        ProgressView()
          .controlSize(.small)
      } else {
        Button(action: { showConfirmation = true }) {
          Text("Rescan")
        }
        .buttonStyle(OmiButtonStyle(.primary, size: .compact))
      }
    }
    .alert("Rescan Files?", isPresented: $showConfirmation) {
      Button("Cancel", role: .cancel) {}
      Button("Rescan") { rescan() }
    } message: {
      Text(
        "Omi re-reads the names, sizes and folders of the files in your standard folders so recent "
          + "ones are searchable. File contents are not read."
      )
    }
  }

  private func rescan() {
    state = .scanning
    Task {
      await FileIndexerService.shared.backgroundRescan()
      let indexed = await FileIndexerService.shared.getIndexedFileCount()
      state = .finished(indexedFiles: indexed)
    }
  }
}
