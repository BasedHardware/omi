import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api/payment.dart';
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
  bool _isPaymentLoading = false;
  bool get isLoading => _isUsageLoading || _isSubscriptionLoading || _isPaymentLoading;

  String? _error;
  String? get error => _error;

  bool _forceOutOfCredits = false;

  // Payment-related state
  Map<String, dynamic>? _availablePlans;
  Map<String, dynamic>? get availablePlans => _availablePlans;
  bool _isLoadingPlans = false;
  bool get isLoadingPlans => _isLoadingPlans;

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

  /// Alias for fetchSubscription - refreshes subscription data from backend
  Future<void> refreshSubscription() => fetchSubscription();

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

  // Payment-related methods
  Future<void> loadAvailablePlans() async {
    if (_isLoadingPlans) return;

    _isLoadingPlans = true;
    _error = null;
    notifyListeners();

    try {
      final response = await getAvailablePlans();
      if (response != null) {
        _availablePlans = response;
      } else {
        _error = 'Failed to load available plans. Please try again later.';
      }
    } catch (e) {
      _error = 'Failed to load available plans. Please try again later.';
      debugPrint('Error loading available plans: $e');
    } finally {
      _isLoadingPlans = false;
      notifyListeners();
    }
  }

  Future<bool> cancelUserSubscription() async {
    if (_isPaymentLoading) return false;

    _isPaymentLoading = true;
    _error = null;
    notifyListeners();

    try {
      final success = await cancelSubscription();
      if (success) {
        await fetchSubscription();
        await loadAvailablePlans();
      }
      return success;
    } catch (e) {
      _error = 'Failed to cancel subscription. Please try again later.';
      debugPrint('Error canceling subscription: $e');
      return false;
    } finally {
      _isPaymentLoading = false;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>?> upgradeUserSubscription({required String priceId}) async {
    if (_isPaymentLoading) return null;

    _isPaymentLoading = true;
    _error = null;
    notifyListeners();

    try {
      final result = await upgradeSubscription(priceId: priceId);
      if (result != null) {
        await fetchSubscription(); // Refresh subscription data
        await loadAvailablePlans(); // Refresh available plans
      }
      return result;
    } catch (e) {
      _error = 'Failed to upgrade subscription. Please try again later.';
      debugPrint('Error upgrading subscription: $e');
      return null;
    } finally {
      _isPaymentLoading = false;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>?> createUserCheckoutSession({required String priceId}) async {
    if (_isPaymentLoading) return null;

    _isPaymentLoading = true;
    _error = null;
    notifyListeners();

    try {
      final sessionData = await createCheckoutSession(priceId: priceId);
      return sessionData;
    } catch (e) {
      _error = 'Failed to create checkout session. Please try again later.';
      debugPrint('Error creating checkout session: $e');
      return null;
    } finally {
      _isPaymentLoading = false;
      notifyListeners();
    }
  }

  Future<Map<String, String>?> openCustomerPortal() async {
    if (_isPaymentLoading) return null;

    _isPaymentLoading = true;
    _error = null;
    notifyListeners();

    try {
      final sessionData = await createCustomerPortalSession();
      return sessionData;
    } catch (e) {
      _error = 'Failed to open customer portal. Please try again.';
      debugPrint('Error opening customer portal: $e');
      return null;
    } finally {
      _isPaymentLoading = false;
      notifyListeners();
    }
  }
}
