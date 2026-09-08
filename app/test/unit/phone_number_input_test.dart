import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl_country_data/intl_country_data.dart';
import 'package:omi/utils/phone_number_input.dart';

/// #11209: phone signup was gated on a digit count against
/// `IntlCountryData.telephoneMin/MaxLength`, a single fixed length per country.
/// Estonia was declared 10/10 against a real range of 7-8, so the Continue
/// button could never enable for any Estonian number.

void main() {
  group('Estonia (#11209)', () {
    test('accepts the reported 7-digit number', () {
      final r = parsePhoneNumberInput(raw: '5142537', isoCode: 'EE');
      expect(r.isValid, isTrue);
      expect(r.e164, '+3725142537');
    });

    test('still rejects 05142537 — Estonia has no trunk prefix', () {
      // The issue also reported this as blocked, but Estonia abolished trunk
      // prefixes: numbers are dialled as-is, so a leading 0 is not a prefix to
      // strip and 05142537 is not a real number. libphonenumber strips the 0
      // only for countries that actually have a national prefix (see the GB
      // case below), which is precisely why per-country metadata beats a
      // blanket "drop a leading zero" rule.
      expect(parsePhoneNumberInput(raw: '05142537', isoCode: 'EE').isValid, isFalse);
    });

    test('accepts an 8-digit mobile number', () {
      expect(parsePhoneNumberInput(raw: '51425370', isoCode: 'EE').isValid, isTrue);
    });

    test('the country entry no longer demands 10 digits', () {
      // Guards the pinned intl_country_data revision: the picker still sources
      // dial codes from it, and 10/10 is what made Estonia unreachable.
      final ee = IntlCountryData.fromCountryCodeAlpha2('EE');
      expect(ee.telephoneMinLength, 7);
      expect(ee.telephoneMaxLength, 8);
    });
  });

  group('typing the country code does not duplicate it', () {
    test('a leading + is not concatenated onto the dial code', () {
      // Previously produced +3723725142537.
      final r = parsePhoneNumberInput(raw: '+372 5142537', isoCode: 'EE');
      expect(r.isValid, isTrue);
      expect(r.e164, '+3725142537');
    });

    test('00 international access is treated the same way', () {
      final r = parsePhoneNumberInput(raw: '00372 5142537', isoCode: 'EE');
      expect(r.e164, '+3725142537');
    });

    test('an explicit + wins over the picker', () {
      // Pasting a UK number while Estonia is selected keeps the UK number
      // rather than silently re-homing it.
      final r = parsePhoneNumberInput(raw: '+442071838750', isoCode: 'EE');
      expect(r.isValid, isTrue);
      expect(r.e164, '+442071838750');
    });
  });

  group('the field passes + through to the parser', () {
    // Regression: the field allowed only [0-9\s\-()], so + was stripped before
    // the parser ever saw it and the explicit-international branch below could
    // never run from the UI. A pasted UK number was re-parsed as Estonian.
    String applyFormatters(String typed) {
      var value = TextEditingValue.empty;
      for (final formatter in phoneFieldInputFormatters) {
        value = formatter.formatEditUpdate(
          TextEditingValue.empty,
          TextEditingValue(text: typed, selection: TextSelection.collapsed(offset: typed.length)),
        );
      }
      return value.text;
    }

    test('a leading + survives the input formatter', () {
      expect(applyFormatters('+442071838750'), '+442071838750');
    });

    test('letters are still rejected', () {
      expect(applyFormatters('44abc207'), '44207');
    });

    test('spacing and punctuation still allowed', () {
      expect(applyFormatters('+372 (514) 25-37'), '+372 (514) 25-37');
    });

    test('end to end: what the field keeps is what validates', () {
      final kept = applyFormatters('+442071838750');
      final parsed = parsePhoneNumberInput(raw: kept, isoCode: 'EE');
      expect(parsed.isValid, isTrue);
      expect(parsed.e164, '+442071838750', reason: 'a pasted UK number must not be re-homed to Estonia');
    });

    testWidgets('the real field accepts a pasted + number', (tester) async {
      final controller = TextEditingController();
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TextField(
            controller: controller,
            keyboardType: TextInputType.phone,
            inputFormatters: phoneFieldInputFormatters,
          ),
        ),
      ));
      await tester.enterText(find.byType(TextField), '+442071838750');
      await tester.pump();
      expect(controller.text, '+442071838750');
      expect(parsePhoneNumberInput(raw: controller.text, isoCode: 'EE').e164, '+442071838750');
    });
  });

  group('stray + characters are tolerated', () {
    test('a + in the middle is ignored', () {
      expect(parsePhoneNumberInput(raw: '514+2537', isoCode: 'EE').e164, '+3725142537');
    });

    test('a duplicated leading + still parses', () {
      expect(parsePhoneNumberInput(raw: '++372 5142537', isoCode: 'EE').e164, '+3725142537');
    });
  });

  group('formatting noise is ignored', () {
    for (final raw in ['514 2537', '514-2537', '(514) 2537', ' 5142537 ']) {
      test('"$raw"', () {
        expect(parsePhoneNumberInput(raw: raw, isoCode: 'EE').e164, '+3725142537');
      });
    }
  });

  group('countries the fixed-length data got wrong stay usable', () {
    // Each of these has a real length range wider than one value, which the
    // old min==max check could not express.
    test('a 10-digit US number', () {
      final r = parsePhoneNumberInput(raw: '4155552671', isoCode: 'US');
      expect(r.isValid, isTrue);
      expect(r.e164, '+14155552671');
    });

    test('a UK number with and without the trunk 0', () {
      expect(parsePhoneNumberInput(raw: '02071838750', isoCode: 'GB').e164, '+442071838750');
      expect(parsePhoneNumberInput(raw: '2071838750', isoCode: 'GB').e164, '+442071838750');
    });

    test('a German number', () {
      expect(parsePhoneNumberInput(raw: '030123456', isoCode: 'DE').isValid, isTrue);
    });
  });

  group('invalid input stays blocked', () {
    test('empty', () {
      expect(parsePhoneNumberInput(raw: '', isoCode: 'EE'), PhoneNumberInput.empty);
      expect(parsePhoneNumberInput(raw: '   ', isoCode: 'EE').isValid, isFalse);
    });

    test('too short for the country', () {
      expect(parsePhoneNumberInput(raw: '51', isoCode: 'EE').isValid, isFalse);
    });

    test('too long for the country', () {
      expect(parsePhoneNumberInput(raw: '514253700000', isoCode: 'EE').isValid, isFalse);
    });

    test('letters only', () {
      expect(parsePhoneNumberInput(raw: 'abcdefg', isoCode: 'EE').isValid, isFalse);
    });

    test('an unknown country code', () {
      expect(parsePhoneNumberInput(raw: '5142537', isoCode: 'ZZ'), PhoneNumberInput.empty);
    });
  });
}
