import 'dart:io' show Platform;

import 'package:shared_preferences/shared_preferences.dart';

/// Localized labels for Android / desktop notification *channels*.
///
/// These strings appear in the OS settings UI (Android: Settings → Apps →
/// Omi → Notifications) and are passed to `awesome_notifications` at
/// channel-registration time. Because `awesome_notifications` registers
/// channels eagerly — sometimes before Flutter's widgets binding has a
/// `BuildContext` available — we cannot use `AppLocalizations` /
/// `context.l10n` here.
///
/// Prefer the in-app locale saved by [LocaleProvider] (`app_locale`), then
/// fall back to `Platform.localeName`. Call [loadAppLocale] before the first
/// channel registration so the SharedPreferences read is warm.
class NotificationChannelStrings {
  NotificationChannelStrings._();

  /// Same key as `LocaleProvider._localeKey`.
  static const String _appLocaleKey = 'app_locale';

  static String? _appLocale;

  /// Load the in-app locale override. Safe in background isolates.
  static Future<void> loadAppLocale() async {
    final prefs = await SharedPreferences.getInstance();
    _appLocale = prefs.getString(_appLocaleKey);
  }

  /// Display name of the main Omi notification channel.
  static String get omiChannelName {
    if (_isJapanese) return 'Omi の通知';
    return 'Omi Notifications';
  }

  /// Description of the main Omi notification channel.
  static String get omiChannelDescription {
    if (_isJapanese) return 'Omi の通知チャンネル';
    return 'Notification channel for Omi';
  }

  /// Display name of the foreground-transcription notification channel.
  static String get foregroundServiceChannelName {
    if (_isJapanese) return 'フォアグラウンドサービス通知';
    return 'Foreground Service Notification';
  }

  /// Description of the foreground-transcription notification channel.
  static String get foregroundServiceChannelDescription {
    if (_isJapanese) return '文字起こしサービスがバックグラウンドで実行中です。';
    return 'Transcription service is running in the background.';
  }

  static bool get _isJapanese {
    final saved = (_appLocale ?? '').toLowerCase();
    if (saved.isNotEmpty) {
      return saved == 'ja' || saved.startsWith('ja_') || saved.startsWith('ja-');
    }
    // Platform.localeName looks like "ja_JP.UTF-8" or "ja-JP".
    final name = Platform.localeName.toLowerCase();
    return name.startsWith('ja_') || name.startsWith('ja-') || name == 'ja';
  }
}
