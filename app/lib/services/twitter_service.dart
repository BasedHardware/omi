import 'package:omi/services/base_integration_service.dart';

class TwitterService extends BaseIntegrationService {
  static const String _appKey = 'twitter';
  static const String _prefKey = 'twitter_connected';

  TwitterService() : super(appKey: _appKey, prefKey: _prefKey);
}
