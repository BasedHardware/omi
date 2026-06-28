// Payment guard (Flutter port of shared/paymentGuard.ts). Cortex's agent acts
// autonomously, but anything that looks like a payment / checkout / purchase must
// stop and ask the user to step in.

final List<RegExp> _paymentPatterns = [
  RegExp(r'\bpay(ment|ments|ing)?\b', caseSensitive: false),
  RegExp(r'\bcheckout\b', caseSensitive: false),
  RegExp(r'\bbuy now\b', caseSensitive: false),
  RegExp(r'\bplace (the )?order\b', caseSensitive: false),
  RegExp(r'\bcomplete (the )?(purchase|order)\b', caseSensitive: false),
  RegExp(r'\bpurchase\b', caseSensitive: false),
  RegExp(r'\bsubscribe\b', caseSensitive: false),
  RegExp(r'\bcard number\b', caseSensitive: false),
  RegExp(r'\bcredit card\b', caseSensitive: false),
  RegExp(r'\bcvv\b|\bcvc\b', caseSensitive: false),
  RegExp(r'\bbilling\b', caseSensitive: false),
  RegExp(r'\bpaypal\b', caseSensitive: false),
  RegExp(r'\bapple pay\b|\bgoogle pay\b', caseSensitive: false),
  RegExp(r'\bconfirm (and )?pay\b', caseSensitive: false),
  RegExp(r'[\$€£]\d', caseSensitive: false),
];

/// True when [text] (an action description / target) is payment-sensitive and
/// must require explicit user confirmation before the agent proceeds.
bool isPaymentSensitive(String text) {
  return _paymentPatterns.any((re) => re.hasMatch(text));
}
