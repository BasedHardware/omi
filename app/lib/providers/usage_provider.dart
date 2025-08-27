import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';

class UsageProvider with ChangeNotifier {
  UserSubscriptionResponse? _subscription;
  UserSubscriptionResponse? get subscription => _subscription;
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

  bool _isUsageLoading = false;
  bool _isSubscriptionLoading = false;
  bool get isLoading => _isUsageLoading || _isSubscriptionLoading;

  String? _error;
  String? get error => _error;

  bool _forceOutOfCredits = false;

  bool get isOutOfCredits {
    if (_forceOutOfCredits) return true;
    if (_subscription == null) return false;
    if (_subscription!.subscription.plan == PlanType.unlimited) return false;
    // For basic plan, check if used is >= limit and limit is not 0 (unlimited).
    if (_subscription!.transcriptionSecondsLimit > 0 &&
        _subscription!.transcriptionSecondsUsed >= _subscription!.transcriptionSecondsLimit) {
      return true;
    }
    return false;
  }

  Future<void> markAsOutOfCreditsAndRefresh() async {
    if (!_forceOutOfCredits) {
      _forceOutOfCredits = true;
      notifyListeners(); // Immediate UI update
    }
    await fetchSubscription(); // Sync with backend
  }

  Future<void> fetchSubscription() async {
    if (_isSubscriptionLoading) return;

    _isSubscriptionLoading = true;
    _error = null;
    notifyListeners();

    try {
      _subscription = await getUserSubscription();
    } catch (e) {
      _error = 'Failed to load subscription data. Please try again later.';
      debugPrint('Failed to fetch subscription: $e');
    } finally {
      _isSubscriptionLoading = false;
      _forceOutOfCredits = false; // Reset optimistic flag
      notifyListeners();
    }
  }

  Future<void> fetchUsageStats({required String period}) async {
    if (_isUsageLoading) return;

    _isUsageLoading = true;
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
      _isUsageLoading = false;
      notifyListeners();
    }
  }
}
