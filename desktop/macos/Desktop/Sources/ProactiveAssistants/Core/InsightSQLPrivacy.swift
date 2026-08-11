import Foundation

enum InsightSQLPrivacy {
  static func filtered(_ query: String, excludedApps: Set<String>) -> String {
    guard !excludedApps.isEmpty else { return query }
    let quoted = excludedApps.sorted().map { "'\($0.replacingOccurrences(of: "'", with: "''"))'" }
      .joined(separator: ",")
    return query.replacingOccurrences(
      of: #"\bscreenshots\b"#,
      with: "(SELECT * FROM screenshots WHERE appName NOT IN (\(quoted))) AS screenshots",
      options: [.regularExpression, .caseInsensitive])
  }
}
