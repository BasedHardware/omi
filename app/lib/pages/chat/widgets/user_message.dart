import 'package:flutter/material.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/widgets/files_handler_widget.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/text_selection_controls.dart';

/// The user's message: their words in a solid pill at the right, in the accent (black in light,
/// white in dark), with the Messages tail at its bottom corner, so a question reads as a text
/// message apart from Omi's unboxed answer. Quoted context sits inside the pill above the words.
class HumanMessage extends StatelessWidget {
  final ServerMessage message;
  final Function(String)? onAskOmi;

  const HumanMessage({super.key, required this.message, this.onAskOmi});

  /// The pill's fill.
  static Color get fill => OmiColors.accent;

  /// The words on [fill].
  static Color get ink => OmiColors.onAccent;

  @override
  Widget build(BuildContext context) {
    String text = message.text.decodeString;
    String? contextText;
    String messageText = text;

    final contextRegex = RegExp(r'^Context: "([\s\S]+?)"\n\n');
    final match = contextRegex.firstMatch(text);

    if (match != null) {
      contextText = match.group(1);
      messageText = text.substring(match.end);
    }

    final ink = HumanMessage.ink;
    return Padding(
      // Room for the tail at the right, as the answer has room at the left.
      padding: const EdgeInsets.only(left: 40, right: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          FilesHandlerWidget(message: message),
          Wrap(
            alignment: WrapAlignment.end,
            children: [
              Stack(
                clipBehavior: Clip.none,
                children: [
                  Container(
                    key: const Key('chat_user_message'),
                    decoration: BoxDecoration(color: fill, borderRadius: OmiRadius.lgAll),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (contextText != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 6),
                            child: Container(
                              constraints: const BoxConstraints(maxWidth: 300),
                              padding: const EdgeInsetsDirectional.only(start: OmiSpacing.xs),
                              decoration: BoxDecoration(
                                border:
                                    BorderDirectional(start: BorderSide(color: ink.withValues(alpha: 0.72), width: 2)),
                              ),
                              child: Text(
                                contextText.length > 50 ? '${contextText.substring(0, 50)}…' : contextText,
                                style: OmiType.footnote.copyWith(color: ink.withValues(alpha: 0.72)),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ),
                        SelectableText(
                          messageText.trimRight(),
                          style: OmiType.body.copyWith(color: ink, height: 1.35),
                          contextMenuBuilder: (context, editableTextState) {
                            return omiSelectionMenuBuilder(context, editableTextState, (text) {
                              onAskOmi?.call(text);
                            });
                          },
                        ),
                      ],
                    ),
                  ),
                  _Tail(fill: fill, canvas: OmiCanvas.pageOf(context)),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// The Messages tail: a spur of the pill's colour past its bottom-right corner, with the canvas
/// cutting the spur's underside into a curve.
class _Tail extends StatelessWidget {
  const _Tail({required this.fill, required this.canvas});

  final Color fill;
  final Color canvas;

  @override
  Widget build(BuildContext context) {
    return Positioned.directional(
      key: const Key('chat_user_message_tail'),
      textDirection: Directionality.of(context),
      end: -12,
      bottom: 0,
      child: SizedBox(
        width: 22,
        height: 18,
        child: Stack(
          children: [
            PositionedDirectional(
              start: 0,
              bottom: 0,
              child: Container(
                width: 16,
                height: 18,
                decoration: BoxDecoration(
                  color: fill,
                  borderRadius: const BorderRadiusDirectional.only(bottomStart: Radius.elliptical(16, 14)),
                ),
              ),
            ),
            PositionedDirectional(
              start: 10,
              bottom: 0,
              child: Container(
                width: 12,
                height: 18,
                decoration: BoxDecoration(
                  color: canvas,
                  borderRadius: const BorderRadiusDirectional.only(bottomStart: Radius.circular(10)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
