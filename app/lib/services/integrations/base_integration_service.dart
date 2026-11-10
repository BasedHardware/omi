import 'package:omi/services/integrations/integration_oauth.dart';

import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/logger.dart';

abstract class BaseIntegrationService {
  final String appKey;
  final String prefKey;

  /// Key whose OAuth flow grants this integration. Defaults to [appKey]; differs
  /// only when several integrations share one grant (Gmail rides Google Calendar).
  final String oauthAppKey;

  BaseIntegrationService({required this.appKey, required this.prefKey, String? oauthAppKey})
      : oauthAppKey = oauthAppKey ?? appKey;

  bool get isAuthenticated {
    return SharedPreferencesUtil().getBool(prefKey);
  }

  Future<void> refreshConnectionStatus() async {
    await checkConnection();
  }

  Future<bool> authenticate({bool Function()? isCurrent}) =>
      launchIntegrationOAuth(() => getIntegrationOAuthUrl(oauthAppKey), isCurrent: isCurrent);

  Future<bool> checkConnection() async {
    try {
      final response = await getIntegration(appKey);
      if (response == null) return isAuthenticated;
      final isConnected = response.connected;
      await SharedPreferencesUtil().saveBool(prefKey, isConnected);
      return isConnected;
    } catch (e) {
      Logger.debug('Error checking $appKey connection: $e');
      return isAuthenticated;
    }
  }

  Future<bool> disconnect() async {
    try {
      final success = await deleteIntegration(appKey);
      if (success) {
        await SharedPreferencesUtil().saveBool(prefKey, false);
        return true;
      }
      return false;
    } catch (e) {
      Logger.debug('Error disconnecting $appKey: $e');
      return false;
    }
  }
}
