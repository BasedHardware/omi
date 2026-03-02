import Cocoa
import SwiftUI

// MARK: - Test Result Model

struct FocusTestResult: Identifiable {
    let id = UUID()
    let index: Int
    let timestamp: Date
    let appName: String
    let windowTitle: String?
    let result: ScreenAnalysis?
    let error: String?
    let duration: TimeInterval
}

// MARK: - SwiftUI View

struct FocusTestRunnerView: View {
    @State private var periodFrom: Date = Calendar.current.date(byAdding: .hour, value: -24, to: Date()) ?? Date()
    @State private var periodTo: Date = Date()
    @State private var isRunning = false
    @State private var results: [FocusTestResult] = []
    @State private var progress: Double = 0
    @State private var elapsedTime: TimeInterval = 0
    @State private var statusMessage = "Ready"
    @State private var cancellationRequested = false
    @State private var totalContextSwitches = 0

    var onClose: (() -> Void)?

    private var focusedCount: Int {
        results.filter { $0.result?.status == .focused }.count
    }

    private var distractedCount: Int {
        results.filter { $0.result?.status == .distracted }.count
    }

    private var errorsCount: Int {
        results.filter { $0.error != nil }.count
    }

    private var distractionPercent: Int {
        let decided = focusedCount + distractedCount
        guard decided > 0 else { return 0 }
        return Int(round(Double(distractedCount) / Double(decided) * 100))
    }

    var body: some View {
        VStack(spacing: 0) {
            header
                .padding(20)
            Divider()
            columnHeaders
                .padding(.horizontal, 20)
                .padding(.vertical, 6)
                .background(Color(nsColor: .windowBackgroundColor))
            Divider()
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
                    Text("Focus Analysis Test Runner")
                        .scaledFont(size: 16, weight: .semibold)
                        .foregroundColor(.primary)

                    Text("Replay departing frames from context switches through the focus analysis pipeline")
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
                .frame(width: 200, alignment: .leading)
            Text("Status")
                .frame(width: 100, alignment: .leading)
            Text("Description")
                .frame(width: 300, alignment: .leading)
            Text("Message")
            Spacer()
            Text("Time")
                .frame(width: 50, alignment: .trailing)
        }
        .scaledFont(size: 11, weight: .medium)
        .foregroundColor(.secondary.opacity(0.7))
    }

    // MARK: - Result Row

    private func resultRow(_ testResult: FocusTestResult) -> some View {
        HStack(spacing: 16) {
            Text("\(testResult.index)")
                .scaledFont(size: 12, design: .monospaced)
                .foregroundColor(.secondary)
                .frame(width: 28, alignment: .trailing)

            Text(testResult.timestamp, format: .dateTime.hour().minute().second())
                .scaledFont(size: 12, design: .monospaced)
                .foregroundColor(.secondary)
                .frame(width: 90, alignment: .leading)

            Text(testResult.appName)
                .scaledFont(size: 12)
                .foregroundColor(.secondary)
                .frame(width: 100, alignment: .leading)
                .lineLimit(1)

            Text(testResult.windowTitle ?? "—")
                .scaledFont(size: 12)
                .foregroundColor(.secondary)
                .frame(width: 200, alignment: .leading)
                .lineLimit(1)

            statusBadge(for: testResult)
                .frame(width: 100, alignment: .leading)

            // Description
            if let error = testResult.error {
                Text(error)
                    .scaledFont(size: 12)
                    .foregroundColor(.orange)
                    .frame(width: 300, alignment: .leading)
                    .lineLimit(2)
            } else if let result = testResult.result {
                Text(result.description)
                    .scaledFont(size: 12)
                    .foregroundColor(.secondary)
                    .frame(width: 300, alignment: .leading)
                    .lineLimit(2)
            } else {
                Text("")
                    .frame(width: 300)
            }

            // Message
            if let result = testResult.result, let message = result.message {
                Text(message)
                    .scaledFont(size: 12)
                    .foregroundColor(.primary.opacity(0.8))
                    .lineLimit(2)
            } else if testResult.error == nil {
                Text("—")
                    .scaledFont(size: 12)
                    .foregroundColor(.secondary.opacity(0.5))
            }

            Spacer()

            Text(String(format: "%.1fs", testResult.duration))
                .scaledFont(size: 12, design: .monospaced)
                .foregroundColor(.secondary.opacity(0.7))
                .frame(width: 50, alignment: .trailing)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 8)
        .background(rowBackground(for: testResult))
    }

    private func statusBadge(for testResult: FocusTestResult) -> some View {
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
                switch result.status {
                case .focused:
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark.circle.fill")
                            .scaledFont(size: 10)
                        Text("Focused")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(.green)
                case .distracted:
                    HStack(spacing: 4) {
                        Image(systemName: "exclamationmark.circle.fill")
                            .scaledFont(size: 10)
                        Text("Distracted")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(.red)
                }
            }
        }
    }

    private func rowBackground(for testResult: FocusTestResult) -> Color {
        guard let result = testResult.result else { return .clear }
        switch result.status {
        case .focused: return Color.green.opacity(0.05)
        case .distracted: return Color.red.opacity(0.05)
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

                    Label("\(focusedCount) focused", systemImage: "checkmark.circle")
                        .scaledFont(size: 12)
                        .foregroundColor(focusedCount > 0 ? .green : .secondary)

                    Label("\(distractedCount) distracted", systemImage: "exclamationmark.circle")
                        .scaledFont(size: 12)
                        .foregroundColor(distractedCount > 0 ? .red : .secondary)

                    Label("\(distractionPercent)%", systemImage: "chart.pie")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)

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
        log("FocusTestRunner: runTest() called")
        isRunning = true
        results = []
        progress = 0
        elapsedTime = 0
        totalContextSwitches = 0
        cancellationRequested = false
        statusMessage = "Finding context switches..."

        Task {
            let startTime = Date()
            let periodStart = periodFrom
            let periodEnd = periodTo

            // Get FocusAssistant from coordinator
            let assistant = await MainActor.run(body: {
                AssistantCoordinator.shared.assistant(withIdentifier: "focus")
            })

            guard let focusAssistant = assistant as? FocusAssistant else {
                log("FocusTestRunner: ERROR - Focus Assistant not available or wrong type")
                await MainActor.run {
                    statusMessage = "Focus Assistant not available"
                    isRunning = false
                }
                return
            }

            // Get excluded apps
            let excludedApps = await MainActor.run {
                FocusAssistantSettings.shared.excludedApps
            }

            // Fetch all screenshots from selected range
            let allScreenshots: [Screenshot]
            do {
                allScreenshots = try await RewindDatabase.shared.getScreenshots(
                    from: periodStart,
                    to: periodEnd,
                    limit: 100_000
                ).reversed() // getScreenshots returns desc, we want chronological
            } catch {
                log("FocusTestRunner: ERROR - Failed to load screenshots: \(error)")
                await MainActor.run {
                    statusMessage = "Failed to load screenshots: \(error.localizedDescription)"
                    isRunning = false
                }
                return
            }

            // Filter out excluded apps and system apps
            let filtered = allScreenshots.filter { screenshot in
                !screenshot.appName.isEmpty
                    && !TaskAssistantSettings.builtInExcludedApps.contains(screenshot.appName)
                    && !excludedApps.contains(screenshot.appName)
            }

            guard filtered.count >= 2 else {
                await MainActor.run {
                    statusMessage = "Not enough screenshots in selected range to detect context switches"
                    isRunning = false
                }
                return
            }

            // Walk chronologically and find departing frames at context switches
            var departingFrames: [Screenshot] = []
            for i in 0..<(filtered.count - 1) {
                let current = filtered[i]
                let next = filtered[i + 1]

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
                    statusMessage = "No context switches found in \(filtered.count) screenshots"
                    isRunning = false
                }
                return
            }

            // Cap at 50 context switches (evenly spaced if more)
            let maxSamples = 50
            let sampled: [Screenshot]
            if departingFrames.count <= maxSamples {
                sampled = departingFrames
            } else {
                let step = Double(departingFrames.count) / Double(maxSamples)
                sampled = (0..<maxSamples).map { i in
                    departingFrames[min(Int(Double(i) * step), departingFrames.count - 1)]
                }
            }

            await MainActor.run {
                totalContextSwitches = departingFrames.count
                statusMessage = "Found \(departingFrames.count) context switches, testing \(sampled.count)..."
            }

            // Process each departing frame
            for (i, screenshot) in sampled.enumerated() {
                if cancellationRequested { break }

                await MainActor.run {
                    statusMessage = "Processing \(i + 1)/\(sampled.count) — \(screenshot.appName)..."
                }

                do {
                    let jpegData = try await RewindStorage.shared.loadScreenshotData(for: screenshot)

                    let analyzeStart = Date()
                    let result = try await focusAssistant.testAnalyze(jpegData: jpegData, appName: screenshot.appName)
                    let duration = Date().timeIntervalSince(analyzeStart)

                    await MainActor.run {
                        results.append(FocusTestResult(
                            index: i + 1,
                            timestamp: screenshot.timestamp,
                            appName: screenshot.appName,
                            windowTitle: screenshot.windowTitle,
                            result: result,
                            error: nil,
                            duration: duration
                        ))
                        progress = Double(i + 1) / Double(sampled.count)
                    }
                } catch {
                    await MainActor.run {
                        results.append(FocusTestResult(
                            index: i + 1,
                            timestamp: screenshot.timestamp,
                            appName: screenshot.appName,
                            windowTitle: screenshot.windowTitle,
                            result: nil,
                            error: error.localizedDescription,
                            duration: 0
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

class FocusTestRunnerWindow: NSWindow {
    private static var sharedWindow: FocusTestRunnerWindow?

    static func show() {
        if let existingWindow = sharedWindow {
            existingWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let window = FocusTestRunnerWindow()
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

        self.title = "Focus Analysis Test Runner"
        self.isReleasedWhenClosed = false
        self.delegate = self
        self.minSize = NSSize(width: 900, height: 600)
        self.center()

        let runnerView = FocusTestRunnerView(onClose: { [weak self] in
            self?.close()
        })

        let hostingView = NSHostingView(rootView: runnerView)
        self.contentView = hostingView
    }
}

// MARK: - NSWindowDelegate

extension FocusTestRunnerWindow: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        FocusTestRunnerWindow.sharedWindow = nil
    }
}

// MARK: - CLI Test Runner (headless, logs to omi-dev.log)

enum FocusTestRunner {

    /// Run the focus test headlessly — triggered by distributed notification from CLI.
    /// Finds context switches in the time range, analyzes departing frames, and logs results.
    static func runCLITest(lookbackHours: Double, maxScreenshots: Int) async {
        let periodEnd = Date()
        let periodStart = periodEnd.addingTimeInterval(-lookbackHours * 3600)

        log("FocusTestCLI: Starting test — range \(periodStart) to \(periodEnd), max \(maxScreenshots) context switches")

        // Get or create FocusAssistant
        let coordAssistant = await MainActor.run {
            AssistantCoordinator.shared.assistant(withIdentifier: "focus")
        }
        let focusAssistant: FocusAssistant
        if let existing = coordAssistant as? FocusAssistant {
            focusAssistant = existing
        } else {
            do {
                focusAssistant = try FocusAssistant()
            } catch {
                log("FocusTestCLI: ERROR — Failed to create FocusAssistant: \(error)")
                return
            }
        }

        // Get excluded apps
        let excludedApps = await MainActor.run {
            FocusAssistantSettings.shared.excludedApps
        }

        // Ensure storage is initialized
        do {
            try await RewindStorage.shared.initialize()
        } catch {
            log("FocusTestCLI: WARNING — Storage init failed: \(error)")
        }

        // Fetch all screenshots from range
        let allScreenshots: [Screenshot]
        do {
            allScreenshots = try await RewindDatabase.shared.getScreenshots(
                from: periodStart,
                to: periodEnd,
                limit: 100_000
            ).reversed()
        } catch {
            log("FocusTestCLI: ERROR — Failed to load screenshots: \(error)")
            return
        }

        // Filter excluded apps
        let filtered = allScreenshots.filter { screenshot in
            !screenshot.appName.isEmpty
                && !TaskAssistantSettings.builtInExcludedApps.contains(screenshot.appName)
                && !excludedApps.contains(screenshot.appName)
        }

        guard filtered.count >= 2 else {
            log("FocusTestCLI: ERROR — Not enough screenshots (\(filtered.count) after filtering)")
            return
        }

        // Find context switches
        var departingFrames: [Screenshot] = []
        for i in 0..<(filtered.count - 1) {
            let current = filtered[i]
            let next = filtered[i + 1]
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
            log("FocusTestCLI: No context switches found in \(filtered.count) screenshots")
            return
        }

        // Sample evenly if too many
        let sampled: [Screenshot]
        if departingFrames.count <= maxScreenshots {
            sampled = departingFrames
        } else {
            let step = Double(departingFrames.count) / Double(maxScreenshots)
            sampled = (0..<maxScreenshots).map { i in
                departingFrames[min(Int(Double(i) * step), departingFrames.count - 1)]
            }
        }

        log("FocusTestCLI: Processing \(sampled.count) context switches (from \(departingFrames.count) total)")

        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "HH:mm:ss"
        var focusedCount = 0
        var distractedCount = 0
        var errorCount = 0
        let testStart = Date()

        for (i, screenshot) in sampled.enumerated() {
            let label = "[\(i + 1)/\(sampled.count)]"
            let time = timeFormatter.string(from: screenshot.timestamp)
            let windowTitle = screenshot.windowTitle ?? "(no title)"

            do {
                let jpegData = try await RewindStorage.shared.loadScreenshotData(for: screenshot)

                let analyzeStart = Date()
                let result = try await focusAssistant.testAnalyze(jpegData: jpegData, appName: screenshot.appName)
                let duration = Date().timeIntervalSince(analyzeStart)

                if let result = result {
                    switch result.status {
                    case .focused:
                        focusedCount += 1
                        log("FocusTestCLI: \(label) \(time) \(screenshot.appName) | \"\(windowTitle)\" → FOCUSED: \(result.description) (\(String(format: "%.1fs", duration)))")
                    case .distracted:
                        distractedCount += 1
                        let msg = result.message.map { " msg=\"\($0)\"" } ?? ""
                        log("FocusTestCLI: \(label) \(time) \(screenshot.appName) | \"\(windowTitle)\" → DISTRACTED: \(result.description)\(msg) (\(String(format: "%.1fs", duration)))")
                    }
                } else {
                    errorCount += 1
                    log("FocusTestCLI: \(label) \(time) \(screenshot.appName) | \"\(windowTitle)\" → nil (\(String(format: "%.1fs", duration)))")
                }
            } catch {
                errorCount += 1
                log("FocusTestCLI: \(label) \(time) \(screenshot.appName) → ERROR: \(error.localizedDescription)")
            }
        }

        let totalTime = Date().timeIntervalSince(testStart)
        let decided = focusedCount + distractedCount
        let distractionPct = decided > 0 ? Int(round(Double(distractedCount) / Double(decided) * 100)) : 0
        log("FocusTestCLI: DONE — \(sampled.count) switches, \(focusedCount) focused, \(distractedCount) distracted (\(distractionPct)%), \(errorCount) errors, \(String(format: "%.1fs", totalTime)) total")
    }
}
