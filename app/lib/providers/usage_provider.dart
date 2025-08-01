import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/models/user_usage.dart';

class UsageProvider with ChangeNotifier {
  UserUsageResponse? _usageResponse;
  UserUsageResponse? get usageResponse => _usageResponse;

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
        if (_usageResponse == null) {
          _usageResponse = response;
        } else {
          _usageResponse = UserUsageResponse(
            today: response.today ?? _usageResponse!.today,
            monthly: response.monthly ?? _usageResponse!.monthly,
            yearly: response.yearly ?? _usageResponse!.yearly,
            allTime: response.allTime ?? _usageResponse!.allTime,
            history: response.history ?? _usageResponse!.history,
          );
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
