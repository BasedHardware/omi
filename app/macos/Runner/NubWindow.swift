import Cocoa
import QuartzCore

// MARK: - Nub State

enum NubState {
    case upcomingMeeting(title: String, minutesUntil: Int, platform: String)
    case meetingStarted(title: String, platform: String)
    case microphoneActive(platform: String)
    case recording(title: String?, platform: String)
}

class NubWindow: NSPanel {

    // MARK: - Constants
    static let NUB_WIDTH: CGFloat = 400
    static let NUB_HEIGHT: CGFloat = 74
    static let PADDING: CGFloat = 16
    static let BUTTON_WIDTH: CGFloat = 140
    static let AUTO_DISMISS_DURATION: TimeInterval = 15.0

    // Offset for the main pill content to allow close button to hang off the left
    static let CONTENT_X_OFFSET: CGFloat = 20.0

    // MARK: - Properties
    private var containerView: NSView!
    private var pillView: PillShapeView!
    private var titleLabel: NSTextField!
    private var appLabel: NSTextField!
    private var actionButton: NSButton!
    private var closeButton: NSButton!
    private var appIconView: NSImageView!
    private var progressBar: ProgressBarView!
    private var meetingApp: String = "Meeting"
    private var dismissTimer: Timer?
    private var progressUpdateTimer: Timer?
    private var startTime: Date?
    private var pausedElapsedTime: TimeInterval = 0
    private var currentState: NubState?
    private var snoozeButton: NSButton?

    // MARK: - Initialization

    override init(contentRect: NSRect, styleMask style: NSWindow.StyleMask, backing backingStoreType: NSWindow.BackingStoreType, defer flag: Bool) {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: Self.NUB_WIDTH, height: Self.NUB_HEIGHT),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        setupWindow()
        setupContentView()
        positionWindow()
    }

    // MARK: - Setup

    private func setupWindow() {
        // Window behavior
        self.isOpaque = false
        self.backgroundColor = .clear
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        self.hidesOnDeactivate = false
        self.hasShadow = true
        self.isMovable = false
        self.styleMask.insert(.fullSizeContentView)
        self.ignoresMouseEvents = false
        self.alphaValue = 1.0

        // Make visible on all workspaces
        self.setIsVisible(false)
        self.isReleasedWhenClosed = false

    }

    private func setupContentView() {
        // Create container view with shadow
        containerView = NSView(frame: NSRect(x: 0, y: 0, width: Self.NUB_WIDTH, height: Self.NUB_HEIGHT))
        containerView.wantsLayer = true
        containerView.layer?.backgroundColor = NSColor.clear.cgColor

        // Add shadow to container
        containerView.layer?.shadowColor = NSColor.black.cgColor
        containerView.layer?.shadowOpacity = 0.3
        containerView.layer?.shadowOffset = CGSize(width: 0, height: -2)
        containerView.layer?.shadowRadius = 8

        // Shifted right by CONTENT_X_OFFSET to make room for close button
        let visualEffectView = NSVisualEffectView(frame: NSRect(x: Self.CONTENT_X_OFFSET, y: 8, width: 380, height: 54))
        visualEffectView.material = .menu
        visualEffectView.blendingMode = .withinWindow
        visualEffectView.state = .active
        visualEffectView.wantsLayer = true
        visualEffectView.layer?.cornerRadius = 18
        visualEffectView.layer?.masksToBounds = true

        // Add subtle border for glass effect
        visualEffectView.layer?.borderWidth = 0.5
        visualEffectView.layer?.borderColor = NSColor.white.withAlphaComponent(0.15).cgColor

        // Create pill view container that sits on top of visual effect
        pillView = PillShapeView(frame: visualEffectView.bounds)
        pillView.wantsLayer = true
        pillView.layer?.backgroundColor = NSColor.clear.cgColor

        visualEffectView.addSubview(pillView)

        // Create Omi logo icon
        appIconView = NSImageView(frame: NSRect(x: Self.PADDING, y: 11, width: 32, height: 32))
        appIconView.wantsLayer = true

        // Use the same Omi logo as the menu bar
        if let customIcon = NSImage(named: "app_launcher_icon") {
            customIcon.size = NSSize(width: 32, height: 32)
            appIconView.image = customIcon
            appIconView.contentTintColor = .white
        } else {
            // Fallback to microphone icon if custom icon fails to load
            let config = NSImage.SymbolConfiguration(pointSize: 20, weight: .medium)
            appIconView.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Omi")?.withSymbolConfiguration(config)
            appIconView.contentTintColor = .white
        }


        // Create "Meeting detected" label
        titleLabel = NSTextField(labelWithString: "Meeting detected")
        titleLabel.frame = NSRect(x: 60, y: 28, width: 140, height: 18)
        titleLabel.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        titleLabel.textColor = NSColor.white
        titleLabel.alignment = .left

        // Create app name label (e.g., "Zoom")
        appLabel = NSTextField(labelWithString: meetingApp)
        appLabel.frame = NSRect(x: 60, y: 12, width: 140, height: 16)
        appLabel.font = NSFont.systemFont(ofSize: 11, weight: .regular)
        appLabel.textColor = NSColor.white.withAlphaComponent(0.7)
        appLabel.alignment = .left

        // Create "Start Recording" button
        // Note: Button position is relative to pillView, so it stays correct
        actionButton = NSButton(frame: NSRect(x: 380 - Self.BUTTON_WIDTH - Self.PADDING, y: 11, width: Self.BUTTON_WIDTH, height: 32))
        actionButton.title = "Start Recording"
        actionButton.bezelStyle = .rounded
        actionButton.wantsLayer = true
        actionButton.layer?.backgroundColor = NSColor(red: 0x8B/255.0, green: 0x5C/255.0, blue: 0xF6/255.0, alpha: 1.0).cgColor
        actionButton.layer?.cornerRadius = 16
        actionButton.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        actionButton.contentTintColor = .white
        actionButton.isBordered = false
        actionButton.target = self
        actionButton.action = #selector(startRecordingClicked)
        
        // Style the button text
        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.alignment = .center
        let attributes: [NSAttributedString.Key: Any] = [
            .foregroundColor: NSColor.white,
            .font: NSFont.systemFont(ofSize: 12, weight: .semibold),
            .paragraphStyle: paragraphStyle
        ]
        actionButton.attributedTitle = NSAttributedString(string: "Start Recording", attributes: attributes)

        // Add hover effect for button
        let buttonTrackingArea = NSTrackingArea(
            rect: actionButton.bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: ["element": "button"]
        )
        actionButton.addTrackingArea(buttonTrackingArea)

        // Create progress bar at the bottom (inside the pill view, so relative to pillView)
        progressBar = ProgressBarView(frame: NSRect(x: 0, y: 0, width: 380, height: 3), cornerRadius: 18)

        // Add all views to pill
        pillView.addSubview(appIconView)
        pillView.addSubview(titleLabel)
        pillView.addSubview(appLabel)
        pillView.addSubview(actionButton)
        pillView.addSubview(progressBar)

        // Add visual effect view to container
        containerView.addSubview(visualEffectView)
        
        // --- Close Button Setup ---
        // Positioned relative to container. 
        // Pill starts at x=20. We want button at x=10 (overlapping left edge by 10px).
        closeButton = NSButton(frame: NSRect(x: 10, y: 45, width: 24, height: 24))
        closeButton.bezelStyle = .circular
        closeButton.isBordered = false
        closeButton.wantsLayer = true
        closeButton.layer?.backgroundColor = NSColor.white.cgColor
        closeButton.layer?.cornerRadius = 12
        closeButton.layer?.shadowColor = NSColor.black.cgColor
        closeButton.layer?.shadowOpacity = 0.2
        closeButton.layer?.shadowOffset = CGSize(width: 0, height: -1)
        closeButton.layer?.shadowRadius = 2
        
        let closeConfig = NSImage.SymbolConfiguration(pointSize: 10, weight: .bold)
        closeButton.image = NSImage(systemSymbolName: "xmark", accessibilityDescription: "Close")?.withSymbolConfiguration(closeConfig)
        closeButton.contentTintColor = .black
        closeButton.target = self
        closeButton.action = #selector(closeClicked)
        closeButton.alphaValue = 0.0
        
        containerView.addSubview(closeButton)
        
        // Tracking area for the entire container to show/hide close button
        let containerTrackingArea = NSTrackingArea(
            rect: containerView.bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: ["element": "container"]
        )
        containerView.addTrackingArea(containerTrackingArea)

        self.contentView = containerView

    }

    // MARK: - Positioning

    func positionWindow() {
        guard let screen = NSScreen.main else { return }

        let screenFrame = screen.visibleFrame
        let x = screenFrame.maxX - Self.NUB_WIDTH - 20  // 20px from right edge
        let y = screenFrame.maxY - Self.NUB_HEIGHT - 20  // 20px from top of screen

        self.setFrameOrigin(NSPoint(x: x, y: y))
    }

    // MARK: - Public Methods

    func show() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { 
                return 
            }
            
            // Position off-screen to the right
            guard let screen = NSScreen.main else { 
                return 
            }
            
            let screenFrame = screen.visibleFrame
            
            let finalX = screenFrame.maxX - Self.NUB_WIDTH - 20
            let finalY = screenFrame.maxY - Self.NUB_HEIGHT - 20
            
            // Position directly at final location
            self.setFrameOrigin(NSPoint(x: finalX, y: finalY))
            self.alphaValue = 1.0
            self.isOpaque = false
            self.orderFrontRegardless()
            self.orderFront(nil)
            
            // Start timer immediately
            self.startAutoDismissTimer()
        }
    }

    func hide() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.cancelTimers()
            self.orderOut(nil)
            self.setIsVisible(false)
        }
    }
    
    // MARK: - Auto-dismiss Timer

    private func startAutoDismissTimer(reset: Bool = true) {
        // Cancel any existing timers without resetting pausedElapsedTime
        dismissTimer?.invalidate()
        dismissTimer = nil
        progressUpdateTimer?.invalidate()
        progressUpdateTimer = nil

        // Only reset if explicitly requested (starting fresh, not resuming)
        if reset {
            pausedElapsedTime = 0
            progressBar.setProgress(0.0)
        }

        startTime = Date()

        // Update progress every 0.1 seconds
        progressUpdateTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let startTime = self.startTime else { return }

            let elapsed = self.pausedElapsedTime + Date().timeIntervalSince(startTime)
            let progress = min(elapsed / Self.AUTO_DISMISS_DURATION, 1.0)

            DispatchQueue.main.async {
                self.progressBar.setProgress(progress)
            }
        }

        // Dismiss after specified duration
        let remainingTime = Self.AUTO_DISMISS_DURATION - pausedElapsedTime
        dismissTimer = Timer.scheduledTimer(withTimeInterval: remainingTime, repeats: false) { [weak self] _ in
            self?.hide()
        }
    }

    private func pauseTimers() {
        // Store elapsed time before pausing
        if let startTime = startTime {
            pausedElapsedTime += Date().timeIntervalSince(startTime)
        }

        // Invalidate timers but don't reset elapsed time
        dismissTimer?.invalidate()
        dismissTimer = nil
        progressUpdateTimer?.invalidate()
        progressUpdateTimer = nil
        startTime = nil
    }

    private func cancelTimers() {
        dismissTimer?.invalidate()
        dismissTimer = nil
        progressUpdateTimer?.invalidate()
        progressUpdateTimer = nil
        startTime = nil
        pausedElapsedTime = 0
    }

    // MARK: - Mouse Events

    override func mouseEntered(with event: NSEvent) {
        guard let userInfo = event.trackingArea?.userInfo,
              let element = userInfo["element"] as? String else {
            return
        }
        
        if element == "button" {
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = 0.15
                self.actionButton.animator().layer?.backgroundColor = NSColor(red: 0x8B/255.0, green: 0x5C/255.0, blue: 0xF6/255.0, alpha: 0.85).cgColor
                self.actionButton.animator().layer?.transform = CATransform3DMakeScale(1.02, 1.02, 1.0)
            })
        } else if element == "container" {
            // Show close button
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = 0.2
                self.closeButton.animator().alphaValue = 1.0
            })

            // Pause auto-dismiss when hovering (preserves elapsed time)
            pauseTimers()
        }
    }

    override func mouseExited(with event: NSEvent) {
        guard let userInfo = event.trackingArea?.userInfo,
              let element = userInfo["element"] as? String else {
            return
        }
        
        if element == "button" {
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = 0.15
                self.actionButton.animator().layer?.backgroundColor = NSColor(red: 0x8B/255.0, green: 0x5C/255.0, blue: 0xF6/255.0, alpha: 1.0).cgColor
                self.actionButton.animator().layer?.transform = CATransform3DIdentity
            })
        } else if element == "container" {
            // Hide close button
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = 0.2
                self.closeButton.animator().alphaValue = 0.0
            })

            // Resume auto-dismiss when leaving (continues from where it paused)
            startAutoDismissTimer(reset: false)
        }
    }

    @objc private func startRecordingClicked() {
        cancelTimers() // Stop auto-dismiss when user interacts

        // Hide immediately when clicked
        self.hide()

        // Post notification after hiding to start recording
        NotificationCenter.default.post(name: .nubClicked, object: nil, userInfo: nil)
    }
    
    @objc private func closeClicked() {
        self.hide()
    }
    
    // MARK: - Public Update Methods

    func updateMeetingApp(_ appName: String) {
        self.meetingApp = appName
        DispatchQueue.main.async { [weak self] in
            self?.appLabel.stringValue = appName
        }
    }

    /// Update nub with new state (calendar or mic-based)
    func updateState(_ state: NubState) {
        self.currentState = state

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }

            switch state {
            case .upcomingMeeting(let title, let minutesUntil, let platform):
                // Update for upcoming meeting (calendar-based) - just a reminder, no action button
                self.titleLabel.stringValue = truncateTitle(title, maxLength: 30)
                self.appLabel.stringValue = "in \(minutesUntil) min • \(platform)"
                self.actionButton.isHidden = true
                self.updateIcon(for: platform, isUpcoming: true)

            case .meetingStarted(let title, let platform):
                // Update for meeting that just started - show "Start Recording" button
                self.titleLabel.stringValue = truncateTitle(title, maxLength: 30)
                self.appLabel.stringValue = "started • \(platform)"
                self.actionButton.isHidden = false
                self.actionButton.title = "Start Recording"
                self.updateButtonAttributes(title: "Start Recording")
                self.updateIcon(for: platform, isUpcoming: false)

            case .microphoneActive(let platform):
                // Update for mic-only detection (existing behavior)
                self.titleLabel.stringValue = "Meeting detected"
                self.appLabel.stringValue = platform
                self.actionButton.isHidden = false
                self.actionButton.title = "Start Recording"
                self.updateButtonAttributes(title: "Start Recording")
                self.updateIcon(for: platform, isUpcoming: false)

            case .recording(let title, let platform):
                // Update for active recording (calendar + mic)
                if let meetingTitle = title {
                    self.titleLabel.stringValue = truncateTitle(meetingTitle, maxLength: 30)
                } else {
                    self.titleLabel.stringValue = "Recording"
                }
                self.appLabel.stringValue = platform
                self.actionButton.isHidden = false
                self.actionButton.title = "Stop Recording"
                self.updateButtonAttributes(title: "Stop Recording")
                self.updateIcon(for: platform, isUpcoming: false)
            }
        }
    }

    private func truncateTitle(_ title: String, maxLength: Int) -> String {
        if title.count > maxLength {
            return String(title.prefix(maxLength - 3)) + "..."
        }
        return title
    }

    private func updateButtonAttributes(title: String) {
        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.alignment = .center
        let attributes: [NSAttributedString.Key: Any] = [
            .foregroundColor: NSColor.white,
            .font: NSFont.systemFont(ofSize: 12, weight: .semibold),
            .paragraphStyle: paragraphStyle
        ]
        self.actionButton.attributedTitle = NSAttributedString(string: title, attributes: attributes)
    }

    private func updateIcon(for platform: String, isUpcoming: Bool) {
        // For upcoming meetings, show clock icon
        if isUpcoming {
            let config = NSImage.SymbolConfiguration(pointSize: 20, weight: .medium)
            appIconView.image = NSImage(systemSymbolName: "clock.fill", accessibilityDescription: "Upcoming")?.withSymbolConfiguration(config)
            appIconView.contentTintColor = .systemOrange
            return
        }

        // Otherwise use Omi logo (existing behavior)
        if let customIcon = NSImage(named: "app_launcher_icon") {
            customIcon.size = NSSize(width: 32, height: 32)
            appIconView.image = customIcon
            appIconView.contentTintColor = .white
        } else {
            let config = NSImage.SymbolConfiguration(pointSize: 20, weight: .medium)
            appIconView.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Omi")?.withSymbolConfiguration(config)
            appIconView.contentTintColor = .white
        }
    }
}

// MARK: - PillShapeView

class PillShapeView: NSView {
    override var wantsUpdateLayer: Bool { return true }

    override func mouseDown(with event: NSEvent) {
        // Allow click events to pass through to gesture recognizer
        super.mouseDown(with: event)
    }
}

// MARK: - RecordingIndicator

class RecordingIndicator: NSView {

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        self.wantsLayer = true
        self.layer?.backgroundColor = NSColor.systemRed.cgColor
        self.layer?.cornerRadius = frameRect.width / 2
        startPulsing()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func startPulsing() {
        let animation = CABasicAnimation(keyPath: "opacity")
        animation.fromValue = 1.0
        animation.toValue = 0.3
        animation.duration = 1.0
        animation.autoreverses = true
        animation.repeatCount = .infinity
        self.layer?.add(animation, forKey: "pulse")
    }
}

// MARK: - ProgressBarView

class ProgressBarView: NSView {
    private var progressLayer: CALayer!

    init(frame frameRect: NSRect, cornerRadius: CGFloat) {
        super.init(frame: frameRect)
        self.wantsLayer = true

        // Background (empty state) - semi-transparent
        self.layer?.backgroundColor = NSColor.white.withAlphaComponent(0.05).cgColor

        // Progress layer (fills from left to right)
        progressLayer = CALayer()
        progressLayer.backgroundColor = NSColor(red: 0x8B/255.0, green: 0x5C/255.0, blue: 0xF6/255.0, alpha: 0.9).cgColor
        progressLayer.frame = CGRect(x: 0, y: 0, width: 0, height: frameRect.height)
        progressLayer.cornerRadius = cornerRadius
        progressLayer.maskedCorners = [.layerMinXMinYCorner, .layerMinXMaxYCorner] // Only left corners

        self.layer?.addSublayer(progressLayer)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func setProgress(_ progress: Double) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)

        let width = self.bounds.width * CGFloat(progress)
        progressLayer.frame = CGRect(x: 0, y: 0, width: width, height: self.bounds.height)

        if progress >= 1.0 {
            progressLayer.maskedCorners = [.layerMinXMinYCorner, .layerMinXMaxYCorner, .layerMaxXMinYCorner, .layerMaxXMaxYCorner]
        } else {
            progressLayer.maskedCorners = [.layerMinXMinYCorner, .layerMinXMaxYCorner] // Only left corners
        }

        CATransaction.commit()
    }
}

// MARK: - Notification Extension

extension Notification.Name {
    static let nubClicked = Notification.Name("com.omi.nub.clicked")
}
