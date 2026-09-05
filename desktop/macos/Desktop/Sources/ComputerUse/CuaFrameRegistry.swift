import CoreGraphics
import Foundation

/// The pictures the model has recently been shown, so a coordinate it names in
/// one of them can be turned back into a point on the desk.
///
/// A computer-use loop is look, then act: the model answers in the space of the
/// last screenshot because that is the only space it can see. Keeping the frame
/// it saw is what makes "click 412, 288" mean the same thing to both sides.
///
/// Four frames, because a loop routinely captures two displays and a window
/// before acting, and an id that has aged out is reported as unknown rather than
/// silently resolved against a different frame — a wrong click is worse than a
/// refused one.
final class CuaFrameRegistry: @unchecked Sendable {
  static let shared = CuaFrameRegistry()

  private let lock = NSLock()
  private var frames: [(id: String, geometry: CuaFrameGeometry)] = []
  private var counter = 0

  @discardableResult
  func store(_ geometry: CuaFrameGeometry) -> String {
    lock.lock()
    defer { lock.unlock() }
    counter += 1
    let id = "frame-\(counter)"
    frames.append((id, geometry))
    if frames.count > 4 { frames.removeFirst(frames.count - 4) }
    return id
  }

  func geometry(id: String) -> CuaFrameGeometry? {
    lock.lock()
    defer { lock.unlock() }
    return frames.first { $0.id == id }?.geometry
  }

  func latest() -> (id: String, geometry: CuaFrameGeometry)? {
    lock.lock()
    defer { lock.unlock() }
    return frames.last
  }

  func reset() {
    lock.lock()
    frames.removeAll()
    counter = 0
    lock.unlock()
  }
}
