/// Prices and trial settings used across the prototype.
///
/// Anything marked "Placeholder:" is a stand-in value that still needs a
/// decision; everything else comes from omi.me or the plan catalog.
class DfPricing {
  const DfPricing._();

  /// Unlimited, billed yearly (omi.me/pricing).
  static const String yearly = r'$269/yr';
  static const String yearlyPerMonth = r'$22.42/mo';

  // Placeholder: monthly Unlimited price. $29.99 is derived from omi.me's
  // "pay for 9 months, get 3 free" framing of the $269 yearly price.
  static const String monthly = r'$29.99/mo';

  /// The pendant: $179 list, $129 after the automatic $50 discount (omi.me).
  static const String deviceList = r'$179';
  static const String devicePrice = r'$129';
  static const String deviceDiscount = r'$50';
}

/// The four arms of the trial-length test on the end-of-onboarding paywall.
///
/// Only the length changes between arms; the headline, button, caption and
/// reminder day follow from it. The reminder lands two days before the trial
/// ends (one day for the 3-day arm).
enum TrialLength {
  threeDays(
    days: 3,
    reminderDay: 2,
    label: '3 days',
    headline: 'Try Unlimited free for 3 days.',
    cta: 'Start my 3-day free trial',
  ),
  oneWeek(
    days: 7,
    reminderDay: 5,
    label: '7 days',
    headline: 'Try Unlimited free for a week.',
    cta: 'Start my free week',
  ),
  twoWeeks(
    days: 14,
    reminderDay: 12,
    label: '14 days',
    headline: 'Two weeks of Unlimited, on us.',
    cta: 'Start my 2 free weeks',
  ),
  oneMonth(
    days: 30,
    reminderDay: 28,
    label: '30 days',
    headline: 'Your first month of Unlimited is free.',
    cta: 'Start my free month',
  );

  const TrialLength({
    required this.days,
    required this.reminderDay,
    required this.label,
    required this.headline,
    required this.cta,
  });

  final int days;
  final int reminderDay;
  final String label;
  final String headline;
  final String cta;

  /// "your free month" for the 30-day arm, "your trial" otherwise.
  String get endingNoun => this == TrialLength.oneMonth ? 'your free month' : 'your trial';

  int get daysOfNotice => days - reminderDay;
}
