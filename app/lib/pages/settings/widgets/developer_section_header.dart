import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A Developer settings section's title with its Docs and Create Key buttons. The buttons wrap
/// under the title instead of overflowing on a narrow phone, in a longer language or at a larger
/// text size.
class DeveloperSectionHeader extends StatelessWidget {
  const DeveloperSectionHeader({super.key, required this.title, required this.docs, required this.onCreateKey});

  final String title;

  /// The section's Docs button.
  final Widget docs;

  final VoidCallback onCreateKey;

  @override
  Widget build(BuildContext context) {
    return OmiSectionHeader(
      title,
      trailing: Wrap(
        spacing: OmiSpacing.xs,
        runSpacing: OmiSpacing.xs,
        children: [
          docs,
          OmiButton.secondary(
            label: context.l10n.createKey,
            leading: const FaIcon(FontAwesomeIcons.plus),
            size: OmiButtonSize.compact,
            onPressed: onCreateKey,
          ),
        ],
      ),
    );
  }
}
