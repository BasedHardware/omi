import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/transcription/transcription_fields.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The native JSON field's limit in text units; a longer configuration keeps the complete Flutter editor.
const nativeJsonEditorLimit = 262144;

/// Pushed editor for a Custom STT request configuration or response schema. Pops with the edited
/// JSON on Save; back discards.
class TranscriptionJsonEditorPage extends StatefulWidget {
  const TranscriptionJsonEditorPage({
    super.key,
    required this.title,
    required this.initialJson,
    required this.provider,
    required this.onReset,
    this.isResponseSchema = false,
  });

  final String title;
  final String initialJson;
  final SttProvider provider;
  final Map<String, dynamic> Function() onReset;
  final bool isResponseSchema;

  @override
  State<TranscriptionJsonEditorPage> createState() => _TranscriptionJsonEditorPageState();
}

class _TranscriptionJsonEditorPageState extends State<TranscriptionJsonEditorPage> {
  late final TextEditingController _controller = TextEditingController(text: widget.initialJson);
  String? _parseError;

  /// Set once the JSON outgrows the native field: the complete Flutter editor then stays for this
  /// page, so shortening the text never swaps editors mid-edit.
  bool _beyondNativeLimit = false;

  @override
  void initState() {
    super.initState();
    _parseJson();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _parseJson() {
    if (_controller.text.length > nativeJsonEditorLimit) _beyondNativeLimit = true;
    try {
      jsonDecode(_controller.text);
      _parseError = null;
    } catch (e) {
      _parseError = e.toString();
    }
    setState(() {});
  }

  void _setJson(Object? json) {
    _controller.text = const JsonEncoder.withIndent('  ').convert(json);
    _parseJson();
  }

  void _applyTemplate(String name) {
    if (widget.isResponseSchema) {
      final schema = SttResponseSchema.templates[name];
      if (schema != null) _setJson(schema.toJson());
    } else {
      final template = SttProviderConfig.requestTemplates[name];
      if (template != null) _setJson(template);
    }
  }

  bool get _showTemplateSelector => widget.provider == SttProvider.custom || widget.provider == SttProvider.customLive;

  @override
  Widget build(BuildContext context) {
    final classic = Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(widget.title),
        actions: [
          TextButton(onPressed: () => _setJson(widget.onReset()), child: Text(context.l10n.reset)),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(OmiSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_showTemplateSelector) ...[_buildTemplateSelector(), const SizedBox(height: OmiSpacing.md)],
                  if (_parseError != null) _buildParseError(),
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      maxLines: null,
                      expands: true,
                      textAlignVertical: TextAlignVertical.top,
                      style: OmiType.footnote.copyWith(fontFamily: 'monospace'),
                      onChanged: (_) => _parseJson(),
                      decoration: transcriptionInputDecoration(),
                    ),
                  ),
                ],
              ),
            ),
          ),
          TranscriptionSaveBar(
            onPressed: _parseError != null ? null : () => Navigator.of(context).pop(_controller.text),
          ),
        ],
      ),
    );
    if (_beyondNativeLimit) return classic;
    final l10n = context.l10n;
    final templates =
        widget.isResponseSchema ? SttResponseSchema.templates.keys : SttProviderConfig.requestTemplates.keys;
    final liveTemplates =
        widget.isResponseSchema ? SttResponseSchema.liveTemplates : SttProviderConfig.liveRequestTemplates;
    return IosNativeSurface(title: widget.title, fallback: classic, toolbar: [
      NativeRow('json_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      NativeRow('json_reset', l10n.reset, action: (_) => _setJson(widget.onReset())),
      NativeRow('json_save', l10n.save,
          enabled: _parseError == null, action: (_) => Navigator.of(context).pop(_controller.text)),
    ], sections: [
      if (_showTemplateSelector)
        NativeSection(
            'json_templates',
            [
              NativeRow('json_template', l10n.selectProviderTemplate,
                  kind: 'menu',
                  options: {
                    for (final name in templates) name: liveTemplates.contains(name) ? '$name · ${l10n.live}' : name
                  },
                  action: (value) => _applyTemplate(value as String)),
            ],
            title: l10n.useTemplateFrom,
            footer: widget.isResponseSchema ? l10n.quicklyPopulateResponse : l10n.quicklyPopulateRequest),
      NativeSection('json_editor', [
        if (_parseError != null) NativeRow('json_error', l10n.invalidJsonError, kind: 'label'),
        NativeRow('json_text', widget.title,
            kind: 'text', maximumLength: nativeJsonEditorLimit, value: _controller.text, action: (value) {
          _controller.text = value as String;
          _parseJson();
        }),
      ]),
    ]);
  }

  Widget _buildTemplateSelector() {
    final isResponseSchema = widget.isResponseSchema;
    final templates =
        isResponseSchema ? SttResponseSchema.templates.keys.toList() : SttProviderConfig.requestTemplates.keys.toList();
    final liveTemplates = isResponseSchema ? SttResponseSchema.liveTemplates : SttProviderConfig.liveRequestTemplates;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionFieldLabel(context.l10n.useTemplateFrom),
        TranscriptionDropdown<String>(
          value: null,
          hint: context.l10n.selectProviderTemplate,
          items: [
            for (final name in templates)
              DropdownMenuItem<String>(
                value: name,
                child: TranscriptionOptionLabel(name, isLive: liveTemplates.contains(name)),
              ),
          ],
          onChanged: (name) {
            if (name != null) _applyTemplate(name);
          },
        ),
        const SizedBox(height: OmiSpacing.xxs),
        TranscriptionHelpText(
          isResponseSchema ? context.l10n.quicklyPopulateResponse : context.l10n.quicklyPopulateRequest,
        ),
      ],
    );
  }

  Widget _buildParseError() {
    return Container(
      margin: const EdgeInsets.only(bottom: OmiSpacing.sm),
      padding: const EdgeInsets.all(OmiSpacing.sm),
      decoration: BoxDecoration(
        color: OmiColors.dangerSurface,
        borderRadius: OmiRadius.smAll,
        border: Border.all(color: OmiColors.danger),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: OmiColors.danger, size: 18),
          const SizedBox(width: OmiSpacing.xs),
          Expanded(
            child: Text(context.l10n.invalidJsonError, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
          ),
        ],
      ),
    );
  }
}
