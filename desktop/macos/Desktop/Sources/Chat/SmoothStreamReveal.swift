import Foundation

enum SmoothStreamReveal {
  static let msPerCharacter: Double = 5
  static let catchUpTicks: Double = 4

  static func step(remaining: Int, elapsedMs: Double) -> Int {
    guard remaining > 0 else { return 0 }
    let base = elapsedMs / msPerCharacter
    let catchUp = Double(remaining) / catchUpTicks
    let step = Int(max(base, catchUp).rounded(.up))
    return min(remaining, max(1, step))
  }
}
