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
  final monthly = plans.firstWhereOrNull((p) => p['interval'] == 'month');
  final yearly = plans.firstWhereOrNull((p) => p['interval'] == 'year');
  final monthlyAmount = (monthly?['unit_amount'] as num?)?.toDouble();
  final yearlyAmount = (yearly?['unit_amount'] as num?)?.toDouble();
  if (monthlyAmount == null || yearlyAmount == null || monthlyAmount <= 0) return null;

  final monthsFree = (12 - (yearlyAmount / monthlyAmount)).round();
  if (monthsFree <= 0) return null;
  return monthsFree == 1 ? '1 Month Free' : '$monthsFree Months Free';
}
