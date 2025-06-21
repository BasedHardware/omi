import Cocoa

// MARK: - Floating Overlay Window
class FloatingRecordingOverlay: NSWindow {
    private var dragOffset: NSPoint = NSPoint.zero
    private var logoImageView: NSImageView!
    private var controlsContainer: NSView!
    private var playPauseButton: NSButton!
    private var stopButton: NSButton!
    private var expandButton: NSButton!
    
    // Callback for button actions
    var onPlayPause: (() -> Void)?
    var onStop: (() -> Void)?
    var onExpand: (() -> Void)?
    
    override init(contentRect: NSRect, styleMask style: NSWindow.StyleMask, backing backingStoreType: NSWindow.BackingStoreType, defer flag: Bool) {
        super.init(contentRect: contentRect, styleMask: [.borderless], backing: backingStoreType, defer: flag)
        
        setupWindow()
        setupUI()
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
        
        // Hide from screen sharing (similar to what we discussed earlier)
        self.sharingType = .none
    }
    
    // Override these properties instead of trying to assign to them
    override var canBecomeKey: Bool {
        return true
    }
    
    override var canBecomeMain: Bool {
        return false
    }
    
    private func setupUI() {
        let containerView = NSView(frame: self.contentView!.bounds)
        containerView.autoresizingMask = [.width, .height]
        
        // Main pill container - optimized width with better proportions
        let pillContainer = NSView(frame: NSRect(x: 0, y: 0, width: 220, height: 52))
        pillContainer.wantsLayer = true
        pillContainer.layer?.cornerRadius = 26
        pillContainer.layer?.masksToBounds = false  // Allow shadows to show
        
        // Add blur effect background
        setupBlurBackground(pillContainer)
        
        // Set initial background overlay (we'll update this based on state)
        setupPillBackground(pillContainer, isRecording: false, isPaused: false)
        
        // Logo container (left side)
        let logoContainer = NSView(frame: NSRect(x: 16, y: 0, width: 52, height: 52))
        pillContainer.addSubview(logoContainer)
        
        // App logo (centered and slightly larger)
        logoImageView = NSImageView(frame: NSRect(x: 14, y: 14, width: 24, height: 24))
        if let appIcon = NSImage(named: "app_launcher_icon") {
            appIcon.size = NSSize(width: 24, height: 24)
            logoImageView.image = appIcon
        } else {
            // Fallback to system mic icon if app icon not found
            let fallbackIcon = NSImage(systemSymbolName: "mic.circle.fill", accessibilityDescription: "Recording")
            fallbackIcon?.size = NSSize(width: 24, height: 24)
            logoImageView.image = fallbackIcon
        }
        logoImageView.wantsLayer = true
        logoImageView.layer?.cornerRadius = 12
        logoImageView.imageScaling = .scaleProportionallyUpOrDown
        setupLogoShadow(logoImageView)
        logoContainer.addSubview(logoImageView)
        
        // Controls container (right side) - better spacing and positioning
        controlsContainer = NSView(frame: NSRect(x: 76, y: 12, width: 132, height: 28))
        setupControls()
        pillContainer.addSubview(controlsContainer)
        
        containerView.addSubview(pillContainer)
        self.contentView = containerView
        
        // Add drag gesture
        let dragGesture = NSPanGestureRecognizer(target: self, action: #selector(handleDrag(_:)))
        containerView.addGestureRecognizer(dragGesture)
        
        // Add subtle entrance animation
        pillContainer.layer?.opacity = 0.0
        pillContainer.layer?.transform = CATransform3DMakeScale(0.9, 0.9, 1.0)
        
        CATransaction.begin()
        CATransaction.setAnimationDuration(0.4)
        CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(name: .easeIn))
        pillContainer.layer?.opacity = 1.0
        pillContainer.layer?.transform = CATransform3DIdentity
        CATransaction.commit()
    }
    
    private func setupBlurBackground(_ container: NSView) {
        // Create blur effect view
        let blurView = NSVisualEffectView(frame: container.bounds)
        blurView.autoresizingMask = [.width, .height]
        blurView.material = .hudWindow
        blurView.blendingMode = .behindWindow
        blurView.state = .active
        blurView.wantsLayer = true
        blurView.layer?.cornerRadius = 30
        blurView.layer?.masksToBounds = true
        
        container.addSubview(blurView, positioned: .below, relativeTo: nil)
    }
    
    private func setupLogoShadow(_ logoView: NSImageView) {
        logoView.layer?.shadowColor = NSColor.black.cgColor
        logoView.layer?.shadowOpacity = 0.08
        logoView.layer?.shadowRadius = 3
        logoView.layer?.shadowOffset = CGSize(width: 0, height: 1)
        logoView.layer?.masksToBounds = false
    }
    
    private func setupPillBackground(_ container: NSView, isRecording: Bool, isPaused: Bool) {
        // Remove existing overlays
        container.layer?.sublayers?.removeAll { layer in
            layer.name == "colorOverlay" || layer.name == "borderLayer"
        }
        
        // Create subtle color overlay on top of blur - more minimal approach
        let overlay = CALayer()
        overlay.name = "colorOverlay"
        overlay.frame = container.bounds
        overlay.cornerRadius = 26
        overlay.masksToBounds = true
        
        if isRecording {
            // Very subtle purple tint for recording
            overlay.backgroundColor = NSColor.systemPurple.withAlphaComponent(0.08).cgColor
        } else if isPaused {
            // Very subtle orange tint for paused
            overlay.backgroundColor = NSColor.systemOrange.withAlphaComponent(0.06).cgColor
        } else {
            // Nearly transparent for idle state
            overlay.backgroundColor = NSColor.controlBackgroundColor.withAlphaComponent(0.03).cgColor
        }
        
        container.layer?.addSublayer(overlay)
        
        // Minimal border following native macOS principles
        let borderLayer = CALayer()
        borderLayer.name = "borderLayer"
        borderLayer.frame = container.bounds
        borderLayer.cornerRadius = 26
        borderLayer.borderWidth = 0.5
        borderLayer.masksToBounds = true
        
        if isRecording {
            borderLayer.borderColor = NSColor.systemPurple.withAlphaComponent(0.15).cgColor
        } else if isPaused {
            borderLayer.borderColor = NSColor.systemOrange.withAlphaComponent(0.12).cgColor
        } else {
            borderLayer.borderColor = NSColor.separatorColor.withAlphaComponent(0.3).cgColor
        }
        
        container.layer?.addSublayer(borderLayer)
        
        // Subtle shadow system
        setupContainerShadow(container, isRecording: isRecording, isPaused: isPaused)
    }
    
    private func setupContainerShadow(_ container: NSView, isRecording: Bool, isPaused: Bool) {
        // Subtle shadow following native macOS design
        container.layer?.shadowColor = NSColor.black.cgColor
        container.layer?.shadowOpacity = 0.08
        container.layer?.shadowRadius = 12
        container.layer?.shadowOffset = CGSize(width: 0, height: 2)
        
        // Very minimal glow for active states - more native feeling
        if isRecording || isPaused {
            let glowColor = isRecording ? NSColor.systemPurple : NSColor.systemOrange
            container.layer?.shadowColor = glowColor.withAlphaComponent(0.08).cgColor
            container.layer?.shadowOpacity = 0.12
            container.layer?.shadowRadius = 16
        }
    }
    
    private func setupControls() {
        // Play/Pause button (primary action) - better spacing
        playPauseButton = NSButton(frame: NSRect(x: 0, y: 0, width: 28, height: 28))
        playPauseButton.isBordered = false
        playPauseButton.bezelStyle = .circular
        playPauseButton.imageScaling = .scaleProportionallyDown
        let playConfig = NSImage.SymbolConfiguration(pointSize: 11, weight: .medium)
        playPauseButton.image = NSImage(systemSymbolName: "play.fill", accessibilityDescription: "Play")?.withSymbolConfiguration(playConfig)
        styleModernButton(playPauseButton, isPrimary: true)
        controlsContainer.addSubview(playPauseButton)
        
        // Stop button (initially hidden, appears when recording with content) - increased spacing
        stopButton = NSButton(frame: NSRect(x: 36, y: 0, width: 28, height: 28))
        stopButton.isBordered = false
        stopButton.bezelStyle = .circular
        stopButton.imageScaling = .scaleProportionallyDown
        let stopConfig = NSImage.SymbolConfiguration(pointSize: 9, weight: .medium)
        stopButton.image = NSImage(systemSymbolName: "stop.fill", accessibilityDescription: "Stop")?.withSymbolConfiguration(stopConfig)
        stopButton.isHidden = true
        styleStopButton(stopButton)
        controlsContainer.addSubview(stopButton)
        
        // Expand/Maximize button (always visible) - proper spacing from other buttons
        expandButton = NSButton(frame: NSRect(x: 72, y: 0, width: 28, height: 28))
        expandButton.isBordered = false
        expandButton.bezelStyle = .circular
        expandButton.imageScaling = .scaleProportionallyDown
        let expandConfig = NSImage.SymbolConfiguration(pointSize: 9, weight: .medium)
        expandButton.image = NSImage(systemSymbolName: "arrow.up.backward.and.arrow.down.forward", accessibilityDescription: "Restore App")?.withSymbolConfiguration(expandConfig)
        styleModernButton(expandButton, isPrimary: false)
        controlsContainer.addSubview(expandButton)
    }
    
    private func styleModernButton(_ button: NSButton, isPrimary: Bool) {
        button.wantsLayer = true
        button.layer?.cornerRadius = 14
        button.layer?.masksToBounds = true
        
        if isPrimary {
            // Primary button - very subtle, native macOS style
            button.layer?.backgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.08).cgColor
            button.layer?.borderWidth = 0.5
            button.layer?.borderColor = NSColor.controlAccentColor.withAlphaComponent(0.15).cgColor
        } else {
            // Secondary button - extremely subtle
            button.layer?.backgroundColor = NSColor.controlBackgroundColor.withAlphaComponent(0.3).cgColor
            button.layer?.borderWidth = 0.5
            button.layer?.borderColor = NSColor.separatorColor.withAlphaComponent(0.2).cgColor
        }
        
        // Very minimal shadow - native macOS approach
        button.layer?.shadowColor = NSColor.black.cgColor
        button.layer?.shadowOpacity = 0.04
        button.layer?.shadowRadius = 2
        button.layer?.shadowOffset = CGSize(width: 0, height: 0.5)
        
        // Add hover effect
        setupButtonHoverEffect(button)
    }
    
    private func styleStopButton(_ button: NSButton) {
        button.wantsLayer = true
        button.layer?.cornerRadius = 14
        button.layer?.masksToBounds = true
        button.layer?.backgroundColor = NSColor.systemRed.withAlphaComponent(0.08).cgColor
        button.layer?.borderWidth = 0.5
        button.layer?.borderColor = NSColor.systemRed.withAlphaComponent(0.2).cgColor
        
        // Minimal red shadow - native approach
        button.layer?.shadowColor = NSColor.systemRed.cgColor
        button.layer?.shadowOpacity = 0.06
        button.layer?.shadowRadius = 3
        button.layer?.shadowOffset = CGSize(width: 0, height: 0.5)
        
        setupButtonHoverEffect(button)
    }
    
    private func setupButtonHoverEffect(_ button: NSButton) {
        let trackingArea = NSTrackingArea(
            rect: button.bounds,
            options: [.activeAlways, .mouseEnteredAndExited],
            owner: self,
            userInfo: ["button": button]
        )
        button.addTrackingArea(trackingArea)
        
        // Add target-action for pressed state feedback
        button.target = self
        if button == playPauseButton {
            button.action = #selector(playPausePressed)
        } else if button == stopButton {
            button.action = #selector(stopPressed)
        } else if button == expandButton {
            button.action = #selector(expandPressed)
        }
    }
    
    @objc private func playPausePressed() {
        animateButtonPress(playPauseButton)
        // Small delay to show the press animation before calling the actual action
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            self.playPauseClicked()
        }
    }
    
    @objc private func stopPressed() {
        animateButtonPress(stopButton)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            self.stopClicked()
        }
    }
    
    @objc private func expandPressed() {
        animateButtonPress(expandButton)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            self.expandClicked()
        }
    }
    
    private func animateButtonPress(_ button: NSButton) {
        // Scale down briefly to show press feedback
        CATransaction.begin()
        CATransaction.setAnimationDuration(0.1)
        button.layer?.transform = CATransform3DMakeScale(0.95, 0.95, 1.0)
        CATransaction.setCompletionBlock {
            CATransaction.begin()
            CATransaction.setAnimationDuration(0.1)
            button.layer?.transform = CATransform3DIdentity
            CATransaction.commit()
        }
        CATransaction.commit()
    }
    
    override func mouseEntered(with event: NSEvent) {
        if let button = event.trackingArea?.userInfo?["button"] as? NSButton {
            // Enhanced hover feedback - more noticeable but still native feeling
            CATransaction.begin()
            CATransaction.setAnimationDuration(0.15)
            
            // Slight scale and brightness change for better button feel
            button.layer?.transform = CATransform3DMakeScale(1.05, 1.05, 1.0)
            
            // Increase background opacity for more prominent hover effect
            if button == playPauseButton {
                button.layer?.backgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.15).cgColor
            } else if button == stopButton {
                button.layer?.backgroundColor = NSColor.systemRed.withAlphaComponent(0.15).cgColor
            } else {
                button.layer?.backgroundColor = NSColor.controlBackgroundColor.withAlphaComponent(0.5).cgColor
            }
            
            CATransaction.commit()
        }
    }
    
    override func mouseExited(with event: NSEvent) {
        if let button = event.trackingArea?.userInfo?["button"] as? NSButton {
            // Return to normal state
            CATransaction.begin()
            CATransaction.setAnimationDuration(0.15)
            
            button.layer?.transform = CATransform3DIdentity
            
            // Reset to original background colors
            if button == playPauseButton {
                button.layer?.backgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.08).cgColor
            } else if button == stopButton {
                button.layer?.backgroundColor = NSColor.systemRed.withAlphaComponent(0.08).cgColor
            } else {
                button.layer?.backgroundColor = NSColor.controlBackgroundColor.withAlphaComponent(0.3).cgColor
            }
            
            CATransaction.commit()
        }
    }
    
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
    
    @objc private func playPauseClicked() {
        onPlayPause?()
    }
    
    @objc private func stopClicked() {
        onStop?()
    }
    
    @objc private func expandClicked() {
        print("DEBUG: Expand button clicked in overlay")
        
        // Just call the callback - let the main window handle restoration and hiding
        onExpand?()
    }
    
    // Public methods to update the UI
    func updateRecordingState(isRecording: Bool, isPaused: Bool) {
        // Update background
        if let pillContainer = self.contentView?.subviews.first?.subviews.first {
            setupPillBackground(pillContainer, isRecording: isRecording, isPaused: isPaused)
        }
        
        // Update button image
        let imageName = isRecording ? "pause.fill" : "play.fill"
        playPauseButton.image = NSImage(systemSymbolName: imageName, accessibilityDescription: isRecording ? "Pause" : "Play")
        
        // Add pulsing animation for logo when recording
        if isRecording {
            startPulsingAnimation()
        } else {
            stopPulsingAnimation()
        }
    }
    
    func updateTranscript(_ text: String, segmentCount: Int) {
        // Show stop button when there are segments (recording has content)
        if segmentCount > 0 {
            stopButton.isHidden = false
            
            // Animate stop button entrance smoothly
            if stopButton.layer?.opacity == 0 {
                stopButton.layer?.opacity = 0
                stopButton.layer?.transform = CATransform3DMakeScale(0.8, 0.8, 1.0)
                
                CATransaction.begin()
                CATransaction.setAnimationDuration(0.25)
                CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(name: .easeOut))
                stopButton.layer?.opacity = 1.0
                stopButton.layer?.transform = CATransform3DIdentity
                CATransaction.commit()
            }
        } else {
            // No segments - hide stop button
            stopButton.isHidden = true
        }
    }
    
    func updateStatusText(_ status: String) {
        // No status text display needed since we removed the transcript label
    }
    
    private func startPulsingAnimation() {
        let animation = CABasicAnimation(keyPath: "opacity")
        animation.fromValue = 0.6
        animation.toValue = 1.0
        animation.duration = 1.2
        animation.autoreverses = true
        animation.repeatCount = .infinity
        logoImageView.layer?.add(animation, forKey: "pulsing")
    }
    
    private func stopPulsingAnimation() {
        logoImageView.layer?.removeAnimation(forKey: "pulsing")
    }
} 