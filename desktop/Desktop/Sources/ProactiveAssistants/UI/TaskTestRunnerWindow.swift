import Cocoa
import SwiftUI

// MARK: - Test Result Model

struct TaskTestResult: Identifiable {
    let id = UUID()
    let index: Int
    let timestamp: Date
    let appName: String
    let windowTitle: String?
    let result: TaskExtractionResult?
    let error: String?
    let duration: TimeInterval
    let searchCount: Int
}

// MARK: - SwiftUI View

struct TaskTestRunnerView: View {
    @State private var periodFrom: Date = Calendar.current.date(byAdding: .hour, value: -24, to: Date()) ?? Date()
    @State private var periodTo: Date = Date()
    @State private var isRunning = false
    @State private var results: [TaskTestResult] = []
    @State private var progress: Double = 0
    @State private var elapsedTime: TimeInterval = 0
    @State private var statusMessage = "Ready"
    @State private var cancellationRequested = false
    @State private var totalContextSwitches = 0

    var onClose: (() -> Void)?

    private var tasksFound: Int {
        results.filter { $0.result?.hasNewTask == true }.count
    }

    private var errorsCount: Int {
        results.filter { $0.error != nil }.count
    }

    private var totalSearches: Int {
        results.reduce(0) { $0 + $1.searchCount }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            header
                .padding(20)

            Divider()

            // Column headers
            columnHeaders
                .padding(.horizontal, 20)
                .padding(.vertical, 6)
                .background(Color(nsColor: .windowBackgroundColor))

            Divider()

            // Results
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(results) { result in
                            resultRow(result)
                                .id(result.id)
                        }
                    }
                    .padding(.vertical, 8)
                }
                .onChange(of: results.count) { _, _ in
                    if let last = results.last {
                        withAnimation {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            // Footer
            footer
                .padding(16)
        }
        .frame(width: 1400, height: 900)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    // MARK: - Header

    private var header: some View {
        VStack(spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Task Extraction Test Runner")
                        .scaledFont(size: 16, weight: .semibold)
                        .foregroundColor(.primary)

                    Text("Replay departing frames from context switches through the extraction pipeline")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button(action: { onClose?() }) {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 16)
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 16) {
                // Time range pickers
                HStack(spacing: 8) {
                    Text("From:")
                        .scaledFont(size: 13)
                        .foregroundColor(.secondary)

                    DatePicker("", selection: $periodFrom, in: ...periodTo)
                        .labelsHidden()
                        .datePickerStyle(.field)
                        .frame(width: 180)
                        .disabled(isRunning)

                    Text("To:")
                        .scaledFont(size: 13)
                        .foregroundColor(.secondary)

                    DatePicker("", selection: $periodTo, in: periodFrom...Date())
                        .labelsHidden()
                        .datePickerStyle(.field)
                        .frame(width: 180)
                        .disabled(isRunning)
                }

                Spacer()

                // Run / Stop button
                if isRunning {
                    Button(action: { cancellationRequested = true }) {
                        HStack(spacing: 4) {
                            Image(systemName: "stop.fill")
                                .scaledFont(size: 10)
                            Text("Stop")
                                .scaledFont(size: 12)
                        }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .tint(.red)
                } else {
                    Button(action: runTest) {
                        HStack(spacing: 4) {
                            Image(systemName: "play.fill")
                                .scaledFont(size: 10)
                            Text("Run Test")
                                .scaledFont(size: 12)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
            }

            // Progress bar
            if isRunning {
                VStack(spacing: 4) {
                    ProgressView(value: progress)
                        .tint(.accentColor)

                    Text(statusMessage)
                        .scaledFont(size: 11)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Column Headers

    private var columnHeaders: some View {
        HStack(spacing: 16) {
            Text("#")
                .frame(width: 28, alignment: .trailing)
            Text("Time")
                .frame(width: 90, alignment: .leading)
            Text("App")
                .frame(width: 100, alignment: .leading)
            Text("Window")
                .frame(width: 250, alignment: .leading)
            Text("Decision")
                .frame(width: 100, alignment: .leading)
            Text("Search")
                .frame(width: 40, alignment: .leading)
            Text("Details")
            Spacer()
            Text("Conf")
                .frame(width: 40, alignment: .trailing)
            Text("Time")
                .frame(width: 50, alignment: .trailing)
        }
        .scaledFont(size: 11, weight: .medium)
        .foregroundColor(.secondary.opacity(0.7))
    }

    // MARK: - Result Row

    private func resultRow(_ testResult: TaskTestResult) -> some View {
        HStack(spacing: 16) {
            // Index
            Text("\(testResult.index)")
                .scaledFont(size: 12, design: .monospaced)
                .foregroundColor(.secondary)
                .frame(width: 28, alignment: .trailing)

            // Timestamp
            Text(testResult.timestamp, format: .dateTime.hour().minute().second())
                .scaledFont(size: 12, design: .monospaced)
                .foregroundColor(.secondary)
                .frame(width: 90, alignment: .leading)

            // App name
            Text(testResult.appName)
                .scaledFont(size: 12)
                .foregroundColor(.secondary)
                .frame(width: 100, alignment: .leading)
                .lineLimit(1)

            // Window title
            Text(testResult.windowTitle ?? "—")
                .scaledFont(size: 12)
                .foregroundColor(.secondary)
                .frame(width: 250, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)

            // Decision column
            decisionBadge(for: testResult)
                .frame(width: 100, alignment: .leading)

            // Search count indicator
            if testResult.searchCount > 0 {
                HStack(spacing: 2) {
                    Image(systemName: "magnifyingglass")
                        .scaledFont(size: 9)
                    Text("×\(testResult.searchCount)")
                        .scaledFont(size: 11, design: .monospaced)
                }
                .foregroundColor(.secondary)
                .frame(width: 40, alignment: .leading)
            } else {
                Text("")
                    .frame(width: 40)
            }

            // Task title or context summary
            if let error = testResult.error {
                Text(error)
                    .scaledFont(size: 12)
                    .foregroundColor(.orange)
                    .lineLimit(2)
            } else if let result = testResult.result {
                if result.hasNewTask, let task = result.task {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(task.title)
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(.primary)
                            .lineLimit(2)
                        HStack(spacing: 8) {
                            Text(task.priority.rawValue)
                                .scaledFont(size: 10, weight: .medium)
                                .foregroundColor(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 1)
                                .background(priorityColor(task.priority))
                                .cornerRadius(3)
                            Text("\(task.sourceCategory)/\(task.sourceSubcategory)")
                                .scaledFont(size: 10, weight: .medium)
                                .foregroundColor(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 1)
                                .background(Color.purple.opacity(0.7))
                                .cornerRadius(3)
                            Text(task.tags.joined(separator: ", "))
                                .scaledFont(size: 10)
                                .foregroundColor(.secondary)
                        }
                    }
                } else {
                    Text(result.contextSummary)
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer()

            // Confidence (only for tasks)
            if let result = testResult.result, result.hasNewTask, let task = result.task {
                Text("\(Int(task.confidence * 100))%")
                    .scaledFont(size: 12, weight: .medium, design: .monospaced)
                    .foregroundColor(.green)
                    .frame(width: 40, alignment: .trailing)
            } else {
                Text("")
                    .frame(width: 40)
            }

            // Duration
            Text(String(format: "%.1fs", testResult.duration))
                .scaledFont(size: 12, design: .monospaced)
                .foregroundColor(.secondary.opacity(0.7))
                .frame(width: 50, alignment: .trailing)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 8)
        .background(testResult.result?.hasNewTask == true ? Color.green.opacity(0.05) : Color.clear)
    }

    private func decisionBadge(for testResult: TaskTestResult) -> some View {
        Group {
            if testResult.error != nil {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .scaledFont(size: 10)
                    Text("Error")
                        .scaledFont(size: 11, weight: .medium)
                }
                .foregroundColor(.orange)
            } else if let result = testResult.result {
                if result.hasNewTask {
                    HStack(spacing: 4) {
                        Image(systemName: "plus.circle.fill")
                            .scaledFont(size: 10)
                        Text("New Task")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(.green)
                } else {
                    HStack(spacing: 4) {
                        Image(systemName: "minus.circle")
                            .scaledFont(size: 10)
                        Text("No Task")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(.secondary)
                }
            }
        }
    }

    private func priorityColor(_ priority: TaskPriority) -> Color {
        switch priority {
        case .high: return .red
        case .medium: return .orange
        case .low: return .blue
        }
    }

    // MARK: - Footer

    private var footer: some View {
        HStack {
            if !results.isEmpty {
                HStack(spacing: 16) {
                    Label("\(results.count)/\(totalContextSwitches)", systemImage: "arrow.triangle.swap")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)

                    Label("\(tasksFound) tasks", systemImage: "checkmark.circle")
                        .scaledFont(size: 12)
                        .foregroundColor(tasksFound > 0 ? .green : .secondary)

                    Label("\(totalSearches) searches", systemImage: "magnifyingglass")
                        .scaledFont(size: 12)
                        .foregroundColor(totalSearches > 0 ? .blue : .secondary)

                    if errorsCount > 0 {
                        Label("\(errorsCount) errors", systemImage: "exclamationmark.triangle")
                            .scaledFont(size: 12)
                            .foregroundColor(.orange)
                    }

                    if elapsedTime > 0 {
                        Label(String(format: "%.1fs total", elapsedTime), systemImage: "clock")
                            .scaledFont(size: 12)
                            .foregroundColor(.secondary)
                    }
                }
            } else {
                Text("Select a time range and click Run Test")
                    .scaledFont(size: 12)
                    .foregroundColor(.secondary.opacity(0.7))
            }

            Spacer()

            Button("Done") {
                onClose?()
            }
            .keyboardShortcut(.return, modifiers: .command)
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
        }
    }

    // MARK: - Test Execution

    private func runTest() {
        log("TaskTestRunner: runTest() called")
        isRunning = true
        results = []
        progress = 0
        elapsedTime = 0
        totalContextSwitches = 0
        cancellationRequested = false
        statusMessage = "Finding context switches..."

        Task {
            log("TaskTestRunner: Starting test task")
            let startTime = Date()
            let periodStart = periodFrom
            let now = periodTo

            // Get TaskAssistant from coordinator
            log("TaskTestRunner: Looking up task-extraction assistant")
            let assistant = await MainActor.run(body: {
                AssistantCoordinator.shared.assistant(withIdentifier: "task-extraction")
            })
            log("TaskTestRunner: Assistant lookup result: \(assistant != nil ? "found" : "nil")")

            guard let taskAssistant = assistant as? TaskAssistant else {
                log("TaskTestRunner: ERROR - Task Assistant not available or wrong type")
                await MainActor.run {
                    statusMessage = "Task Assistant not available"
                    isRunning = false
                }
                return
            }
            log("TaskTestRunner: Task Assistant successfully retrieved")

            // Build filter parameters from current settings
            let (allowedApps, browserApps, browserPatterns) = await MainActor.run { () -> (Set<String>, Set<String>, [String]) in
                let settings = TaskAssistantSettings.shared
                return (settings.allowedApps, TaskAssistantSettings.browserApps, settings.browserKeywords)
            }
            log("TaskTestRunner: allowedApps = \(allowedApps)")
            log("TaskTestRunner: browserApps = \(browserApps)")
            log("TaskTestRunner: browserPatterns count = \(browserPatterns.count)")

            // Fetch all filtered screenshots chronologically from selected range
            log("TaskTestRunner: Fetching screenshots from \(periodStart) to \(now) with filters")
            let allScreenshots: [Screenshot]
            do {
                allScreenshots = try await RewindDatabase.shared.getScreenshotsFiltered(
                    from: periodStart,
                    to: now,
                    allowedApps: allowedApps,
                    browserApps: browserApps,
                    browserWindowPatterns: browserPatterns,
                    limit: 100_000
                ).reversed()  // getScreenshotsFiltered returns desc, we want chronological
            } catch {
                log("TaskTestRunner: ERROR - Failed to load screenshots: \(error)")
                await MainActor.run {
                    statusMessage = "Failed to load screenshots: \(error.localizedDescription)"
                    isRunning = false
                }
                return
            }

            log("TaskTestRunner: Loaded \(allScreenshots.count) screenshots from selected range")

            guard allScreenshots.count >= 2 else {
                log("TaskTestRunner: ERROR - Not enough screenshots (\(allScreenshots.count) < 2)")
                await MainActor.run {
                    statusMessage = "Not enough screenshots in selected range to detect context switches"
                    isRunning = false
                }
                return
            }

            // Walk through chronologically and find departing frames at context switches
            var departingFrames: [Screenshot] = []
            for i in 0..<(allScreenshots.count - 1) {
                let current = allScreenshots[i]
                let next = allScreenshots[i + 1]

                if ContextDetection.didContextChange(
                    fromApp: current.appName,
                    fromWindowTitle: current.windowTitle,
                    toApp: next.appName,
                    toWindowTitle: next.windowTitle
                ) {
                    departingFrames.append(current)
                }
            }

            guard !departingFrames.isEmpty else {
                await MainActor.run {
                    statusMessage = "No context switches found in \(allScreenshots.count) screenshots from selected range"
                    isRunning = false
                }
                return
            }

            let sampled = departingFrames

            await MainActor.run {
                totalContextSwitches = sampled.count
                statusMessage = "Found \(sampled.count) context switches, testing all..."
            }

            // Process each departing frame
            for (i, screenshot) in sampled.enumerated() {
                if cancellationRequested { break }

                await MainActor.run {
                    statusMessage = "Processing \(i + 1)/\(sampled.count)..."
                }

                do {
                    // Load JPEG from video chunk
                    let jpegData = try await RewindStorage.shared.loadScreenshotData(for: screenshot)

                    // Run extraction pipeline
                    let analyzeStart = Date()
                    let (result, searchCount) = try await taskAssistant.testAnalyze(jpegData: jpegData, appName: screenshot.appName)
                    let duration = Date().timeIntervalSince(analyzeStart)

                    await MainActor.run {
                        results.append(TaskTestResult(
                            index: i + 1,
                            timestamp: screenshot.timestamp,
                            appName: screenshot.appName,
                            windowTitle: screenshot.windowTitle,
                            result: result,
                            error: nil,
                            duration: duration,
                            searchCount: searchCount
                        ))
                        progress = Double(i + 1) / Double(sampled.count)
                    }
                } catch {
                    await MainActor.run {
                        results.append(TaskTestResult(
                            index: i + 1,
                            timestamp: screenshot.timestamp,
                            appName: screenshot.appName,
                            windowTitle: screenshot.windowTitle,
                            result: nil,
                            error: error.localizedDescription,
                            duration: 0,
                            searchCount: 0
                        ))
                        progress = Double(i + 1) / Double(sampled.count)
                    }
                }
            }

            let totalElapsed = Date().timeIntervalSince(startTime)
            await MainActor.run {
                elapsedTime = totalElapsed
                statusMessage = cancellationRequested ? "Stopped" : "Complete"
                isRunning = false
            }
        }
    }
}

// MARK: - NSWindow Subclass

class TaskTestRunnerWindow: NSWindow {
    private static var sharedWindow: TaskTestRunnerWindow?

    static func show() {
        if let existingWindow = sharedWindow {
            existingWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let window = TaskTestRunnerWindow()
        sharedWindow = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    static func close() {
        sharedWindow?.close()
        sharedWindow = nil
    }

    private init() {
        let contentRect = NSRect(x: 0, y: 0, width: 1400, height: 900)

        super.init(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )

        self.title = "Task Extraction Test Runner"
        self.isReleasedWhenClosed = false
        self.delegate = self
        self.minSize = NSSize(width: 900, height: 600)
        self.center()

        let runnerView = TaskTestRunnerView(onClose: { [weak self] in
            self?.close()
        })

        let hostingView = NSHostingView(rootView: runnerView)
        self.contentView = hostingView
    }
}

// MARK: - NSWindowDelegate

extension TaskTestRunnerWindow: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        TaskTestRunnerWindow.sharedWindow = nil
    }
}
