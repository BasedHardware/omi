import 'package:collection/collection.dart';

/// "N Months Free" for a tier's annual card, derived from the tier's own prices.
///
/// Discounts differ per tier — legacy Neo saves 2 months while Plus and
/// Unlimited save 3 — so this must never be hardcoded. [plans] is the raw
/// available-plans payload for a single tier, containing its `month` and `year`
/// entries with a Stripe `unit_amount`.
///
/// Returns null when either price is missing or the annual plan isn't actually
/// cheaper, so the caller simply renders no badge.
String? annualSaveTag(List<Map<String, dynamic>> plans) {
  final monthsFree = _annualMonthsFree(plans);
  if (monthsFree == null) return null;
  return monthsFree == 1 ? '1 Month Free' : '$monthsFree Months Free';
}

/// Whole-percent discount of a tier's annual price vs paying monthly for a year.
///
/// Plus/Unlimited bill 9 of 12 months → 25%; legacy Neo → ~17%. Null when the
/// prices aren't usable or annual isn't cheaper.
int? annualDiscountPercent(List<Map<String, dynamic>> plans) {
  final prices = _monthlyAndYearly(plans);
  if (prices == null) return null;
  final (monthlyAmount, yearlyAmount) = prices;

  final percent = ((1 - (yearlyAmount / (monthlyAmount * 12))) * 100).round();
  return percent <= 0 ? null : percent;
}

/// Largest annual discount across tiers, for the shared yearly-billing toggle.
///
/// Tiers discount differently (Neo ~17%, Plus/Unlimited 25%), so the one shared
/// badge advertises the best available rather than a stale hardcoded number.
int? bestAnnualDiscountPercent(Iterable<List<Map<String, dynamic>>> tiers) {
  final percents = tiers.map(annualDiscountPercent).nonNulls;
  return percents.isEmpty ? null : percents.reduce((a, b) => a > b ? a : b);
}

int? _annualMonthsFree(List<Map<String, dynamic>> plans) {
  final prices = _monthlyAndYearly(plans);
  if (prices == null) return null;
  final (monthlyAmount, yearlyAmount) = prices;

  final monthsFree = (12 - (yearlyAmount / monthlyAmount)).round();
  return monthsFree <= 0 ? null : monthsFree;
}

(double, double)? _monthlyAndYearly(List<Map<String, dynamic>> plans) {
  final monthly = plans.firstWhereOrNull((p) => p['interval'] == 'month');
  final yearly = plans.firstWhereOrNull((p) => p['interval'] == 'year');
  final monthlyAmount = (monthly?['unit_amount'] as num?)?.toDouble();
  final yearlyAmount = (yearly?['unit_amount'] as num?)?.toDouble();
  if (monthlyAmount == null || yearlyAmount == null || monthlyAmount <= 0) return null;
  return (monthlyAmount, yearlyAmount);
}
