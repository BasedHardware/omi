import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

// Pieces of the chat composer that carry no page state. The text field and the Send button stay
// in `chat/page.dart`: they are the catalogued controls (omi.chat.input / omi.chat.send).

/// The soft shadow that lifts the composer pill and its side button off the transcript.
const List<BoxShadow> kChatComposerShadow = [
  BoxShadow(color: Color.fromRGBO(0, 0, 0, 0.65), blurRadius: 60, spreadRadius: 14, offset: Offset(0, -16)),
  BoxShadow(color: Color.fromRGBO(0, 0, 0, 0.45), blurRadius: 32, spreadRadius: 6, offset: Offset(0, -8)),
  BoxShadow(color: Color.fromRGBO(0, 0, 0, 0.25), blurRadius: 10, offset: Offset(0, 2)),
];

/// The 48 pt round button beside the composer pill: Add (idle) or Stop (recording).
///
/// Labelled for screen readers and long-press; [onPressed] null draws it disabled.
class ChatComposerSideButton extends StatelessWidget {
  const ChatComposerSideButton({super.key, required this.icon, required this.label, required this.onPressed});

  final Widget icon;
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        button: true,
        enabled: enabled,
        label: label,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onPressed,
          child: Container(
            height: 48,
            width: 48,
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              shape: BoxShape.circle,
              border: Border.all(color: OmiColors.surface3, width: 1),
              boxShadow: kChatComposerShadow,
            ),
            child: Center(
              child: ExcludeSemantics(
                child: IconTheme.merge(
                  data: IconThemeData(color: enabled ? OmiColors.textPrimary : OmiColors.textDisabled, size: 18),
                  child: icon,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The round 38 pt button inside the composer pill (mic, send-while-recording), in a 44 pt target.
///
/// A disabled button is visibly disabled: a dark fill and a dimmed glyph instead of the white
/// "ready" fill. The glyph is a widget (FontAwesome `arrowUp` / `microphone`, like the side
/// button's `plus`), 16 pt and tinted through [IconTheme].
class ChatComposerRoundButton extends StatelessWidget {
  const ChatComposerRoundButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onPressed,
    this.buttonKey,
  });

  final Widget icon;
  final String label;
  final VoidCallback? onPressed;

  /// Key for the tappable widget itself (automation addresses it).
  final Key? buttonKey;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        button: true,
        enabled: enabled,
        label: label,
        child: GestureDetector(
          key: buttonKey,
          behavior: HitTestBehavior.opaque,
          onTap: onPressed,
          child: SizedBox.square(
            dimension: kOmiMinTapTarget,
            child: Center(
              child: AnimatedContainer(
                duration: OmiMotion.of(context).quick,
                height: 38,
                width: 38,
                decoration: BoxDecoration(
                  color: enabled ? OmiColors.accent : OmiColors.surface3,
                  shape: BoxShape.circle,
                ),
                child: ExcludeSemantics(
                  child: IconTheme.merge(
                    data: IconThemeData(size: 16, color: enabled ? OmiColors.onAccent : OmiColors.textDisabled),
                    child: Center(child: icon),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Thumbnails of the files picked for the next message, each with a labelled remove control and
/// a spinner while it uploads.
class ChatSelectedFilesStrip extends StatelessWidget {
  const ChatSelectedFilesStrip({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<MessageProvider>(
      builder: (context, provider, child) {
        if (provider.selectedFiles.isEmpty) return const SizedBox.shrink();
        return Container(
          margin: const EdgeInsets.only(top: OmiSpacing.md, bottom: OmiSpacing.xs),
          // Align with the chat bar's left edge: outer padding (8) + side button (48) + gap (8).
          padding: const EdgeInsets.only(left: 64, right: OmiSpacing.xs),
          height: 70,
          child: ListView.builder(
            scrollDirection: Axis.horizontal,
            itemCount: provider.selectedFiles.length,
            itemBuilder: (context, index) {
              final file = provider.selectedFiles[index];
              final isImage = provider.selectedFileTypes[index] == 'image';
              return Container(
                margin: const EdgeInsets.only(right: OmiSpacing.xs),
                width: 60,
                height: 60,
                decoration: BoxDecoration(
                  color: OmiColors.surface2,
                  borderRadius: OmiRadius.lgAll,
                  image: isImage ? DecorationImage(image: FileImage(file), fit: BoxFit.cover) : null,
                ),
                child: Stack(
                  children: [
                    if (!isImage)
                      const Center(child: Icon(Icons.insert_drive_file, color: OmiColors.textPrimary, size: 24)),
                    if (provider.isFileUploading(file.path))
                      Container(
                        decoration: BoxDecoration(
                          color: OmiColors.surface0.withValues(alpha: 0.5),
                          borderRadius: OmiRadius.lgAll,
                        ),
                        child: const Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
                      ),
                    Positioned(
                      top: 0,
                      right: 0,
                      child: _RemoveFileButton(onPressed: () => provider.clearSelectedFile(index)),
                    ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }
}

class _RemoveFileButton extends StatelessWidget {
  const _RemoveFileButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final label = context.l10n.removeAttachment;
    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        button: true,
        label: label,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onPressed,
          // The glyph is small so it does not cover the thumbnail; the target is the full 44 pt.
          child: SizedBox.square(
            dimension: kOmiMinTapTarget,
            child: Align(
              alignment: Alignment.topRight,
              child: Container(
                width: 20,
                height: 20,
                margin: const EdgeInsets.all(OmiSpacing.xxs),
                decoration: const BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                child: const Center(child: FaIcon(FontAwesomeIcons.xmark, size: 10, color: OmiColors.onAccent)),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
