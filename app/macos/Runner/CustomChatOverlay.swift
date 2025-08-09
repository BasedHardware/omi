import Cocoa

// MARK: - Custom Chat Overlay Window
class CustomChatOverlay: NSWindow {
    
    // UI States matching Flutter DesktopVoiceRecorderWidget
    enum OverlayState {
        case recording
        case transcribing
        case transcribeSuccess
        case transcribeFailed
    }
    
    // Current state
    private var currentState: OverlayState = .recording
    
    // Drag functionality
    private var dragOffset: NSPoint = NSPoint.zero
    
    // Main container
    private var containerView: NSView!
    private var mainContainer: NSView!
    
    // Recording state UI elements
    private var closeButton: NSButton!
    private var checkButton: NSButton!
    private var waveformView: AudioWaveformView!
    
    // Transcribing state UI elements
    private var transcribingLabel: NSTextField!
    
    // Transcript success state UI elements
    private var transcriptContainer: NSView!
    private var transcriptLabel: NSTextField!
    private var actionButtonsContainer: NSView!
    private var sendButton: NSButton!
    private var successCloseButton: NSButton!
    
    // Error state UI elements
    private var errorLabel: NSTextField!
    private var retryButton: NSButton!
    private var errorCloseButton: NSButton!
    
    // Callbacks
    var onClose: (() -> Void)?
    var onCheck: (() -> Void)?
    var onSend: ((String) -> Void)?
    var onRetry: (() -> Void)?
    
    // Sample transcript for testing
    private var transcript: String = ""
    
    override init(contentRect: NSRect, styleMask style: NSWindow.StyleMask, backing backingStoreType: NSWindow.BackingStoreType, defer flag: Bool) {
        super.init(contentRect: contentRect, styleMask: [.borderless], backing: backingStoreType, defer: flag)
        
        setupWindow()
        setupUI()
        positionWindow()
    }
    
    private func setupWindow() {
        // Make window float above all other applications
        self.level = NSWindow.Level.floating
        self.isOpaque = false
        self.backgroundColor = NSColor.clear
        self.hasShadow = true
        self.ignoresMouseEvents = false
        
        // Enable mouse tracking for hover effects
        self.acceptsMouseMovedEvents = true
        
        // Make window appear above all other windows including fullscreen apps
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        
        // Hide from screen sharing
        self.sharingType = .none
    }
    
    // Override these properties instead of trying to assign to them
    override var canBecomeKey: Bool {
        return true
    }
    
    override var canBecomeMain: Bool {
        return false
    }
    
    private func positionWindow() {
        guard let screen = NSScreen.main else { return }
        let screenFrame = screen.visibleFrame
        
        // Dynamic width based on content, height matches Flutter implementation
        let overlayWidth: CGFloat = 350
        let overlayHeight: CGFloat = 60
        let margin: CGFloat = 120
        
        let overlayFrame = NSRect(
            x: screenFrame.origin.x + (screenFrame.width - overlayWidth) / 2,  // Center horizontally
            y: screenFrame.origin.y + margin,                                   // 120px from bottom
            width: overlayWidth,
            height: overlayHeight
        )
        
        self.setFrame(overlayFrame, display: true)
    }
    
    private func setupUI() {
        containerView = NSView(frame: self.contentView!.bounds)
        containerView.autoresizingMask = [.width, .height]
        
        // Create all UI elements for different states
        setupRecordingStateUI()
        setupTranscribingStateUI()
        setupTranscriptSuccessStateUI()
        setupErrorStateUI()
        
        self.contentView = containerView
        
        // Show recording state by default
        updateUIForState(.recording)
        
        // Add drag gesture
        let dragGesture = NSPanGestureRecognizer(target: self, action: #selector(handleDrag(_:)))
        containerView.addGestureRecognizer(dragGesture)
        
        // Add entrance animation
        addEntranceAnimation()
    }
    
    private func setupRecordingStateUI() {
        // Main container matching Flutter design
        mainContainer = NSView(frame: NSRect(x: 0, y: 0, width: 350, height: 56))
        mainContainer.wantsLayer = true
        mainContainer.layer?.cornerRadius = 12
        mainContainer.layer?.masksToBounds = true
        
        // Background color matching ResponsiveHelper.backgroundTertiary
        mainContainer.layer?.backgroundColor = NSColor.controlBackgroundColor.cgColor
        
        // Purple border matching ResponsiveHelper.purplePrimary
        mainContainer.layer?.borderWidth = 1.0
        mainContainer.layer?.borderColor = NSColor.systemPurple.withAlphaComponent(0.3).cgColor
        
        // Close button (left side) - matching Flutter OmiIconButton
        closeButton = NSButton(frame: NSRect(x: 8, y: 12, width: 32, height: 32))
        closeButton.isBordered = false
        closeButton.bezelStyle = .circular
        closeButton.imageScaling = .scaleProportionallyDown
        
        // Set close icon
        let closeIcon = NSImage(systemSymbolName: "xmark", accessibilityDescription: "Close")
        if let icon = closeIcon {
            let config = NSImage.SymbolConfiguration(pointSize: 14, weight: .medium)
            closeButton.image = icon.withSymbolConfiguration(config)
        }
        
        styleOutlineButton(closeButton)
        closeButton.target = self
        closeButton.action = #selector(closeButtonClicked)
        
        // Waveform view (center)
        waveformView = AudioWaveformView(frame: NSRect(x: 48, y: 8, width: 254, height: 40))
        
        // Check button (right side) - matching Flutter OmiIconButton filled style
        checkButton = NSButton(frame: NSRect(x: 310, y: 12, width: 32, height: 32))
        checkButton.isBordered = false
        checkButton.bezelStyle = .circular
        checkButton.imageScaling = .scaleProportionallyDown
        
        // Set check icon
        let checkIcon = NSImage(systemSymbolName: "checkmark", accessibilityDescription: "Check")
        if let icon = checkIcon {
            let config = NSImage.SymbolConfiguration(pointSize: 14, weight: .medium)
            checkButton.image = icon.withSymbolConfiguration(config)
        }
        
        styleFilledButton(checkButton)
        checkButton.target = self
        checkButton.action = #selector(checkButtonClicked)
        
        // Add to main container
        mainContainer.addSubview(closeButton)
        mainContainer.addSubview(waveformView)
        mainContainer.addSubview(checkButton)
        
        containerView.addSubview(mainContainer)
    }
    
    private func setupTranscribingStateUI() {
        // Transcribing label (will be shown/hidden based on state)
        transcribingLabel = NSTextField(frame: NSRect(x: 0, y: 18, width: 350, height: 20))
        transcribingLabel.isEditable = false
        transcribingLabel.isBordered = false
        transcribingLabel.backgroundColor = NSColor.clear
        transcribingLabel.stringValue = "Transcribing..."
        transcribingLabel.alignment = .center
        transcribingLabel.font = NSFont.systemFont(ofSize: 14)
        transcribingLabel.textColor = NSColor.labelColor
        transcribingLabel.isHidden = true
        
        containerView.addSubview(transcribingLabel)
    }
    
    private func setupTranscriptSuccessStateUI() {
        // Transcript container
        transcriptContainer = NSView(frame: NSRect(x: 0, y: 36, width: 350, height: 50))
        transcriptContainer.wantsLayer = true
        transcriptContainer.layer?.cornerRadius = 12
        transcriptContainer.layer?.masksToBounds = true
        transcriptContainer.layer?.backgroundColor = NSColor.controlBackgroundColor.cgColor
        transcriptContainer.layer?.borderWidth = 1.0
        transcriptContainer.layer?.borderColor = NSColor.systemPurple.withAlphaComponent(0.3).cgColor
        transcriptContainer.isHidden = true
        
        // Transcript text
        transcriptLabel = NSTextField(frame: NSRect(x: 12, y: 15, width: 326, height: 20))
        transcriptLabel.isEditable = false
        transcriptLabel.isBordered = false
        transcriptLabel.backgroundColor = NSColor.clear
        transcriptLabel.font = NSFont.systemFont(ofSize: 14)
        transcriptLabel.textColor = NSColor.labelColor
        transcriptLabel.cell?.wraps = true
        transcriptLabel.cell?.isScrollable = false
        
        transcriptContainer.addSubview(transcriptLabel)
        
        // Action buttons container
        actionButtonsContainer = NSView(frame: NSRect(x: 0, y: 8, width: 350, height: 28))
        actionButtonsContainer.isHidden = true
        
        // Success close button
        successCloseButton = NSButton(frame: NSRect(x: 290, y: 0, width: 28, height: 28))
        successCloseButton.isBordered = false
        successCloseButton.bezelStyle = .circular
        successCloseButton.imageScaling = .scaleProportionallyDown
        
        let successCloseIcon = NSImage(systemSymbolName: "xmark", accessibilityDescription: "Close")
        if let icon = successCloseIcon {
            let config = NSImage.SymbolConfiguration(pointSize: 12, weight: .medium)
            successCloseButton.image = icon.withSymbolConfiguration(config)
        }
        
        styleSmallOutlineButton(successCloseButton)
        successCloseButton.target = self
        successCloseButton.action = #selector(closeButtonClicked)
        
        // Send button
        sendButton = NSButton(frame: NSRect(x: 322, y: 0, width: 28, height: 28))
        sendButton.isBordered = false
        sendButton.bezelStyle = .circular
        sendButton.imageScaling = .scaleProportionallyDown
        
        let sendIcon = NSImage(systemSymbolName: "arrow.up", accessibilityDescription: "Send")
        if let icon = sendIcon {
            let config = NSImage.SymbolConfiguration(pointSize: 12, weight: .medium)
            sendButton.image = icon.withSymbolConfiguration(config)
        }
        
        styleSmallFilledButton(sendButton)
        sendButton.target = self
        sendButton.action = #selector(sendButtonClicked)
        
        actionButtonsContainer.addSubview(successCloseButton)
        actionButtonsContainer.addSubview(sendButton)
        
        containerView.addSubview(transcriptContainer)
        containerView.addSubview(actionButtonsContainer)
    }
    
    private func setupErrorStateUI() {
        // Error UI elements will reuse main container with different styling
        errorLabel = NSTextField(frame: NSRect(x: 16, y: 20, width: 60, height: 20))
        errorLabel.isEditable = false
        errorLabel.isBordered = false
        errorLabel.backgroundColor = NSColor.clear
        errorLabel.stringValue = "Error"
        errorLabel.font = NSFont.systemFont(ofSize: 14, weight: .semibold)
        errorLabel.textColor = NSColor.systemRed
        errorLabel.isHidden = true
        
        // Retry button
        retryButton = NSButton(frame: NSRect(x: 278, y: 12, width: 28, height: 28))
        retryButton.isBordered = false
        retryButton.bezelStyle = .circular
        retryButton.imageScaling = .scaleProportionallyDown
        
        let retryIcon = NSImage(systemSymbolName: "arrow.clockwise", accessibilityDescription: "Retry")
        if let icon = retryIcon {
            let config = NSImage.SymbolConfiguration(pointSize: 12, weight: .medium)
            retryButton.image = icon.withSymbolConfiguration(config)
        }
        
        styleSmallFilledButton(retryButton)
        retryButton.target = self
        retryButton.action = #selector(retryButtonClicked)
        retryButton.isHidden = true
        
        // Error close button
        errorCloseButton = NSButton(frame: NSRect(x: 310, y: 12, width: 28, height: 28))
        errorCloseButton.isBordered = false
        errorCloseButton.bezelStyle = .circular
        errorCloseButton.imageScaling = .scaleProportionallyDown
        
        let errorCloseIcon = NSImage(systemSymbolName: "xmark", accessibilityDescription: "Close")
        if let icon = errorCloseIcon {
            let config = NSImage.SymbolConfiguration(pointSize: 12, weight: .medium)
            errorCloseButton.image = icon.withSymbolConfiguration(config)
        }
        
        styleSmallOutlineButton(errorCloseButton)
        errorCloseButton.target = self
        errorCloseButton.action = #selector(closeButtonClicked)
        errorCloseButton.isHidden = true
        
        containerView.addSubview(errorLabel)
        containerView.addSubview(retryButton)
        containerView.addSubview(errorCloseButton)
    }
    
    // MARK: - Button Styling
    
    private func styleOutlineButton(_ button: NSButton) {
        button.wantsLayer = true
        button.layer?.cornerRadius = 8
        button.layer?.masksToBounds = true
        button.layer?.backgroundColor = NSColor.clear.cgColor
        button.layer?.borderWidth = 1.0
        button.layer?.borderColor = NSColor.separatorColor.withAlphaComponent(0.12).cgColor
    }
    
    private func styleFilledButton(_ button: NSButton) {
        button.wantsLayer = true
        button.layer?.cornerRadius = 8
        button.layer?.masksToBounds = true
        button.layer?.backgroundColor = NSColor.systemPurple.cgColor
        button.layer?.borderWidth = 0
    }
    
    private func styleSmallOutlineButton(_ button: NSButton) {
        button.wantsLayer = true
        button.layer?.cornerRadius = 8
        button.layer?.masksToBounds = true
        button.layer?.backgroundColor = NSColor.clear.cgColor
        button.layer?.borderWidth = 1.0
        button.layer?.borderColor = NSColor.separatorColor.withAlphaComponent(0.12).cgColor
    }
    
    private func styleSmallFilledButton(_ button: NSButton) {
        button.wantsLayer = true
        button.layer?.cornerRadius = 8
        button.layer?.masksToBounds = true
        button.layer?.backgroundColor = NSColor.systemPurple.cgColor
        button.layer?.borderWidth = 0
    }
    
    // MARK: - State Management
    
    func updateUIForState(_ state: OverlayState) {
        currentState = state
        
        // Hide all UI elements first
        hideAllStateUI()
        
        switch state {
        case .recording:
            showRecordingUI()
        case .transcribing:
            showTranscribingUI()
        case .transcribeSuccess:
            showTranscriptSuccessUI()
        case .transcribeFailed:
            showErrorUI()
        }
    }
    
    private func hideAllStateUI() {
        // Recording state
        closeButton.isHidden = true
        waveformView.isHidden = true
        checkButton.isHidden = true
        
        // Transcribing state
        transcribingLabel.isHidden = true
        
        // Success state
        transcriptContainer.isHidden = true
        actionButtonsContainer.isHidden = true
        
        // Error state
        errorLabel.isHidden = true
        retryButton.isHidden = true
        errorCloseButton.isHidden = true
        
        // Reset main container border to purple
        mainContainer.layer?.borderColor = NSColor.systemPurple.withAlphaComponent(0.3).cgColor
    }
    
    private func showRecordingUI() {
        closeButton.isHidden = false
        waveformView.isHidden = false
        checkButton.isHidden = false
        waveformView.startAnimating() // Start animation timer to enable waveform redraws
    }
    
    private func showTranscribingUI() {
        transcribingLabel.isHidden = false
        startShimmerEffect()
    }
    
    private func showTranscriptSuccessUI() {
        transcriptContainer.isHidden = false
        actionButtonsContainer.isHidden = false
        transcriptLabel.stringValue = transcript.isEmpty ? "Sample transcript text" : transcript
    }
    
    private func showErrorUI() {
        // Show error elements with main container
        closeButton.isHidden = true
        checkButton.isHidden = true
        waveformView.isHidden = false
        
        errorLabel.isHidden = false
        retryButton.isHidden = false
        errorCloseButton.isHidden = false
        
        // Change border to red for error state
        mainContainer.layer?.borderColor = NSColor.systemRed.withAlphaComponent(0.3).cgColor
    }
    
    // MARK: - Animations
    
    private func addEntranceAnimation() {
        containerView.layer?.opacity = 0.0
        containerView.layer?.transform = CATransform3DMakeScale(0.9, 0.9, 1.0)
        
        CATransaction.begin()
        CATransaction.setAnimationDuration(0.4)
        CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(name: .easeIn))
        containerView.layer?.opacity = 1.0
        containerView.layer?.transform = CATransform3DIdentity
        CATransaction.commit()
    }
    
    private func startShimmerEffect() {
        let shimmerAnimation = CABasicAnimation(keyPath: "opacity")
        shimmerAnimation.fromValue = 0.5
        shimmerAnimation.toValue = 1.0
        shimmerAnimation.duration = 1.0
        shimmerAnimation.autoreverses = true
        shimmerAnimation.repeatCount = .infinity
        transcribingLabel.layer?.add(shimmerAnimation, forKey: "shimmer")
    }
    
    private func stopShimmerEffect() {
        transcribingLabel.layer?.removeAnimation(forKey: "shimmer")
    }
    
    // MARK: - Button Actions
    
    @objc private func closeButtonClicked() {
        onClose?()
    }
    
    @objc private func checkButtonClicked() {
        print("🔵 CHECKMARK BUTTON CLICKED")
        onCheck?()
    }
    
    @objc private func sendButtonClicked() {
        onSend?(transcript)
    }
    
    @objc private func retryButtonClicked() {
        onRetry?()
    }
    
    // MARK: - Drag Handling
    
    @objc private func handleDrag(_ gesture: NSPanGestureRecognizer) {
        let location = gesture.location(in: self.contentView)
        
        switch gesture.state {
        case .began:
            dragOffset = NSPoint(x: location.x, y: location.y)
        case .changed:
            let newOrigin = NSPoint(
                x: self.frame.origin.x + location.x - dragOffset.x,
                y: self.frame.origin.y + location.y - dragOffset.y
            )
            self.setFrameOrigin(newOrigin)
        default:
            break
        }
    }
    
    // MARK: - Public Methods
    
    func setTranscript(_ text: String) {
        transcript = text
        transcriptLabel.stringValue = text
    }
    
    func setState(_ state: OverlayState) {
        DispatchQueue.main.async {
            self.updateUIForState(state)
        }
    }
    
    func updateWaveform(levels: [Double]) {
        DispatchQueue.main.async {
            self.waveformView.updateAudioLevels(levels)
        }
    }
}

// MARK: - Audio Waveform View
class AudioWaveformView: NSView {
    private var audioLevels: [Double] = Array(repeating: 0.1, count: 20)
    private var animationTimer: Timer?
    
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        self.wantsLayer = true
    }
    
    required init?(coder: NSCoder) {
        super.init(coder: coder)
        self.wantsLayer = true
    }
    
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        
        guard let context = NSGraphicsContext.current?.cgContext else { return }
        
        // Set purple color matching ResponsiveHelper.purplePrimary
        context.setStrokeColor(NSColor.systemPurple.cgColor)
        context.setLineWidth(3.0)
        context.setLineCap(.round)
        
        let width = bounds.width
        let height = bounds.height
        let barWidth = width / CGFloat(audioLevels.count) / 2
        
        for (i, level) in audioLevels.enumerated() {
            let x = CGFloat(i) * (barWidth * 2) + barWidth
            let barHeight = CGFloat(level) * height * 0.8
            
            let topY = height / 2 - barHeight / 2
            let bottomY = height / 2 + barHeight / 2
            
            context.move(to: CGPoint(x: x, y: topY))
            context.addLine(to: CGPoint(x: x, y: bottomY))
            context.strokePath()
        }
    }
    
    func startAnimating() {
        // Animation timer now only triggers redraws - real audio data comes from updateAudioLevels
        animationTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { _ in
            DispatchQueue.main.async {
                self.needsDisplay = true
            }
        }
    }
    
    func stopAnimating() {
        animationTimer?.invalidate()
        animationTimer = nil
    }
    
    func updateAudioLevels(_ levels: [Double]) {
        audioLevels = levels
        DispatchQueue.main.async {
            self.needsDisplay = true
        }
    }
    
    deinit {
        stopAnimating()
    }
}