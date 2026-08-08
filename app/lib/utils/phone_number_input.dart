import 'package:flutter/services.dart';
import 'package:phone_numbers_parser/phone_numbers_parser.dart';

/// Characters the phone field accepts.
///
/// `+` has to be here: [parsePhoneNumberInput] treats a leading `+` as "the
/// user supplied their own country code" and lets it override the picker, and
/// a formatter that strips `+` makes that branch unreachable from the UI. Lives
/// beside the parser so the two cannot drift apart.
final phoneFieldInputFormatters = <TextInputFormatter>[
  FilteringTextInputFormatter.allow(RegExp(r'[0-9+\s\-\(\)]')),
];

/// What the user typed on the phone-setup screen, interpreted for one country.
///
/// Validation used to be a digit count against `IntlCountryData`'s
/// telephoneMin/MaxLength. Those are a single fixed length per country and are
/// wrong wherever numbers vary — Estonia was declared 10/10 against a real
/// range of 7-8, so no Estonian number could ever pass (#11209). Lengths now
/// come from libphonenumber metadata via `phone_numbers_parser`; the country
/// data is only the picker's names, flags and dial codes.
class PhoneNumberInput {
  /// The number in E.164, e.g. `+3725142537`. Empty when nothing parsed.
  final String e164;

  /// True when libphonenumber recognizes this as a real number for its country.
  final bool isValid;

  const PhoneNumberInput({required this.e164, required this.isValid});

  static const empty = PhoneNumberInput(e164: '', isValid: false);
}

/// Interprets [raw] as a phone number for [isoCode].
///
/// Handles the two ways users defeat a naive `+$dialCode$digits` concatenation:
/// typing the country code themselves (which used to produce `+3723725142537`),
/// and keeping the national trunk prefix (`05142537`). An explicit leading `+`
/// is trusted over the picker, so pasting a foreign number does the obvious
/// thing rather than being silently re-homed to the selected country.
PhoneNumberInput parsePhoneNumberInput({required String raw, required String isoCode}) {
  // Only a leading + carries meaning; any other one is a typo, and leaving it
  // in makes the whole string unparseable rather than just ignoring it.
  final cleaned = raw.trim();
  final trimmed =
      cleaned.startsWith('+') ? '+${cleaned.substring(1).replaceAll('+', '')}' : cleaned.replaceAll('+', '');
  if (trimmed.isEmpty) return PhoneNumberInput.empty;

  final iso = _isoOrNull(isoCode);
  if (iso == null) return PhoneNumberInput.empty;

  // A leading + means the user supplied the country code; parsing it as a
  // national number for the selected country would prepend a second one.
  final looksInternational = trimmed.startsWith('+') || trimmed.startsWith('00');
  final candidates = looksInternational
      ? [() => PhoneNumber.parse(trimmed), () => PhoneNumber.parse(trimmed, destinationCountry: iso)]
      : [() => PhoneNumber.parse(trimmed, destinationCountry: iso)];

  PhoneNumber? best;
  for (final attempt in candidates) {
    final parsed = _tryParse(attempt);
    if (parsed == null) continue;
    best ??= parsed;
    if (parsed.isValid()) return PhoneNumberInput(e164: parsed.international, isValid: true);
  }

  if (best == null) return PhoneNumberInput.empty;
  return PhoneNumberInput(e164: best.international, isValid: false);
}

PhoneNumber? _tryParse(PhoneNumber Function() attempt) {
  try {
    return attempt();
  } catch (_) {
    return null;
  }
}

IsoCode? _isoOrNull(String code) {
  final upper = code.toUpperCase();
  for (final iso in IsoCode.values) {
    if (iso.name == upper) return iso;
  }
  return null;
}
