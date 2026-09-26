import 'package:flutter/material.dart';

import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/transcription/stt_language.dart';
import 'package:omi/pages/settings/transcription/transcription_fields.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Sections of the Transcription settings page that carry no page state of their own.

/// `en (English)` for a provider language code.
String sttLanguageLabel(String code) {
  final name = SttLanguages.common[code];
  return name != null ? '$code ($name)' : code;
}

/// The Custom STT provider's language.
///
/// By default it follows the primary language (Settings → Language) and is shown read-only with an
/// Override button. Only an explicit override shows the per-provider picker, with a way back.
class SttLanguageSection extends StatelessWidget {
  const SttLanguageSection({
    super.key,
    required this.provider,
    required this.overridden,
    required this.language,
    required this.primaryLanguage,
    required this.primaryLanguageName,
    required this.onOverride,
    required this.onUsePrimary,
    required this.onChanged,
    this.pickerKey,
  });

  final SttProvider provider;
  final bool overridden;

  /// The provider code in use (`en`, `multi`).
  final String language;

  /// The primary-language code and its display name.
  final String primaryLanguage;
  final String primaryLanguageName;

  final VoidCallback onOverride;
  final VoidCallback onUsePrimary;

  /// A provider code picked in the override picker.
  final ValueChanged<String> onChanged;

  /// Key for the picker, so it resets when the stored value changes underneath it.
  final Key? pickerKey;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (overridden) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TranscriptionAutocompleteField(
            key: pickerKey,
            label: l10n.languageLabel,
            hint: sttLanguageLabel('en'),
            value: sttLanguageLabel(language),
            suggestions: SttLanguage.supported(provider).map(sttLanguageLabel).toList(),
            // Suggestions read "en (English)"; the code is the first word.
            onChanged: (value) => onChanged(value.split(' ').first.trim()),
          ),
          const SizedBox(height: OmiSpacing.xxs),
          OmiButton.tertiary(label: l10n.sttUsePrimaryLanguage, size: OmiButtonSize.compact, onPressed: onUsePrimary),
        ],
      );
    }

    final name = SttLanguages.common[language] ?? language;
    final unsupported = primaryLanguage.isNotEmpty && SttLanguage.mapPrimary(provider, primaryLanguage) == null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionFieldLabel(l10n.languageLabel),
        OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              title: name,
              subtitle: unsupported
                  ? l10n.sttPrimaryLanguageUnsupported(primaryLanguageName, name)
                  : l10n.sttLanguageFollowsPrimary,
              trailing: OmiButton.secondary(
                label: l10n.sttLanguageOverride,
                size: OmiButtonSize.compact,
                onPressed: onOverride,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// On-device Whisper model: ready (with Re-download), downloading (progress and Cancel), or a
/// Download button.
class WhisperModelStatus extends StatelessWidget {
  const WhisperModelStatus({
    super.key,
    required this.modelFile,
    required this.hasModel,
    required this.isDownloading,
    required this.progress,
    required this.status,
    required this.onDownload,
    required this.onCancel,
  });

  final String modelFile;
  final bool hasModel;
  final bool isDownloading;
  final double progress;
  final String? status;
  final VoidCallback onDownload;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (isDownloading) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LinearProgressIndicator(value: progress, backgroundColor: OmiColors.surface3, color: OmiColors.accent),
          const SizedBox(height: OmiSpacing.xs),
          Center(child: Text(l10n.doNotCloseApp, style: OmiType.footnote.copyWith(color: OmiColors.warning))),
          const SizedBox(height: OmiSpacing.xxs),
          Row(
            children: [
              Expanded(child: TranscriptionHelpText(status ?? l10n.downloading)),
              OmiButton.tertiary(label: l10n.cancel, size: OmiButtonSize.compact, onPressed: onCancel),
            ],
          ),
        ],
      );
    }
    if (hasModel) {
      return Container(
        padding: const EdgeInsets.only(left: OmiSpacing.sm, top: OmiSpacing.xxs, bottom: OmiSpacing.xxs),
        decoration: BoxDecoration(
          color: OmiColors.successSurface,
          borderRadius: OmiRadius.smAll,
          border: Border.all(color: OmiColors.success.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            const Icon(Icons.check_circle, color: OmiColors.success, size: 20),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Text(l10n.modelReadyWithName(modelFile),
                  style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500)),
            ),
            OmiButton.tertiary(label: l10n.reDownload, size: OmiButtonSize.compact, onPressed: onDownload),
          ],
        ),
      );
    }
    return OmiButton(
      label: l10n.downloadModelWithName(modelFile),
      icon: Icons.download,
      expand: true,
      onPressed: onDownload,
    );
  }
}

/// The Custom STT log viewer, collapsible, with Copy Logs.
class CustomSttLogsSection extends StatefulWidget {
  const CustomSttLogsSection({super.key});

  @override
  State<CustomSttLogsSection> createState() => _CustomSttLogsSectionState();
}

class _CustomSttLogsSectionState extends State<CustomSttLogsSection> {
  bool _expanded = true;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final logService = CustomSttLogService.instance;
    final logs = logService.logs;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionDisclosureHeader(
          title: l10n.logs,
          expanded: _expanded,
          onToggle: () => setState(() => _expanded = !_expanded),
          trailing: _expanded && logs.isNotEmpty
              ? OmiIconButton(
                  icon: const Icon(Icons.copy, size: 16),
                  label: l10n.copyLogs,
                  color: OmiColors.textTertiary,
                  onPressed: () => OmiClipboard.copy(context, logService.logsAsText, what: l10n.logs),
                )
              : null,
        ),
        if (_expanded)
          Container(
            constraints: const BoxConstraints(maxHeight: 200),
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.mdAll,
              border: Border.all(color: OmiColors.border),
            ),
            child: logs.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    child: Center(child: TranscriptionHelpText(l10n.noLogsYet)),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    padding: const EdgeInsets.all(OmiSpacing.xs),
                    itemCount: logs.length,
                    itemBuilder: (context, index) => _LogLine(log: logs[index]),
                  ),
          ),
      ],
    );
  }
}

class _LogLine extends StatelessWidget {
  const _LogLine({required this.log});

  final CustomSttLogEntry log;

  @override
  Widget build(BuildContext context) {
    final (IconData icon, Color color) = switch (log.level) {
      CustomSttLogLevel.error => (Icons.error_outline, OmiColors.danger),
      CustomSttLogLevel.warning => (Icons.warning_amber_outlined, OmiColors.warning),
      _ => (Icons.info_outline, OmiColors.textSecondary),
    };
    final mono = OmiType.caption.copyWith(fontFamily: 'monospace');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(log.formattedTime, style: mono.copyWith(color: OmiColors.textTertiary)),
          const SizedBox(width: 6),
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 6),
          Expanded(child: Text('[${log.source}] ${log.message}', style: mono.copyWith(color: color))),
        ],
      ),
    );
  }
}
