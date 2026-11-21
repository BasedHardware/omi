import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_sheet.dart';
import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/l10n_extensions.dart';

Future<void> showLoggerFeedbackSheet(
  BuildContext context, {
  required String stackTrace,
}) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.errorLabel(''),
    builder: (context) => _LoggerFeedbackSheet(stackTrace: stackTrace),
  );
}

class _LoggerFeedbackSheet extends StatelessWidget {
  final String stackTrace;

  const _LoggerFeedbackSheet({required this.stackTrace});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(
              color: OmiColors.surface2,
              borderRadius: OmiRadius.mdAll,
            ),
            child: Text(
              stackTrace,
              style: OmiType.caption.copyWith(
                fontFamily: 'monospace',
                color: OmiColors.textSecondary,
              ),
            ),
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiButton(
            label: context.l10n.reportAnIssue,
            onPressed: () async {
              Navigator.pop(context);
              if (IntercomManager.instance.isIntercomEnabled) {
                await IntercomManager.instance.intercom.displayMessageComposer(
                  stackTrace,
                );
              }
            },
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}
