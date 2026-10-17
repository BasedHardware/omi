/// One presentation lifetime. Native views receive data, never auth credentials.
/// Every asynchronous read is checked before and after its existing service call.
class NativeReadSession {
  NativeReadSession({required this.isCurrent});

  final bool Function() isCurrent;
  bool _disposed = false;

  bool get active => !_disposed && isCurrent();

  Future<T?> read<T>(Future<T?> Function() fetch) async {
    if (!active) return null;
    final result = await fetch();
    return active ? result : null;
  }

  void dispose() => _disposed = true;
}
