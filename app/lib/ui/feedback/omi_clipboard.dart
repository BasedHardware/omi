import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import 'package:device_info_plus/device_info_plus.dart';

import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one way to copy text (docs/ux-contract.md §7).
///
/// ```dart
/// await OmiClipboard.copy(context, transcript, what: l10n.transcript);
/// ```
///
/// * Empty or whitespace-only text is not copied and nothing is shown (returns `false`), so the
///   reader is never told "Copied" about nothing.
/// * After copying it confirms with [OmiFeedback.confirm] ("Copied" / "Transcript copied") —
///   except on Android 13+ (API 33), where the system already shows its own clipboard chip and a
///   second toast would double-confirm.
abstract final class OmiClipboard {
  static int? _androidSdkInt;
  static bool _sdkLookedUp = false;

  /// Test hooks: pin the platform decision instead of reading the device.
  @visibleForTesting
  static bool? debugSystemConfirmsCopy;

  /// Copies [text]; returns whether anything was copied. [what] names the thing ("Transcript")
  /// for the confirmation; without it the toast says "Copied".
  static Future<bool> copy(BuildContext context, String text, {String? what}) async {
    if (text.trim().isEmpty) return false;
    await Clipboard.setData(ClipboardData(text: text)); // omi-ux-allow: raw-clipboard -- the primitive itself
    if (!context.mounted) return true;
    await confirmCopied(context, what: what);
    return true;
  }

  /// Shows the "Copied" confirmation for a copy something else already performed (for example a
  /// text-selection toolbar), with the same Android 13+ rule as [copy].
  static Future<void> confirmCopied(BuildContext context, {String? what}) async {
    if (await systemConfirmsCopy()) return;
    if (!context.mounted) return;
    OmiFeedback.confirm(context, what == null ? context.l10n.copied : context.l10n.labelCopied(what));
  }

  /// Whether the OS shows its own copy confirmation (Android 13+). Cached after the first lookup.
  static Future<bool> systemConfirmsCopy() async {
    final pinned = debugSystemConfirmsCopy;
    if (pinned != null) return pinned;
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return false;
    if (!_sdkLookedUp) {
      _sdkLookedUp = true;
      try {
        _androidSdkInt = (await DeviceInfoPlugin().androidInfo).version.sdkInt;
      } catch (_) {
        _androidSdkInt = null;
      }
    }
    return (_androidSdkInt ?? 0) >= 33;
  }
}
