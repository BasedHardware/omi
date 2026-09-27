import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Form pieces shared by the Transcription settings page and its JSON editor.

/// Small grey label above a field, with an optional trailing control.
class TranscriptionFieldLabel extends StatelessWidget {
  const TranscriptionFieldLabel(this.text, {super.key, this.trailing});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
      child: Row(
        children: [
          Expanded(child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary))),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

/// Supporting text under a field.
class TranscriptionHelpText extends StatelessWidget {
  const TranscriptionHelpText(this.text, {super.key, this.monospace = false});

  final String text;
  final bool monospace;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontFamily: monospace ? 'monospace' : null),
    );
  }
}

/// The filled, bordered field decoration used on the page.
InputDecoration transcriptionInputDecoration({String? hint, Widget? suffixIcon}) {
  OutlineInputBorder border(Color color) =>
      OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide(color: color));
  return InputDecoration(
    hintText: hint,
    hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
    filled: true,
    fillColor: OmiColors.surface1,
    contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
    border: border(OmiColors.border),
    enabledBorder: border(OmiColors.border),
    focusedBorder: border(OmiColors.accent),
    suffixIcon: suffixIcon,
  );
}

/// A labelled single-line text field.
class TranscriptionTextField extends StatelessWidget {
  const TranscriptionTextField({
    super.key,
    required this.controller,
    required this.label,
    required this.hint,
    this.keyboardType,
    this.onChanged,
  });

  final TextEditingController controller;
  final String label;
  final String hint;
  final TextInputType? keyboardType;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionFieldLabel(label),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          style: OmiType.subhead,
          onChanged: onChanged,
          decoration: transcriptionInputDecoration(hint: hint),
        ),
      ],
    );
  }
}

/// A labelled text field that suggests [suggestions] as the reader types.
class TranscriptionAutocompleteField extends StatelessWidget {
  const TranscriptionAutocompleteField({
    super.key,
    required this.label,
    required this.hint,
    required this.value,
    required this.suggestions,
    required this.onChanged,
  });

  final String label;
  final String hint;
  final String value;
  final List<String> suggestions;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionFieldLabel(label),
        Autocomplete<String>(
          initialValue: TextEditingValue(text: value),
          optionsBuilder: (textEditingValue) {
            final query = textEditingValue.text.toLowerCase();
            if (query.isEmpty) return suggestions;
            return suggestions.where((option) => option.toLowerCase().contains(query));
          },
          optionsViewBuilder: (context, onSelected, options) {
            return Align(
              alignment: Alignment.topLeft,
              child: Material(
                elevation: 4,
                color: OmiColors.surface2,
                borderRadius: OmiRadius.mdAll,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 200, maxWidth: 300),
                  child: ListView.builder(
                    padding: EdgeInsets.zero,
                    shrinkWrap: true,
                    itemCount: options.length,
                    itemBuilder: (context, index) {
                      final option = options.elementAt(index);
                      return ListTile(
                        dense: true,
                        title: Text(option, style: OmiType.subhead),
                        onTap: () => onSelected(option),
                      );
                    },
                  ),
                ),
              ),
            );
          },
          fieldViewBuilder: (context, controller, focusNode, onFieldSubmitted) {
            return TextField(
              controller: controller,
              focusNode: focusNode,
              style: OmiType.subhead,
              onChanged: onChanged,
              onSubmitted: (_) => onFieldSubmitted(),
              decoration: transcriptionInputDecoration(hint: hint),
            );
          },
          onSelected: onChanged,
        ),
      ],
    );
  }
}

/// A full-width dropdown in the page's field style.
class TranscriptionDropdown<T> extends StatelessWidget {
  const TranscriptionDropdown(
      {super.key, required this.value, required this.items, required this.onChanged, this.hint});

  final T? value;
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T?> onChanged;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<T>(
          value: value,
          hint: hint == null ? null : Text(hint!, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
          isExpanded: true,
          dropdownColor: OmiColors.surface2,
          style: OmiType.subhead,
          icon: const Icon(Icons.keyboard_arrow_down, color: OmiColors.textTertiary),
          items: items,
          onChanged: onChanged,
        ),
      ),
    );
  }
}

/// A dropdown item label with an optional "Live" badge.
class TranscriptionOptionLabel extends StatelessWidget {
  const TranscriptionOptionLabel(this.text, {super.key, this.isLive = false});

  final String text;
  final bool isLive;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Text(text)),
        if (isLive)
          Container(
            margin: const EdgeInsets.only(left: OmiSpacing.xs),
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: const BoxDecoration(color: OmiColors.successSurface, borderRadius: OmiRadius.smAll),
            child: Text(
              context.l10n.live,
              style: OmiType.caption.copyWith(color: OmiColors.success, fontWeight: FontWeight.w600),
            ),
          ),
      ],
    );
  }
}

/// A tappable header that expands and collapses a section ("Advanced", "Logs").
class TranscriptionDisclosureHeader extends StatelessWidget {
  const TranscriptionDisclosureHeader({
    super.key,
    required this.title,
    required this.expanded,
    required this.onToggle,
    this.trailing,
  });

  final String title;
  final bool expanded;
  final VoidCallback onToggle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Semantics(
            button: true,
            expanded: expanded,
            child: InkWell(
              onTap: onToggle,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 44),
                child: Row(
                  children: [
                    Text(title, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                    const SizedBox(width: OmiSpacing.xs),
                    Icon(
                      expanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                      color: OmiColors.textTertiary,
                      size: 18,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}

/// A card that opens a JSON editor, previewing the first keys of [jsonContent].
class TranscriptionJsonCard extends StatelessWidget {
  const TranscriptionJsonCard({
    super.key,
    required this.title,
    required this.jsonContent,
    required this.onTap,
    this.isCustomized = false,
  });

  final String title;
  final String jsonContent;
  final VoidCallback onTap;
  final bool isCustomized;

  @override
  Widget build(BuildContext context) {
    String preview = '';
    try {
      final parsed = jsonDecode(jsonContent);
      if (parsed is Map) {
        preview = parsed.keys.take(3).join(', ');
        if (parsed.keys.length > 3) preview += '…';
      }
    } catch (_) {
      preview = context.l10n.invalidJsonError;
    }

    return Material(
      color: OmiColors.surface1,
      shape: RoundedRectangleBorder(
        borderRadius: OmiRadius.mdAll,
        side: BorderSide(color: isCustomized ? OmiColors.accent : OmiColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(child: Text(title, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500))),
                        if (isCustomized) ...[
                          const SizedBox(width: OmiSpacing.xs),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: const BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
                            child: Text(context.l10n.modified, style: OmiType.caption),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: OmiSpacing.xxs),
                    Text(
                      preview,
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontFamily: 'monospace'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: OmiColors.textTertiary),
            ],
          ),
        ),
      ),
    );
  }
}

/// The pinned bottom bar with the page's primary action.
class TranscriptionSaveBar extends StatelessWidget {
  const TranscriptionSaveBar({super.key, required this.onPressed, this.isLoading = false});

  final VoidCallback? onPressed;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return Container(
      // The SafeArea below adds the system inset; adding it here as well left
      // twice the inset of dead space under the content on inset devices.
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.md),
      decoration: const BoxDecoration(
        color: OmiColors.surface0,
        border: Border(top: BorderSide(color: OmiColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: OmiButton(label: context.l10n.save, onPressed: onPressed, isLoading: isLoading, expand: true),
      ),
    );
  }
}
