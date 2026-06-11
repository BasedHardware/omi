import AppKit
import CoreGraphics
import Foundation
import ImageIO
import Vision

// MARK: - Output Types

/// A node in the accessibility tree with spatial and textual context.
struct AXNode: Codable {
    let role: String
    let label: String?
    let value: String?
    let description: String?
    let children: [AXNode]
    /// Bounding box in window-local pixel coordinates (origin top-left, y-down).
    let bounds: CGRect?
    /// The depth of this node from the root.
    let depth: Int
    /// True if this node represents an image or custom view that needs visual captioning.
    let needsVisualCaption: Bool
}

/// A visual crop captured from the screen for ANE captioning or OCR.
struct VisualCrop: Codable {
    /// Bounding box in window-local pixel coordinates.
    let bounds: CGRect
    /// The role of the AX element (e.g., "AXImage", "AXUnknown").
    let role: String
    /// ANE-generated caption (populated by Layer 3).
    var caption: String?
    /// OCR text fallback (populated by Layer 4, only for nodes that needed it).
    var ocrText: String?
}

/// Complete screen context payload — lightweight JSON, no images.
struct ScreenContextPayload: Codable {
    let appName: String
    let windowTitle: String?
    let axTree: AXNode?
    let visualCrops: [VisualCrop]
    let capturedAt: Date
    /// True if the AX tree was truncated (depth or node count ceiling hit).
    var axTruncated: Bool
    /// Total AX nodes traversed (before pruning).
    var axNodeCount: Int
}

// MARK: - Pipeline

/// 4-layer screen context extraction pipeline.
///
/// Layer 1: AX tree traversal — maps the accessibility hierarchy of the active app.
/// Layer 2: Selective visual cropping — only captures regions marked as image/custom roles.
/// Layer 3: ANE-backed captioning — VNGenerateImageCaptionsRequest for image descriptions.
/// Layer 4: Targeted Vision OCR — localized VNRecognizeTextRequest for canvases where
///          the AX tree returned empty but the node visually contains text.
///
/// All heavy work runs off the main thread. Results are cached with instant invalidation
/// on active window change via NSWorkspace notifications.
actor ScreenContextPipeline {
    static let shared = ScreenContextPipeline()

    // MARK: - Cache

    private var cachedPayload: ScreenContextPayload?
    private var cachedAppBundleID: String?
    private var cachedWindowID: CGWindowID?
    private var cacheTimestamp: Date?
    /// Maximum cache age before forced refresh (even on same window).
    private let cacheTTL: TimeInterval = 3.0

    // MARK: - Configuration

    /// Minimum width/height in points for an AX node to be included in the tree.
    private let minNodeSize: CGFloat = 10.0
    /// Maximum tree depth before truncation.
    private let maxDepth: Int = 12
    /// Maximum total AX nodes before truncation.
    private let maxNodeCount: Int = 500

    // MARK: - Pipeline Entry Point

    /// Capture the current screen context using the 4-layer pipeline.
    /// Returns nil if no active window can be resolved.
    func capture() async -> ScreenContextPayload? {
        // Resolve active window
        let (appName, windowTitle, windowID) = await ScreenCaptureService.getActiveWindowInfoAsync()
        guard let windowID = windowID, let appName = appName else {
            log("ScreenContextPipeline: No active window found")
            return nil
        }

        // Resolve bundle ID for cache key
        let bundleID = NSWorkspace.shared.frontmostApplication?.bundleIdentifier

        // Cache hit check
        if let bundleID = bundleID,
           let cached = cachedPayload,
           cachedAppBundleID == bundleID,
           cachedWindowID == windowID,
           let ts = cacheTimestamp,
           Date().timeIntervalSince(ts) < cacheTTL
        {
            return cached
        }

        // Capture window CGImage for Layers 2-4
        let screenCaptureService = ScreenCaptureService()
        let cgImage: CGImage?
        if #available(macOS 14.0, *) {
            switch await screenCaptureService.captureWindowCGImage(windowID: windowID) {
            case .success(let image): cgImage = image
            case .windowGone: cgImage = await screenCaptureService.captureActiveWindowCGImage()
            case .failed: cgImage = nil
            }
        } else {
            cgImage = await screenCaptureService.captureActiveWindowCGImage()
        }

        guard let windowImage = cgImage else {
            log("ScreenContextPipeline: Failed to capture window image")
            return nil
        }

        // Get window frame for coordinate mapping
        let windowFrame = await Self.getWindowFrame(windowID: windowID)
        let backingScaleFactor = await Self.getWindowBackingScale(windowID: windowID)

        // Run all layers off main thread
        let payload = await Task.detached(priority: .userInitiated) {
            return Self.runPipeline(
                appName: appName,
                windowTitle: windowTitle,
                windowImage: windowImage,
                windowFrame: windowFrame,
                backingScaleFactor: backingScaleFactor,
                windowID: windowID
            )
        }.value

        // Cache the result
        cachedPayload = payload
        cachedAppBundleID = bundleID
        cachedWindowID = windowID
        cacheTimestamp = Date()

        // Subscribe to window change for invalidation
        ensureWindowChangeObserver()

        return payload
    }

    /// Capture using a pre-existing CGImage (for PTT optimization — OCR runs during speech).
    /// The caller is responsible for resolving the active window info.
    func captureFromImage(
        _ cgImage: CGImage,
        appName: String,
        windowTitle: String?,
        windowID: CGWindowID
    ) async -> ScreenContextPayload? {
        let windowFrame = await Self.getWindowFrame(windowID: windowID)
        let backingScaleFactor = await Self.getWindowBackingScale(windowID: windowID)

        return await Task.detached(priority: .userInitiated) {
            return Self.runPipeline(
                appName: appName,
                windowTitle: windowTitle,
                windowImage: cgImage,
                windowFrame: windowFrame,
                backingScaleFactor: backingScaleFactor,
                windowID: windowID
            )
        }.value
    }

    /// Invalidate the cache (called on window change).
    func invalidateCache() {
        cachedPayload = nil
        cachedAppBundleID = nil
        cachedWindowID = nil
        cacheTimestamp = nil
    }

    // MARK: - Window Change Observer

    private var observerInstalled = false

    private func ensureWindowChangeObserver() {
        guard !observerInstalled else { return }
        observerInstalled = true
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { await self?.invalidateCache() }
        }
    }

    // MARK: - Pipeline Runner (non-isolated, runs off main thread)

    private nonisolated static func runPipeline(
        appName: String,
        windowTitle: String?,
        windowImage: CGImage,
        windowFrame: CGRect?,
        backingScaleFactor: CGFloat,
        windowID: CGWindowID
    ) -> ScreenContextPayload {
        let scale = backingScaleFactor > 0 ? backingScaleFactor : 2.0

        // Layer 1: Traverse accessibility tree
        var axTruncated = false
        var axNodeCount = 0
        let axTree = traverseAXTree(
            windowFrame: windowFrame,
            backingScaleFactor: scale,
            truncated: &axTruncated,
            nodeCount: &axNodeCount
        )

        // Collect nodes that need visual captioning
        let visualNodes = collectVisualNodes(from: axTree)

        // Layer 2: Selective visual cropping + Layer 3: ANE captioning + Layer 4: OCR fallback
        var visualCrops: [VisualCrop] = []
        for vn in visualNodes {
            guard let bounds = vn.bounds else { continue }

            // Crop the region from the window image
            guard let croppedImage = cropImage(windowImage, to: bounds) else { continue }

            var crop = VisualCrop(bounds: bounds, role: vn.role, caption: nil, ocrText: nil)

            // Layer 3: ANE captioning (macOS 14+)
            if #available(macOS 14.0, *), vn.needsCaption {
                let paddedImage = padToAspectRatio(croppedImage, targetRatio: 1.0)
                if let caption = generateCaption(paddedImage) {
                    crop.caption = caption
                }
            }

            // Layer 4: Targeted OCR for nodes where AX text was empty
            if vn.needsOCR {
                let ocrText = extractOCRText(croppedImage)
                if let text = ocrText, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    crop.ocrText = text
                }
            }

            visualCrops.append(crop)
        }

        return ScreenContextPayload(
            appName: appName,
            windowTitle: windowTitle,
            axTree: axTree,
            visualCrops: visualCrops,
            capturedAt: Date(),
            axTruncated: axTruncated,
            axNodeCount: axNodeCount
        )
    }

    // MARK: - Layer 1: AX Tree Traversal

    private struct VisualNode {
        let role: String
        let bounds: CGRect?
        let needsCaption: Bool
        let needsOCR: Bool
    }

    /// Collect all visual nodes (AXImage, AXUnknown, or nodes where text is empty but bounds exist).
    private static func collectVisualNodes(from root: AXNode?) -> [VisualNode] {
        guard let root = root else { return [] }
        var result: [VisualNode] = []
        collectVisualNodesRecursive(root, &result)
        return result
    }

    private static func collectVisualNodesRecursive(_ node: AXNode, _ result: inout [VisualNode]) {
        if node.needsVisualCaption, node.bounds != nil {
            let hasText = !(node.label?.isEmpty ?? true)
                || !(node.value?.isEmpty ?? true)
                || !(node.description?.isEmpty ?? true)
            result.append(VisualNode(
                role: node.role,
                bounds: node.bounds,
                needsCaption: true,
                needsOCR: !hasText  // Only OCR if AX didn't give us text
            ))
        }
        for child in node.children {
            collectVisualNodesRecursive(child, &result)
        }
    }

    /// Traverse the AX tree from the frontmost app's focused window.
    private nonisolated static func traverseAXTree(
        windowFrame: CGRect?,
        backingScaleFactor: CGFloat,
        truncated: inout Bool,
        nodeCount: inout Int
    ) -> AXNode? {
        guard let frontApp = NSWorkspace.shared.frontmostApplication else { return nil }
        let pid = frontApp.processIdentifier
        let appElement = AXUIElementCreateApplication(pid)

        var focusedWindow: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(
            appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow)
        guard result == .success, let windowElement = focusedWindow else { return nil }

        guard let windowElement = windowElement as? AXUIElement else { return nil }
        return traverseElement(
            windowElement,
            depth: 0,
            windowFrame: windowFrame,
            backingScaleFactor: backingScaleFactor,
            truncated: &truncated,
            nodeCount: &nodeCount
        )
    }

    private nonisolated static func traverseElement(
        _ element: AXUIElement,
        depth: Int,
        windowFrame: CGRect?,
        backingScaleFactor: CGFloat,
        truncated: inout Bool,
        nodeCount: inout Int
    ) -> AXNode {
        nodeCount += 1

        // Circuit breakers
        if depth > maxDepth || nodeCount > maxNodeCount {
            truncated = true
            return AXNode(
                role: "truncated",
                label: nil, value: nil, description: nil,
                children: [],
                bounds: nil,
                depth: depth,
                needsVisualCaption: false
            )
        }

        let role = getAXRole(element)
        let label = getAXString(element, attribute: kAXDescriptionAttribute as CFString)
            ?? getAXString(element, attribute: kAXTitleAttribute as CFString)
        let value = getAXString(element, attribute: kAXValueAttribute as CFString)
        let description = getAXString(element, attribute: kAXHelpAttribute as CFString)

        // Determine if this node needs visual captioning
        let needsVisualCaption = role == kAXImageRole
            || role == kAXUnknownRole
            || role == "AXCell"  // Cells often contain images

        // Get bounds
        let bounds = getAXBounds(element, role: role, windowFrame: windowFrame, backingScaleFactor: backingScaleFactor)

        // Prune tiny nodes (spacers, utility divs in Electron/browsers)
        if let b = bounds, (b.width < minNodeSize || b.height < minNodeSize) {
            return AXNode(
                role: role,
                label: label, value: value, description: description,
                children: [],  // Don't recurse into tiny nodes
                bounds: bounds,
                depth: depth,
                needsVisualCaption: needsVisualCaption
            )
        }

        // Get children
        var children: [AXNode] = []
        var childRefs: CFTypeRef?
        let childResult = AXUIElementCopyAttributeValue(
            element, kAXChildrenAttribute as CFString, &childRefs)

        let shouldRecurse = depth < maxDepth && nodeCount < maxNodeCount
        if childResult == .success, let childArray = childRefs as? [AXUIElement], shouldRecurse {
            for child in childArray {
                let childNode = traverseElement(
                    child,
                    depth: depth + 1,
                    windowFrame: windowFrame,
                    backingScaleFactor: backingScaleFactor,
                    truncated: &truncated,
                    nodeCount: &nodeCount
                )
                children.append(childNode)
            }
        }

        return AXNode(
            role: role,
            label: label, value: value, description: description,
            children: children,
            bounds: bounds,
            depth: depth,
            needsVisualCaption: needsVisualCaption
        )
    }

    // MARK: - AX Helpers

    private nonisolated static func getAXRole(_ element: AXUIElement) -> String {
        var roleValue: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(
            element, kAXRoleAttribute as CFString, &roleValue)
        guard result == .success, let role = roleValue as? String else {
            return "AXUnknown"
        }
        return role
    }

    private nonisolated static func getAXString(_ element: AXUIElement, attribute: CFString) -> String? {
        var value: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(element, attribute, &value)
        guard result == .success else { return nil }
        if let str = value as? String, !str.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return str
        }
        return nil
    }

    private nonisolated static func getAXBounds(
        _ element: AXUIElement,
        role: String,
        windowFrame: CGRect?,
        backingScaleFactor: CGFloat
    ) -> CGRect? {
        // Get position
        var positionValue: CFTypeRef?
        let posResult = AXUIElementCopyAttributeValue(
            element, kAXPositionAttribute as CFString, &positionValue)
        guard posResult == .success, let posRef = positionValue else { return nil }
        var position = CGPoint.zero
        guard AXValueGetValue(posRef as! AXValue, .cgPoint, &position) else { return nil }

        // Get size
        var sizeValue: CFTypeRef?
        let sizeResult = AXUIElementCopyAttributeValue(
            element, kAXSizeAttribute as CFString, &sizeValue)
        guard sizeResult == .success, let sizeRef = sizeValue else { return nil }
        var size = CGSize.zero
        guard AXValueGetValue(sizeRef as! AXValue, .cgSize, &size) else { return nil }

        // Validate dimensions
        guard size.width > 0, size.height > 0,
              position.x.isFinite, position.y.isFinite,
              size.width.isFinite, size.height.isFinite
        else { return nil }

        // AX coordinates are in global screen points (top-left origin, y-down).
        // Convert to window-local pixel coordinates (top-left origin, y-down).
        var localRect = CGRect(origin: position, size: size)

        if let wf = windowFrame {
            // Subtract window origin
            localRect.origin.x -= wf.origin.x
            localRect.origin.y -= wf.origin.y

            // Clamp to window bounds
            localRect = localRect.intersection(CGRect(origin: .zero, size: wf.size))
        }

        // Scale from points to pixels
        if backingScaleFactor > 0 {
            localRect.origin.x *= backingScaleFactor
            localRect.origin.y *= backingScaleFactor
            localRect.size.width *= backingScaleFactor
            localRect.size.height *= backingScaleFactor
        }

        // Validate the result isn't zero-sized or negative
        guard localRect.width >= 1 && localRect.height >= 1 else { return nil }

        return localRect
    }

    // MARK: - Layer 2: Selective Cropping

    /// Crop a region from a CGImage. The bounds are in image-local pixel coordinates (top-left origin, y-down).
    /// CGImage uses bottom-left origin (y-up), so we flip the Y coordinate.
    private nonisolated static func cropImage(_ image: CGImage, to bounds: CGRect) -> CGImage? {
        let imageHeight = CGFloat(image.height)

        // Convert from top-left (y-down) to bottom-left (y-up) coordinate system
        let flippedY = imageHeight - bounds.origin.y - bounds.height

        // Clamp to image bounds
        let clampedX = max(0, bounds.origin.x)
        let clampedY = max(0, flippedY)
        let clampedWidth = min(bounds.width, CGFloat(image.width) - clampedX)
        let clampedHeight = min(bounds.height, CGFloat(image.height) - clampedY)

        guard clampedWidth > 0, clampedHeight > 0 else { return nil }

        let cropRect = CGRect(x: clampedX, y: clampedY, width: clampedWidth, height: clampedHeight)
        return image.cropping(to: cropRect)
    }

    // MARK: - Layer 3: Caption Aspect Ratio Padding

    /// Pad an image to a target aspect ratio (width/height) centered with black borders.
    private nonisolated static func padToAspectRatio(_ image: CGImage, targetRatio: CGFloat) -> CGImage? {
        let imgW = CGFloat(image.width)
        let imgH = CGFloat(image.height)

        guard imgW > 0, imgH > 0 else { return nil }

        let currentRatio = imgW / imgH

        // Already close to target — no padding needed
        if abs(currentRatio - targetRatio) < 0.1 { return image }

        var paddedW = imgW
        var paddedH = imgH

        if currentRatio > targetRatio {
            // Image is too wide — pad top/bottom
            paddedH = imgW / targetRatio
        } else {
            // Image is too tall — pad left/right
            paddedW = imgH * targetRatio
        }

        let offsetX = (paddedW - imgW) / 2.0
        let offsetY = (paddedH - imgH) / 2.0

        guard let ctx = CGContext(
            data: nil,
            width: Int(paddedW),
            height: Int(paddedH),
            bitsPerComponent: image.bitsPerComponent,
            bytesPerRow: 0,
            space: image.colorSpace ?? CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: image.bitmapInfo.rawValue
        ) else { return nil }

        // Fill with black
        ctx.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1))
        ctx.fill(CGRect(x: 0, y: 0, width: paddedW, height: paddedH))

        // Draw image centered
        ctx.draw(image, in: CGRect(x: offsetX, y: offsetY, width: imgW, height: imgH))

        return ctx.makeImage()
    }

    /// Generate a caption using Apple's Neural Engine (macOS 14+).
    @available(macOS 14.0, *)
    private nonisolated static func generateCaption(_ image: CGImage) -> String? {
        let request = VNGenerateImageCaptionsRequest()
        let handler = VNImageRequestHandler(cgImage: image, options: [:])

        do {
            try handler.perform([request])
            guard let results = request.results, let caption = results.first else { return nil }
            // Filter out low-confidence captions
            if caption.confidence < 0.3 { return nil }
            return caption.caption
        } catch {
            return nil
        }
    }

    // MARK: - Layer 4: Targeted OCR

    /// Run localized OCR on a small cropped region. Uses .accurate since the crop is tiny.
    private nonisolated static func extractOCRText(_ image: CGImage) -> String? {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        request.recognitionLanguages = ["en-US"]

        let handler = VNImageRequestHandler(cgImage: image, options: [:])

        do {
            try handler.perform([request])
            guard let observations = request.results as? [VNRecognizedTextObservation],
                  !observations.isEmpty
            else { return nil }

            let texts = observations.compactMap { obs -> String? in
                guard let candidate = obs.topCandidates(1).first else { return nil }
                return candidate.string
            }
            return texts.joined(separator: " ")
        } catch {
            return nil
        }
    }

    // MARK: - Window Geometry Helpers

    /// Get the frame of a window in global screen coordinates.
    private nonisolated static func getWindowFrame(windowID: CGWindowID) async -> CGRect? {
        guard let windowList = CGWindowListCopyWindowInfo([.optionOnScreenOnly], windowID) as? [[String: Any]],
              let window = windowList.first,
              let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
              let x = bounds["X"], let y = bounds["Y"],
              let width = bounds["Width"], let height = bounds["Height"]
        else { return nil }
        return CGRect(x: x, y: y, width: width, height: height)
    }

    /// Get the backing scale factor for a window's screen.
    private nonisolated static func getWindowBackingScale(windowID: CGWindowID) async -> CGFloat {
        guard let windowList = CGWindowListCopyWindowInfo([.optionOnScreenOnly], windowID) as? [[String: Any]],
              let window = windowList.first,
              let screenBounds = window[kCGWindowBounds as String] as? [String: CGFloat],
              let x = screenBounds["X"], let y = screenBounds["Y"]
        else { return 2.0 }

        let windowCenter = CGPoint(x: x + 50, y: y + 50)  // Safe: even edge windows have >50px
        for screen in NSScreen.screens {
            if screen.frame.contains(windowCenter) {
                return screen.backingScaleFactor
            }
        }
        return NSScreen.main?.backingScaleFactor ?? 2.0
    }

    // MARK: - JSON Serialization

    /// Convert the payload to a compact JSON string suitable for LLM system prompts.
    nonisolated func toPromptContext(_ payload: ScreenContextPayload) -> String {
        var lines: [String] = []
        lines.append("App: \(payload.appName)")
        if let title = payload.windowTitle, !title.isEmpty {
            lines.append("Window: \(title)")
        }

        // AX tree as structured text
        if let tree = payload.axTree {
            lines.append("")
            lines.append("UI Hierarchy:")
            if payload.axTruncated {
                lines.append("(tree truncated at \(payload.axNodeCount) nodes)")
            }
            formatAXNode(tree, indent: 0, into: &lines)
        }

        // Visual crops with captions
        if !payload.visualCrops.isEmpty {
            lines.append("")
            lines.append("Visual Elements:")
            for (i, crop) in payload.visualCrops.enumerated() {
                var desc = "  [\(i)] \(crop.role)"
                if let caption = crop.caption {
                    desc += " — \(caption)"
                }
                if let ocr = crop.ocrText {
                    desc += " — text: \"\(ocr)\""
                }
                lines.append(desc)
            }
        }

        return lines.joined(separator: "\n")
    }

    private nonisolated func formatAXNode(_ node: AXNode, indent: Int, into lines: inout [String]) {
        let prefix = String(repeating: "  ", count: indent)
        var parts: [String] = [node.role]

        if let label = node.label, !label.isEmpty {
            parts.append("\"\(label)\"")
        }
        if let value = node.value, !value.isEmpty {
            parts.append("= \(value)")
        }

        lines.append(prefix + parts.joined(separator: " "))

        for child in node.children {
            formatAXNode(child, indent: indent + 1, into: &lines)
        }
    }
}
