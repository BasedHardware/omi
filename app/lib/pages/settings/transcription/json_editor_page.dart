import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/pages/settings/transcription/transcription_fields.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
    return Scaffold(
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
          const Icon(Icons.error_outline, color: OmiColors.danger, size: 18),
          const SizedBox(width: OmiSpacing.xs),
          Expanded(
            child: Text(context.l10n.invalidJsonError, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
          ),
        ],
      ),
    );
  }
}
