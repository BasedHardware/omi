import 'package:flutter/widgets.dart';

import 'package:intl/intl.dart';

import 'package:omi/l10n/app_localizations.dart';

/// The one way to put a date or time on screen (docs/ux-contract.md §8).
///
/// Every style follows the app's locale (month names, order, separators) and the device's 24-hour
/// setting. Never format with a pattern string such as `DateFormat('h:mm a')`: it forces English
/// order and a 12-hour clock on everyone.
///
/// | Style        | en_US example                          | Use                                   |
/// |--------------|----------------------------------------|---------------------------------------|
/// | [time]       | 10:43 AM                               | a row inside a day group              |
/// | [dayHeader]  | Today · Yesterday · Wed, Sep 23 · Wed, Sep 23, 2025 | a group header           |
/// | [date]       | Sep 23, 2026                           | a date standing alone                 |
/// | [dateTime]   | Sep 23, 2026 10:43 AM                  | an absolute moment (details, exports) |
/// | [timestamp]  | 10:43 AM · Yesterday at 10:43 AM · Sep 21 10:43 AM | a moment in a feed        |
/// | [timeRange]  | 10:17 – 11:19 AM                       | a span (cross-day spans show dates)   |
///
/// ```dart
/// final dates = OmiDateFormat.of(context);
/// Text(dates.time(conversation.startedAt));
/// ```
class OmiDateFormat {
  OmiDateFormat({
    required Locale locale,
    required this.use24HourFormat,
    required AppLocalizations l10n,
    DateTime Function()? clock,
  })  : localeName = resolveIntlLocale(locale),
        _l10n = l10n,
        _clock = clock ?? DateTime.now;

  /// Reads the app locale, its strings and the device's 24-hour setting from [context].
  factory OmiDateFormat.of(BuildContext context) {
    return OmiDateFormat(
      locale: Localizations.localeOf(context),
      use24HourFormat: MediaQuery.maybeAlwaysUse24HourFormatOf(context) ?? false,
      l10n: AppLocalizations.of(context),
    );
  }

  /// The intl locale actually used (falls back to the language, then `en`, when intl lacks data).
  final String localeName;

  /// Force a 24-hour clock even where the locale defaults to 12 hours.
  final bool use24HourFormat;

  final AppLocalizations _l10n;
  final DateTime Function() _clock;

  /// Clock time: "10:43 AM", or "10:43" under a 24-hour setting or locale.
  String time(DateTime value) => _timeFormat().format(value);

  /// Group header: "Today", "Yesterday", a weekday with month and day, and the year when it is not
  /// the current one.
  String dayHeader(DateTime value) {
    final day = _dayOnly(value);
    final today = _dayOnly(_clock());
    if (day == today) return _l10n.today;
    if (day == DateTime(today.year, today.month, today.day - 1)) return _l10n.yesterday;
    return (value.year == today.year ? DateFormat.MMMEd(localeName) : DateFormat.yMMMEd(localeName)).format(value);
  }

  /// A date standing alone: "Sep 23, 2026".
  String date(DateTime value) => DateFormat.yMMMd(localeName).format(value);

  /// An absolute moment: "Sep 23, 2026 10:43 AM" (locale order and separators).
  String dateTime(DateTime value) {
    final format = DateFormat.yMMMd(localeName);
    return use24HourFormat ? format.add_Hm().format(value) : format.add_jm().format(value);
  }

  /// A moment in a feed: the time today, "Yesterday at 10:43 AM", then month and day (plus the
  /// year when not the current one) with the time.
  String timestamp(DateTime value) {
    final day = _dayOnly(value);
    final today = _dayOnly(_clock());
    if (day == today) return time(value);
    if (day == DateTime(today.year, today.month, today.day - 1)) return _l10n.yesterdayAtTime(time(value));
    final format = value.year == today.year ? DateFormat.MMMd(localeName) : DateFormat.yMMMd(localeName);
    return use24HourFormat ? format.add_Hm().format(value) : format.add_jm().format(value);
  }

  /// A span. Same day: "10:17 – 11:19 AM" (the period written once when both ends share it),
  /// "10:17 – 11:19" on a 24-hour clock. Across days: both ends in full.
  String timeRange(DateTime start, DateTime end) {
    if (_dayOnly(start) != _dayOnly(end)) return '${dateTime(start)} – ${dateTime(end)}';
    final endText = time(end);
    final startText = _sharesTrailingPeriod(start, end) ? _timeWithoutPeriod(start) : time(start);
    return '$startText – $endText';
  }

  DateFormat _timeFormat() => use24HourFormat ? DateFormat.Hm(localeName) : DateFormat.jm(localeName);

  static final RegExp _trailingPeriod = RegExp(r'[\s\u00a0\u202f]*a$');

  bool _sharesTrailingPeriod(DateTime start, DateTime end) {
    if (use24HourFormat) return false;
    final pattern = DateFormat.jm(localeName).pattern ?? '';
    if (!_trailingPeriod.hasMatch(pattern)) return false;
    return (start.hour < 12) == (end.hour < 12);
  }

  String _timeWithoutPeriod(DateTime value) {
    final pattern = DateFormat.jm(localeName).pattern ?? '';
    return DateFormat(pattern.replaceFirst(_trailingPeriod, ''), localeName).format(value);
  }

  static DateTime _dayOnly(DateTime value) => DateTime(value.year, value.month, value.day);

  /// The intl locale name for [locale], degrading to its language and then to `en` when intl has
  /// no date symbols for it (so formatting never throws).
  static String resolveIntlLocale(Locale locale) {
    for (final candidate in [locale.toString(), locale.toLanguageTag(), locale.languageCode]) {
      final canonical = Intl.canonicalizedLocale(candidate);
      if (DateFormat.localeExists(canonical)) return canonical;
    }
    return 'en';
  }
}
