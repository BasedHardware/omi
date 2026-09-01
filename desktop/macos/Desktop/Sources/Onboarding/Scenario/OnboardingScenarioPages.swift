import AppKit
import Foundation

struct OnboardingScenarioDates: Equatable {
  let deliveryDate: Date
  let returnDate: Date
  let saleEndDate: Date

  static func make(now: Date = Date(), calendar: Calendar = .current) -> Self {
    let start = calendar.startOfDay(for: now)
    return Self(
      deliveryDate: calendar.date(byAdding: .day, value: 3, to: start) ?? start,
      returnDate: calendar.date(byAdding: .day, value: 4, to: start) ?? start,
      saleEndDate: calendar.date(byAdding: .day, value: 6, to: start) ?? start
    )
  }

  func atNineAM(_ date: Date, calendar: Calendar = .current) -> Date {
    calendar.date(bySettingHour: 9, minute: 0, second: 0, of: date) ?? date
  }
}

struct OnboardingScenarioPageContext: Equatable {
  let name: String
  let dates: OnboardingScenarioDates
  let nonce: String

  init(name: String, dates: OnboardingScenarioDates, nonce: String = UUID().uuidString.lowercased()) {
    self.name = name
    self.dates = dates
    self.nonce = nonce
  }

  private static let dateFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "EEE, MMM d"
    return formatter
  }()

  private static let weekdayFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "EEEE"
    return formatter
  }()

  var deliveryDateText: String { Self.dateFormatter.string(from: dates.deliveryDate) }
  var returnDateText: String { Self.dateFormatter.string(from: dates.returnDate) }
  var saleEndDateText: String { Self.dateFormatter.string(from: dates.saleEndDate) }
  var deliveryWeekday: String { Self.weekdayFormatter.string(from: dates.deliveryDate) }
  var saleEndWeekday: String { Self.weekdayFormatter.string(from: dates.saleEndDate) }

  var prefilledNote: String {
    "Hey Sam — got the lamp we talked about. Arrives \(deliveryWeekday). I'll send you the link by \(deliveryWeekday) so you can grab one before the sale ends \(saleEndWeekday)."
  }

  var replacements: [String: String] {
    [
      "{{name}}": name,
      "{{deliveryDate}}": deliveryDateText,
      "{{returnDate}}": returnDateText,
      "{{saleEndDate}}": saleEndDateText,
      "{{deliveryWeekday}}": deliveryWeekday,
      "{{saleEndWeekday}}": saleEndWeekday,
      "{{nonce}}": nonce,
    ]
  }
}

struct OnboardingScenarioPageLocator {
  let roots: [URL]

  func url(for fileName: String) -> URL? {
    for root in roots {
      for candidate in [
        root.appendingPathComponent(fileName),
        root.appendingPathComponent("onboarding-pages", isDirectory: true).appendingPathComponent(fileName),
      ] where FileManager.default.isReadableFile(atPath: candidate.path) {
        return candidate
      }
    }
    return nil
  }

  static let bundled = OnboardingScenarioPageLocator(roots: OmiSoundAssetLocator.bundledRoots())
}

enum OnboardingScenarioPageRenderer {
  static func render(template: String, context: OnboardingScenarioPageContext) -> String {
    context.replacements.reduce(template) { partial, replacement in
      partial.replacingOccurrences(of: replacement.key, with: htmlEscaped(replacement.value))
    }
  }

  static func render(fileName: String, context: OnboardingScenarioPageContext) throws -> String {
    guard let source = OnboardingScenarioPageLocator.bundled.url(for: fileName) else {
      throw CocoaError(.fileNoSuchFile)
    }
    return render(template: try String(contentsOf: source, encoding: .utf8), context: context)
  }

  static func writeAndOpen(
    fileName: String,
    context: OnboardingScenarioPageContext,
    directory: URL,
    open: (URL) -> Bool = NSWorkspace.shared.open
  ) throws -> URL {
    let rendered = try render(fileName: fileName, context: context)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let destination = directory.appendingPathComponent(fileName)
    try rendered.write(to: destination, atomically: true, encoding: .utf8)
    _ = open(destination)
    return destination
  }

  private static func htmlEscaped(_ value: String) -> String {
    value
      .replacingOccurrences(of: "&", with: "&amp;")
      .replacingOccurrences(of: "<", with: "&lt;")
      .replacingOccurrences(of: ">", with: "&gt;")
      .replacingOccurrences(of: "\"", with: "&quot;")
  }
}
