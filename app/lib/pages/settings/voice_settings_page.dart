import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/assistant_voices.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/services/voice_playback/chat_reply_read_aloud.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class VoiceSettingsPage extends StatefulWidget {
  const VoiceSettingsPage({super.key, this.api, this.onPreview, this.onStopPreview, this.onRevokeReadAloud});

  final AssistantVoicesApi? api;

  final Future<void> Function(String voiceId)? onPreview;

  final Future<void> Function()? onStopPreview;

  final void Function()? onRevokeReadAloud;

  @override
  State<VoiceSettingsPage> createState() => _VoiceSettingsPageState();
}

class _VoiceSettingsPageState extends State<VoiceSettingsPage> {
  final _prefs = SharedPreferencesUtil();

  bool _loading = true;
  String? _error;
  List<AssistantVoice> _voices = const [];
  String _defaultVoiceId = 'Charon';
  String? _selectedVoiceId;
  bool _saving = false;
  final ValueNotifier<String?> _previewing = ValueNotifier(null);
  int _loadEpoch = 0;
  int _previewEpoch = 0;
  late final String _ownerUid = _prefs.uid;

  AssistantVoicesApi get _api => widget.api ?? const AssistantVoicesApi();

  bool get _ownerChanged => _prefs.uid != _ownerUid;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _previewEpoch++;
    _previewing.dispose();
    (widget.onStopPreview ?? OmiVoicePlaybackService.instance.stopPreview)();
    super.dispose();
  }

  Future<void> _load() async {
    final epoch = ++_loadEpoch;
    setState(() {
      _loading = true;
      _error = null;
    });
    if (_ownerChanged) {
      setState(() {
        _loading = false;
        _error = 'unavailable';
      });
      return;
    }
    final ApiResult<AssistantVoiceCatalog> catalog;
    try {
      catalog = await _api.getCatalog();
    } catch (e) {
      if (!mounted || epoch != _loadEpoch) return;
      if (_ownerChanged) {
        setState(() {
          _loading = false;
          _error = 'unavailable';
        });
        return;
      }
      setState(() {
        _loading = false;
        _error = e.toString();
      });
      return;
    }
    if (!mounted || epoch != _loadEpoch) return;
    if (_ownerChanged) {
      setState(() {
        _loading = false;
        _error = 'unavailable';
      });
      return;
    }
    switch (catalog) {
      case ApiFailure(:final problem):
        setState(() {
          _loading = false;
          _error = problem.toString();
        });
        return;
      case ApiSuccess(:final data):
        _voices = data.voices;
        _defaultVoiceId = data.defaultVoiceId;
    }
    if (_ownerChanged) {
      setState(() {
        _loading = false;
        _error = 'unavailable';
      });
      return;
    }
    final ApiResult<AssistantVoicePreference> preference;
    try {
      preference = await _api.getPreference();
    } catch (e) {
      if (!mounted || epoch != _loadEpoch) return;
      if (_ownerChanged) {
        setState(() {
          _loading = false;
          _error = 'unavailable';
        });
        return;
      }
      setState(() {
        _loading = false;
        _error = e.toString();
      });
      return;
    }
    if (!mounted || epoch != _loadEpoch) return;
    if (_ownerChanged) {
      setState(() {
        _loading = false;
        _error = 'unavailable';
      });
      return;
    }
    switch (preference) {
      case ApiFailure(:final problem):
        setState(() {
          _loading = false;
          _error = problem.toString();
        });
      case ApiSuccess(:final data):
        setState(() {
          _loading = false;
          _selectedVoiceId = data.voiceId;
        });
    }
  }

  Future<void> _preview(String voiceId) async {
    if (_previewing.value != null || _ownerChanged) return;
    final epoch = ++_previewEpoch;
    _previewing.value = voiceId;
    final preview = widget.onPreview ??
        (id) => OmiVoicePlaybackService.instance.playPreview(
              context.l10n.voicePreviewSample,
              voiceId: id,
              allowSystemFallback: false,
            );
    try {
      await preview(voiceId);
    } catch (_) {
      if (mounted && epoch == _previewEpoch && !_ownerChanged) {
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
    }
    if (mounted && epoch == _previewEpoch) {
      _previewing.value = null;
    }
  }

  Future<void> _saveVoice(String voiceId) async {
    if (_saving || voiceId == _selectedVoiceId || _ownerChanged) return;
    setState(() => _saving = true);
    try {
      final result = await _api.setPreference(voiceId);
      if (!mounted || _ownerChanged) return;
      switch (result) {
        case ApiSuccess(:final data):
          setState(() => _selectedVoiceId = data.voiceId);
        case ApiFailure():
          OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
    } catch (_) {
      if (mounted && !_ownerChanged) {
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _revokeReadAloud() {
    (widget.onRevokeReadAloud ?? ChatReplyReadAloud.instance.revoke)();
  }

  AssistantVoice? get _selectedVoice {
    for (final voice in _voices) {
      if (voice.id == _selectedVoiceId) return voice;
    }
    return null;
  }

  String _voiceResponseModeLabel(int mode) {
    switch (mode) {
      case 0:
        return context.l10n.voiceResponseOff;
      case 2:
        return context.l10n.voiceResponseAlways;
      case 1:
      default:
        return context.l10n.voiceResponseHeadphonesOnly;
    }
  }

  Future<void> _showModeSheet() async {
    final current = _prefs.voiceResponseMode;
    final picked = await showOmiSheet<int>(
      context: context,
      title: context.l10n.voiceResponseModeTitle,
      builder: (sheetContext) => OmiSettingsGroup(
        children: [
          for (final mode in const [0, 1, 2])
            OmiSettingsRow(
              title: _voiceResponseModeLabel(mode),
              trailing: mode == current ? Icon(Icons.check, color: OmiColors.textPrimary, size: 20) : null,
              showChevron: false,
              onTap: () => Navigator.of(sheetContext).pop(mode),
            ),
        ],
      ),
    );
    _applyMode(picked, current);
  }

  /// Persists a picked response mode; Off also withdraws a read-aloud grant.
  void _applyMode(int? picked, int current) {
    if (picked == null || picked == current || !mounted || _ownerChanged) return;
    setState(() => _prefs.voiceResponseMode = picked);
    if (picked == 0) _revokeReadAloud();
    PlatformManager.instance.analytics.voiceResponseModeChanged(picked);
  }

  void _setReadAloud(bool value) {
    if (_ownerChanged) return;
    setState(() => _prefs.readChatRepliesAloud = value);
    if (!value) _revokeReadAloud();
  }

  Widget _voicePickerList(BuildContext sheetContext, List<AssistantVoice> voices, String? selected) =>
      SingleChildScrollView(
        child: OmiSettingsGroup(
          children: [
            for (final voice in voices)
              OmiSettingsRow(
                key: ValueKey('settings_voice_${voice.id}'),
                title: voice.name,
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (voice.id == selected) Icon(Icons.check, color: OmiColors.textPrimary, size: 20),
                    ValueListenableBuilder<String?>(
                      valueListenable: _previewing,
                      builder: (_, previewing, __) => OmiIconButton(
                        key: ValueKey('settings_voice_preview_${voice.id}'),
                        icon: previewing == voice.id
                            ? const OmiSpinner(size: OmiSpinnerSize.small)
                            : const Icon(Icons.play_arrow, size: 18),
                        label: context.l10n.preview,
                        onPressed: previewing == null ? () => _preview(voice.id) : null,
                      ),
                    ),
                  ],
                ),
                showChevron: false,
                onTap: _saving ? null : () => Navigator.of(sheetContext).pop(voice.id),
              ),
          ],
        ),
      );

  Future<void> _showVoicePicker() async {
    final selected = _selectedVoiceId;
    // Native rows address voices by index into the catalog as it was when the picker opened.
    final voices = _voices;
    try {
      final picked = await showOmiSheet<String>(
        context: context,
        title: context.l10n.assistantVoice,
        builder: (sheetContext) => _voicePickerList(sheetContext, voices, selected),
        nativeBuilder: (sheetContext) => NativeVoicePicker(
          voices: voices,
          selectedId: selected,
          previewing: _previewing,
          saving: _saving,
          onPreview: _preview,
          fallback: OmiSheetScaffold(
            title: sheetContext.l10n.assistantVoice,
            child: _voicePickerList(sheetContext, voices, selected),
          ),
        ),
      );
      if (picked == null || !mounted || _ownerChanged) return;
      await _saveVoice(picked);
    } finally {
      _previewEpoch++;
      await (widget.onStopPreview ?? OmiVoicePlaybackService.instance.stopPreview)();
      if (mounted) _previewing.value = null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final classic = Scaffold(
      key: const ValueKey('settings_page_voice'),
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.assistantVoiceSettingsTitle)),
      body: _loading
          ? const OmiLoadingState()
          : _error != null
              ? OmiErrorState(message: l10n.somethingWentWrong, onRetry: _load)
              : ListView(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.xxl),
                  children: [
                    OmiSettingsGroup(
                      footer: l10n.voiceSharedAcrossDevices,
                      children: [
                        OmiSettingsRow(
                          key: const ValueKey('settings_row_assistantVoice'),
                          leading: const FaIcon(FontAwesomeIcons.waveSquare),
                          title: l10n.assistantVoice,
                          subtitle: _selectedVoice?.name ?? _selectedVoiceId ?? _defaultVoiceId,
                          trailing: _selectedVoiceId == null
                              ? null
                              : ValueListenableBuilder<String?>(
                                  valueListenable: _previewing,
                                  builder: (_, previewing, __) => OmiIconButton(
                                    key: const ValueKey('settings_voice_preview_selected'),
                                    icon: previewing == _selectedVoiceId
                                        ? const OmiSpinner(size: OmiSpinnerSize.small)
                                        : const Icon(Icons.play_arrow, size: 18),
                                    label: l10n.preview,
                                    onPressed: previewing == null ? () => _preview(_selectedVoiceId!) : null,
                                  ),
                                ),
                          onTap: _saving ? null : _showVoicePicker,
                        ),
                      ],
                    ),
                    const SizedBox(height: OmiSpacing.xl),
                    OmiSettingsGroup(
                      children: [
                        OmiSettingsRow(
                          key: const ValueKey('settings_row_voiceResponseMode'),
                          leading: const FaIcon(FontAwesomeIcons.volumeHigh),
                          title: l10n.voiceResponseMode,
                          value: _voiceResponseModeLabel(_prefs.voiceResponseMode),
                          onTap: _showModeSheet,
                        ),
                        OmiSettingsRow.toggle(
                          key: const ValueKey('settings_row_readChatRepliesAloud'),
                          leading: const FaIcon(FontAwesomeIcons.commentDots),
                          title: l10n.readChatRepliesAloud,
                          subtitle: l10n.readChatRepliesAloudDescription,
                          value: _prefs.readChatRepliesAloud,
                          onChanged: _setReadAloud,
                        ),
                      ],
                    ),
                  ],
                ),
    );
    return ValueListenableBuilder<String?>(
      valueListenable: _previewing,
      builder: (context, previewing, _) {
        final mode = _prefs.voiceResponseMode;
        return IosNativeSurface(
          title: l10n.assistantVoiceSettingsTitle,
          fallback: classic,
          loading: _loading,
          failed: _error != null,
          errorMessage: l10n.somethingWentWrong,
          onRefresh: (_) => _load(),
          toolbar: [
            NativeRow('voice_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          ],
          sections: [
            if (!_loading && _error == null) ...[
              NativeSection(
                'voice',
                [
                  NativeRow('voice_current', l10n.assistantVoice,
                      kind: 'navigation',
                      symbol: 'waveform',
                      subtitle: _selectedVoice?.name ?? _selectedVoiceId ?? _defaultVoiceId,
                      enabled: !_saving,
                      action: (_) => _showVoicePicker()),
                  if (_selectedVoiceId != null)
                    NativeRow('voice_preview_current', l10n.preview,
                        symbol: previewing == _selectedVoiceId ? 'hourglass' : 'play.fill',
                        enabled: previewing == null,
                        action: (_) => _preview(_selectedVoiceId!)),
                ],
                footer: l10n.voiceSharedAcrossDevices,
              ),
              NativeSection('voice_options', [
                NativeRow('voice_mode', l10n.voiceResponseMode,
                    kind: 'choice',
                    symbol: 'speaker.wave.2',
                    // An unknown stored mode reads as the default, exactly as the classic label does.
                    value: const [0, 1, 2].contains(mode) ? '$mode' : '1',
                    options: {
                      for (final option in const [0, 1, 2]) '$option': _voiceResponseModeLabel(option)
                    },
                    action: (value) => _applyMode(int.parse(value as String), _prefs.voiceResponseMode)),
                NativeRow('voice_read_aloud', l10n.readChatRepliesAloud,
                    kind: 'toggle',
                    subtitle: l10n.readChatRepliesAloudDescription,
                    value: _prefs.readChatRepliesAloud,
                    action: (value) => _setReadAloud(value as bool)),
              ]),
            ],
          ],
        );
      },
    );
  }
}

/// The voice picker's native rows: 'voice:<index>' picks the voice at that index of [voices] (the
/// catalog captured when the picker opened) and 'voice_preview:<index>' previews it. Picking pops
/// the voice id; the caller saves it and stops any preview when the sheet closes.
class NativeVoicePicker extends StatelessWidget {
  const NativeVoicePicker({
    super.key,
    required this.voices,
    required this.selectedId,
    required this.previewing,
    required this.saving,
    required this.onPreview,
    required this.fallback,
  });

  final List<AssistantVoice> voices;
  final String? selectedId;
  final ValueListenable<String?> previewing;
  final bool saving;
  final Future<void> Function(String voiceId) onPreview;

  /// The complete Flutter picker, already inside its sheet scaffold.
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ValueListenableBuilder<String?>(
      valueListenable: previewing,
      builder: (context, current, _) => IosNativeSurface(
        title: l10n.assistantVoice,
        fallback: fallback,
        toolbar: [
          NativeRow('voice_picker_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
        ],
        sections: [
          for (final (index, voice) in voices.indexed)
            NativeSection('voice_group:$index', [
              NativeRow('voice:$index', voice.name,
                  // A selection outside the catalog checks nothing.
                  symbol: voice.id == selectedId ? 'checkmark' : null,
                  enabled: !saving,
                  action: (_) => Navigator.of(context).pop(voice.id)),
              NativeRow('voice_preview:$index', l10n.preview,
                  subtitle: voice.name,
                  symbol: current == voice.id ? 'hourglass' : 'play.fill',
                  enabled: current == null,
                  action: (_) => onPreview(voice.id)),
            ]),
        ],
      ),
    );
  }
}
