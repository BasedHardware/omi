import 'package:flutter/material.dart';

class BaseProvider extends ChangeNotifier {
  bool loading = false;

  void setLoadingState(bool value) {
    loading = value;
    notifyListeners();
  }
}
