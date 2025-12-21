import 'package:omi/services/base_integration_service.dart';

class GoogleCalendarService extends BaseIntegrationService {
  static const String _appKey = 'google_calendar';
  static const String _prefKey = 'google_calendar_connected';

  GoogleCalendarService() : super(appKey: _appKey, prefKey: _prefKey);
}
