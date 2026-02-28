import Cocoa
import SwiftUI

// MARK: - Test Result Model

struct AdviceTestResult: Identifiable {
    let id = UUID()
    let index: Int
    let timestamp: Date
    let appName: String
    let windowTitle: String?
    let result: AdviceExtractionResult?
    let error: String?
    let duration: TimeInterval
    let sqlQueryCount: Int
}

// MARK: - SwiftUI View

struct AdviceTestRunnerView: View {
    @State private var periodFrom: Date = Calendar.current.date(byAdding: .hour, value: -24, to: Date()) ?? Date()
    @State private var periodTo: Date = Date()
    @State private var isRunning = false
    @State private var results: [AdviceTestResult] = []
    @State private var progress: Double = 0
    @State private var elapsedTime: TimeInterval = 0
    @State private var statusMessage = "Ready"
    @State private var cancellationRequested = false
    @State private var totalScreenshots = 0

    var onClose: (() -> Void)?

    private var adviceFound: Int {
        results.filter { $0.result?.hasAdvice == true }.count
    }

    private var errorsCount: Int {
        results.filter { $0.error != nil }.count
    }

    private var totalSqlQueries: Int {
        results.reduce(0) { $0 + $1.sqlQueryCount }
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
                    Text("Advice Extraction Test Runner")
                        .scaledFont(size: 16, weight: .semibold)
                        .foregroundColor(.primary)

                    Text("Replay screenshots through the agentic advice pipeline (activity summary + SQL investigation + advice)")
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
                .frame(width: 200, alignment: .leading)
            Text("Decision")
                .frame(width: 100, alignment: .leading)
            Text("SQL")
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

    private func resultRow(_ testResult: AdviceTestResult) -> some View {
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
                .frame(width: 200, alignment: .leading)
                .lineLimit(1)

            // Decision column
            decisionBadge(for: testResult)
                .frame(width: 100, alignment: .leading)

            // SQL query count indicator
            if testResult.sqlQueryCount > 0 {
                HStack(spacing: 2) {
                    Image(systemName: "cylinder")
                        .scaledFont(size: 9)
                    Text("×\(testResult.sqlQueryCount)")
                        .scaledFont(size: 11, design: .monospaced)
                }
                .foregroundColor(.secondary)
                .frame(width: 40, alignment: .leading)
            } else {
                Text("")
                    .frame(width: 40)
            }

            // Advice text or context summary
            if let error = testResult.error {
                Text(error)
                    .scaledFont(size: 12)
                    .foregroundColor(.orange)
                    .lineLimit(2)
            } else if let result = testResult.result {
                if result.hasAdvice, let advice = result.advice {
                    VStack(alignment: .leading, spacing: 2) {
                        if let headline = advice.headline {
                            Text(headline)
                                .scaledFont(size: 12, weight: .medium)
                                .foregroundColor(.primary)
                                .lineLimit(1)
                        }
                        Text(advice.advice)
                            .scaledFont(size: 11)
                            .foregroundColor(.primary.opacity(0.8))
                            .lineLimit(2)
                        HStack(spacing: 8) {
                            Text(advice.category.rawValue)
                                .scaledFont(size: 10, weight: .medium)
                                .foregroundColor(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 1)
                                .background(categoryColor(advice.category))
                                .cornerRadius(3)
                            Text(advice.sourceApp)
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

            // Confidence (only for advice)
            if let result = testResult.result, result.hasAdvice, let advice = result.advice {
                Text("\(Int(advice.confidence * 100))%")
                    .scaledFont(size: 12, weight: .medium, design: .monospaced)
                    .foregroundColor(confidenceColor(advice.confidence))
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
        .background(testResult.result?.hasAdvice == true ? Color.green.opacity(0.05) : Color.clear)
    }

    private func decisionBadge(for testResult: AdviceTestResult) -> some View {
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
                if result.hasAdvice {
                    HStack(spacing: 4) {
                        Image(systemName: "lightbulb.fill")
                            .scaledFont(size: 10)
                        Text("Advice")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(.green)
                } else {
                    HStack(spacing: 4) {
                        Image(systemName: "minus.circle")
                            .scaledFont(size: 10)
                        Text("No Advice")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(.secondary)
                }
            }
        }
    }

    private func categoryColor(_ category: AdviceCategory) -> Color {
        switch category {
        case .productivity: return .blue
        case .communication: return .purple
        case .learning: return .orange
        case .health: return .green
        case .other: return .gray
        }
    }

    private func confidenceColor(_ confidence: Double) -> Color {
        if confidence >= 0.9 { return .green }
        if confidence >= 0.75 { return .yellow }
        return .orange
    }

    // MARK: - Footer

    private var footer: some View {
        HStack {
            if !results.isEmpty {
                HStack(spacing: 16) {
                    Label("\(results.count)/\(totalScreenshots)", systemImage: "photo")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)

                    Label("\(adviceFound) advice", systemImage: "lightbulb")
                        .scaledFont(size: 12)
                        .foregroundColor(adviceFound > 0 ? .green : .secondary)

                    Label("\(totalSqlQueries) SQL queries", systemImage: "cylinder")
                        .scaledFont(size: 12)
                        .foregroundColor(totalSqlQueries > 0 ? .blue : .secondary)

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
        log("AdviceTestRunner: runTest() called")
        isRunning = true
        results = []
        progress = 0
        elapsedTime = 0
        totalScreenshots = 0
        cancellationRequested = false
        statusMessage = "Loading screenshots..."

        Task {
            let startTime = Date()
            let periodStart = periodFrom
            let periodEnd = periodTo

            // Get AdviceAssistant from coordinator
            let assistant = await MainActor.run(body: {
                AssistantCoordinator.shared.assistant(withIdentifier: "advice")
            })

            guard let adviceAssistant = assistant as? AdviceAssistant else {
                log("AdviceTestRunner: ERROR - Advice Assistant not available")
                await MainActor.run {
                    statusMessage = "Advice Assistant not available"
                    isRunning = false
                }
                return
            }

            // Get excluded apps
            let excludedApps = await MainActor.run {
                AdviceAssistantSettings.shared.excludedApps
            }

            // Fetch all screenshots from selected range (excluding excluded apps)
            let allScreenshots: [Screenshot]
            do {
                allScreenshots = try await RewindDatabase.shared.getScreenshots(
                    from: periodStart,
                    to: periodEnd,
                    limit: 100_000
                ).reversed() // getScreenshots returns desc, we want chronological
            } catch {
                log("AdviceTestRunner: ERROR - Failed to load screenshots: \(error)")
                await MainActor.run {
                    statusMessage = "Failed to load screenshots: \(error.localizedDescription)"
                    isRunning = false
                }
                return
            }

            // Filter out excluded apps and apps with no name
            let filtered = allScreenshots.filter { screenshot in
                !screenshot.appName.isEmpty
                    && !TaskAssistantSettings.builtInExcludedApps.contains(screenshot.appName)
                    && !excludedApps.contains(screenshot.appName)
            }

            guard !filtered.isEmpty else {
                await MainActor.run {
                    statusMessage = "No screenshots found in selected range (after excluding apps)"
                    isRunning = false
                }
                return
            }

            // Sample evenly: pick up to 50 screenshots spread across the range
            let maxSamples = 50
            let sampled: [Screenshot]
            if filtered.count <= maxSamples {
                sampled = filtered
            } else {
                let step = Double(filtered.count) / Double(maxSamples)
                sampled = (0..<maxSamples).map { i in
                    filtered[min(Int(Double(i) * step), filtered.count - 1)]
                }
            }

            await MainActor.run {
                totalScreenshots = sampled.count
                statusMessage = "Testing \(sampled.count) screenshots (sampled from \(filtered.count))..."
            }

            // Process each sampled screenshot
            for (i, screenshot) in sampled.enumerated() {
                if cancellationRequested { break }

                await MainActor.run {
                    statusMessage = "Processing \(i + 1)/\(sampled.count) — \(screenshot.appName)..."
                }

                do {
                    let jpegData = try await RewindStorage.shared.loadScreenshotData(for: screenshot)

                    let analyzeStart = Date()
                    let (result, sqlCount) = try await adviceAssistant.testAnalyze(
                        jpegData: jpegData,
                        appName: screenshot.appName,
                        windowTitle: screenshot.windowTitle,
                        screenshotTime: screenshot.timestamp
                    )
                    let duration = Date().timeIntervalSince(analyzeStart)

                    await MainActor.run {
                        results.append(AdviceTestResult(
                            index: i + 1,
                            timestamp: screenshot.timestamp,
                            appName: screenshot.appName,
                            windowTitle: screenshot.windowTitle,
                            result: result,
                            error: nil,
                            duration: duration,
                            sqlQueryCount: sqlCount
                        ))
                        progress = Double(i + 1) / Double(sampled.count)
                    }
                } catch {
                    await MainActor.run {
                        results.append(AdviceTestResult(
                            index: i + 1,
                            timestamp: screenshot.timestamp,
                            appName: screenshot.appName,
                            windowTitle: screenshot.windowTitle,
                            result: nil,
                            error: error.localizedDescription,
                            duration: 0,
                            sqlQueryCount: 0
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

class AdviceTestRunnerWindow: NSWindow {
    private static var sharedWindow: AdviceTestRunnerWindow?

    static func show() {
        if let existingWindow = sharedWindow {
            existingWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let window = AdviceTestRunnerWindow()
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

        self.title = "Advice Extraction Test Runner"
        self.isReleasedWhenClosed = false
        self.delegate = self
        self.minSize = NSSize(width: 900, height: 600)
        self.center()

        let runnerView = AdviceTestRunnerView(onClose: { [weak self] in
            self?.close()
        })

        let hostingView = NSHostingView(rootView: runnerView)
        self.contentView = hostingView
    }
}

// MARK: - NSWindowDelegate

extension AdviceTestRunnerWindow: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        AdviceTestRunnerWindow.sharedWindow = nil
    }
}
