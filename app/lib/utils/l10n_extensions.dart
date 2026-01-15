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
