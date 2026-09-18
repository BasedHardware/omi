import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:timeago/timeago.dart' as timeago;

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/widgets/review_avatar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/extensions/string.dart';

class RatingDistributionWidget extends StatelessWidget {
  final double ratingAvg;
  final int ratingCount;
  final List<AppReview> reviews;

  const RatingDistributionWidget({
    super.key,
    required this.ratingAvg,
    required this.ratingCount,
    required this.reviews,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text(
          ratingAvg.toStringAsFixed(1),
          style: TextStyle(fontSize: 40, fontWeight: FontWeight.bold, color: Colors.grey.shade400, height: 1),
        ),
        const SizedBox(width: 16),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: List.generate(5, (index) {
                return Padding(
                  padding: EdgeInsets.only(right: index < 4 ? 4 : 0),
                  child: FaIcon(
                    FontAwesomeIcons.solidStar,
                    size: 14,
                    color: index < ratingAvg.round() ? Colors.white : Colors.grey.shade700,
                  ),
                );
              }),
            ),
            const SizedBox(height: 4),
            Text(
              ratingCount == 1 ? '1 rating' : '$ratingCount ratings',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade500),
            ),
          ],
        ),
      ],
    );
  }
}

class RecentReviewsSection extends StatefulWidget {
  final List<AppReview> reviews;
  final AppReview? userReview;
  final App app;
  final VoidCallback? onReviewUpdated;

  const RecentReviewsSection({
    super.key,
    required this.reviews,
    required this.app,
    this.userReview,
    this.onReviewUpdated,
  });

  @override
  State<RecentReviewsSection> createState() => _RecentReviewsSectionState();
}

class _RecentReviewsSectionState extends State<RecentReviewsSection> {
  bool isEditing = false;
  double editRating = 0;
  late TextEditingController reviewController;
  bool isSubmitting = false;

  @override
  void initState() {
    super.initState();
    reviewController = TextEditingController(text: widget.userReview?.review ?? '');
    editRating = widget.userReview?.score ?? 0;
  }

  @override
  void dispose() {
    reviewController.dispose();
    super.dispose();
  }

  Future<void> _submitReview() async {
    if (editRating == 0) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.pleaseSelectRating)));
      return;
    }

    setState(() => isSubmitting = true);

    try {
      final prefs = SharedPreferencesUtil();
      final userName = widget.userReview?.username.isNotEmpty == true
          ? widget.userReview!.username
          : prefs.fullName.isNotEmpty
              ? prefs.fullName
              : prefs.givenName;

      final rev = AppReview(
        uid: prefs.uid,
        review: reviewController.text,
        score: editRating,
        ratedAt: widget.userReview?.ratedAt ?? DateTime.now(),
        response: widget.userReview?.response ?? '',
        username: userName,
      );

      bool isSuccessful;
      if (widget.userReview == null) {
        isSuccessful = await reviewApp(widget.app.id, rev);
        if (isSuccessful) {
          widget.app.ratingCount += 1;
        }
      } else {
        isSuccessful = await updateAppReview(widget.app.id, rev);
      }

      if (isSuccessful) {
        widget.app.userReview = AppReview(
          uid: prefs.uid,
          ratedAt: DateTime.now(),
          review: reviewController.text,
          score: editRating,
          username: userName,
          response: widget.userReview?.response ?? '',
        );

        var appsList = SharedPreferencesUtil().appsList;
        var index = appsList.indexWhere((element) => element.id == widget.app.id);
        if (index != -1) {
          appsList[index] = widget.app;
          SharedPreferencesUtil().appsList = appsList;
        }

        PlatformManager.instance.analytics.appRated(widget.app.id, editRating);

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                widget.userReview == null
                    ? context.l10n.reviewAddedSuccessfully
                    : context.l10n.reviewUpdatedSuccessfully,
              ),
            ),
          );
          setState(() => isEditing = false);
          widget.onReviewUpdated?.call();
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.failedToSubmitReview)));
        }
      }
    } finally {
      if (mounted) {
        setState(() => isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // Filter out user's review from the list if it exists
    final filteredReviews = widget.userReview != null
        ? widget.reviews.where((r) => r.uid != widget.userReview!.uid).take(3).toList()
        : widget.reviews.take(3).toList();

    final showUserReviewSection =
        widget.userReview != null || (!widget.app.isOwner(SharedPreferencesUtil().uid) && widget.app.enabled);

    if (filteredReviews.isEmpty && !showUserReviewSection) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Recent reviews from others
        ...filteredReviews.map((review) => _buildReviewItem(context, review)),
        // User's review section (editable)
        if (showUserReviewSection) ...[
          if (filteredReviews.isNotEmpty) const SizedBox(height: 8),
          _buildUserReviewSection(),
        ],
      ],
    );
  }

  Widget _buildUserReviewSection() {
    final userReview = widget.userReview;

    if (isEditing || userReview == null) {
      // Edit mode or no review yet
      return _buildEditableReview();
    } else {
      // Display mode with tap to edit
      return GestureDetector(
        onTap: () {
          setState(() {
            isEditing = true;
            reviewController.text = userReview.review;
            editRating = userReview.score;
          });
        },
        child: _buildReviewItem(context, userReview, isUserReview: true),
      );
    }
  }

  Widget _buildEditableReview() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                widget.userReview == null ? 'Add Your Review' : 'Edit Your Review',
                style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
              ),
              const Spacer(),
              if (widget.userReview != null)
                GestureDetector(
                  onTap: () {
                    setState(() {
                      isEditing = false;
                      reviewController.text = widget.userReview?.review ?? '';
                      editRating = widget.userReview?.score ?? 0;
                    });
                  },
                  child: Text('Cancel', style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
                ),
            ],
          ),
          const SizedBox(height: 12),
          // Star rating
          Row(
            children: List.generate(5, (index) {
              return GestureDetector(
                onTap: () {
                  setState(() => editRating = index + 1.0);
                },
                child: Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FaIcon(
                    FontAwesomeIcons.solidStar,
                    size: 24,
                    color: index < editRating ? Colors.white : Colors.grey.shade600,
                  ),
                ),
              );
            }),
          ),
          const SizedBox(height: 12),
          // Review text field
          TextField(
            controller: reviewController,
            maxLines: 3,
            maxLength: 250,
            style: const TextStyle(color: Colors.white, fontSize: 14),
            decoration: InputDecoration(
              hintText: context.l10n.writeReviewOptional,
              hintStyle: TextStyle(color: Colors.grey.shade500),
              filled: true,
              fillColor: Colors.black.withValues(alpha: 0.3),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
              contentPadding: const EdgeInsets.all(12),
              counterStyle: TextStyle(color: Colors.grey.shade500),
            ),
          ),
          const SizedBox(height: 12),
          // Submit button
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              key: const ValueKey('app_detail_submit_review_button'),
              onPressed: isSubmitting ? null : _submitReview,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black,
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              child: isSubmitting
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        // The button surface is now white, so a white spinner would be invisible.
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.black),
                      ),
                    )
                  : Text(
                      widget.userReview == null
                          ? AppLocalizations.of(context).submitReview
                          : AppLocalizations.of(context).updateReview,
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildReviewItem(BuildContext context, AppReview review, {bool isUserReview = false}) {
    final l10n = AppLocalizations.of(context);
    final displayName =
        isUserReview ? l10n.yourReview : (review.username.isNotEmpty ? review.username : l10n.anonymousUser);
    final avatarSeed = review.uid.isNotEmpty ? review.uid : review.username;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Avatar
              ReviewAvatar(
                seed: avatarSeed,
                username: review.username,
                size: 36,
                backgroundColor: isUserReview ? Colors.white.withValues(alpha: 0.2) : null,
                foregroundColor: isUserReview ? Colors.white : null,
              ),
              const SizedBox(width: 12),
              // Name, date, and stars
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          displayName,
                          style: TextStyle(
                            color: isUserReview ? Colors.white : Colors.grey,
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          timeago.format(review.ratedAt),
                          style: TextStyle(color: Colors.grey.shade700, fontSize: 12),
                        ),
                        if (isUserReview) ...[const Spacer(), Icon(Icons.edit, size: 14, color: Colors.grey.shade500)],
                      ],
                    ),
                    const SizedBox(height: 8),
                    // Star rating
                    Row(
                      children: List.generate(5, (index) {
                        return Padding(
                          padding: const EdgeInsets.only(right: 4),
                          child: FaIcon(
                            FontAwesomeIcons.solidStar,
                            size: 14,
                            color: index < review.score.round() ? Colors.white : Colors.grey.shade700,
                          ),
                        );
                      }),
                    ),
                  ],
                ),
              ),
            ],
          ),
          // Review text - limited to 2 lines
          if (review.review.isNotEmpty) ...[
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.only(left: 48),
              child: Text(
                review.review.decodeString,
                style: const TextStyle(color: Colors.grey, fontSize: 14, height: 1.4),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
