import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';

Future<void> showShareSpeechProfileDialog(
  BuildContext context, {
  bool? cachedHasProfile,
  VoidCallback? onShared,
}) async {
  final hasProfile = (cachedHasProfile == true) ? true : await userHasSpeakerProfile();
  if (!context.mounted) return;

  if (!hasProfile) {
    final goRecord = await showDialog<bool>(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context, false),
        () => Navigator.pop(context, true),
        context.l10n.shareSpeechProfile,
        context.l10n.noSpeechProfileRecorded,
        okButtonText: context.l10n.recordNow,
      ),
    );
    if (goRecord == true && context.mounted) {
      routeToPage(context, const SpeechProfilePage());
    }
    return;
  }

  final controller = TextEditingController();
  if (!context.mounted) return;
  showDialog(
    context: context,
    builder: (ctx) {
      bool isSharing = false;
      final outerContext = context;
      return StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            backgroundColor: const Color(0xFF1C1C1E),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Text(context.l10n.shareSpeechProfile, style: const TextStyle(color: Colors.white)),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(context.l10n.enterUserIdToShare, style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 14)),
                const SizedBox(height: 12),
                TextField(
                  controller: controller,
                  enabled: !isSharing,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: context.l10n.userId,
                    hintStyle: const TextStyle(color: Color(0xFF636366)),
                    enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Color(0xFF3C3C43))),
                    focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Colors.white)),
                  ),
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: isSharing ? null : () => Navigator.pop(ctx),
                child: Text(context.l10n.cancel, style: TextStyle(color: isSharing ? Colors.grey : Colors.white)),
              ),
              TextButton(
                onPressed: isSharing
                    ? null
                    : () async {
                        final targetUid = controller.text.trim();
                        if (targetUid.isEmpty) return;
                        if (targetUid == SharedPreferencesUtil().uid) {
                          Navigator.pop(ctx);
                          if (!outerContext.mounted) return;
                          ScaffoldMessenger.of(
                            outerContext,
                          ).showSnackBar(SnackBar(content: Text(outerContext.l10n.cannotShareWithSelf)));
                          return;
                        }
                        setState(() => isSharing = true);
                        final result = await shareSpeechProfile(targetUid);
                        if (!ctx.mounted) return;
                        Navigator.pop(ctx);
                        if (!outerContext.mounted) return;
                        if (result['status'] == 'ok') {
                          ScaffoldMessenger.of(
                            outerContext,
                          ).showSnackBar(SnackBar(content: Text(outerContext.l10n.profileSharedSuccess)));
                          onShared?.call();
                        } else {
                          final error = result['error'] ?? '';
                          String message;
                          if (error.contains('not found')) {
                            message = outerContext.l10n.userNotFound;
                          } else if (error.contains('yourself')) {
                            message = outerContext.l10n.cannotShareWithSelf;
                          } else if (error.contains('No speech profile')) {
                            message = outerContext.l10n.noSpeechProfileRecorded;
                          } else if (error.contains('Already shared')) {
                            message = outerContext.l10n.alreadySharedWithUser;
                          } else {
                            message = outerContext.l10n.profileSharedFail;
                          }
                          ScaffoldMessenger.of(outerContext).showSnackBar(SnackBar(content: Text(message)));
                        }
                      },
                child: isSharing
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : Text(context.l10n.share, style: const TextStyle(color: Colors.white)),
              ),
            ],
          );
        },
      );
    },
  );
}
