import 'package:flutter/material.dart';

import 'package:intercom_flutter/intercom_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class LoggerErrorSheet extends StatefulWidget {
  final String initialText;

  const LoggerErrorSheet({super.key, required this.initialText});

  @override
  State<LoggerErrorSheet> createState() => _LoggerErrorSheetState();
}

class _LoggerErrorSheetState extends State<LoggerErrorSheet> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialText);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _controller,
          maxLines: 10,
          style: OmiType.body.copyWith(color: OmiColors.textPrimary),
          decoration: InputDecoration(
            filled: true,
            fillColor: OmiColors.surface2,
            border: const OutlineInputBorder(
              borderRadius: OmiRadius.mdAll,
              borderSide: BorderSide.none,
            ),
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
        OmiButton(
          label: context.l10n.submit,
          onPressed: () {
            Intercom.instance.displayMessageComposer(_controller.text);
            Navigator.pop(context);
          },
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
    );
  }
}
