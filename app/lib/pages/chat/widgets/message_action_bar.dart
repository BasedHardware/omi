import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'message_action_commands.dart';

export 'message_action_commands.dart';

/// Why a reply was rated down. [key] is the wire value the backend stores.
enum FeedbackReason {
  tooVerbose('too_verbose'),
  incorrectOrHallucination('incorrect_or_hallucination'),
  notHelpfulOrIrrelevant('not_helpful_or_irrelevant'),
  didntFollowInstructions('didnt_follow_instructions'),
  other('other');

  final String key;

  const FeedbackReason(this.key);

  String label(AppLocalizations l10n) => switch (this) {
        FeedbackReason.tooVerbose => l10n.feedbackReasonTooVerbose,
        FeedbackReason.incorrectOrHallucination => l10n.feedbackReasonIncorrect,
        FeedbackReason.notHelpfulOrIrrelevant => l10n.feedbackReasonNotHelpful,
        FeedbackReason.didntFollowInstructions => l10n.feedbackReasonIgnoredInstructions,
        FeedbackReason.other => l10n.cancelReasonOther,
      };
}

/// The body of the "What went wrong?" sheet shown for a thumbs-down: a reason (required), an
/// optional comment and Submit. Present it with [showFeedbackBottomSheet].
///
/// [native] projects the same sheet as a native surface: one button per reason, the comment field
/// (500 characters, like the Flutter field) and Close plus Submit, which stays disabled until a
/// reason is chosen. Submit reports the same (key, comment) pair; Close submits nothing.
class FeedbackBottomSheet extends StatefulWidget {
  final Function(String reason, String? comment) onSubmit;
  final bool native;

  const FeedbackBottomSheet({super.key, required this.onSubmit, this.native = false});

  @override
  State<FeedbackBottomSheet> createState() => _FeedbackBottomSheetState();
}

class _FeedbackBottomSheetState extends State<FeedbackBottomSheet> {
  FeedbackReason? _selectedReason;
  final TextEditingController _commentController = TextEditingController();

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  void _submit() {
    final reason = _selectedReason;
    if (reason == null) return;
    OmiHaptics.medium();
    final comment = _commentController.text.trim();
    widget.onSubmit(reason.key, comment.isEmpty ? null : comment);
    Navigator.pop(context);
  }

  Widget _native(BuildContext context) {
    final l10n = context.l10n;
    return IosNativeSurface(
      title: l10n.whatWentWrong,
      fallback: OmiSheetScaffold(title: l10n.whatWentWrong, child: FeedbackBottomSheet(onSubmit: widget.onSubmit)),
      toolbar: [
        NativeRow('feedback_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
        NativeRow(
          'feedback_submit',
          l10n.submit,
          enabled: _selectedReason != null,
          action: (_) => _submit(),
        ),
      ],
      sections: [
        NativeSection('feedback_reasons', title: l10n.selectAReason, [
          for (final reason in FeedbackReason.values)
            NativeRow(
              'feedback_reason_${reason.key}',
              reason.label(l10n),
              symbol: _selectedReason == reason ? 'checkmark.circle.fill' : 'circle',
              action: (_) {
                OmiHaptics.selection();
                setState(() => _selectedReason = reason);
              },
            ),
        ]),
        NativeSection('feedback_comment', title: l10n.additionalFeedbackOptional, [
          NativeRow(
            'feedback_comment_text',
            l10n.tellUsMoreWhatWentWrong,
            kind: 'text',
            value: _commentController.text,
            maximumLength: 500,
            action: (value) => setState(() => _commentController.text = value as String),
          ),
        ]),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (widget.native) return _native(context);
    final l10n = context.l10n;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.selectAReason, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: 10),
          Wrap(
            spacing: OmiSpacing.xs,
            runSpacing: OmiSpacing.xs,
            children: [
              for (final reason in FeedbackReason.values)
                ChoiceChip(
                  label: Text(reason.label(l10n)),
                  selected: _selectedReason == reason,
                  showCheckmark: false,
                  materialTapTargetSize: MaterialTapTargetSize.padded,
                  backgroundColor: OmiColors.surface2,
                  selectedColor: OmiColors.accent,
                  side: BorderSide.none,
                  shape: const StadiumBorder(),
                  labelStyle: OmiType.subhead.copyWith(
                    color: _selectedReason == reason ? OmiColors.onAccent : OmiColors.textPrimary,
                    fontWeight: _selectedReason == reason ? FontWeight.w600 : FontWeight.w400,
                  ),
                  onSelected: (_) {
                    OmiHaptics.selection();
                    setState(() => _selectedReason = reason);
                  },
                ),
            ],
          ),
          const SizedBox(height: OmiSpacing.lg),
          Text(l10n.additionalFeedbackOptional, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: OmiSpacing.xxs),
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
            child: TextField(
              controller: _commentController,
              style: OmiType.subhead.copyWith(height: 1.4),
              decoration: InputDecoration(
                border: InputBorder.none,
                contentPadding: const EdgeInsets.symmetric(vertical: 10),
                hintText: l10n.tellUsMoreWhatWentWrong,
                hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
              ),
              maxLines: 3,
              minLines: 2,
              maxLength: 500,
              buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
              textCapitalization: TextCapitalization.sentences,
            ),
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiButton(label: l10n.submit, expand: true, onPressed: _selectedReason == null ? null : _submit),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}

/// Show the thumbs-down feedback sheet.
Future<void> showFeedbackBottomSheet(
  BuildContext context, {
  required Function(String reason, String? comment) onSubmit,
}) {
  return showOmiSheet(
    context: context,
    title: context.l10n.whatWentWrong,
    builder: (context) => FeedbackBottomSheet(onSubmit: onSubmit),
    nativeBuilder: (context) => FeedbackBottomSheet(onSubmit: onSubmit, native: true),
  );
}

/// Copy, Helpful, Not Helpful and Share under an AI reply.
class MessageActionBar extends StatefulWidget {
  final String messageText;
  final Function(int, {String? reason})? setMessageNps;
  final int? currentNps;

  const MessageActionBar({super.key, required this.messageText, this.setMessageNps, this.currentNps});

  @override
  State<MessageActionBar> createState() => _MessageActionBarState();
}

class _MessageActionBarState extends State<MessageActionBar> {
  late final MessageActionCommands _commands = MessageActionCommands(
    messageText: widget.messageText,
    setMessageNps: widget.setMessageNps,
    currentNps: widget.currentNps,
    onChanged: () {
      if (mounted) setState(() {});
    },
  );
  bool _copied = false;
  Timer? _copyTimer;

  int? get _selectedNps => _commands.selectedNps;

  @override
  void dispose() {
    _copyTimer?.cancel();
    _commands.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(MessageActionBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    _commands
      ..messageText = widget.messageText
      ..setMessageNps = widget.setMessageNps;
    // Update local state if the widget's currentNps changed (e.g., from server fetch)
    if (oldWidget.currentNps != widget.currentNps) {
      setState(() => _commands.syncCurrentNps(widget.currentNps));
    }
  }

  /// Show bottom sheet with thumbs down reason options and comment field
  void _showThumbsDownReasonPicker() {
    showFeedbackBottomSheet(
      context,
      onSubmit: (reason, comment) => _commands.submitNotHelpful(context, reason, comment),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(left: OmiSpacing.xxs),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildActionButton(
            icon: _copied ? FontAwesomeIcons.check : FontAwesomeIcons.copy,
            label: _copied ? l10n.copied : l10n.copyMessage,
            onTap: () async {
              OmiHaptics.light();
              if (!await _commands.copy(context)) return;
              if (!mounted) return;
              _copyTimer?.cancel();
              setState(() => _copied = true);
              _copyTimer = Timer(const Duration(seconds: 2), () {
                if (mounted) setState(() => _copied = false);
              });
            },
          ),
          _buildActionButton(
            icon: _selectedNps == 1 ? FontAwesomeIcons.solidThumbsUp : FontAwesomeIcons.thumbsUp,
            label: l10n.helpful,
            isSelected: _selectedNps == 1,
            onTap: () {
              OmiHaptics.light();
              _commands.toggleHelpful();
            },
          ),
          _buildActionButton(
            icon: _selectedNps == -1 ? FontAwesomeIcons.solidThumbsDown : FontAwesomeIcons.thumbsDown,
            label: l10n.notHelpful,
            isSelected: _selectedNps == -1,
            onTap: () {
              OmiHaptics.light();
              if (_selectedNps == -1) {
                // Already thumbs down, toggle off
                _commands.clearNotHelpful();
              } else {
                _showThumbsDownReasonPicker();
              }
            },
          ),
          _buildActionButton(
            icon: FontAwesomeIcons.share,
            label: l10n.share,
            onTap: () async {
              if (widget.messageText.isEmpty) return;
              OmiHaptics.light();
              await _commands.share();
            },
          ),
        ],
      ),
    );
  }

  Widget _buildActionButton({
    required FaIconData icon,
    required String label,
    required VoidCallback onTap,
    bool isSelected = false,
  }) {
    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        button: true,
        label: label,
        selected: isSelected,
        child: InkWell(
          borderRadius: OmiRadius.mdAll,
          splashColor: Colors.white24,
          highlightColor: Colors.white10,
          onTap: onTap,
          child: SizedBox(
            width: 48,
            height: 48,
            child: Center(
              child: ExcludeSemantics(
                child: AnimatedSwitcher(
                  duration: OmiMotion.of(context).quick,
                  child: FaIcon(
                    icon,
                    key: ValueKey(icon),
                    color: isSelected ? OmiColors.textPrimary : OmiColors.textSecondary,
                    size: 16,
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
