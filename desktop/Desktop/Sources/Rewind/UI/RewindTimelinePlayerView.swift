import SwiftUI

/// A full-screen timeline player view with playback controls
/// Similar to screenpipe's timeline view - shows the current frame with a timeline slider
struct RewindTimelinePlayerView: View {
    @StateObject private var viewModel: TimelinePlayerViewModel
    @Environment(\.dismiss) private var dismiss

    init(screenshots: [Screenshot], initialIndex: Int = 0) {
        _viewModel = StateObject(wrappedValue: TimelinePlayerViewModel(
            screenshots: screenshots,
            initialIndex: initialIndex
        ))
    }

    var body: some View {
        ZStack {
            // Background
            Color.black.ignoresSafeArea()

            // Main content
            VStack(spacing: 0) {
                // Top bar with close button and info
                topBar

                // Current frame display
                Spacer()
                frameDisplay
                Spacer()

                // Timeline and controls at bottom
                VStack(spacing: 12) {
                    // Timeline slider
                    timelineSlider

                    // Playback controls
                    playbackControls

                    // Time and app info
                    frameInfo
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 24)
                .background(
                    LinearGradient(
                        colors: [.clear, .black.opacity(0.8)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(height: 200)
                    .offset(y: -50)
                )
            }
        }
        .onKeyPress(.escape) {
            dismiss()
            return .handled
        }
        .onKeyPress(.space) {
            viewModel.togglePlayback()
            return .handled
        }
        .onKeyPress(.leftArrow) {
            viewModel.previousFrame()
            return .handled
        }
        .onKeyPress(.rightArrow) {
            viewModel.nextFrame()
            return .handled
        }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack {
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(width: 32, height: 32)
                    .background(Color.white.opacity(0.2))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)

            Spacer()

            // Screenshot count
            Text("\(viewModel.currentIndex + 1) / \(viewModel.screenshots.count)")
                .font(.system(size: 14, weight: .medium, design: .monospaced))
                .foregroundColor(.white.opacity(0.8))

            Spacer()

            // Playback speed
            Menu {
                ForEach([0.5, 1.0, 2.0, 4.0, 8.0], id: \.self) { speed in
                    Button {
                        viewModel.playbackSpeed = speed
                    } label: {
                        HStack {
                            Text("\(speed, specifier: "%.1f")x")
                            if viewModel.playbackSpeed == speed {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "speedometer")
                    Text("\(viewModel.playbackSpeed, specifier: "%.1f")x")
                }
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.white.opacity(0.8))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.white.opacity(0.2))
                .cornerRadius(8)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 20)
        .padding(.top, 16)
    }

    // MARK: - Frame Display

    private var frameDisplay: some View {
        Group {
            if viewModel.isLoading {
                ProgressView()
                    .progressViewStyle(.circular)
                    .scaleEffect(1.5)
                    .tint(.white)
            } else if let image = viewModel.currentImage {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .cornerRadius(8)
                    .shadow(color: .black.opacity(0.5), radius: 20)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "photo")
                        .font(.system(size: 48))
                        .foregroundColor(.white.opacity(0.5))
                    Text("Failed to load frame")
                        .font(.system(size: 14))
                        .foregroundColor(.white.opacity(0.5))
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 40)
    }

    // MARK: - Timeline Slider

    private var timelineSlider: some View {
        VStack(spacing: 8) {
            // App activity visualization
            GeometryReader { geometry in
                HStack(spacing: 1) {
                    ForEach(Array(viewModel.appSegments.enumerated()), id: \.offset) { index, segment in
                        Rectangle()
                            .fill(segment.color)
                            .frame(width: max(2, geometry.size.width * segment.widthRatio))
                            .opacity(isInCurrentSegment(index) ? 1.0 : 0.6)
                    }
                }
            }
            .frame(height: 8)
            .cornerRadius(4)

            // Slider
            Slider(
                value: Binding(
                    get: { Double(viewModel.currentIndex) },
                    set: { viewModel.seekToIndex(Int($0)) }
                ),
                in: 0...Double(max(0, viewModel.screenshots.count - 1)),
                step: 1
            )
            .tint(OmiColors.purplePrimary)
        }
    }

    private func isInCurrentSegment(_ segmentIndex: Int) -> Bool {
        var startIndex = 0
        for (index, segment) in viewModel.appSegments.enumerated() {
            let endIndex = startIndex + segment.count - 1
            if index == segmentIndex {
                return viewModel.currentIndex >= startIndex && viewModel.currentIndex <= endIndex
            }
            startIndex = endIndex + 1
        }
        return false
    }

    // MARK: - Playback Controls

    private var playbackControls: some View {
        HStack(spacing: 24) {
            // Skip to start
            Button {
                viewModel.seekToIndex(0)
            } label: {
                Image(systemName: "backward.end.fill")
                    .font(.system(size: 20))
                    .foregroundColor(.white)
            }
            .buttonStyle(.plain)
            .disabled(viewModel.currentIndex == 0)
            .opacity(viewModel.currentIndex == 0 ? 0.5 : 1.0)

            // Previous frame
            Button {
                viewModel.previousFrame()
            } label: {
                Image(systemName: "backward.frame.fill")
                    .font(.system(size: 24))
                    .foregroundColor(.white)
            }
            .buttonStyle(.plain)
            .disabled(viewModel.currentIndex == 0)
            .opacity(viewModel.currentIndex == 0 ? 0.5 : 1.0)

            // Play/Pause
            Button {
                viewModel.togglePlayback()
            } label: {
                Image(systemName: viewModel.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 32))
                    .foregroundColor(OmiColors.textPrimary)
                    .frame(width: 64, height: 64)
                    .background(Color.white)
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)

            // Next frame
            Button {
                viewModel.nextFrame()
            } label: {
                Image(systemName: "forward.frame.fill")
                    .font(.system(size: 24))
                    .foregroundColor(.white)
            }
            .buttonStyle(.plain)
            .disabled(viewModel.currentIndex >= viewModel.screenshots.count - 1)
            .opacity(viewModel.currentIndex >= viewModel.screenshots.count - 1 ? 0.5 : 1.0)

            // Skip to end
            Button {
                viewModel.seekToIndex(viewModel.screenshots.count - 1)
            } label: {
                Image(systemName: "forward.end.fill")
                    .font(.system(size: 20))
                    .foregroundColor(.white)
            }
            .buttonStyle(.plain)
            .disabled(viewModel.currentIndex >= viewModel.screenshots.count - 1)
            .opacity(viewModel.currentIndex >= viewModel.screenshots.count - 1 ? 0.5 : 1.0)
        }
    }

    // MARK: - Frame Info

    private var frameInfo: some View {
        HStack {
            if let screenshot = viewModel.currentScreenshot {
                // App icon and name
                HStack(spacing: 8) {
                    AppIconView(appName: screenshot.appName, size: 20)
                    Text(screenshot.appName)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.white)
                }

                Spacer()

                // Timestamp
                Text(screenshot.formattedDate)
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundColor(.white.opacity(0.8))
            }
        }
    }
}

// MARK: - View Model

@MainActor
class TimelinePlayerViewModel: ObservableObject {
    let screenshots: [Screenshot]

    @Published var currentIndex: Int
    @Published var currentImage: NSImage?
    @Published var isLoading = false
    @Published var isPlaying = false
    @Published var playbackSpeed: Double = 1.0

    private var playbackTimer: Timer?

    // App segments for timeline visualization
    struct AppSegment {
        let appName: String
        let color: Color
        let count: Int
        let widthRatio: CGFloat
    }

    var appSegments: [AppSegment] {
        guard !screenshots.isEmpty else { return [] }

        var segments: [AppSegment] = []
        var currentApp = screenshots.first!.appName
        var currentCount = 0

        for screenshot in screenshots {
            if screenshot.appName == currentApp {
                currentCount += 1
            } else {
                segments.append(AppSegment(
                    appName: currentApp,
                    color: colorForApp(currentApp),
                    count: currentCount,
                    widthRatio: CGFloat(currentCount) / CGFloat(screenshots.count)
                ))
                currentApp = screenshot.appName
                currentCount = 1
            }
        }

        // Add final segment
        segments.append(AppSegment(
            appName: currentApp,
            color: colorForApp(currentApp),
            count: currentCount,
            widthRatio: CGFloat(currentCount) / CGFloat(screenshots.count)
        ))

        return segments
    }

    var currentScreenshot: Screenshot? {
        guard currentIndex >= 0 && currentIndex < screenshots.count else { return nil }
        return screenshots[currentIndex]
    }

    init(screenshots: [Screenshot], initialIndex: Int) {
        self.screenshots = screenshots
        self.currentIndex = min(initialIndex, screenshots.count - 1)

        Task {
            await loadCurrentFrameOrFindValid()
        }
    }

    /// Load the current frame, or if it fails, find the first valid frame
    func loadCurrentFrameOrFindValid() async {
        guard !screenshots.isEmpty else { return }

        isLoading = true

        // Try to load current frame
        if let image = await tryLoadFrame(at: currentIndex) {
            currentImage = image
            isLoading = false
            return
        }

        // Current frame failed - search for first valid frame
        // Search forward first, then backward
        for offset in 1..<screenshots.count {
            // Try forward
            let forwardIndex = currentIndex + offset
            if forwardIndex < screenshots.count {
                if let image = await tryLoadFrame(at: forwardIndex) {
                    currentIndex = forwardIndex
                    currentImage = image
                    isLoading = false
                    log("TimelinePlayer: Skipped to valid frame at index \(forwardIndex)")
                    return
                }
            }

            // Try backward
            let backwardIndex = currentIndex - offset
            if backwardIndex >= 0 {
                if let image = await tryLoadFrame(at: backwardIndex) {
                    currentIndex = backwardIndex
                    currentImage = image
                    isLoading = false
                    log("TimelinePlayer: Skipped to valid frame at index \(backwardIndex)")
                    return
                }
            }
        }

        // No valid frames found
        currentImage = nil
        isLoading = false
        logError("TimelinePlayer: No valid frames found in timeline")
    }

    /// Try to load a frame at a specific index, returns nil if failed
    private func tryLoadFrame(at index: Int) async -> NSImage? {
        guard index >= 0 && index < screenshots.count else { return nil }
        let screenshot = screenshots[index]

        do {
            return try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
        } catch {
            // Don't log errors during search - only log when we find a valid frame or give up
            return nil
        }
    }

    func loadCurrentFrame() async {
        guard let screenshot = currentScreenshot else { return }

        isLoading = true

        do {
            let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
            currentImage = image
        } catch {
            logError("TimelinePlayer: Failed to load frame: \(error)")
            currentImage = nil
        }

        isLoading = false
    }

    func seekToIndex(_ index: Int) {
        let newIndex = max(0, min(index, screenshots.count - 1))
        guard newIndex != currentIndex else { return }

        currentIndex = newIndex
        Task {
            await loadCurrentFrame()
        }
    }

    func nextFrame() {
        seekToIndex(currentIndex + 1)
    }

    func previousFrame() {
        seekToIndex(currentIndex - 1)
    }

    func togglePlayback() {
        if isPlaying {
            stopPlayback()
        } else {
            startPlayback()
        }
    }

    func startPlayback() {
        guard !isPlaying else { return }
        isPlaying = true

        // Calculate interval based on speed (base is 1 second per frame at 1x)
        let interval = 1.0 / playbackSpeed

        playbackTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self = self else { return }

                if self.currentIndex < self.screenshots.count - 1 {
                    self.nextFrame()
                } else {
                    // Reached end, stop playback
                    self.stopPlayback()
                }
            }
        }
    }

    func stopPlayback() {
        isPlaying = false
        playbackTimer?.invalidate()
        playbackTimer = nil
    }

    private func colorForApp(_ appName: String) -> Color {
        // Generate a consistent color for each app
        let hash = appName.hashValue
        let hue = Double(abs(hash) % 360) / 360.0
        return Color(hue: hue, saturation: 0.6, brightness: 0.8)
    }
}

#Preview {
    RewindTimelinePlayerView(screenshots: [], initialIndex: 0)
        .frame(width: 1200, height: 800)
}
