// Uses real disk writes with one-shot file-operation failures to exercise
// journal custody and the pending watermark after accepted batch appends.
import 'dart:io';

class FaultingWalWriter implements RandomAccessFile {
  FaultingWalWriter(File file) : _source = file.openSync(mode: FileMode.append);
  final RandomAccessFile _source;
  bool failFlush = false;
  bool failClose = false;
  bool failWrite = false;

  @override
  void writeFromSync(List<int> buffer, [int start = 0, int? end]) {
    if (failWrite) {
      failWrite = false;
      throw const FileSystemException('injected write failure');
    }
    _source.writeFromSync(buffer, start, end);
  }

  @override
  void flushSync() {
    if (failFlush) {
      failFlush = false;
      throw const FileSystemException('injected flush failure');
    }
    _source.flushSync();
  }

  @override
  void closeSync() {
    if (failClose) {
      failClose = false;
      throw const FileSystemException('injected close failure');
    }
    _source.closeSync();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
