import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/transcription/transcription_fields.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Dialogs of the Transcription settings page, on the shared dialog system (docs/ux-contract.md §5).

/// Asks before switching to on-device transcription. [lowSpec] devices get a stronger warning;
/// on Android that warning's default is to stay put (Whisper may crash there).
Future<bool> confirmOnDeviceTranscription(
  BuildContext context, {
  required bool lowSpec,
  required bool isIOS,
  required String specDetails,
}) {
  final l10n = context.l10n;
  if (lowSpec && !isIOS) {
    return showOmiConfirm(
      context,
      title: l10n.deviceNotCompatibleTitle,
      message: [
        l10n.deviceNotMeetRequirements,
        specDetails,
        l10n.willLikelyCrash,
        l10n.transcriptionSlowerLessAccurate,
      ].join('\n\n'),
      confirmLabel: l10n.proceedAnyway,
      cancelLabel: l10n.close,
      destructive: true,
    );
  }
  if (lowSpec) {
    return showOmiConfirm(
      context,
      title: l10n.olderDeviceDetected,
      message: '$specDetails\n\n${l10n.transcriptionSlowerOnDevice}\n'
          '• ${l10n.batteryUsageHigher}\n• ${l10n.considerOmiCloud}',
      confirmLabel: l10n.continueButton,
    );
  }
  return showOmiConfirm(
    context,
    title: l10n.highResourceUsage,
    message: '${l10n.computationallyIntensive}\n\n'
        '• ${l10n.batteryDrainSignificantly}\n• ${l10n.deviceMayWarmUp}\n• ${l10n.speedAccuracyLower}',
    confirmLabel: l10n.iUnderstand,
  );
}

/// Asks before downloading a Whisper model; Download is disabled when there is not enough space.
Future<bool> confirmModelDownload(
  BuildContext context, {
  required String modelName,
  required double estimatedSizeMB,
  required double? freeSpaceMB,
}) async {
  final notEnoughSpace = freeSpaceMB != null && freeSpaceMB < estimatedSizeMB;
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      final l10n = dialogContext.l10n;
      return OmiAlertDialog(
        title: l10n.downloadModel,
        message: [
          l10n.modelNameWithFile('ggml-$modelName.bin'),
          l10n.estimatedSizeWithValue(estimatedSizeMB.toStringAsFixed(0)),
          l10n.availableSpaceWithValue(
            freeSpaceMB != null ? '${freeSpaceMB.toStringAsFixed(0)} MB' : l10n.unknown,
          ),
        ].join('\n'),
        content: notEnoughSpace
            ? Text(
                l10n.notEnoughSpace,
                style: OmiType.subhead.copyWith(color: OmiColors.danger, fontWeight: FontWeight.w600),
              )
            : null,
        actions: [
          OmiDialogAction(label: l10n.cancel, onPressed: () => Navigator.of(dialogContext).pop(false)),
          OmiDialogAction(
            label: l10n.download,
            isDefault: true,
            onPressed: notEnoughSpace ? null : () => Navigator.of(dialogContext).pop(true),
          ),
        ],
      );
    },
  );
  return confirmed ?? false;
}

/// The longest configuration the native text field holds; the caller itself imports any length.
const _nativeImportLimit = 262144;

/// Asks for a pasted JSON configuration; resolves to the text, or null when cancelled.
///
/// Natively, Paste reads the clipboard here in Dart and presents the sheet again with that text. A
/// clipboard longer than the native field's limit is returned at once for import rather than cut.
/// Without the native presentation, the Flutter dialog opens with the text entered so far.
Future<String?> showImportConfigDialog(BuildContext context) async {
  var text = '';
  while (true) {
    if (!context.mounted) return null;
    final l10n = context.l10n;
    final result = await showIosNativeModal(
      context,
      title: l10n.importConfiguration,
      actions: [
        NativeRow('cancel', l10n.cancel),
        NativeRow('paste', l10n.paste),
        NativeRow('import', l10n.import),
      ],
      sections: [
        NativeSection('import_config', [
          NativeRow('import_hint', l10n.pasteJsonConfig, kind: 'label'),
          NativeRow('import_json', l10n.transcriptionJsonPlaceholder,
              kind: 'text', maximumLength: _nativeImportLimit, value: text),
          NativeRow('import_api_key', l10n.addApiKeyAfterImport, kind: 'label'),
        ]),
      ],
    );
    if (result == null) {
      if (!context.mounted) return null;
      return _showFlutterImportConfigDialog(context, initialText: text);
    }
    // Cancelled, dismissed or withdrawn: nothing is imported.
    if (result.action == null) return null;
    final edited = result.values['import_json'] as String? ?? text;
    if (result.action == 'import') return edited;
    final pasted = (await Clipboard.getData(Clipboard.kTextPlain))?.text;
    if (pasted != null && pasted.length > _nativeImportLimit) return pasted;
    text = pasted ?? edited;
  }
}

Future<String?> _showFlutterImportConfigDialog(BuildContext context, {String initialText = ''}) =>
    showDialog<String>(context: context, builder: (_) => _ImportConfigDialog(initialText: initialText));

/// Owns its text controller, so the field stays usable through the dialog's exit transition.
class _ImportConfigDialog extends StatefulWidget {
  const _ImportConfigDialog({required this.initialText});

  final String initialText;

  @override
  State<_ImportConfigDialog> createState() => _ImportConfigDialogState();
}

class _ImportConfigDialogState extends State<_ImportConfigDialog> {
  late final TextEditingController _controller = TextEditingController(text: widget.initialText);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiAlertDialog(
      title: l10n.importConfiguration,
      message: l10n.pasteJsonConfig,
      content: Material(
        type: MaterialType.transparency,
        child: SizedBox(
          width: double.maxFinite,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                height: 200,
                child: TextField(
                  controller: _controller,
                  maxLines: null,
                  expands: true,
                  textAlignVertical: TextAlignVertical.top,
                  style: OmiType.footnote.copyWith(fontFamily: 'monospace'),
                  decoration: transcriptionInputDecoration(hint: l10n.transcriptionJsonPlaceholder),
                ),
              ),
              const SizedBox(height: OmiSpacing.xs),
              TranscriptionHelpText(l10n.addApiKeyAfterImport),
            ],
          ),
        ),
      ),
      actions: [
        OmiDialogAction(label: l10n.cancel, onPressed: () => Navigator.of(context).pop()),
        OmiDialogAction(
          label: l10n.paste,
          onPressed: () async {
            final clipboardData = await Clipboard.getData(Clipboard.kTextPlain);
            final text = clipboardData?.text;
            if (text != null && mounted) _controller.text = text;
          },
        ),
        OmiDialogAction(
          label: l10n.import,
          isDefault: true,
          onPressed: () => Navigator.of(context).pop(_controller.text),
        ),
      ],
    );
  }
}
