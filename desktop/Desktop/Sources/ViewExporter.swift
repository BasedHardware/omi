import SwiftUI
import AppKit
import ObjCExceptionCatcher

// MARK: - View Exporter
// Run with: --export-views /path/to/output/dir
// Renders each major SwiftUI view to PNG + SVG using NSHostingView
// Each view is exported in a separate subprocess to isolate crashes
//
// Modes:
//   --export-views <dir>              Export all standalone page views
//   --export-fullpages <dir>          Export full pages (sidebar + content)
//   --export-single <index> <dir>     Export a single standalone view (subprocess)
//   --export-fullpage-single <index> <dir>  Export a single full page (subprocess)

@MainActor
enum ViewExporter {

    static func shouldExport() -> Bool {
        let args = CommandLine.arguments
        return args.contains("--export-views") ||
               args.contains("--export-single") ||
               args.contains("--export-fullpages") ||
               args.contains("--export-fullpage-single")
    }

    static func outputDir() -> String {
        let args = CommandLine.arguments
        for flag in ["--export-views", "--export-fullpages"] {
            if let idx = args.firstIndex(of: flag), idx + 1 < args.count {
                return args[idx + 1]
            }
        }
        for flag in ["--export-single", "--export-fullpage-single"] {
            if let idx = args.firstIndex(of: flag), idx + 2 < args.count {
                return args[idx + 2]
            }
        }
        return "/tmp/omi-view-exports"
    }

    // MARK: - Standalone view registry

    static func standaloneViewAt(_ index: Int) -> (String, AnyView, CGSize)? {
        let views: [(String, () -> AnyView, CGSize)] = [
            ("01-sign-in",
             { AnyView(SignInView(authState: AuthState.shared)) },
             CGSize(width: 900, height: 600)),

            ("02-dashboard",
             { AnyView(DashboardPage(viewModel: DashboardViewModel(), appState: AppState(), selectedIndex: .constant(0))) },
             CGSize(width: 900, height: 700)),

            ("03-ai-chat",
             { AnyView(ChatPage(appProvider: AppProvider(), chatProvider: ChatProvider())) },
             CGSize(width: 900, height: 700)),

            ("04-conversations",
             { AnyView(ConversationsPage(appState: AppState(), selectedConversation: .constant(nil))) },
             CGSize(width: 900, height: 700)),

            ("05-focus",
             { AnyView(FocusPage()) },
             CGSize(width: 900, height: 700)),

            ("06-advice",
             { AnyView(AdvicePage()) },
             CGSize(width: 900, height: 700)),

            ("07-rewind",
             { AnyView(RewindPage()) },
             CGSize(width: 1000, height: 700)),

            ("08-apps",
             { AnyView(AppsPage(appProvider: AppProvider())) },
             CGSize(width: 900, height: 700)),

            ("09-permissions",
             { AnyView(PermissionsPage(appState: AppState())) },
             CGSize(width: 900, height: 700)),

            ("10-device-settings",
             { AnyView(DeviceSettingsPage()) },
             CGSize(width: 900, height: 700)),

            ("11-desktop-home",
             { AnyView(DesktopHomeView()) },
             CGSize(width: 1200, height: 800)),

            ("12-onboarding",
             { AnyView(OnboardingView(appState: AppState(), chatProvider: ChatProvider())) },
             CGSize(width: 900, height: 600)),

            ("13-daily-score",
             { AnyView(DailyScoreWidget(dailyScore: nil)) },
             CGSize(width: 400, height: 350)),

            ("14-chat-sessions",
             { AnyView(ChatSessionsSidebar(chatProvider: ChatProvider())) },
             CGSize(width: 250, height: 500)),

            ("15-settings",
             { AnyView(SettingsPage(appState: AppState(), selectedSection: .constant(.general), highlightedSettingId: .constant(nil))) },
             CGSize(width: 900, height: 700)),
        ]

        guard index >= 0 && index < views.count else { return nil }
        let entry = views[index]
        return (entry.0, entry.1(), entry.2)
    }

    static var standaloneViewCount: Int { 15 }

    // MARK: - Full page registry (sidebar + content)

    /// Lightweight sidebar mock that uses only SF Symbols (no bundle resources needed)
    private struct ExportSidebarMock: View {
        let selectedIndex: Int

        private let items: [(String, String, Int)] = [
            ("Dashboard",      "house.fill",                     0),
            ("Conversations",  "text.bubble.fill",               1),
            ("Chat",           "bubble.left.and.bubble.right.fill", 2),
            ("Memories",       "brain",                          3),
            ("Tasks",          "checklist",                      4),
            ("Focus",          "eye.fill",                       5),
            ("Advice",         "lightbulb.fill",                 6),
            ("Rewind",         "clock.arrow.circlepath",         7),
            ("Apps",           "puzzlepiece.fill",               8),
        ]

        private let bottomItems: [(String, String, Int)] = [
            ("Settings",       "gearshape.fill",                 9),
        ]

        var body: some View {
            VStack(alignment: .leading, spacing: 0) {
                // Logo placeholder
                HStack {
                    Circle()
                        .fill(Color.white.opacity(0.9))
                        .frame(width: 28, height: 28)
                        .overlay(Text("O").font(.system(size: 14, weight: .bold)).foregroundColor(.black))
                    Text("Omi")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(.white)
                    Spacer()
                }
                .padding(.horizontal, 16)
                .padding(.top, 20)
                .padding(.bottom, 16)

                // Main nav items
                ForEach(items, id: \.2) { item in
                    sidebarRow(title: item.0, icon: item.1, index: item.2)
                }

                Spacer()

                Divider()
                    .background(Color.white.opacity(0.1))
                    .padding(.horizontal, 12)

                // Bottom items
                ForEach(bottomItems, id: \.2) { item in
                    sidebarRow(title: item.0, icon: item.1, index: item.2)
                }
                .padding(.bottom, 12)
            }
            .frame(width: 220)
            .background(Color(nsColor: NSColor(red: 0.07, green: 0.07, blue: 0.07, alpha: 1)))
        }

        private func sidebarRow(title: String, icon: String, index: Int) -> some View {
            let isSelected = index == selectedIndex
            return HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundColor(isSelected ? .white : .white.opacity(0.5))
                    .frame(width: 20)
                Text(title)
                    .font(.system(size: 13))
                    .foregroundColor(isSelected ? .white : .white.opacity(0.5))
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? Color.white.opacity(0.1) : Color.clear)
                    .padding(.horizontal, 8)
            )
        }
    }

    static func fullPageViewAt(_ index: Int) -> (String, AnyView, CGSize)? {
        // Pages that can be shown with the sidebar
        let pages: [(String, Int, () -> AnyView)] = [
            ("full-dashboard",    0,  { AnyView(DashboardPage(viewModel: DashboardViewModel(), appState: AppState(), selectedIndex: .constant(0))) }),
            ("full-ai-chat",      2,  { AnyView(ChatPage(appProvider: AppProvider(), chatProvider: ChatProvider())) }),
            ("full-memories",     3,  { AnyView(MemoriesPage(viewModel: MemoriesViewModel())) }),
            ("full-tasks",        4,  {
                let cp = ChatProvider()
                return AnyView(TasksPage(viewModel: TasksViewModel(), chatCoordinator: TaskChatCoordinator(chatProvider: cp), chatProvider: cp))
            }),
            ("full-focus",        5,  { AnyView(FocusPage()) }),
            ("full-advice",       6,  { AnyView(AdvicePage()) }),
            ("full-rewind",       7,  { AnyView(RewindPage()) }),
            ("full-apps",         8,  { AnyView(AppsPage(appProvider: AppProvider())) }),
            ("full-settings",     9,  { AnyView(SettingsPage(appState: AppState(), selectedSection: .constant(.general), highlightedSettingId: .constant(nil))) }),
            ("full-permissions",  10, { AnyView(PermissionsPage(appState: AppState())) }),
            ("full-device",       11, { AnyView(DeviceSettingsPage()) }),
        ]

        guard index >= 0 && index < pages.count else { return nil }
        let entry = pages[index]
        let sidebarIndex = entry.1
        let pageContent = entry.2()

        // Compose: mock sidebar + rounded content area (mirrors DesktopHomeView layout)
        let fullView = AnyView(
            HStack(spacing: 0) {
                ExportSidebarMock(selectedIndex: sidebarIndex)

                ZStack {
                    RoundedRectangle(cornerRadius: 16)
                        .fill(Color(nsColor: NSColor(red: 0.09, green: 0.09, blue: 0.09, alpha: 1)).opacity(0.4))
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(Color(nsColor: NSColor(red: 0.15, green: 0.15, blue: 0.15, alpha: 1)).opacity(0.3), lineWidth: 1)
                        )
                    pageContent
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                .padding(12)
            }
        )

        return (entry.0, fullView, CGSize(width: 1200, height: 800))
    }

    static var fullPageCount: Int { 11 }

    // MARK: - Run

    static func run() {
        let args = CommandLine.arguments

        // Single standalone view mode
        if let idx = args.firstIndex(of: "--export-single"),
           idx + 1 < args.count,
           let viewIndex = Int(args[idx + 1]) {
            let dir = outputDir()
            try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
            if let (name, view, size) = standaloneViewAt(viewIndex) {
                NSLog("ViewExporter: [single] Rendering \(name)...")
                let success = exportView(name: name, view: view, size: size, dir: dir)
                exit(success ? 0 : 1)
            }
            exit(1)
        }

        // Single full page mode
        if let idx = args.firstIndex(of: "--export-fullpage-single"),
           idx + 1 < args.count,
           let viewIndex = Int(args[idx + 1]) {
            let dir = outputDir()
            try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
            if let (name, view, size) = fullPageViewAt(viewIndex) {
                NSLog("ViewExporter: [fullpage-single] Rendering \(name)...")
                let success = exportView(name: name, view: view, size: size, dir: dir)
                exit(success ? 0 : 1)
            }
            exit(1)
        }

        // Batch standalone views
        if args.contains("--export-views") {
            let dir = outputDir()
            try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
            runBatch(mode: "standalone", count: standaloneViewCount, flag: "--export-single", dir: dir)
        }

        // Batch full pages
        if args.contains("--export-fullpages") {
            let dir = outputDir()
            try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
            runBatch(mode: "fullpage", count: fullPageCount, flag: "--export-fullpage-single", dir: dir)
        }

        exit(0)
    }

    private static func runBatch(mode: String, count: Int, flag: String, dir: String) {
        NSLog("ViewExporter: Exporting \(count) \(mode) views to \(dir)")

        let executablePath = CommandLine.arguments[0]
        var exportedCount = 0
        var failedCount = 0
        var crashedViews: [String] = []

        for i in 0..<count {
            let viewName: String
            if flag == "--export-single" {
                viewName = standaloneViewAt(i)?.0 ?? "unknown-\(i)"
            } else {
                viewName = fullPageViewAt(i)?.0 ?? "unknown-\(i)"
            }
            NSLog("ViewExporter: [\(i+1)/\(count)] Spawning subprocess for \(viewName)...")

            let process = Process()
            process.executableURL = URL(fileURLWithPath: executablePath)
            process.arguments = [flag, "\(i)", dir]
            process.standardError = Pipe()
            process.standardOutput = FileHandle.nullDevice

            do {
                try process.run()
                process.waitUntilExit()

                if process.terminationStatus == 0 {
                    NSLog("ViewExporter: [\(i+1)/\(count)] \(viewName) OK")
                    exportedCount += 1
                } else {
                    NSLog("ViewExporter: [\(i+1)/\(count)] \(viewName) FAILED (exit \(process.terminationStatus))")
                    failedCount += 1
                    crashedViews.append(viewName)
                }
            } catch {
                NSLog("ViewExporter: [\(i+1)/\(count)] \(viewName) FAILED (\(error.localizedDescription))")
                failedCount += 1
                crashedViews.append(viewName)
            }
        }

        // Convert all PDFs to SVG using pdf2svg
        convertPDFsToSVG(dir: dir)

        NSLog("ViewExporter: \(mode) done! \(exportedCount) exported, \(failedCount) failed -> \(dir)")
        if !crashedViews.isEmpty {
            NSLog("ViewExporter: Crashed: \(crashedViews.joined(separator: ", "))")
        }
    }

    // MARK: - Export single view (PNG + PDF)

    @discardableResult
    private static func exportView(name: String, view: AnyView, size: CGSize, dir: String) -> Bool {
        let wrappedView = ZStack {
            Color(nsColor: NSColor(red: 0.07, green: 0.07, blue: 0.07, alpha: 1))
            view
        }
        .environment(\.colorScheme, .dark)

        let hostingView = NSHostingView(rootView: wrappedView)
        hostingView.setFrameSize(size)

        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.contentView = hostingView
        window.backgroundColor = NSColor(red: 0.07, green: 0.07, blue: 0.07, alpha: 1)

        hostingView.needsLayout = true
        hostingView.layoutSubtreeIfNeeded()

        var success = false
        do {
            try ObjCExceptionCatcher.catching {
                // Export PNG
                guard let bitmapRep = hostingView.bitmapImageRepForCachingDisplay(in: hostingView.bounds) else {
                    NSLog("ViewExporter: SKIP \(name) - no bitmap")
                    return
                }
                hostingView.cacheDisplay(in: hostingView.bounds, to: bitmapRep)

                if let pngData = bitmapRep.representation(using: .png, properties: [:]) {
                    let pngPath = "\(dir)/\(name).png"
                    try? pngData.write(to: URL(fileURLWithPath: pngPath))
                    let kb = pngData.count / 1024
                    NSLog("ViewExporter: \(name).png (\(Int(size.width))x\(Int(size.height))) \(kb)KB")
                }

                // Export PDF (vector data preserved for SVG conversion)
                let pdfData = hostingView.dataWithPDF(inside: hostingView.bounds)
                let pdfPath = "\(dir)/\(name).pdf"
                try? pdfData.write(to: URL(fileURLWithPath: pdfPath))
                NSLog("ViewExporter: \(name).pdf (\(pdfData.count / 1024)KB)")

                success = true
            }
        } catch {
            NSLog("ViewExporter: SKIP \(name) - \(error.localizedDescription)")
        }

        window.orderOut(nil)
        return success
    }

    // MARK: - PDF to SVG conversion

    private static func convertPDFsToSVG(dir: String) {
        let pdf2svgPath = "/opt/homebrew/bin/pdf2svg"
        guard FileManager.default.fileExists(atPath: pdf2svgPath) else {
            NSLog("ViewExporter: pdf2svg not found at \(pdf2svgPath), skipping SVG conversion")
            return
        }

        let fm = FileManager.default
        guard let files = try? fm.contentsOfDirectory(atPath: dir) else { return }
        let pdfFiles = files.filter { $0.hasSuffix(".pdf") }.sorted()

        NSLog("ViewExporter: Converting \(pdfFiles.count) PDFs to SVG...")
        for pdfFile in pdfFiles {
            let svgFile = pdfFile.replacingOccurrences(of: ".pdf", with: ".svg")
            let process = Process()
            process.executableURL = URL(fileURLWithPath: pdf2svgPath)
            process.arguments = ["\(dir)/\(pdfFile)", "\(dir)/\(svgFile)"]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice

            do {
                try process.run()
                process.waitUntilExit()
                if process.terminationStatus == 0 {
                    NSLog("ViewExporter: \(svgFile) OK")
                } else {
                    NSLog("ViewExporter: \(svgFile) FAILED")
                }
            } catch {
                NSLog("ViewExporter: \(svgFile) FAILED (\(error.localizedDescription))")
            }
        }
    }
}
