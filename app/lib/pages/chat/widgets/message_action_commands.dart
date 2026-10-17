import 'package:flutter/widgets.dart';

import 'package:share_plus/share_plus.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/share_sheet.dart';

/// Copy, rating and share for one AI reply, shared by the Flutter action bar and the native
/// actions menu. The rating paints optimistically and reverts when [setMessageNps] answers false;
/// [MessageProvider.setMessageNps] stays the only owner that persists it.
class MessageActionCommands {
  MessageActionCommands({required this.messageText, this.setMessageNps, int? currentNps, this.onChanged})
      : _currentNps = currentNps,
        selectedNps = currentNps;

  String messageText;
  Function(int, {String? reason})? setMessageNps;

  /// Called after the optimistic rating changes, so the renderer repaints.
  VoidCallback? onChanged;

  /// 1 (helpful), -1 (not helpful) or null, as currently shown.
  int? selectedNps;
  int? _currentNps;
  bool _disposed = false;

  /// Analytics get the shape of the message, never its words.
  Map<String, Object> get analytics => {'message_length': messageText.length};

  /// Adopts a rating the owner reports (a server fetch, or another renderer), as the bar's
  /// didUpdateWidget does.
  void syncCurrentNps(int? value) {
    if (value == _currentNps) return;
    _currentNps = value;
    selectedNps = value;
  }

  void _set(int? value) {
    if (_disposed) return;
    selectedNps = value;
    onChanged?.call();
  }

  /// Copies the reply; answers whether the clipboard took it.
  Future<bool> copy(BuildContext context) async {
    final copied = await OmiClipboard.copy(context, messageText);
    if (!copied) return false;
    PlatformManager.instance.analytics.track('Chat Message Copied', properties: analytics);
    return true;
  }

  /// Helpful toggles between 1 and 0 (no rating).
  Future<void> toggleHelpful() async {
    final previous = selectedNps;
    _set(selectedNps == 1 ? null : 1);
    final saved = await setMessageNps?.call(selectedNps ?? 0);
    if (saved == false) _set(previous);
  }

  /// Clears a Not Helpful rating back to 0.
  Future<void> clearNotHelpful() async {
    _set(null);
    final saved = await setMessageNps?.call(0);
    if (saved == false) _set(-1);
  }

  /// Rates the reply Not Helpful with the reason (and optional comment) from the feedback sheet.
  Future<void> submitNotHelpful(BuildContext context, String reason, String? comment) async {
    final previous = selectedNps;
    _set(-1);
    // Combine reason and comment for the API call
    var feedbackReason = reason;
    if (comment != null && comment.isNotEmpty) feedbackReason = '$reason: $comment';
    final saved = await setMessageNps?.call(-1, reason: feedbackReason);
    if (saved == false) {
      _set(previous);
      return;
    }
    if (!_disposed && context.mounted) OmiFeedback.confirm(context, context.l10n.thanksForYourFeedback);
  }

  /// Opens the system share sheet with the reply text.
  Future<void> share() async {
    if (messageText.isEmpty) return;
    await SharePlus.instance.share(ShareParams(text: messageText, sharePositionOrigin: shareSheetOrigin()));
    PlatformManager.instance.analytics.track('Chat Message Shared', properties: analytics);
  }

  void dispose() => _disposed = true;
}
