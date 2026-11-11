import 'dart:io';

/// Removes a test's temporary directory if it still exists.
///
/// Boot suites tear down directories that can already be gone (temp cleanup, a
/// prior teardown). Only [PathNotFoundException] — the check-then-delete race —
/// is absorbed; any other failure still fails the test.
Future<void> deleteTempDirQuietly(Directory directory) async {
  if (await directory.exists()) {
    try {
      await directory.delete(recursive: true);
    } on PathNotFoundException {
      // Removed between the exists() check and the delete.
    }
  }
}
