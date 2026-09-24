import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PromptTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  const PromptTextField({super.key, required this.controller, required this.label, required this.hint});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
      child: TextFormField(
        maxLines: null,
        minLines: 4,
        controller: controller,
        validator: (value) {
          if (value == null || value.isEmpty) {
            return context.l10n.pleaseProvidePrompt;
          }
          return null;
        },
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          hintMaxLines: 4,
          labelStyle: TextStyle(color: Colors.grey.shade400),
          hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
          floatingLabelStyle: TextStyle(color: Colors.grey.shade300),
          alignLabelWithHint: true,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 16.0),
          border: OutlineInputBorder(
            borderRadius: OmiRadius.mdAll,
            borderSide: BorderSide(color: Colors.grey.withValues(alpha: 0.3), width: 1),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: OmiRadius.mdAll,
            borderSide: BorderSide(color: Colors.grey.withValues(alpha: 0.3), width: 1),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: OmiRadius.mdAll,
            borderSide: BorderSide(color: Colors.grey.shade400, width: 1),
          ),
          errorBorder: const OutlineInputBorder(
            borderRadius: OmiRadius.mdAll,
            borderSide: BorderSide(color: OmiColors.danger, width: 1),
          ),
          filled: false,
        ),
      ),
    );
  }
}
