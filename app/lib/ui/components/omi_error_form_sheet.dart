import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/components/omi_sheet.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:intercom_flutter/intercom_flutter.dart';

Future<void> showOmiErrorFormSheet(
  BuildContext context, {
  required String stackTrace,
  String? message,
}) {
  return showOmiSheet<void>(
    context: context,
    title: 'Report Issue',
    builder: (context) =>
        _OmiErrorFormSheet(stackTrace: stackTrace, message: message),
  );
}

class _OmiErrorFormSheet extends StatefulWidget {
  final String stackTrace;
  final String? message;

  const _OmiErrorFormSheet({required this.stackTrace, this.message});

  @override
  State<_OmiErrorFormSheet> createState() => _OmiErrorFormSheetState();
}

class _OmiErrorFormSheetState extends State<_OmiErrorFormSheet> {
  final TextEditingController _descriptionController = TextEditingController();

  @override
  void dispose() {
    _descriptionController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final description = _descriptionController.text.trim();
    final issueReport =
        'User Description:\n$description\n\nError Message:\n${widget.message ?? 'Unknown'}\n\nStack Trace:\n${widget.stackTrace}';

    // Using intercom as fallback / standard way for user communication
    await Intercom.instance.displayMessageComposer(issueReport);
    if (mounted) {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'What were you trying to do when the error occurred?',
              style: OmiType.subhead.copyWith(color: OmiColors.textPrimary),
            ),
            const SizedBox(height: OmiSpacing.sm),
            TextField(
              controller: _descriptionController,
              maxLines: 5,
              style: OmiType.body,
              decoration: InputDecoration(
                hintText: 'Describe the issue...',
                hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
                filled: true,
                fillColor: OmiColors.surface2,
                border: const OutlineInputBorder(
                  borderRadius: OmiRadius.mdAll,
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.all(OmiSpacing.sm),
              ),
            ),
            const SizedBox(height: OmiSpacing.lg),
            Text(
              'Error Details',
              style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: OmiSpacing.xs),
            Container(
              padding: const EdgeInsets.all(OmiSpacing.sm),
              decoration: BoxDecoration(
                color: OmiColors.surface2,
                borderRadius: OmiRadius.smAll,
              ),
              child: SelectableText(
                '${widget.message ?? 'Error'}\n\n${widget.stackTrace}',
                style: OmiType.caption.copyWith(
                  fontFamily: 'monospace',
                  color: OmiColors.textSecondary,
                ),
                maxLines: 10,
              ),
            ),
            const SizedBox(height: OmiSpacing.xl),
            OmiButton(label: 'Submit Report', onPressed: _submit),
          ],
        ),
      ),
    );
  }
}
