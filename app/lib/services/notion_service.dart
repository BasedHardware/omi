import 'package:omi/services/base_integration_service.dart';

class NotionService extends BaseIntegrationService {
  static const String _appKey = 'notion';
  static const String _prefKey = 'notion_connected';

  NotionService() : super(appKey: _appKey, prefKey: _prefKey);
}
