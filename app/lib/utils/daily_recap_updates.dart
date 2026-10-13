import 'package:flutter/foundation.dart';

/// Invalidates mounted recap readers after recovery from another screen.
/// Carries no account data; readers reload through their authenticated API.
class DailyRecapUpdates extends ChangeNotifier {
  void recovered() => notifyListeners();
}

final dailyRecapUpdates = DailyRecapUpdates();
