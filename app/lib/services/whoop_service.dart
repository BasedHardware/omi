import 'package:omi/services/base_integration_service.dart';

class WhoopService extends BaseIntegrationService {
  static const String _appKey = 'whoop';
  static const String _prefKey = 'whoop_connected';

  WhoopService() : super(appKey: _appKey, prefKey: _prefKey);
}
