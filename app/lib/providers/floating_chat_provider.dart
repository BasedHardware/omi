import 'package:flutter/foundation.dart';

class FloatingChatProvider extends ChangeNotifier {
  bool _isWindowVisible = false;
  bool get isWindowVisible => _isWindowVisible;

  void showWindow() {
    if (!_isWindowVisible) {
      _isWindowVisible = true;
      notifyListeners();
    }
  }

  void hideWindow() {
    if (_isWindowVisible) {
      _isWindowVisible = false;
      notifyListeners();
    }
  }

  void toggleWindow() {
    _isWindowVisible = !_isWindowVisible;
    notifyListeners();
  }
}
