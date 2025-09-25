import 'package:flutter/foundation.dart';
import 'package:omi/providers/message_provider.dart';

class FloatingChatWindowModel {
  final String id;
  final MessageProvider messageProvider;

  FloatingChatWindowModel({required this.id, required this.messageProvider});
}

class FloatingChatWindowManagerProvider with ChangeNotifier {
  final Map<String, FloatingChatWindowModel> _windows = {};

  Map<String, FloatingChatWindowModel> get windows => _windows;

  void createOrShowWindow(String id) {
    if (!_windows.containsKey(id)) {
      _windows[id] = FloatingChatWindowModel(
        id: id,
        messageProvider: MessageProvider(),
      );
      notifyListeners();
      debugPrint('Created new floating chat window with id: $id');
    }
  }

  void closeWindow(String id) {
    if (_windows.containsKey(id)) {
      // TODO: Dispose messageProvider if needed
      _windows.remove(id);
      notifyListeners();
      debugPrint('Closed floating chat window with id: $id');
    }
  }

  MessageProvider? getMessageProviderForWindow(String id) {
    return _windows[id]?.messageProvider;
  }
}
