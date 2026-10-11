class StartupErrorRouter {
  StartupErrorRouter({required this.report});

  final void Function(Object error, StackTrace stack, {required bool fatal, required String origin}) report;

  bool _startupComplete = false;

  void beginStartup() {
    _startupComplete = false;
  }

  void completeStartup() {
    _startupComplete = true;
  }

  void handleZoneError(Object error, StackTrace stack) {
    final startupComplete = _startupComplete;
    report(error, stack, fatal: !startupComplete, origin: startupComplete ? 'uncaught_async' : 'boot');
  }

  bool handlePlatformError(Object error, StackTrace stack) {
    handleZoneError(error, stack);
    return true;
  }
}
