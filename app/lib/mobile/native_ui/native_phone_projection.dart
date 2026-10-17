import 'package:omi/mobile/native_ui/ios_native_surface.dart';

/// Telephone keypad letters are the same labels as the current dialer. The caller still owns
/// number editing, dialing and DTMF; this contract only distinguishes their allowed controls.
NativeRow nativePhoneKeypad({
  required String id,
  required String title,
  required String digits,
  required NativeAction action,
  required bool dtmf,
  String? eraseLabel,
  String? clearLabel,
}) =>
    NativeRow(id, title,
        kind: 'keypad',
        value: digits,
        keypadMode: dtmf ? 'dtmf' : 'dialer',
        eraseLabel: eraseLabel,
        clearLabel: clearLabel,
        options: const {
          '1': '',
          '2': 'ABC',
          '3': 'DEF',
          '4': 'GHI',
          '5': 'JKL',
          '6': 'MNO',
          '7': 'PQRS',
          '8': 'TUV',
          '9': 'WXYZ',
          '*': '',
          '0': '+',
          '#': '',
        },
        action: action);
