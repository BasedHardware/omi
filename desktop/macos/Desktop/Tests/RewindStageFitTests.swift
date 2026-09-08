import AppKit
import XCTest

@testable import Omi_Computer

/// Where Rewind's photograph lands on its stage, and therefore where the controls that belong to it
/// have to be.
///
/// **The defect this holds shut.** The timestamp pill, the zoom cluster and the two segment chevrons
/// are an overlay on the stage, so they used to pin to the *stage's* edges. That is right only while
/// the picture fills the stage, and it does not: a screen capture is around 1.8 wide while the stage
/// at the app's own default window width is around 2.55, so the picture is height-bound with a wide
/// band of empty glass down each side. The chevron then sat a long way from the frame it steps
/// through. Everything below is stated as a ratio or a relation rather than a measured point, so it
/// survives the next padding change and still fails if the fit stops being a fit.
final class RewindStageFitTests: XCTestCase {

  /// Shapes worth fitting: taller than wide, square, 4:3, 16:10, 16:9, the stage's own measured
  /// proportion, and something absurdly wide.
  private static let ratios: [CGFloat] = [0.5, 1, 4.0 / 3.0, 1.6, 16.0 / 9.0, 2.55, 4]

  /// Containers worth fitting into — one squat, one square-ish, one very wide.
  private static let containers: [CGSize] = [
    CGSize(width: 400, height: 800),
    CGSize(width: 600, height: 600),
    CGSize(width: 1_382, height: 541),
  ]

  private func image(ratio: CGFloat, height: CGFloat = 720) -> CGSize {
    CGSize(width: height * ratio, height: height)
  }

  private func aspect(_ size: CGSize) -> CGFloat { size.width / size.height }

  // MARK: - The fit is a fit

  func testThePictureKeepsItsShapeAtEveryAspectRatio() {
    for container in Self.containers {
      for ratio in Self.ratios {
        let rect = RewindStageFit.pictureRect(image: image(ratio: ratio), in: container)
        XCTAssertEqual(
          aspect(rect.size), ratio, accuracy: 0.001,
          "a \(ratio) picture in a \(container) stage must not be stretched")
      }
    }
  }

  func testThePictureStaysInsideTheStageAtEveryAspectRatio() {
    for container in Self.containers {
      for ratio in Self.ratios {
        let rect = RewindStageFit.pictureRect(image: image(ratio: ratio), in: container)
        let bounds = CGRect(origin: .zero, size: container)
        XCTAssertTrue(
          bounds.contains(rect),
          "a \(ratio) picture escaped a \(container) stage: \(rect)")
      }
    }
  }

  func testThePictureIsCentredAtEveryAspectRatio() {
    for container in Self.containers {
      for ratio in Self.ratios {
        let rect = RewindStageFit.pictureRect(image: image(ratio: ratio), in: container)
        XCTAssertEqual(
          rect.midX, container.width / 2, accuracy: 0.001,
          "the leftover width is split evenly, never banked on one side")
        XCTAssertEqual(rect.midY, container.height / 2, accuracy: 0.001)
      }
    }
  }

  /// A fit that does not touch its binding edge is a fit that threw room away.
  func testThePictureTouchesTheEdgeThatBindsIt() {
    for container in Self.containers {
      for ratio in Self.ratios {
        let rect = RewindStageFit.pictureRect(image: image(ratio: ratio), in: container)
        if ratio > aspect(container) {
          XCTAssertEqual(
            rect.width, container.width, accuracy: 0.001,
            "relatively wider than its stage — it must span the full width")
          XCTAssertLessThanOrEqual(rect.height, container.height + 0.001)
        } else {
          XCTAssertEqual(
            rect.height, container.height, accuracy: 0.001,
            "relatively taller than its stage — it must span the full height")
          XCTAssertLessThanOrEqual(rect.width, container.width + 0.001)
        }
      }
    }
  }

  func testAMatchingAspectRatioFillsTheStageExactly() {
    let container = CGSize(width: 1_200, height: 750)
    let rect = RewindStageFit.pictureRect(image: image(ratio: aspect(container)), in: container)

    XCTAssertEqual(rect.origin.x, 0, accuracy: 0.001)
    XCTAssertEqual(rect.origin.y, 0, accuracy: 0.001)
    XCTAssertEqual(rect.width, container.width, accuracy: 0.001)
    XCTAssertEqual(rect.height, container.height, accuracy: 0.001)
  }

  // MARK: - The band of empty glass, which is the whole point

  /// The shape the app is actually in: a screen capture on a stage far wider than it. The picture
  /// must be inset from the stage on both sides by a real amount — that inset is precisely the
  /// distance the chrome used to be wrong by.
  func testAScreenCaptureOnAWideStageLeavesGlassOnBothSidesOfIt() {
    let container = CGSize(width: 1_382, height: 541)
    let rect = RewindStageFit.pictureRect(image: image(ratio: 16.0 / 9.0), in: container)

    XCTAssertGreaterThan(
      rect.minX, container.width * 0.05,
      "a 16:9 picture on a 2.55 stage is height-bound and cannot start at the stage's edge")
    XCTAssertEqual(
      rect.minX, container.width - rect.maxX, accuracy: 0.001,
      "the two bands of glass are the same width")
  }

  /// The same claim in the coordinate space the chrome is actually laid out in.
  func testThePicturesEdgeIsNotTheStagesEdgeWhenTheShapesDisagree() {
    let stageSize = CGSize(width: 1_418, height: 565)
    let stage = RewindStageFit.stageRect(in: stageSize)
    let picture = RewindStageFit.pictureRectInStage(image: image(ratio: 16.0 / 9.0), stage: stageSize)

    XCTAssertGreaterThan(
      picture.minX - stage.minX, RewindStageFit.horizontalInset,
      "pinning a chevron to the stage would put it further from the frame than the stage's own inset")
    XCTAssertTrue(stage.contains(picture), "the picture still lives inside the stage")
  }

  // MARK: - The two coordinate spaces

  func testTheStageIsTheOuterRectLessItsOwnInsets() {
    let outer = CGSize(width: 1_000, height: 600)
    let stage = RewindStageFit.stageRect(in: outer)

    XCTAssertEqual(stage.minX, RewindStageFit.horizontalInset, accuracy: 0.001)
    XCTAssertEqual(stage.minY, RewindStageFit.verticalInset, accuracy: 0.001)
    XCTAssertEqual(stage.width, outer.width - RewindStageFit.horizontalInset * 2, accuracy: 0.001)
    XCTAssertEqual(stage.height, outer.height - RewindStageFit.verticalInset * 2, accuracy: 0.001)
  }

  func testTheStageNeverInvertsOnAWindowSmallerThanItsOwnInsets() {
    let stage = RewindStageFit.stageRect(in: CGSize(width: 4, height: 4))

    XCTAssertGreaterThanOrEqual(stage.width, 0)
    XCTAssertGreaterThanOrEqual(stage.height, 0)
  }

  /// `pictureRectInStage` is the composition of the two, and a caller cannot apply one and forget
  /// the other.
  func testThePictureInTheStageIsThePictureOffsetByTheInsets() {
    let outer = CGSize(width: 1_418, height: 565)
    for ratio in Self.ratios {
      let stage = RewindStageFit.stageRect(in: outer)
      let inner = RewindStageFit.pictureRect(image: image(ratio: ratio), in: stage.size)
      let composed = RewindStageFit.pictureRectInStage(image: image(ratio: ratio), stage: outer)

      XCTAssertEqual(composed.minX, inner.minX + stage.minX, accuracy: 0.001)
      XCTAssertEqual(composed.minY, inner.minY + stage.minY, accuracy: 0.001)
      XCTAssertEqual(composed.size.width, inner.size.width, accuracy: 0.001)
      XCTAssertEqual(composed.size.height, inner.size.height, accuracy: 0.001)
    }
  }

  // MARK: - Nothing degenerate escapes

  /// An empty rect at the stage's centre, not at its origin: before the first frame decodes there is
  /// no picture, and chrome that parks in the top-left corner for a frame and then jumps is worse
  /// than chrome that is simply not there yet.
  func testAnUndecodedImageIsAnEmptyRectAtTheCentre() {
    let container = CGSize(width: 800, height: 400)
    let rect = RewindStageFit.pictureRect(image: .zero, in: container)

    XCTAssertEqual(rect.width, 0)
    XCTAssertEqual(rect.height, 0)
    XCTAssertEqual(rect.midX, container.width / 2, accuracy: 0.001)
    XCTAssertEqual(rect.midY, container.height / 2, accuracy: 0.001)
  }

  func testNoDegenerateInputProducesNaNOrANegativeSize() {
    let degenerate: [(CGSize, CGSize)] = [
      (.zero, .zero),
      (.zero, CGSize(width: 100, height: 50)),
      (CGSize(width: 100, height: 50), .zero),
      (CGSize(width: -100, height: 50), CGSize(width: 100, height: 50)),
      (CGSize(width: 100, height: 50), CGSize(width: 100, height: -50)),
    ]

    for (image, container) in degenerate {
      let rect = RewindStageFit.pictureRect(image: image, in: container)
      XCTAssertFalse(rect.origin.x.isNaN || rect.origin.y.isNaN, "\(image) in \(container)")
      XCTAssertFalse(rect.size.width.isNaN || rect.size.height.isNaN, "\(image) in \(container)")
      XCTAssertGreaterThanOrEqual(rect.width, 0, "\(image) in \(container)")
      XCTAssertGreaterThanOrEqual(rect.height, 0, "\(image) in \(container)")
    }
  }
}
