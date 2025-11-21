import Cocoa
import QuartzCore

class NubWindow: NSPanel {

    // MARK: - Constants
    static let NUB_WIDTH: CGFloat = 500
    static let NUB_HEIGHT: CGFloat = 70
    static let PADDING: CGFloat = 16
    static let BUTTON_WIDTH: CGFloat = 140
    static let AUTO_DISMISS_DURATION: TimeInterval = 15.0

    // MARK: - Properties
    private var containerView: NSView!
    private var pillView: PillShapeView!
    private var recordingIndicator: RecordingIndicator!
    private var titleLabel: NSTextField!
    private var appLabel: NSTextField!
    private var actionButton: NSButton!
    private var appIconView: NSImageView!
    private var progressBar: ProgressBarView!
    private var meetingApp: String = "Meeting"
    private var dismissTimer: Timer?
    private var progressUpdateTimer: Timer?
    private var startTime: Date?

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
        self.level = .floating  // Changed from .statusBar to .floating for better visibility
        self.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        self.hidesOnDeactivate = false
        self.hasShadow = true  // Changed to true for visibility
        self.isMovable = false
        self.styleMask.insert(.fullSizeContentView)
        self.ignoresMouseEvents = false  // Make sure it can receive mouse events
        self.alphaValue = 1.0  // Ensure full opacity

        // Make visible on all workspaces
        self.setIsVisible(false)
        self.isReleasedWhenClosed = false

        print("NubWindow: Window setup complete")
    }

    private func setupContentView() {
        // Create container view with shadow
        containerView = NSView(frame: NSRect(x: 0, y: 0, width: Self.NUB_WIDTH, height: Self.NUB_HEIGHT))
        containerView.wantsLayer = true
        containerView.layer?.backgroundColor = NSColor.clear.cgColor
        
        // Add shadow to container
        containerView.layer?.shadowColor = NSColor.black.cgColor
        containerView.layer?.shadowOpacity = 0.5
        containerView.layer?.shadowOffset = CGSize(width: 0, height: -4)
        containerView.layer?.shadowRadius = 12

        // Create pill-shaped background view (horizontal now)
        pillView = PillShapeView(frame: NSRect(x: 0, y: 8, width: Self.NUB_WIDTH, height: 54))
        pillView.wantsLayer = true
        pillView.layer?.backgroundColor = NSColor(red: 0.1, green: 0.1, blue: 0.1, alpha: 0.95).cgColor
        pillView.layer?.cornerRadius = 18  // Reduced from 27 for less roundness
        pillView.layer?.masksToBounds = true  // Changed to true to clip progress bar properly
        pillView.layer?.shadowColor = NSColor.black.cgColor
        pillView.layer?.shadowOpacity = 0.5
        pillView.layer?.shadowOffset = CGSize(width: 0, height: -2)
        pillView.layer?.shadowRadius = 8

        // Add subtle border
        pillView.layer?.borderWidth = 1.0
        pillView.layer?.borderColor = NSColor.white.withAlphaComponent(0.2).cgColor

        // Create microphone icon
        appIconView = NSImageView(frame: NSRect(x: Self.PADDING, y: 15, width: 24, height: 24))
        appIconView.wantsLayer = true
        
        // Simple microphone symbol
        let config = NSImage.SymbolConfiguration(pointSize: 16, weight: .medium)
        appIconView.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Microphone")?.withSymbolConfiguration(config)
        appIconView.contentTintColor = .white

        // Create recording indicator (red dot next to icon)
        recordingIndicator = RecordingIndicator(frame: NSRect(x: 38, y: 36, width: 8, height: 8))

        // Create "Meeting detected" label
        titleLabel = NSTextField(labelWithString: "Meeting detected")
        titleLabel.frame = NSRect(x: 54, y: 28, width: 140, height: 18)
        titleLabel.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        titleLabel.textColor = NSColor.white
        titleLabel.alignment = .left

        // Create app name label (e.g., "Zoom")
        appLabel = NSTextField(labelWithString: meetingApp)
        appLabel.frame = NSRect(x: 54, y: 12, width: 140, height: 16)
        appLabel.font = NSFont.systemFont(ofSize: 11, weight: .regular)
        appLabel.textColor = NSColor.white.withAlphaComponent(0.7)
        appLabel.alignment = .left

        // Create "Start Recording" button
        actionButton = NSButton(frame: NSRect(x: Self.NUB_WIDTH - Self.BUTTON_WIDTH - Self.PADDING, y: 11, width: Self.BUTTON_WIDTH, height: 32))
        actionButton.title = "Start Recording"
        actionButton.bezelStyle = .rounded
        actionButton.wantsLayer = true
        actionButton.layer?.backgroundColor = NSColor.systemGreen.cgColor
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
        let trackingArea = NSTrackingArea(
            rect: actionButton.bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: ["element": "button"]
        )
        actionButton.addTrackingArea(trackingArea)

        // Create progress bar at the bottom (inside the pill view, so relative to pillView)
        progressBar = ProgressBarView(frame: NSRect(x: 0, y: 0, width: Self.NUB_WIDTH, height: 3), cornerRadius: 18)
        
        // Add all views to pill
        pillView.addSubview(appIconView)
        pillView.addSubview(recordingIndicator)
        pillView.addSubview(titleLabel)
        pillView.addSubview(appLabel)
        pillView.addSubview(actionButton)
        pillView.addSubview(progressBar)
        containerView.addSubview(pillView)
        self.contentView = containerView

        print("NubWindow: Content view setup complete")
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
                print("NubWindow: Self is nil, cannot show")
                return 
            }
            
            // Position off-screen to the right
            guard let screen = NSScreen.main else { 
                print("NubWindow: No main screen found")
                return 
            }
            
            let screenFrame = screen.visibleFrame
            print("NubWindow: Screen frame: \(screenFrame)")
            
            let finalX = screenFrame.maxX - Self.NUB_WIDTH - 20
            let finalY = screenFrame.maxY - Self.NUB_HEIGHT - 20
            
            print("NubWindow: Final position: (\(finalX), \(finalY))")
            
            // Position directly at final location (skip animation for now to debug)
            self.setFrameOrigin(NSPoint(x: finalX, y: finalY))
            self.alphaValue = 1.0
            self.isOpaque = false
            self.orderFrontRegardless()
            self.orderFront(nil)
            
            print("NubWindow: Window ordered front, visible: \(self.isVisible), alpha: \(self.alphaValue), frame: \(self.frame)")
            print("NubWindow: containerView frame: \(self.containerView?.frame ?? .zero)")
            print("NubWindow: pillView frame: \(self.pillView?.frame ?? .zero)")
            
            // Start timer immediately
            self.startAutoDismissTimer()
            
            print("NubWindow: Shown with slide-in animation")
        }
    }

    func hide() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.cancelTimers()
            self.orderOut(nil)
            self.setIsVisible(false)
            print("NubWindow: Hidden")
        }
    }
    
    // MARK: - Auto-dismiss Timer
    
    private func startAutoDismissTimer() {
        cancelTimers()
        
        startTime = Date()
        progressBar.setProgress(0.0)
        
        // Update progress every 0.1 seconds
        progressUpdateTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let startTime = self.startTime else { return }
            
            let elapsed = Date().timeIntervalSince(startTime)
            let progress = min(elapsed / Self.AUTO_DISMISS_DURATION, 1.0)
            
            DispatchQueue.main.async {
                self.progressBar.setProgress(progress)
            }
        }
        
        // Dismiss after 30 seconds
        dismissTimer = Timer.scheduledTimer(withTimeInterval: Self.AUTO_DISMISS_DURATION, repeats: false) { [weak self] _ in
            print("NubWindow: Auto-dismissing after \(Self.AUTO_DISMISS_DURATION) seconds")
            self?.hide()
        }
    }
    
    private func cancelTimers() {
        dismissTimer?.invalidate()
        dismissTimer = nil
        progressUpdateTimer?.invalidate()
        progressUpdateTimer = nil
        startTime = nil
    }

    // MARK: - Mouse Events

    override func mouseEntered(with event: NSEvent) {
        guard let userInfo = event.trackingArea?.userInfo,
              let element = userInfo["element"] as? String,
              element == "button" else {
            return
        }
        
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.15
            self.actionButton.animator().layer?.backgroundColor = NSColor.systemGreen.withAlphaComponent(0.85).cgColor
            self.actionButton.animator().layer?.transform = CATransform3DMakeScale(1.02, 1.02, 1.0)
        })
    }

    override func mouseExited(with event: NSEvent) {
        guard let userInfo = event.trackingArea?.userInfo,
              let element = userInfo["element"] as? String,
              element == "button" else {
            return
        }
        
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.15
            self.actionButton.animator().layer?.backgroundColor = NSColor.systemGreen.cgColor
            self.actionButton.animator().layer?.transform = CATransform3DIdentity
        })
    }

    @objc private func startRecordingClicked() {
        print("NubWindow: Start Recording clicked - opening main app")
        cancelTimers() // Stop auto-dismiss when user interacts
        NotificationCenter.default.post(name: .nubClicked, object: nil)
        
        // Hide the pill after clicking
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
            self?.hide()
        }
    }
    
    // MARK: - Public Update Methods
    
    func updateMeetingApp(_ appName: String) {
        self.meetingApp = appName
        DispatchQueue.main.async { [weak self] in
            self?.appLabel.stringValue = appName
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
    private var pillCornerRadius: CGFloat
    
    init(frame frameRect: NSRect, cornerRadius: CGFloat) {
        self.pillCornerRadius = cornerRadius
        super.init(frame: frameRect)
        self.wantsLayer = true
        
        // Background (empty state) - semi-transparent
        self.layer?.backgroundColor = NSColor.white.withAlphaComponent(0.05).cgColor
        
        // Progress layer (fills from left to right)
        progressLayer = CALayer()
        progressLayer.backgroundColor = NSColor.systemGreen.withAlphaComponent(0.9).cgColor
        progressLayer.frame = CGRect(x: 0, y: 0, width: 0, height: frameRect.height)
        progressLayer.masksToBounds = true
        
        // Create a mask for rounded corners on the left side
        let maskLayer = CAShapeLayer()
        progressLayer.mask = maskLayer
        
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
        
        // Update mask to apply rounded corners
        if let maskLayer = progressLayer.mask as? CAShapeLayer {
            let path = CGMutablePath()
            
            if progress < 1.0 {
                // Progress bar not complete - round only bottom-left corner
                let rect = CGRect(x: 0, y: 0, width: width, height: self.bounds.height)
                
                path.move(to: CGPoint(x: pillCornerRadius, y: 0))
                path.addLine(to: CGPoint(x: width, y: 0))
                path.addLine(to: CGPoint(x: width, y: self.bounds.height))
                path.addLine(to: CGPoint(x: pillCornerRadius, y: self.bounds.height))
                path.addArc(
                    center: CGPoint(x: pillCornerRadius, y: self.bounds.height - pillCornerRadius),
                    radius: pillCornerRadius,
                    startAngle: .pi / 2,
                    endAngle: .pi,
                    clockwise: false
                )
                path.addLine(to: CGPoint(x: 0, y: pillCornerRadius))
                path.addArc(
                    center: CGPoint(x: pillCornerRadius, y: pillCornerRadius),
                    radius: pillCornerRadius,
                    startAngle: .pi,
                    endAngle: -.pi / 2,
                    clockwise: false
                )
                path.closeSubpath()
            } else {
                // Progress bar complete - round both bottom corners to match pill
                let rect = CGRect(x: 0, y: 0, width: width, height: self.bounds.height)
                
                path.move(to: CGPoint(x: pillCornerRadius, y: 0))
                path.addLine(to: CGPoint(x: width - pillCornerRadius, y: 0))
                path.addLine(to: CGPoint(x: width - pillCornerRadius, y: self.bounds.height))
                path.addArc(
                    center: CGPoint(x: width - pillCornerRadius, y: self.bounds.height - pillCornerRadius),
                    radius: pillCornerRadius,
                    startAngle: .pi / 2,
                    endAngle: 0,
                    clockwise: true
                )
                path.addLine(to: CGPoint(x: width, y: pillCornerRadius))
                path.addLine(to: CGPoint(x: 0, y: pillCornerRadius))
                path.addArc(
                    center: CGPoint(x: pillCornerRadius, y: pillCornerRadius),
                    radius: pillCornerRadius,
                    startAngle: .pi,
                    endAngle: -.pi / 2,
                    clockwise: false
                )
                path.closeSubpath()
            }
            
            maskLayer.path = path
        }
        
        CATransaction.commit()
    }
}

// MARK: - Notification Extension

extension Notification.Name {
    static let nubClicked = Notification.Name("com.omi.nub.clicked")
}
