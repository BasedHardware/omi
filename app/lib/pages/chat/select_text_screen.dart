import 'package:flutter/material.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'widgets/markdown_message_widget.dart';

class SelectTextScreen extends StatelessWidget {
  final ServerMessage message;
  const SelectTextScreen({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        automaticallyImplyLeading: true,
        title: Text(context.l10n.selectText),
        centerTitle: false,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new),
          onPressed: () {
            Navigator.pop(context);
          },
        ),
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(10.0),
        child: SelectionArea(child: getMarkdownWidget(context, message.text)),
      ),
    );
  }
}
