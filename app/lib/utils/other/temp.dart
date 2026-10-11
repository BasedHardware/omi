import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:intl/intl.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/omi_date_format.dart';
import 'package:omi/ui/omi_routes.dart';

/// Formats [dateTime] with a pattern string. Legacy: a pattern fixes the order and the 12/24-hour
/// clock for every locale. New code uses `OmiDateFormat.of(context)` (docs/ux-contract.md §7); the
/// mobile UX ratchet counts new `dateTimeFormat('…')` calls.
String dateTimeFormat(String format, DateTime? dateTime, {String? locale}) {
  if (dateTime == null) return '';
  return DateFormat(format, locale).format(dateTime);
}

/// Pushes [page] with the platform route ([omiPageRoute]: Cupertino with the iOS back swipe on
/// iOS, Material elsewhere). With [replace], it becomes the only route.
Future routeToPage(BuildContext context, Widget page, {bool replace = false}) {
  if (!context.mounted) {
    return Future.value();
  }

  final route = omiPageRoute<dynamic>(builder: (c) => page);
  if (replace) {
    return Navigator.of(context).pushAndRemoveUntil(route, (route) => false);
  }
  return Navigator.of(context).push(route);
}

/// A moment in a feed: the time today, "Yesterday at 10:43 AM", then the date with the time.
/// Delegates to [OmiDateFormat.timestamp]. Without a [context] it uses the process locale and
/// English day words.
String formatChatTimestamp(DateTime dateTime, {BuildContext? context}) {
  if (context != null) return OmiDateFormat.of(context).timestamp(dateTime);
  final locale = Intl.getCurrentLocale().split(RegExp('[_-]'));
  return OmiDateFormat(
    locale: Locale(locale.first, locale.length > 1 ? locale[1] : null),
    use24HourFormat: false,
    l10n: lookupAppLocalizations(const Locale('en')),
  ).timestamp(dateTime);
}

String countryFlagFromCode(String countryCode) {
  const flagOffset = 0x1F1E6;
  const asciiOffset = 0x41;

  final firstChar = countryCode.codeUnitAt(0) - asciiOffset + flagOffset;
  final secondChar = countryCode.codeUnitAt(1) - asciiOffset + flagOffset;

  return String.fromCharCode(firstChar) + String.fromCharCode(secondChar);
}
