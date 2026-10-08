import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:timeago/timeago.dart' as timeago;

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/app_detail/reviews_section.dart';
import 'package:omi/pages/apps/app_detail/widgets/review_avatar.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';

/// Sends an owner's reply to a review; [replyToAppReview] is the owner.
typedef ReviewReplySender = Future<bool> Function(String appId, String reply, String reviewerUid);

class ReviewsListPage extends StatefulWidget {
  final App app;
  const ReviewsListPage({super.key, required this.app});

  /// Debug-only: replaces the HTTP owner of replies so tests stay hermetic. Release and profile
  /// builds always use [replyToAppReview].
  @visibleForTesting
  static ReviewReplySender? debugReplySenderForTest;

  @override
  State<ReviewsListPage> createState() => _ReviewsListPageState();
}

class _ReviewsListPageState extends State<ReviewsListPage> {
  List<AppReview> filteredReviews = [];
  int selectedRating = 0;

  @override
  void initState() {
    filteredReviews = widget.app.reviews;
    filteredReviews.sort((a, b) => b.ratedAt.compareTo(a.ratedAt));
    super.initState();
  }

  void filterReviews(int rating) {
    if (selectedRating == rating) return;
    if (rating == 0) {
      setState(() {
        selectedRating = 0;
        filteredReviews = widget.app.reviews;
      });
    } else {
      setState(() {
        selectedRating = rating;
        filteredReviews = widget.app.reviews
            .where((element) => (element.score >= rating.toDouble() && element.score < (rating + 1).toDouble()))
            .toList();
      });
    }
    filteredReviews.sort((a, b) => b.ratedAt.compareTo(a.ratedAt));
  }

  /// The existing reply body: sends [reply] trimmed, updates the provider and the review, and shows
  /// the same toasts. [onSent] runs where the dialog used to close. Answers whether it was sent.
  Future<bool> _submitReply(AppReview review, String reply, {VoidCallback? onSent}) async {
    final text = reply.trim();
    if (text.isEmpty) return false;
    try {
      await ((kDebugMode ? ReviewsListPage.debugReplySenderForTest : null) ?? replyToAppReview)(
          widget.app.id, text, review.uid);
      if (mounted) {
        context.read<AppProvider>().updateLocalAppReviewResponse(
              widget.app.id,
              text,
              review.uid,
            );
      }
      review.response = text;
      review.respondedAt = DateTime.now();
      onSent?.call();
      if (mounted) {
        setState(() {});
        OmiFeedback.confirm(context, context.l10n.replySentSuccessfully);
      }
      return true;
    } catch (e) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.failedToSendReply(readableError(e)));
      }
      return false;
    }
  }

  /// The native reply editor, or the Flutter dialog when it is unavailable.
  Future<void> _reply(AppReview review) async {
    var draft = review.response;
    if (await _replyNative(review, (text) => draft = text) || !mounted) return;
    await _showReplyDialog(review, initialText: draft);
  }

  /// Answers false when the native editor could not be used, so the caller opens the Flutter dialog.
  /// Blank text is never sent and keeps the editor open, as does a send that throws; [onDraft] keeps
  /// the latest text for the Flutter dialog.
  Future<bool> _replyNative(AppReview review, ValueChanged<String> onDraft) async {
    var draft = review.response;
    while (true) {
      if (!mounted) return true;
      final l10n = context.l10n;
      final result = await showIosNativeModal(context, title: l10n.replyToReview, guardEdits: true, actions: [
        NativeRow('cancel', l10n.cancel, symbol: 'xmark'),
        NativeRow('send', l10n.send),
      ], sections: [
        NativeSection('review_reply', [
          NativeRow('review_reply_text', l10n.writeYourReply, kind: 'text', value: draft, maximumLength: 250),
        ]),
      ]);
      if (result == null) return false;
      final text = result.values['review_reply_text'];
      if (result.action != 'send' || text is! String || !mounted) return true;
      draft = text;
      onDraft(draft);
      if (draft.trim().isEmpty) continue;
      final activity = await showIosNativeActivity(context, label: l10n.replyToReview);
      final bool sent;
      try {
        sent = await _submitReply(review, draft);
      } finally {
        await activity?.dismiss();
      }
      if (sent) return true;
    }
  }

  Future<void> _showReplyDialog(AppReview review, {String? initialText}) async {
    final controller = TextEditingController(text: initialText ?? review.response);
    final isSubmitting = ValueNotifier<bool>(false);

    Future<void> submit(BuildContext dialogContext) async {
      if (controller.text.trim().isEmpty) return;
      isSubmitting.value = true;
      try {
        await _submitReply(review, controller.text, onSent: () {
          if (dialogContext.mounted) {
            Navigator.pop(dialogContext);
          }
        });
      } finally {
        isSubmitting.value = false;
      }
    }

    await showDialog<void>(
      context: context,
      builder: (dialogContext) => ValueListenableBuilder<bool>(
        valueListenable: isSubmitting,
        builder: (dialogContext, submitting, _) {
          return OmiAlertDialog(
            title: context.l10n.replyToReview,
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: controller,
                  enabled: !submitting,
                  maxLines: 4,
                  maxLength: 250,
                  style: TextStyle(color: OmiColors.textPrimary),
                  decoration: InputDecoration(
                    hintText: context.l10n.writeYourReply,
                    hintStyle: TextStyle(color: OmiColors.textTertiary),
                    filled: true,
                    fillColor: OmiColors.surface0.withValues(alpha: 0.3),
                    border: const OutlineInputBorder(borderRadius: OmiRadius.smAll, borderSide: BorderSide.none),
                    contentPadding: const EdgeInsets.all(OmiSpacing.sm),
                  ),
                ),
                if (submitting) ...[
                  const SizedBox(height: OmiSpacing.sm),
                  const Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
                ],
              ],
            ),
            actions: [
              OmiDialogAction(
                label: context.l10n.cancel,
                onPressed: submitting ? null : () => Navigator.pop(dialogContext),
              ),
              OmiDialogAction(
                label: context.l10n.send,
                isDefault: true,
                onPressed: submitting ? null : () => submit(dialogContext),
              ),
            ],
          );
        },
      ),
    );
  }

  Map<int, int> _getRatingDistribution(List<AppReview> reviews) {
    final distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0};
    for (final review in reviews) {
      final score = review.score.round().clamp(1, 5);
      distribution[score] = (distribution[score] ?? 0) + 1;
    }
    return distribution;
  }

  @override
  Widget build(BuildContext context) {
    final allReviews = widget.app.reviews;
    final distribution = _getRatingDistribution(allReviews);

    final classic = Scaffold(
      appBar: AppBar(
        backgroundColor: OmiColors.surface0,
        elevation: 0,
        leading: const OmiBackButton(),
        title: Text(context.l10n.ratingsAndReviews, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
      ),
      backgroundColor: OmiColors.surface0,
      body: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: OmiSpacing.lg),
            // Rating Distribution Widget
            Padding(
              padding: EdgeInsets.symmetric(horizontal: MediaQuery.of(context).size.width * 0.05),
              child: RatingDistributionWidget(
                ratingAvg: widget.app.ratingAvg ?? 0,
                ratingCount: widget.app.ratingCount,
                reviews: allReviews,
              ),
            ),
            const SizedBox(height: OmiSpacing.xl),
            // Filter Chips
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
              child: Row(
                children: [
                  _buildFilterChip(context.l10n.all, selectedRating == 0, () => filterReviews(0)),
                  const SizedBox(width: OmiSpacing.xs),
                  ...List.generate(5, (index) {
                    final starCount = index + 1;
                    final count = distribution[starCount] ?? 0;
                    // Only show filter chip if there are reviews for this star rating
                    if (count == 0) return const SizedBox.shrink();
                    return Padding(
                      padding: const EdgeInsets.only(right: OmiSpacing.xs),
                      child: _buildFilterChip(
                        context.l10n.starFilterLabel(starCount),
                        selectedRating == starCount,
                        () => filterReviews(starCount),
                      ),
                    );
                  }),
                ],
              ),
            ),
            const SizedBox(height: OmiSpacing.xl),
            // Reviews List
            filteredReviews.isEmpty
                ? OmiEmptyState(
                    glyph: const FaIcon(FontAwesomeIcons.star),
                    title: context.l10n.noReviewsFound,
                  )
                : ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    padding: EdgeInsets.symmetric(horizontal: MediaQuery.of(context).size.width * 0.05),
                    itemCount: filteredReviews.length,
                    itemBuilder: (context, index) {
                      return _buildReviewItem(filteredReviews[index]);
                    },
                    separatorBuilder: (context, index) => const SizedBox(height: 12),
                  ),
            const SizedBox(height: 60),
          ],
        ),
      ),
    );
    if (!nativePresentationEnabled) return classic;
    return _nativeList(classic, distribution);
  }

  /// The same list in the native presentation; filtering and replies stay with this page.
  Widget _nativeList(Widget classic, Map<int, int> distribution) {
    final l10n = context.l10n;
    final isOwner = widget.app.isOwner(SharedPreferencesUtil().uid);
    String stars(double score) {
      final filled = score.isFinite ? score.round().clamp(0, 5) : 0;
      return '${'★' * filled}${'☆' * (5 - filled)}';
    }

    final ratingAvg = widget.app.ratingAvg ?? 0;
    final filters = {
      '0': l10n.all,
      for (var starCount = 1; starCount <= 5; starCount++)
        if ((distribution[starCount] ?? 0) > 0) '$starCount': l10n.starFilterLabel(starCount),
    };
    return IosNativeSurface(
      title: l10n.ratingsAndReviews,
      fallback: classic,
      empty: l10n.noReviewsFound,
      toolbar: [
        NativeRow('reviews_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('reviews_summary', [
          NativeRow('reviews_rating', ratingAvg.isFinite ? ratingAvg.toStringAsFixed(1) : '0.0',
              kind: 'label', subtitle: '${stars(ratingAvg)} · ${l10n.appRatingCount(widget.app.ratingCount)}'),
          NativeRow('reviews_filter', l10n.filters,
              kind: filters.length <= 4 ? 'segmented' : 'choice',
              value: filters.containsKey('$selectedRating') ? '$selectedRating' : '0',
              options: filters,
              action: (value) => filterReviews(int.parse(value as String))),
        ]),
        NativeSection('reviews_list', [
          if (filteredReviews.isEmpty) NativeRow('reviews_empty', l10n.noReviewsFound, kind: 'label', symbol: 'star'),
          for (final (index, review) in filteredReviews.indexed) ...[
            NativeRow('review:$index', review.username.isNotEmpty ? review.username : l10n.anonymousUser,
                kind: 'label',
                subtitle: [
                  '${stars(review.score)} · ${timeago.format(review.ratedAt)}',
                  if (review.review.isNotEmpty) review.review.decodeString,
                  if (review.response.isNotEmpty) ...[
                    [
                      widget.app.author,
                      if (review.respondedAt != null) timeago.format(review.respondedAt!),
                    ].join(' · '),
                    review.response.decodeString,
                  ],
                ].join('\n')),
            if (isOwner)
              NativeRow('review_reply:$index', review.response.isNotEmpty ? l10n.editReply : l10n.reply,
                  symbol: review.response.isNotEmpty ? 'pencil' : 'arrowshape.turn.up.left',
                  action: (_) => _reply(review)),
          ],
        ]),
      ],
    );
  }

  Widget _buildFilterChip(String label, bool selected, VoidCallback onTap) {
    return Semantics(
      button: true,
      selected: selected,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
          decoration: BoxDecoration(
            color: selected ? OmiColors.textPrimary.withValues(alpha: 0.22) : OmiColors.surface2,
            borderRadius: OmiRadius.pillAll,
            border: Border.all(color: selected ? OmiColors.textPrimary : OmiColors.border, width: 1),
          ),
          child: Text(
            label,
            style: OmiType.subhead.copyWith(
              color: selected ? OmiColors.textPrimary : OmiColors.textSecondary,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildReviewItem(AppReview review) {
    final displayName = review.username.isNotEmpty ? review.username : context.l10n.anonymousUser;
    final avatarSeed = review.uid.isNotEmpty ? review.uid : review.username;
    final isOwner = widget.app.isOwner(SharedPreferencesUtil().uid);

    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1.withValues(alpha: 0.8),
        borderRadius: OmiRadius.lgAll,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Avatar
              ReviewAvatar(seed: avatarSeed, username: review.username, size: 40),
              const SizedBox(width: OmiSpacing.sm),
              // Name, date, and stars
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          displayName,
                          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                        ),
                        const SizedBox(width: OmiSpacing.xs),
                        Text(
                          timeago.format(review.ratedAt),
                          style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                        ),
                      ],
                    ),
                    const SizedBox(height: OmiSpacing.xs),
                    // Star rating
                    Row(
                      children: List.generate(5, (index) {
                        return Padding(
                          padding: const EdgeInsets.only(right: OmiSpacing.xxs),
                          child: FaIcon(
                            FontAwesomeIcons.solidStar,
                            size: 14,
                            color: index < review.score.round() ? OmiColors.textPrimary : OmiColors.textTertiary,
                          ),
                        );
                      }),
                    ),
                  ],
                ),
              ),
            ],
          ),
          // Review text
          if (review.review.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.sm),
            Text(
              review.review.decodeString,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
            ),
          ],
          // Owner response
          if (review.response.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.md),
            Container(
              padding: const EdgeInsets.all(OmiSpacing.sm),
              decoration: BoxDecoration(
                color: OmiColors.surface0.withValues(alpha: 0.3),
                borderRadius: OmiRadius.mdAll,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        widget.app.author,
                        style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600),
                      ),
                      if (review.respondedAt != null) ...[
                        const SizedBox(width: OmiSpacing.xs),
                        Text(
                          timeago.format(review.respondedAt!),
                          style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: OmiSpacing.xxs),
                  Text(
                    review.response.decodeString,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.4),
                  ),
                ],
              ),
            ),
          ],
          // Reply button for owners
          if (isOwner) ...[
            const SizedBox(height: OmiSpacing.sm),
            Align(
              alignment: Alignment.centerRight,
              child: OmiButton.tertiary(
                label: review.response.isNotEmpty ? context.l10n.editReply : context.l10n.reply,
                size: OmiButtonSize.compact,
                leading: FaIcon(review.response.isNotEmpty ? FontAwesomeIcons.pencil : FontAwesomeIcons.reply),
                onPressed: () => _showReplyDialog(review),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
