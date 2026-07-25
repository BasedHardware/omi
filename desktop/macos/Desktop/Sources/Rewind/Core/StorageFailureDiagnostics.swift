import Foundation
import GRDB

/// Produces the bounded storage context attached to Rewind durability failures.
/// It deliberately projects only volume/file measurements and SQLite/POSIX codes;
/// filesystem paths and error descriptions remain local-only.
enum StorageFailureDiagnostics {
  static func context(
    pathClass: String,
    containingURL: URL,
    databaseURL: URL?,
    error: Error?,
    appIsTerminating: Bool,
    fileManager: FileManager = .default
  ) -> DesktopErrorDiagnosticContext {
    let volume = (try? fileManager.attributesOfFileSystem(forPath: containingURL.path)) ?? [:]
    let databaseSize = databaseURL.flatMap { url -> Int64? in
      let attributes = try? fileManager.attributesOfItem(atPath: url.path)
      return (attributes?[.size] as? NSNumber)?.int64Value
    }
    let sqlite = error as? DatabaseError
    let underlying = underlyingNSError(from: error)

    var values: [String: any Sendable] = [
      "path_class": pathClass,
      "volume_free_bytes": (volume[.systemFreeSize] as? NSNumber)?.int64Value ?? -1,
      "volume_total_bytes": (volume[.systemSize] as? NSNumber)?.int64Value ?? -1,
      "database_file_size_bytes": databaseSize ?? -1,
      "app_terminating": appIsTerminating,
      "error_domain": underlying?.domain ?? "unknown",
      "error_code": underlying?.code ?? -1,
      "sqlite_result_code": sqlite.map { $0.resultCode.rawValue } ?? -1,
      "sqlite_extended_result_code": sqlite.map { $0.extendedResultCode.rawValue } ?? -1,
    ]
    // Keep this allow-list explicit. It is the scrub boundary for Sentry context.
    values = values.filter { key, _ in
      [
        "path_class", "volume_free_bytes", "volume_total_bytes", "database_file_size_bytes",
        "app_terminating", "error_domain", "error_code", "sqlite_result_code",
        "sqlite_extended_result_code",
      ].contains(key)
    }
    return DesktopErrorDiagnosticContext(values)
  }

  private static func underlyingNSError(from error: Error?) -> NSError? {
    guard let error else { return nil }
    let nsError = error as NSError
    if let nested = nsError.userInfo[NSUnderlyingErrorKey] as? NSError {
      return nested
    }
    return nsError
  }
}
