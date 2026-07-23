import 'package:omi/services/integrations/base_integration_service.dart';

/// Gmail rides the same Google OAuth grant as Google Calendar, so it starts the
/// `google_calendar` OAuth flow but tracks its own connection status — the grant
/// only counts as connected for Gmail once the Gmail scope was approved.
class GmailService extends BaseIntegrationService {
  static const String _appKey = 'gmail';
  static const String _oauthAppKey = 'google_calendar';
  static const String _prefKey = 'gmail_connected';

  GmailService() : super(appKey: _appKey, prefKey: _prefKey, oauthAppKey: _oauthAppKey);
}
