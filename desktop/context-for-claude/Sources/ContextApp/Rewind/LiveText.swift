import AppKit
import ContextCore
import SwiftUI
import Vision

/// Text detected in the displayed frame, with the boxes it was found in.
///
/// Our capture pipeline runs Vision on every frame but keeps **only the joined string** —
/// `ScreenPipeline.recognizeText` maps observations to `topCandidates(1).first?.string` and throws
/// every `boundingBox` away. So the geometry Live Text needs does not exist in the database and
/// cannot be recovered from it.
///
/// The only two honest options were to store boxes at capture time or to recompute them on demand.
/// Recomputing wins here and it is not a compromise: capture happens every three seconds forever and
/// Live Text is a button someone presses occasionally, so storing per-frame box geometry for millions
/// of frames to serve a rare request is the wrong trade — and re-running Vision on one 1600 px HEIC
/// is well under a second. What was *not* an option was deriving highlight rectangles from the stored
/// string: laying out `ocrText` over the image would draw boxes that look authoritative and sit in
/// the wrong places, which is worse than no feature.
///
/// This is exactly what the spec's "dims when no text has been detected yet" describes: the control
/// is dim because nothing has been detected *yet* — no pass has run — and lights up once one has.
struct LiveTextResult: Sendable, Equatable {
    /// The pixel size of the image the boxes were measured against. Highlights are positioned
    /// relative to this, never to the file on disk, so a re-decode at a different size cannot
    /// silently shift them.
    let imageSize: CGSize
    let blocks: [LiveTextBlock]

    var isEmpty: Bool { blocks.isEmpty }
}

/// One recognised run of text and where it sits.
struct LiveTextBlock: Sendable, Equatable, Identifiable {
    let id: Int
    let text: String
    /// Vision's own normalised rect: origin **bottom-left**, 0–1 on both axes.
    let boundingBox: CGRect

    /// The rect in top-left origin coordinates, scaled to `imageSize`.
    ///
    /// The Y flip is ported from the Omi desktop implementation
    /// (`Rewind/Core/RewindOCRService.swift:17`) because it is the one line here that is easy to get
    /// subtly wrong. Vision measures from the bottom-left; every drawing system this lands in
    /// measures from the top-left. The flip is `1 - y - height` and **not** `1 - y`: the latter maps
    /// the box's bottom edge to the new top edge, so every highlight sits one box-height too high —
    /// a bug that looks like a rounding error on a line of small text and like nonsense on a heading.
    func screenRect(for imageSize: CGSize) -> CGRect {
        // Vision uses bottom-left origin, convert to top-left origin for display
        let screenX = boundingBox.origin.x * imageSize.width
        let screenY = (1.0 - boundingBox.origin.y - boundingBox.height) * imageSize.height  // Flip Y
        let screenWidth = boundingBox.width * imageSize.width
        let screenHeight = boundingBox.height * imageSize.height
        return CGRect(x: screenX, y: screenY, width: screenWidth, height: screenHeight)
    }
}

/// Runs a boxed recognition pass over one stored frame, off the main thread.
enum LiveTextRecognizer {

    /// Recognises text in the HEIC at `path`.
    ///
    /// Deliberately mirrors `ScreenPipeline.recognizeText`'s configuration — `.accurate`,
    /// `en-US`, `VNRecognizeTextRequestRevision3`, `minimumTextHeight = 0` — so what is highlighted
    /// here is the same text the database was indexed on. A different revision or a different
    /// minimum height would highlight a different set of words than `recall` can find, and the user
    /// would be looking at a discrepancy with no way to explain it.
    ///
    /// Unlike capture, the result is **not** scrubbed through `Redaction`. That is correct rather
    /// than an oversight: nothing here is stored, searched, or handed to a model — the boxes are
    /// drawn over the pixels the user is already looking at, and a credential visible in the image
    /// is already visible. Scrubbing would only misalign the boxes from the glyphs beneath them.
    static func recognize(path: String) async -> LiveTextResult? {
        await Task.detached(priority: .userInitiated) { () -> LiveTextResult? in
            autoreleasepool { () -> LiveTextResult? in
                let url = URL(fileURLWithPath: path)
                guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
                    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
                else { return nil }

                let sink = BoxSink()
                let request = VNRecognizeTextRequest { request, error in
                    if error != nil { return }
                    guard let observations = request.results as? [VNRecognizedTextObservation] else {
                        return
                    }
                    // Defensive copy for the same reason capture makes one: Vision hands back a
                    // bridged NSArray whose buffer can be released underneath an enumeration, which
                    // traps the process rather than throwing (omi #5891, #5151).
                    sink.observations = Array(observations)
                }
                request.recognitionLevel = .accurate
                request.usesLanguageCorrection = true
                request.recognitionLanguages = ["en-US"]
                request.revision = VNRecognizeTextRequestRevision3
                request.minimumTextHeight = 0

                do {
                    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
                } catch {
                    return nil
                }

                let blocks = sink.observations.enumerated().compactMap {
                    index, observation -> LiveTextBlock? in
                    guard let text = observation.topCandidates(1).first?.string,
                        !text.isEmpty
                    else { return nil }
                    let box = observation.boundingBox
                    // A non-finite rect would propagate NaN into a SwiftUI frame and trap on layout.
                    guard box.origin.x.isFinite, box.origin.y.isFinite,
                        box.width.isFinite, box.height.isFinite
                    else { return nil }
                    return LiveTextBlock(id: index, text: text, boundingBox: box)
                }

                return LiveTextResult(
                    imageSize: CGSize(width: image.width, height: image.height),
                    blocks: blocks)
            }
        }.value
    }

    /// Vision writes its observations synchronously inside `perform`, before it returns, so this box
    /// is never touched from two threads despite the block signature permitting it.
    private final class BoxSink: @unchecked Sendable {
        var observations: [VNRecognizedTextObservation] = []
    }
}

/// Draws the detected text boxes over the displayed frame, and makes each one selectable.
///
/// The container is almost never the image's aspect ratio, so the highlight layer has to reproduce
/// exactly the letterboxing `.aspectRatio(contentMode: .fit)` applied to the image — otherwise every
/// box is offset by the size of the black bars. That geometry is computed here rather than guessed.
struct LiveTextOverlay: View {
    let result: LiveTextResult
    /// The size of the box the frame is being drawn inside.
    let containerSize: CGSize

    /// Where and how large the image actually ended up inside `containerSize` under `.fit`.
    private var layout: (size: CGSize, offset: CGSize) {
        let imageAspect = result.imageSize.width / max(result.imageSize.height, 1)
        let containerAspect = containerSize.width / max(containerSize.height, 1)
        if imageAspect > containerAspect {
            // Wider than the container: width is the binding constraint, bars top and bottom.
            let width = containerSize.width
            let height = width / max(imageAspect, 0.0001)
            return (CGSize(width: width, height: height),
                    CGSize(width: 0, height: (containerSize.height - height) / 2))
        }
        let height = containerSize.height
        let width = height * imageAspect
        return (CGSize(width: width, height: height),
                CGSize(width: (containerSize.width - width) / 2, height: 0))
    }

    var body: some View {
        let placed = layout
        ZStack(alignment: .topLeading) {
            ForEach(result.blocks) { block in
                // Measured against a unit image, then scaled — so the normalised rect is converted
                // once and the letterbox offset is applied once.
                let unit = block.screenRect(for: CGSize(width: 1, height: 1))
                Rectangle()
                    .fill(Ink.accent.opacity(0.22))
                    .overlay(Rectangle().strokeBorder(Ink.accent.opacity(0.85), lineWidth: 1))
                    .frame(
                        width: max(1, unit.width * placed.size.width),
                        height: max(1, unit.height * placed.size.height))
                    .position(
                        x: placed.offset.width + unit.midX * placed.size.width,
                        y: placed.offset.height + unit.midY * placed.size.height)
                    .help(block.text)
                    .accessibilityLabel(Text(block.text))
            }
        }
        .frame(width: containerSize.width, height: containerSize.height, alignment: .topLeading)
        .allowsHitTesting(true)
    }
}
