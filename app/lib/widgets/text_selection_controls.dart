import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/utils/l10n_extensions.dart';

class OmiTextSelectionToolbar extends StatelessWidget {
  final Offset anchorAbove;
  final Offset anchorBelow;
  final List<Widget> children;

  const OmiTextSelectionToolbar({
    super.key,
    required this.anchorAbove,
    required this.anchorBelow,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoTheme(
      data: const CupertinoThemeData(
        brightness: Brightness.dark,
        primaryColor: Colors.blue,
      ),
      child: CupertinoTextSelectionToolbar(
        anchorAbove: anchorAbove,
        anchorBelow: anchorBelow,
        children: children,
      ),
    );
  }
}

class OmiToolbarAction extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;

  const OmiToolbarAction({
    super.key,
    required this.label,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoTextSelectionToolbarButton.text(
      onPressed: onPressed,
      text: label,
    );
  }
}

class OmiToolbarDivider extends StatelessWidget {
  const OmiToolbarDivider({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1.0 / MediaQuery.of(context).devicePixelRatio,
      height: 20,
      color: const Color.fromARGB(70, 255, 255, 255), 
    );
  }
}

Widget omiSelectionMenuBuilder(
  BuildContext context,
  dynamic delegate,
  Function(String) onAskOmi, {
  String? selectedText,
}) {
  final List<Widget> toolbarItems = [];
  String text = selectedText ?? '';
  
  if (delegate is TextSelectionDelegate && text.isEmpty) {
    text = delegate.textEditingValue.selection.textInside(delegate.textEditingValue.text);
  }
  
  // Ask Omi
  if (text.trim().isNotEmpty) {
    toolbarItems.add(OmiToolbarAction(
      label: 'Ask Omi',
      onPressed: () {
        onAskOmi(text);
        delegate.hideToolbar();
      },
    ));
  }

  if (text.isNotEmpty) {
    if (toolbarItems.isNotEmpty) {
      toolbarItems.add(const OmiToolbarDivider());
    }
    toolbarItems.add(OmiToolbarAction(
      label: 'Copy',
      onPressed: () {
        delegate.copySelection(SelectionChangedCause.toolbar);
        delegate.hideToolbar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.messageCopied),
            duration: const Duration(seconds: 2),
          ),
        );
      },
    ));
  }

  // Select All
  if (toolbarItems.isNotEmpty) {
    toolbarItems.add(const OmiToolbarDivider());
  }
  toolbarItems.add(OmiToolbarAction(
    label: context.l10n.selectAll,
    onPressed: () {
      delegate.selectAll(SelectionChangedCause.toolbar);
    },
  ));

  if (toolbarItems.isEmpty) {
    return const SizedBox.shrink();
  }

  return OmiTextSelectionToolbar(
    anchorAbove: delegate.contextMenuAnchors.primaryAnchor,
    anchorBelow: delegate.contextMenuAnchors.secondaryAnchor ??
        delegate.contextMenuAnchors.primaryAnchor,
    children: toolbarItems,
  );
}
