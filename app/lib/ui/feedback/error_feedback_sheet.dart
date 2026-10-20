import 'package:flutter/material.dart';
import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/components/omi_sheet.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:talker_flutter/talker_flutter.dart';
import 'package:omi/utils/l10n_extensions.dart';

Future<void> showErrorFeedbackSheet(
  BuildContext context, {
  required dynamic error,
}) {
  return showOmiSheet<void>(
    context: context,
    title: 'Report an Issue',
    builder: (context) => _ErrorFeedbackSheet(error: error),
  );
}

class _ErrorFeedbackSheet extends StatefulWidget {
  final dynamic error;

  const _ErrorFeedbackSheet({required this.error});

  @override
  State<_ErrorFeedbackSheet> createState() => _ErrorFeedbackSheetState();
}

class _ErrorFeedbackSheetState extends State<_ErrorFeedbackSheet> {
  final _textController = TextEditingController();
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    String errorString = '';
    if (widget.error is TalkerError) {
      errorString =
          '${(widget.error as TalkerError).message}\n${(widget.error as TalkerError).stackTrace}';
    } else if (widget.error is TalkerException) {
      errorString =
          '${(widget.error as TalkerException).message}\n${(widget.error as TalkerException).stackTrace}';
    } else {
      errorString = widget.error.toString();
    }
    _textController.text = errorString;
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _isSubmitting = true);
    try {
      await IntercomManager.instance.intercom.displayMessageComposer(
        _textController.text,
      );
      if (mounted) Navigator.pop(context);
    } catch (e) {
      await IntercomManager.instance.intercom.displayMessenger();
      if (mounted) Navigator.pop(context);
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Please provide more details about what happened (optional):',
              style: OmiType.body.copyWith(color: OmiColors.textPrimary),
            ),
            const SizedBox(height: OmiSpacing.sm),
            TextField(
              controller: _textController,
              maxLines: 8,
              minLines: 4,
              decoration: const InputDecoration(
                hintText: 'Describe the issue...',
                filled: true,
                fillColor: OmiColors.surface2,
                border: OutlineInputBorder(
                  borderRadius: OmiRadius.smAll,
                  borderSide: BorderSide.none,
                ),
                contentPadding: EdgeInsets.all(OmiSpacing.sm),
              ),
              style: OmiType.body.copyWith(color: OmiColors.textPrimary),
            ),
            const SizedBox(height: OmiSpacing.md),
            OmiButton(
              onPressed: _submit,
              isLoading: _isSubmitting,
              child: const Text('Submit to Support'),
            ),
            const SizedBox(height: OmiSpacing.md),
          ],
        ),
      ),
    );
  }
}
