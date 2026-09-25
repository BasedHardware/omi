import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/share_sheet.dart';

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
class FeedbackBottomSheet extends StatefulWidget {
  final Function(String reason, String? comment) onSubmit;

  const FeedbackBottomSheet({super.key, required this.onSubmit});

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

  @override
  Widget build(BuildContext context) {
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
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
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
  int? _selectedNps;
  bool _copied = false;
  Timer? _copyTimer;

  @override
  void dispose() {
    _copyTimer?.cancel();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _selectedNps = widget.currentNps;
  }

  @override
  void didUpdateWidget(MessageActionBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Update local state if the widget's currentNps changed (e.g., from server fetch)
    if (oldWidget.currentNps != widget.currentNps) {
      setState(() {
        _selectedNps = widget.currentNps;
      });
    }
  }

  /// Show bottom sheet with thumbs down reason options and comment field
  void _showThumbsDownReasonPicker() {
    showFeedbackBottomSheet(
      context,
      onSubmit: (reason, comment) async {
        final previous = _selectedNps;
        setState(() {
          _selectedNps = -1;
        });
        // Combine reason and comment for the API call
        String feedbackReason = reason;
        if (comment != null && comment.isNotEmpty) {
          feedbackReason = '$reason: $comment';
        }
        final saved = await widget.setMessageNps?.call(-1, reason: feedbackReason);
        if (saved == false) {
          if (mounted) setState(() => _selectedNps = previous);
          return;
        }
        if (mounted) OmiFeedback.confirm(context, context.l10n.thanksForYourFeedback);
      },
    );
  }

  /// Analytics get the shape of the message, never its words.
  Map<String, Object> get _messageAnalytics => {'message_length': widget.messageText.length};

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
              final copied = await OmiClipboard.copy(context, widget.messageText);
              if (!copied) return;
              PlatformManager.instance.analytics.track('Chat Message Copied', properties: _messageAnalytics);
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
            onTap: () async {
              OmiHaptics.light();
              final previous = _selectedNps;
              setState(() {
                _selectedNps = _selectedNps == 1 ? null : 1;
              });
              final saved = await widget.setMessageNps?.call(_selectedNps ?? 0);
              if (saved == false && mounted) setState(() => _selectedNps = previous);
            },
          ),
          _buildActionButton(
            icon: _selectedNps == -1 ? FontAwesomeIcons.solidThumbsDown : FontAwesomeIcons.thumbsDown,
            label: l10n.notHelpful,
            isSelected: _selectedNps == -1,
            onTap: () async {
              OmiHaptics.light();
              if (_selectedNps == -1) {
                // Already thumbs down, toggle off
                setState(() {
                  _selectedNps = null;
                });
                final saved = await widget.setMessageNps?.call(0);
                if (saved == false && mounted) setState(() => _selectedNps = -1);
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
              await SharePlus.instance.share(
                ShareParams(text: widget.messageText, sharePositionOrigin: shareSheetOrigin()),
              );
              PlatformManager.instance.analytics.track('Chat Message Shared', properties: _messageAnalytics);
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
