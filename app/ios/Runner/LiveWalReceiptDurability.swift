import Foundation
import Darwin

enum LiveWalReceiptDurabilityError: Error {
  case invalidPath
  case syncFailed(String)
}

enum LiveWalReceiptDurability {
  static func syncDirectory(_ rawPath: String, documentsURL: URL) throws {
    let documents = documentsURL.resolvingSymlinksInPath().standardizedFileURL.path
    let directory = URL(fileURLWithPath: rawPath).resolvingSymlinksInPath().standardizedFileURL.path
    var isDirectory: ObjCBool = false
    guard directory == documents || directory.hasPrefix(documents + "/"),
          FileManager.default.fileExists(atPath: directory, isDirectory: &isDirectory),
          isDirectory.boolValue else {
      throw LiveWalReceiptDurabilityError.invalidPath
    }

    let descriptor = Darwin.open(directory, O_RDONLY | O_DIRECTORY)
    guard descriptor >= 0 else {
      throw LiveWalReceiptDurabilityError.syncFailed(String(cString: strerror(errno)))
    }
    let status = Darwin.fsync(descriptor)
    let syncError = errno
    Darwin.close(descriptor)
    guard status == 0 else {
      throw LiveWalReceiptDurabilityError.syncFailed(String(cString: strerror(syncError)))
    }
  }
}
