import 'dart:io' show Platform;

/// Localized labels for Android / desktop notification *channels*.
///
/// These strings appear in the OS settings UI (Android: Settings → Apps →
/// Omi → Notifications) and are passed to `awesome_notifications` at
/// channel-registration time. Because `awesome_notifications` registers
/// channels eagerly — sometimes before Flutter's widgets binding has a
/// `BuildContext` available — we cannot use `AppLocalizations` /
/// `context.l10n` here. Instead we read the host OS locale directly via
/// `Platform.localeName` (e.g. `"ja_JP.UTF-8"`, `"en_US"`).
///
/// Only languages that the rest of the app already ships translations for
/// are switched explicitly; everything else falls through to English.
class NotificationChannelStrings {
  NotificationChannelStrings._();

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
    // Platform.localeName looks like "ja_JP.UTF-8" or "ja-JP".
    final name = Platform.localeName.toLowerCase();
    return name.startsWith('ja_') || name.startsWith('ja-') || name == 'ja';
  }
}
