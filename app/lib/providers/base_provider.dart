import 'package:flutter/material.dart';

class BaseProvider extends ChangeNotifier {
  bool loading = false;

  void changeLoadingState() {
    loading = !loading;
    notifyListeners();
  }
}
