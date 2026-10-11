import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/payment.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/utils/logger.dart';

typedef UsageRequest = Future<UserUsageResponse?> Function({required String period, required String? timeZone});

class UsageProvider with ChangeNotifier {
  UsageProvider({
    Future<String?> Function()? deviceTimeZone,
    UsageRequest? usageRequest,
    Future<UserSubscriptionResponse?> Function()? subscriptionRequest,
    DateTime Function()? now,
  })  : _deviceTimeZone = deviceTimeZone ?? getUsageDeviceTimeZone,
        _usageRequest = usageRequest ?? getUserUsage,
        _subscriptionRequest = subscriptionRequest ?? getUserSubscription,
        _now = now ?? DateTime.now;

  final Future<String?> Function() _deviceTimeZone;
  final UsageRequest _usageRequest;
  final Future<UserSubscriptionResponse?> Function() _subscriptionRequest;
  final DateTime Function() _now;
  String? _usageTimeZone;
  String? get usageTimeZone => _usageTimeZone;
  bool _usageTimeZoneResolved = false;
  int _timeZoneLookupGeneration = 0;
  int _usageTimeZoneGeneration = 0;
  Future<bool>? _timeZoneLookupInFlight;
  Future<void>? _usageFetchInFlight;

  UserSubscriptionResponse? _subscription;
  UserSubscriptionResponse? get subscription => _subscription;

  /// Defaults to true when the subscription response hasn't loaded yet, so a
  /// network blip doesn't silently hide paid surfaces from real users.
  bool get showSubscriptionUI => _subscription?.showSubscriptionUi ?? true;
  UsageStats? _todayUsage;
  int? _todayCacheKey;
  UsageStats? get todayUsage => _todayUsage;

  UsageStats? _monthlyUsage;
  int? _monthlyCacheKey;
  UsageStats? get monthlyUsage => _monthlyUsage;

  UsageStats? _yearlyUsage;
  int? _yearlyCacheKey;
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

  /// Bumped on [clearUserData] so responses from a previous session's
  /// in-flight fetches are discarded instead of repopulating cleared state.
  int _sessionGeneration = 0;

  // Chat quota derived from subscription response
  double get chatQuotaUsed => _subscription?.chatQuotaUsed ?? 0.0;
  String? get chatQuotaUnit => _subscription?.chatQuotaUnit;
  double get chatQuotaPercent => _subscription?.chatQuotaPercent ?? 0.0;
  bool get chatQuotaAllowed => _subscription?.chatQuotaAllowed ?? true;

  // Phone call feature — derived from subscription response. Only consult
  // the server-driven quota when the user is on the free tier or the
  // subscription UI is hidden; paid users with the paywall visible skip
  // straight to the existing unlimited behavior.
  PhoneCallQuota? get phoneCallQuota => _subscription?.phoneCallQuota;

  bool get _isPaidPlan => _subscription?.subscription.plan.isPaid ?? false;

  bool get canAccessPhoneCalls {
    if (_isPaidPlan) return true;
    final quota = phoneCallQuota;
    if (quota == null) return false;
    return quota.hasAccess;
  }

  bool get shouldShowPhoneCallsEntry {
    if (_isPaidPlan) return true;
    final quota = phoneCallQuota;
    final freeTierEnabled = quota != null && (quota.monthlyLimit ?? 0) > 0;
    if (freeTierEnabled) return true;
    // Free tier disabled → only surface the entry for real users who can still
    // see the paywall. Hidden-paywall builds (App Review) keep it off-screen.
    return showSubscriptionUI;
  }

  // Payment-related state
  Map<String, dynamic>? _availablePlans;
  Map<String, dynamic>? get availablePlans => _availablePlans;
  bool _isLoadingPlans = false;
  bool get isLoadingPlans => _isLoadingPlans;

  bool get isOutOfCredits {
    if (_forceOutOfCredits) return true;
    if (_subscription == null) return false;
    final plan = _subscription!.subscription.plan;
    // Plus is paid but metered, so it falls through to the usage check below.
    if (plan.hasUnlimitedTranscription) return false;
    // For metered plans, check if used is >= limit and limit is not 0 (unlimited).
    if (_subscription!.transcriptionSecondsLimit > 0 &&
        _subscription!.transcriptionSecondsUsed >= _subscription!.transcriptionSecondsLimit) {
      return true;
    }
    return false;
  }

  @visibleForTesting
  void debugSetSubscription(UserSubscriptionResponse? value) {
    _subscription = value;
    TranscriptionAllowanceCache.replace(value?.transcriptionAllowance);
    notifyListeners();
  }

  @visibleForTesting
  void debugSetAvailablePlans(Map<String, dynamic>? value) {
    _availablePlans = value;
    notifyListeners();
  }

  @visibleForTesting
  void debugSetUsage(String period, UsageStats stats, List<UsageHistoryPoint> history) {
    switch (period) {
      case 'today':
        _todayUsage = stats;
        _todayCacheKey = _periodKey(period);
        _todayHistory = history;
      case 'monthly':
        _monthlyUsage = stats;
        _monthlyCacheKey = _periodKey(period);
        _monthlyHistory = history;
      case 'yearly':
        _yearlyUsage = stats;
        _yearlyCacheKey = _periodKey(period);
        _yearlyHistory = history;
      case 'all_time':
        _allTimeUsage = stats;
        _allTimeHistory = history;
    }
    notifyListeners();
  }

  /// Wipes user-scoped state on logout so the next account doesn't inherit
  /// the previous account's subscription/usage (e.g. a stale Pro badge).
  void clearUserData() {
    TranscriptionAllowanceCache.clear();
    _subscription = null;
    _todayUsage = null;
    _todayCacheKey = null;
    _monthlyUsage = null;
    _monthlyCacheKey = null;
    _yearlyUsage = null;
    _yearlyCacheKey = null;
    _allTimeUsage = null;
    _todayHistory = null;
    _monthlyHistory = null;
    _yearlyHistory = null;
    _allTimeHistory = null;
    _usageTimeZone = null;
    _usageTimeZoneResolved = false;
    _timeZoneLookupGeneration++;
    _usageTimeZoneGeneration++;
    _timeZoneLookupInFlight = null;
    _usageFetchInFlight = null;
    _availablePlans = null;
    _forceOutOfCredits = false;
    _error = null;
    _sessionGeneration++;
    _isSubscriptionLoading = false;
    _isUsageLoading = false;
    _isPaymentLoading = false;
    _isLoadingPlans = false;
    notifyListeners();
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

    final generation = _sessionGeneration;
    _isSubscriptionLoading = true;
    _error = null;
    notifyListeners();

    try {
      final subscription = await _subscriptionRequest();
      if (generation != _sessionGeneration) return; // Session cleared mid-flight; discard stale response.
      if (subscription == null) {
        _error = 'Failed to load subscription data. Please try again later.';
        return;
      }
      _subscription = subscription;
      TranscriptionAllowanceCache.replace(subscription.transcriptionAllowance);
      await _releasePaywallOnDevicePin(subscription.subscription.plan);
      PlatformManager.instance.analytics.setSubscriptionTier(subscription.subscription.plan.name);
    } catch (e) {
      if (generation != _sessionGeneration) return;
      _error = 'Failed to load subscription data. Please try again later.';
      Logger.debug('Failed to fetch subscription: $e');
    } finally {
      if (generation == _sessionGeneration) {
        _isSubscriptionLoading = false;
        _forceOutOfCredits = false; // Reset optimistic flag
        notifyListeners();
      }
    }
  }

  /// The paywall's "switch to free" persists on-device STT with raw audio off, and a persisted
  /// Custom STT outranks the plan. Once the user pays, release that pin so capture returns to Omi
  /// (and audio reaches Omi again, e.g. for audio-bytes webhooks) instead of staying on-device.
  Future<void> _releasePaywallOnDevicePin(PlanType plan) async {
    final prefs = SharedPreferencesUtil();
    final pinned = prefs.paywallOnDeviceSttConfigId;
    if (!plan.isPaid || pinned.isEmpty) return;
    if (prefs.customSttConfig.sttConfigId == pinned) {
      await prefs.saveCustomSttConfig(CustomSttConfig.defaultConfig);
    }
    prefs.paywallOnDeviceSttConfigId = '';
  }

  /// Alias for fetchSubscription - refreshes subscription data from backend
  Future<void> refreshSubscription() => fetchSubscription();

  int _periodKey(String period) {
    final date = _now();
    return switch (period) {
      'today' => date.year * 10000 + date.month * 100 + date.day,
      'monthly' => date.year * 100 + date.month,
      'yearly' => date.year,
      _ => 0,
    };
  }

  bool _expireCalendarCaches() {
    var expired = false;
    if (_todayUsage != null && _todayCacheKey != _periodKey('today')) {
      _todayUsage = null;
      _todayHistory = null;
      _todayCacheKey = null;
      expired = true;
    }
    if (_monthlyUsage != null && _monthlyCacheKey != _periodKey('monthly')) {
      _monthlyUsage = null;
      _monthlyHistory = null;
      _monthlyCacheKey = null;
      expired = true;
    }
    if (_yearlyUsage != null && _yearlyCacheKey != _periodKey('yearly')) {
      _yearlyUsage = null;
      _yearlyHistory = null;
      _yearlyCacheKey = null;
      expired = true;
    }
    if (expired) notifyListeners();
    return expired;
  }

  /// Drop local-calendar periods when the device zone or calendar period changes.
  /// All-time usage has no local period boundary and remains reusable.
  Future<bool> refreshUsageTimeZone() {
    final pending = _timeZoneLookupInFlight;
    if (pending != null) return pending;
    late final Future<bool> lookup;
    lookup = _refreshUsageTimeZone().whenComplete(() {
      if (identical(_timeZoneLookupInFlight, lookup)) _timeZoneLookupInFlight = null;
    });
    return _timeZoneLookupInFlight = lookup;
  }

  Future<bool> _refreshUsageTimeZone() async {
    final session = _sessionGeneration;
    final lookup = ++_timeZoneLookupGeneration;
    String? zone;
    try {
      zone = await _deviceTimeZone();
    } catch (_) {
      // Match the API fallback when the platform timezone is unavailable.
    }
    if (session != _sessionGeneration || lookup != _timeZoneLookupGeneration) return false;
    if (!_usageTimeZoneResolved) {
      _usageTimeZone = zone;
      _usageTimeZoneResolved = true;
      return _expireCalendarCaches();
    }
    if (_usageTimeZone == zone) return _expireCalendarCaches();
    _usageTimeZone = zone;
    _usageTimeZoneGeneration++;
    _todayUsage = null;
    _todayCacheKey = null;
    _monthlyUsage = null;
    _monthlyCacheKey = null;
    _yearlyUsage = null;
    _yearlyCacheKey = null;
    _todayHistory = null;
    _monthlyHistory = null;
    _yearlyHistory = null;
    notifyListeners();
    return true;
  }

  Future<void> fetchUsageStats({required String period}) async {
    while (_usageFetchInFlight != null) {
      await _usageFetchInFlight;
    }
    final fetch = _fetchUsageStats(period);
    _usageFetchInFlight = fetch;
    try {
      await fetch;
    } finally {
      if (identical(_usageFetchInFlight, fetch)) _usageFetchInFlight = null;
    }
  }

  Future<void> _fetchUsageStats(String period) async {
    final generation = _sessionGeneration;
    await refreshUsageTimeZone();
    if (generation != _sessionGeneration) return;
    final timeZoneGeneration = _usageTimeZoneGeneration;
    final cacheKey = _periodKey(period);
    _isUsageLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _usageRequest(period: period, timeZone: _usageTimeZone);
      if (generation != _sessionGeneration || timeZoneGeneration != _usageTimeZoneGeneration) return;
      if (response != null) {
        switch (period) {
          case 'today':
            _todayUsage = response.today;
            _todayCacheKey = cacheKey;
            _todayHistory = response.history;
            break;
          case 'monthly':
            _monthlyUsage = response.monthly;
            _monthlyCacheKey = cacheKey;
            _monthlyHistory = response.history;
            break;
          case 'yearly':
            _yearlyUsage = response.yearly;
            _yearlyCacheKey = cacheKey;
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
      if (generation != _sessionGeneration || timeZoneGeneration != _usageTimeZoneGeneration) return;
      _error = 'Failed to load usage data. Please try again later.';
      Logger.debug('Failed to fetch usage stats: $e');
    } finally {
      if (generation == _sessionGeneration) {
        _isUsageLoading = false;
        notifyListeners();
      }
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
      Logger.debug('Error loading available plans: $e');
    } finally {
      _isLoadingPlans = false;
      notifyListeners();
    }
  }

  Future<bool> cancelUserSubscription({String? reason, String? reasonDetails}) async {
    if (_isPaymentLoading) return false;

    _isPaymentLoading = true;
    _error = null;
    notifyListeners();

    try {
      final success = await cancelSubscription(reason: reason, reasonDetails: reasonDetails);
      if (success) {
        await fetchSubscription();
        await loadAvailablePlans();
      }
      return success;
    } catch (e) {
      _error = 'Failed to cancel subscription. Please try again later.';
      Logger.debug('Error canceling subscription: $e');
      return false;
    } finally {
      _isPaymentLoading = false;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>?> upgradeUserSubscription({required String priceId, String? promotionCode}) async {
    if (_isPaymentLoading) return null;

    _isPaymentLoading = true;
    _error = null;
    notifyListeners();

    try {
      final result = await upgradeSubscription(priceId: priceId, promotionCode: promotionCode);
      if (result != null && result['error'] != true) {
        await fetchSubscription();
        await loadAvailablePlans();
      }
      return result;
    } catch (e) {
      _error = 'Failed to upgrade subscription. Please try again later.';
      Logger.debug('Error upgrading subscription: $e');
      return null;
    } finally {
      _isPaymentLoading = false;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>?> createUserCheckoutSession({required String priceId, String? promotionCode}) async {
    if (_isPaymentLoading) return null;

    _isPaymentLoading = true;
    _error = null;
    notifyListeners();

    try {
      final sessionData = await createCheckoutSession(priceId: priceId, promotionCode: promotionCode);
      return sessionData;
    } catch (e) {
      _error = 'Failed to create checkout session. Please try again later.';
      Logger.debug('Error creating checkout session: $e');
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
      Logger.debug('Error opening customer portal: $e');
      return null;
    } finally {
      _isPaymentLoading = false;
      notifyListeners();
    }
  }
}
