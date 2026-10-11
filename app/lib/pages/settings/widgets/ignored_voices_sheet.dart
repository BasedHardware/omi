import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/speaker_tag_prompts.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef IgnoredVoicesLoader = Future<ApiResult<GeneratedIgnoredVoicesResponse>> Function();
typedef IgnoredVoiceRestorer = Future<ApiResult<void>> Function(String conversationId, int speakerId);

/// Voices marked Not a Person (TV, podcasts). Restoring one lets Omi ask about it again.
Future<void> showIgnoredVoicesSheet(
  BuildContext context, {
  IgnoredVoicesLoader load = api.getIgnoredVoices,
  IgnoredVoiceRestorer restore = api.restoreIgnoredVoice,
}) =>
    showOmiSheet<void>(
      context: context,
      title: context.l10n.ignoredVoicesTitle,
      builder: (_) => _IgnoredVoices(load: load, restore: restore),
    );

class _IgnoredVoices extends StatefulWidget {
  const _IgnoredVoices({required this.load, required this.restore});

  final IgnoredVoicesLoader load;
  final IgnoredVoiceRestorer restore;

  @override
  State<_IgnoredVoices> createState() => _IgnoredVoicesState();
}

class _IgnoredVoicesState extends State<_IgnoredVoices> {
  List<GeneratedIgnoredVoice>? _voices;
  bool _failed = false;
  final Set<String> _restoring = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _failed = false);
    final result = await widget.load();
    if (!mounted) return;
    setState(() {
      switch (result) {
        case ApiSuccess(:final data):
          _voices = data.voices;
        case ApiFailure():
          _failed = true;
      }
    });
  }

  Future<void> _restore(GeneratedIgnoredVoice voice) async {
    final key = '${voice.conversationId}:${voice.speakerId}';
    setState(() => _restoring.add(key));
    final result = await widget.restore(voice.conversationId, voice.speakerId);
    if (!mounted) return;
    setState(() => _restoring.remove(key));
    if (result is ApiSuccess) {
      OmiHaptics.success();
      setState(() => _voices = _voices?.where((v) => v != voice).toList());
      OmiFeedback.confirm(context, context.l10n.voiceRestoredToast);
    } else {
      OmiFeedback.error(context, context.l10n.somethingWentWrongTryAgain);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final voices = _voices;
    if (_failed) {
      return OmiErrorState(message: l10n.somethingWentWrongTryAgain, onRetry: _load);
    }
    if (voices == null) return const Padding(padding: EdgeInsets.all(OmiSpacing.xl), child: OmiSpinner());
    if (voices.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xl),
        child: Text(
          l10n.ignoredVoicesEmpty,
          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          textAlign: TextAlign.center,
        ),
      );
    }
    final dates = OmiDateFormat.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
      child: OmiSettingsGroup(
        footer: l10n.ignoredVoicesSubtitle,
        children: [
          for (final voice in voices)
            OmiSettingsRow(
              leading: const Icon(Icons.tv_outlined),
              // No transcript here to number speakers densely (§9), so the conversation stands in.
              title: voice.conversationTitle.isEmpty ? l10n.untitledConversation : voice.conversationTitle,
              subtitle: dates.timestamp(voice.conversationStartedAt ?? voice.ignoredAt),
              trailing: OmiButton.secondary(
                label: l10n.restoreAction,
                size: OmiButtonSize.compact,
                isLoading: _restoring.contains('${voice.conversationId}:${voice.speakerId}'),
                onPressed: () => _restore(voice),
              ),
            ),
        ],
      ),
    );
  }
}
