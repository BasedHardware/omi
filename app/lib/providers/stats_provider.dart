import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/models/user_stats.dart';

class StatsProvider with ChangeNotifier {
  UserStats? _stats;
  UserStats? get stats => _stats;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  String? _error;
  String? get error => _error;

  Future<void> loadStats() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _stats = await getUserStats();
      if (_stats == null) {
        _error = 'Failed to load stats';
      }
    } catch (e) {
      _error = 'Failed to load stats';
    }

    _isLoading = false;
    notifyListeners();
  }
}
