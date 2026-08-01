import 'package:url_launcher/url_launcher.dart';

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

  Future<bool> authenticate() async {
    try {
      final authUrl = await getIntegrationOAuthUrl(oauthAppKey);
      if (authUrl == null) {
        Logger.debug('Failed to get OAuth URL for $oauthAppKey');
        return false;
      }

      final uri = Uri.parse(authUrl);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return true;
      } else {
        Logger.debug('Cannot launch OAuth URL for $appKey');
        return false;
      }
    } catch (e) {
      Logger.debug('Error during $appKey authentication: $e');
      return false;
    }
  }

  Future<bool> checkConnection() async {
    try {
      final response = await getIntegration(appKey);
      final isConnected = response != null && response.connected;
      await SharedPreferencesUtil().saveBool(prefKey, isConnected);
      return isConnected;
    } catch (e) {
      Logger.debug('Error checking $appKey connection: $e');
      await SharedPreferencesUtil().saveBool(prefKey, false);
      return false;
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
