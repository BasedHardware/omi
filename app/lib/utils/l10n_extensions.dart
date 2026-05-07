import 'package:flutter/widgets.dart';

import 'package:omi/l10n/app_localizations.dart';

/// Extension on BuildContext for convenient access to localized strings.
///
/// Usage:
/// ```dart
/// Text(context.l10n.deleteConversationTitle)
/// ```
///
/// This is cleaner than:
/// ```dart
/// Text(AppLocalizations.of(context)!.deleteConversationTitle)
/// ```
extension LocalizationExtension on BuildContext {
  /// Get the current [AppLocalizations] instance.
  ///
  /// This will throw if AppLocalizations is not available in the widget tree,
  /// which should never happen if MaterialApp is configured correctly.
  AppLocalizations get l10n => AppLocalizations.of(this);
}

// Temporary accessors for new English ARB keys until generated localizations are refreshed.
extension TrashLocalizationExtension on AppLocalizations {
  String get trash => 'Trash';
  String get trashEmpty => 'Trash is empty';
  String get trashDescription => 'Conversations in Trash are permanently deleted after 30 days.';
  String get moveToTrash => 'Move to Trash';
  String get deleteForever => 'Delete forever';
  String daysRemaining(int days) => '$days days remaining';
  String get trashConfirmTitle => 'Move conversation to Trash?';
  String get trashConfirmMessage => 'You can restore it from Settings > Trash for the next 30 days.';
  String get restoreSuccess => 'Conversation restored';
  String get deleteForeverConfirmTitle => 'Delete forever?';
  String get trashedAtLabel => 'Moved to Trash';
}
