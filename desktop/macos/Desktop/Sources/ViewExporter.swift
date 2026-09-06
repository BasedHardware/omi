import AppKit
import ObjCExceptionCatcher
import OmiTheme
import SwiftUI

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
    return args.contains("--export-views") || args.contains("--export-single")
      || args.contains("--export-fullpages") || args.contains("--export-fullpage-single")
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
      (
        "01-sign-in",
        { AnyView(SignInView(authState: AuthState.shared)) },
        CGSize(width: 900, height: 600)
      ),

      (
        "04-conversations",
        { AnyView(ConversationsPage(appState: AppState(), selectedConversation: .constant(nil))) },
        CGSize(width: 900, height: 700)
      ),

      (
        "07-rewind",
        { AnyView(RewindPage()) },
        CGSize(width: 1000, height: 700)
      ),

      (
        "08-apps",
        { AnyView(AppsPage(appProvider: AppProvider())) },
        CGSize(width: 900, height: 700)
      ),

      (
        "09-permissions",
        { AnyView(PermissionsPage(appState: AppState())) },
        CGSize(width: 900, height: 700)
      ),

      (
        "11-desktop-home",
        { AnyView(DesktopHomeView().environmentObject(AppState())) },
        CGSize(width: 1200, height: 800)
      ),

      (
        "14-chat-sessions",
        { AnyView(ChatSessionsSidebar(chatProvider: ChatProvider())) },
        CGSize(width: 250, height: 500)
      ),

      (
        "15-settings",
        {
          AnyView(
            SettingsPage(
              appState: AppState(), selectedSection: .constant(.general),
              highlightedSettingId: .constant(nil)))
        },
        CGSize(width: 900, height: 700)
      ),

      (
        "16-memory-atlas",
        { MemoryAtlasExportPreview.surface() },
        CGSize(width: 1200, height: 820)
      ),

      (
        "17-memory-atlas-single-type",
        { MemoryAtlasExportPreview.singleTypeSurface() },
        CGSize(width: 1200, height: 820)
      ),

      (
        "18-brain-map-inspector",
        { MemoryAtlasExportPreview.inspectorSurface() },
        CGSize(width: 1400, height: 820)
      ),

      (
        "19-brain-map-connection",
        { MemoryAtlasExportPreview.connectionInspectorSurface() },
        CGSize(width: 1400, height: 820)
      ),
    ]

    guard index >= 0 && index < views.count else { return nil }
    let entry = views[index]
    return (entry.0, entry.1(), entry.2)
  }

  /// Must equal the number of entries in the `standaloneViewAt` registry above;
  /// `runBatch` iterates `0..<count`, so a mismatch spawns failing "unknown-N" exports.
  static var standaloneViewCount: Int { 14 }

  // MARK: - Full page registry (sidebar + content)

  /// Lightweight sidebar mock that uses only SF Symbols (no bundle resources needed)
  private struct ExportSidebarMock: View {
    let selectedIndex: Int

    private let items: [(String, String, Int)] = [
      ("Home", "house.fill", 0),
      ("Conversations", "text.bubble.fill", 1),
      ("Chat", "bubble.left.and.bubble.right.fill", 2),
      ("Memories", "brain", 3),
      ("Tasks", "checklist", 4),
      ("Advice", "lightbulb.fill", 6),
      ("Rewind", "clock.arrow.circlepath", 7),
      ("Apps", "puzzlepiece.fill", 8),
    ]

    private let bottomItems: [(String, String, Int)] = [
      ("Settings", "gearshape.fill", 9)
    ]

    var body: some View {
      VStack(alignment: .leading, spacing: 0) {
        // Logo placeholder
        HStack {
          Circle()
            .fill(Ink.primary.opacity(0.9))
            .frame(width: 28, height: 28)
            .overlay(Text("O").font(.system(size: 14, weight: .bold)).foregroundColor(.black))
          Text("Omi")
            .font(.system(size: 18, weight: .semibold))
            .foregroundColor(.white)
          Spacer()
        }
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.top, OmiSpacing.xl)
        .padding(.bottom, OmiSpacing.lg)

        // Main nav items
        ForEach(items, id: \.2) { item in
          sidebarRow(title: item.0, icon: item.1, index: item.2)
        }

        Spacer()

        Divider()
          .background(Ink.rowFillHover)
          .padding(.horizontal, OmiSpacing.md)

        // Bottom items
        ForEach(bottomItems, id: \.2) { item in
          sidebarRow(title: item.0, icon: item.1, index: item.2)
        }
        .padding(.bottom, OmiSpacing.md)
      }
      .frame(width: 220)
      .background(Color(nsColor: NSColor(red: 0.07, green: 0.07, blue: 0.07, alpha: 1)))
    }

    private func sidebarRow(title: String, icon: String, index: Int) -> some View {
      let isSelected = index == selectedIndex
      return HStack(spacing: OmiSpacing.sm) {
        Image(systemName: icon)
          .font(.system(size: 14))
          .foregroundColor(isSelected ? .white : .white.opacity(0.5))
          .frame(width: 20)
        Text(title)
          .font(.system(size: 13))
          .foregroundColor(isSelected ? .white : .white.opacity(0.5))
        Spacer()
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isSelected ? Ink.rowFillHover : Color.clear)
          .padding(.horizontal, OmiSpacing.sm)
      )
    }
  }

  static func fullPageViewAt(_ index: Int) -> (String, AnyView, CGSize)? {
    // Pages that can be shown with the sidebar
    let pages: [(String, Int, () -> AnyView)] = [
      (
        "full-conversations", 1,
        {
          AnyView(
            ConversationsPage(
              appState: previewConversationsAppState(),
              selectedConversation: .constant(nil)
            ))
        }
      ),
      (
        "full-memories", 3,
        {
          AnyView(
            MemoriesPage(viewModel: previewMemoriesViewModel())
          )
        }
      ),
      (
        "full-tasks", 4,
        {
          let cp = ChatProvider()
          return AnyView(
            TasksPage(
              viewModel: TasksViewModel(), chatCoordinator: TaskChatCoordinator(chatProvider: cp),
              chatProvider: cp))
        }
      ),
      ("full-rewind", 7, { AnyView(RewindPage()) }),
      ("full-apps", 8, { AnyView(AppsPage(appProvider: AppProvider())) }),
      (
        "full-settings", 9,
        {
          AnyView(
            SettingsPage(
              appState: AppState(), selectedSection: .constant(.general),
              highlightedSettingId: .constant(nil)))
        }
      ),
      ("full-permissions", 10, { AnyView(PermissionsPage(appState: AppState())) }),
    ]

    guard index >= 0 && index < pages.count else { return nil }
    let entry = pages[index]
    let pageContent = entry.2()

    let topBarAppState = AppState()
    let topBarMemories = previewMemoriesViewModel()
    let topBarTasks = TasksStore.shared

    // Compose with the production top bar and rounded shell.
    let fullView = AnyView(
      ZStack {
        RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
          .fill(Color(red: 0.050, green: 0.052, blue: 0.059))
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
              .stroke(Ink.separator, lineWidth: 1)
          )

        VStack(spacing: 0) {
          DesktopTopBar(
            selectedIndex: .constant(entry.1),
            memoryDestinationRawValue: .constant(MemoryHubDestination.memories.rawValue),
            appState: topBarAppState,
            memoriesViewModel: topBarMemories,
            tasksStore: topBarTasks,
            sinceDate: Date()
          )
          pageContent
        }
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous))
      }
      .padding(OmiSpacing.md)
    )

    return (entry.0, fullView, CGSize(width: 1600, height: 1000))
  }

  static var fullPageCount: Int { 11 }

  private static func previewConversationsAppState() -> AppState {
    let appState = AppState()
    let now = Date()
    let previews = [
      (
        "Product design review",
        "We reviewed the desktop Memory experience and agreed to remove the nested navigation, widen the content, and make search behavior consistent.",
        "✨"
      ),
      (
        "Launch readiness check",
        "The team covered beta health, release notes, and the final desktop smoke test before the next rollout.",
        "🚀"
      ),
      (
        "Weekly planning",
        "Priorities this week are onboarding polish, a cleaner conversation reader, and fewer competing controls in the header.",
        "🗓"
      ),
      (
        "Customer feedback",
        "Customers want transcripts to be easier to scan and Memory to feel like one coherent place instead of three separate tools.",
        "💬"
      ),
      (
        "Engineering sync",
        "The search services now share the same debounce and cancellation policy while preserving each page's data source.",
        "🛠"
      ),
      (
        "Design system cleanup",
        "We aligned search fields, filter pills, radii, and loading states around the existing Omi neutral palette.",
        "◐"
      ),
    ]

    appState.conversations = previews.enumerated().map { index, preview in
      let createdAt = now.addingTimeInterval(Double(-index * 3_600))
      return ServerConversation(
        id: "conversation_preview_\(index)",
        createdAt: createdAt,
        startedAt: createdAt,
        finishedAt: createdAt.addingTimeInterval(2_700),
        structured: Structured(
          title: preview.0,
          overview: preview.1,
          emoji: preview.2,
          category: "other",
          actionItems: [],
          events: []
        ),
        transcriptSegments: [],
        transcriptSegmentsIncluded: true,
        geolocation: nil,
        photos: [],
        appsResults: [],
        source: .desktop,
        language: "en",
        status: .completed,
        discarded: false,
        deleted: false,
        isLocked: false,
        starred: index == 0,
        folderId: nil,
        inputDeviceName: "MacBook Pro Microphone"
      )
    }
    return appState
  }

  private static func previewChatProvider() -> ChatProvider {
    let provider = ChatProvider()
    provider.isLoading = false
    provider.messages = [
      ChatMessage(
        text: "Summarize what I should do about the launch checklist and keep it tight.",
        createdAt: Date().addingTimeInterval(-420),
        sender: .user
      ),
      ChatMessage(
        text:
          "You should lock the hero copy, verify pricing copy, and do one final desktop smoke test before sending the build.",
        createdAt: Date().addingTimeInterval(-360),
        sender: .ai
      ),
      ChatMessage(
        text: "Also flag anything that still looks too dense in Memories.",
        createdAt: Date().addingTimeInterval(-240),
        sender: .user
      ),
      ChatMessage(
        text:
          "Memories needs the most restraint: fewer borders, more breathing room, and softer chips so the content reads first.",
        createdAt: Date().addingTimeInterval(-180),
        sender: .ai
      ),
    ]
    return provider
  }

  private static func previewMemoriesViewModel() -> MemoriesViewModel {
    let viewModel = MemoriesViewModel()
    let now = Date()
    viewModel.memories = [
      ServerMemory(
        id: "memory_preview_1",
        content:
          "Nik prefers brutally concise launch updates with concrete status, blockers, and next steps.",
        category: .manual,
        createdAt: now.addingTimeInterval(-90),
        updatedAt: now.addingTimeInterval(-90),
        conversationId: nil,
        reviewed: true,
        userReview: true,
        visibility: "private",
        manuallyAdded: true,
        scoring: nil,
        source: "manual",
        confidence: 0.98,
        sourceApp: "Omi Desktop",
        contextSummary: "Founder preferences captured from direct instruction.",
        isRead: false,
        isDismissed: false,
        tags: ["manual"],
        reasoning: nil,
        currentActivity: "Refining the desktop app UI",
        inputDeviceName: nil,
        windowTitle: "macOS polish notes",
        headline: nil
      ),
      ServerMemory(
        id: "memory_preview_2",
        content:
          "Dashboard widgets should feel like roomy cards, not admin panels: larger radii, fewer strokes, stronger spacing.",
        category: .interesting,
        createdAt: now.addingTimeInterval(-3600),
        updatedAt: now.addingTimeInterval(-3600),
        conversationId: "conversation_preview_dashboard",
        reviewed: false,
        userReview: nil,
        visibility: "private",
        manuallyAdded: false,
        scoring: nil,
        source: "conversation",
        confidence: 0.92,
        sourceApp: "Design Review",
        contextSummary: "Notes from comparing the new macOS build to the old Flutter app.",
        isRead: true,
        isDismissed: false,
        tags: ["interesting", "productivity"],
        reasoning: "Repeated design feedback emphasized spacing and chrome over feature changes.",
        currentActivity: "Reviewing home surfaces",
        inputDeviceName: "MacBook Pro Microphone",
        windowTitle: "Home",
        headline: nil
      ),
      ServerMemory(
        id: "memory_preview_3",
        content:
          "Tip: keep memory rows mostly borderless and let hover depth do the work instead of outlining every card.",
        category: .system,
        createdAt: now.addingTimeInterval(-7200),
        updatedAt: now.addingTimeInterval(-7200),
        conversationId: "conversation_preview_memories",
        reviewed: false,
        userReview: nil,
        visibility: "private",
        manuallyAdded: false,
        scoring: nil,
        source: "advice",
        confidence: 0.89,
        sourceApp: "Omi Assistant",
        contextSummary: "Extracted from the desktop UI polish pass.",
        isRead: false,
        isDismissed: false,
        tags: ["tips", "productivity"],
        reasoning: "Dense outlines competed with content and made the list feel cheaper.",
        currentActivity: "Polishing memory cards",
        inputDeviceName: nil,
        windowTitle: "Memories",
        headline: "Less chrome, more content"
      ),
    ]
    return viewModel
  }

  // MARK: - Run

  static func run() {
    let args = CommandLine.arguments

    // Single standalone view mode
    if let idx = args.firstIndex(of: "--export-single"),
      idx + 1 < args.count,
      let viewIndex = Int(args[idx + 1])
    {
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
      let viewIndex = Int(args[idx + 1])
    {
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
      runBatch(
        mode: "standalone",
        count: standaloneViewCount,
        flag: "--export-single",
        dir: dir,
        viewNameAt: { standaloneViewAt($0)?.0 ?? "unknown-\($0)" }
      )
    }

    // Batch full pages
    if args.contains("--export-fullpages") {
      let dir = outputDir()
      try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
      runBatch(
        mode: "fullpage",
        count: fullPageCount,
        flag: "--export-fullpage-single",
        dir: dir,
        viewNameAt: { fullPageViewAt($0)?.0 ?? "unknown-\($0)" }
      )
    }

    exit(0)
  }

  private static func runBatch(
    mode: String,
    count: Int,
    flag: String,
    dir: String,
    viewNameAt: (Int) -> String
  ) {
    NSLog("ViewExporter: Exporting \(count) \(mode) views to \(dir)")

    let executablePath = CommandLine.arguments[0]
    var exportedCount = 0
    var failedCount = 0
    var crashedViews: [String] = []

    for i in 0..<count {
      let viewName = viewNameAt(i)
      NSLog("ViewExporter: [\(i+1)/\(count)] Spawning subprocess for \(viewName)...")

      let process = Process()
      process.executableURL = URL(fileURLWithPath: executablePath)
      process.arguments = [flag, "\(i)", dir]
      process.environment = ProcessInfo.processInfo.environment
      process.standardError = Pipe()
      process.standardOutput = FileHandle.nullDevice

      do {
        try process.run()
        process.waitUntilExit()

        if process.terminationStatus == 0 {
          NSLog("ViewExporter: [\(i+1)/\(count)] \(viewName) OK")
          exportedCount += 1
        } else {
          NSLog(
            "ViewExporter: [\(i+1)/\(count)] \(viewName) FAILED (exit \(process.terminationStatus))"
          )
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
    // Light: the app's glass is pinned `.aqua`, so a dark export is a picture of a product that no
    // longer exists.
    .environment(\.colorScheme, .light)

    let hostingView = NSHostingView(rootView: wrappedView)
    hostingView.setFrameSize(size)

    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: size),
      styleMask: [.borderless],
      backing: .buffered,
      defer: false
    )
    window.contentView = hostingView
    window.backgroundColor = Ink.nsSurface

    hostingView.needsLayout = true
    hostingView.layoutSubtreeIfNeeded()

    var success = false
    let exception = ObjCExceptionCatcher.catching {
      // Export PNG
      guard let bitmapRep = hostingView.bitmapImageRepForCachingDisplay(in: hostingView.bounds)
      else {
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
    if let exception {
      NSLog("ViewExporter: SKIP \(name) - \(exception.name.rawValue): \(exception.reason ?? "unknown")")
      success = false
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
