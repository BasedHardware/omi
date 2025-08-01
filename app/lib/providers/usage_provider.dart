import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/models/user_usage.dart';

class UsageProvider with ChangeNotifier {
  UsageStats? _todayUsage;
  UsageStats? get todayUsage => _todayUsage;

  UsageStats? _monthlyUsage;
  UsageStats? get monthlyUsage => _monthlyUsage;

  UsageStats? _yearlyUsage;
  UsageStats? get yearlyUsage => _yearlyUsage;

  UsageStats? _allTimeUsage;
  UsageStats? get allTimeUsage => _allTimeUsage;

  List<UsageHistoryPoint>? _todayHistory;
  List<UsageHistoryPoint>? get todayHistory => _todayHistory;

  List<UsageHistoryPoint>? _monthlyHistory;
  List<UsageHistoryPoint>? get monthlyHistory => _monthlyHistory;

  List<UsageHistoryPoint>? _yearlyHistory;
  List<UsageHistoryPoint>? get yearlyHistory => _yearlyHistory;

  List<UsageHistoryPoint>? _allTimeHistory;
  List<UsageHistoryPoint>? get allTimeHistory => _allTimeHistory;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  String? _error;
  String? get error => _error;

  Future<void> fetchUsageStats({required String period}) async {
    if (_isLoading) return;

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await getUserUsage(period: period);
      if (response != null) {
        switch (period) {
          case 'today':
            _todayUsage = response.today;
            _todayHistory = response.history;
            break;
          case 'monthly':
            _monthlyUsage = response.monthly;
            _monthlyHistory = response.history;
            break;
          case 'yearly':
            _yearlyUsage = response.yearly;
            _yearlyHistory = response.history;
            break;
          case 'all_time':
            _allTimeUsage = response.allTime;
            _allTimeHistory = response.history;
            break;
        }
      } else {
        _error = 'Failed to load usage data. Please try again later.';
      }
    } catch (e) {
      _error = 'Failed to load usage data. Please try again later.';
      debugPrint('Failed to fetch usage stats: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
