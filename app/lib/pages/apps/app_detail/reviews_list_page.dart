import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:timeago/timeago.dart' as timeago;

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/widgets/extensions/string.dart';

class ReviewsListPage extends StatefulWidget {
  final App app;
  const ReviewsListPage({super.key, required this.app});

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

  Future<void> _showReplyDialog(AppReview review) async {
    final controller = TextEditingController(text: review.response);
    final isSubmitting = ValueNotifier<bool>(false);

    await showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          'Reply to Review',
          style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        content: ValueListenableBuilder<bool>(
          valueListenable: isSubmitting,
          builder: (context, submitting, _) {
            return Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: controller,
                  enabled: !submitting,
                  maxLines: 4,
                  maxLength: 250,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: 'Write your reply...',
                    hintStyle: TextStyle(color: Colors.grey.shade500),
                    filled: true,
                    fillColor: Colors.black.withOpacity(0.3),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.all(12),
                  ),
                ),
              ],
            );
          },
        ),
        actions: [
          TextButton(
            onPressed: isSubmitting.value ? null : () => Navigator.pop(context),
            child: Text(
              'Cancel',
              style: TextStyle(color: Colors.grey.shade400),
            ),
          ),
          ValueListenableBuilder<bool>(
            valueListenable: isSubmitting,
            builder: (context, submitting, _) {
              return ElevatedButton(
                onPressed: submitting
                    ? null
                    : () async {
                        if (controller.text.trim().isEmpty) return;
                        isSubmitting.value = true;
                        try {
                          await replyToAppReview(widget.app.id, controller.text.trim(), review.uid);
                          context
                              .read<AppProvider>()
                              .updateLocalAppReviewResponse(widget.app.id, controller.text.trim(), review.uid);
                          review.response = controller.text.trim();
                          review.respondedAt = DateTime.now();
                          if (mounted) {
                            Navigator.pop(context);
                            setState(() {});
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Reply sent successfully'),
                                backgroundColor: Colors.green,
                              ),
                            );
                          }
                        } catch (e) {
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('Failed to send reply: $e'),
                                backgroundColor: Colors.red,
                              ),
                            );
                          }
                        } finally {
                          isSubmitting.value = false;
                        }
                      },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                ),
                child: submitting
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : const Text('Send'),
              );
            },
          ),
        ],
      ),
    );
  }

  String _getAvatarUrl(String seed, String? username) {
    if (username != null && username.isNotEmpty) {
      return 'https://avatar.iran.liara.run/username?username=${Uri.encodeComponent(username)}';
    }
    return 'https://avatar.iran.liara.run/public/${seed.hashCode % 100}';
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

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        automaticallyImplyLeading: false,
        leading: Container(
          width: 36,
          height: 36,
          margin: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: Colors.grey.withOpacity(0.3),
            shape: BoxShape.circle,
          ),
          child: IconButton(
            padding: EdgeInsets.zero,
            onPressed: () => Navigator.pop(context),
            icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16.0, color: Colors.white),
          ),
        ),
        title: const Text(
          'Ratings & Reviews',
          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 20),
            // Rating Distribution Widget
            Padding(
              padding: EdgeInsets.symmetric(horizontal: MediaQuery.of(context).size.width * 0.05),
              child: RatingDistributionWidget(
                ratingAvg: widget.app.ratingAvg ?? 0,
                ratingCount: widget.app.ratingCount,
                reviews: allReviews,
              ),
            ),
            const SizedBox(height: 24),
            // Filter Chips
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                children: [
                  _buildFilterChip('All', selectedRating == 0, () => filterReviews(0)),
                  const SizedBox(width: 8),
                  ...List.generate(5, (index) {
                    final starCount = index + 1;
                    final count = distribution[starCount] ?? 0;
                    // Only show filter chip if there are reviews for this star rating
                    if (count == 0) return const SizedBox.shrink();
                    return Padding(
                      padding: const EdgeInsets.only(right: 8.0),
                      child: _buildFilterChip(
                        '$starCount Star',
                        selectedRating == starCount,
                        () => filterReviews(starCount),
                      ),
                    );
                  }),
                ],
              ),
            ),
            const SizedBox(height: 24),
            // Reviews List
            filteredReviews.isEmpty
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 60.0),
                      child: Column(
                        children: [
                          Icon(
                            FontAwesomeIcons.star,
                            size: 48,
                            color: Colors.grey.shade600,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            'No Reviews Found',
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 16,
                            ),
                          ),
                        ],
                      ),
                    ),
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
  }

  Widget _buildFilterChip(String label, bool selected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? Colors.deepPurple : Colors.grey.shade800.withOpacity(0.5),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: selected ? Colors.deepPurple : Colors.grey.shade700,
            width: 1,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.white : Colors.grey.shade300,
            fontSize: 14,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          ),
        ),
      ),
    );
  }

  Widget _buildReviewItem(AppReview review) {
    final displayName = review.username.isNotEmpty ? review.username : 'Anonymous User';
    final avatarSeed = review.uid.isNotEmpty ? review.uid : review.username;
    final isOwner = widget.app.isOwner(SharedPreferencesUtil().uid);

    return Container(
      padding: const EdgeInsets.all(16.0),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25).withOpacity(0.8),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Avatar
              ClipOval(
                child: Container(
                  width: 40,
                  height: 40,
                  color: Colors.grey.shade800,
                  child: Image.network(
                    _getAvatarUrl(avatarSeed, review.username),
                    width: 40,
                    height: 40,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      final initial = review.username.isNotEmpty ? review.username[0].toUpperCase() : 'A';
                      return Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade800,
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: Text(
                            initial,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
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
                          style: const TextStyle(
                            color: Colors.grey,
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          timeago.format(review.ratedAt),
                          style: TextStyle(
                            color: Colors.grey.shade700,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    // Star rating
                    Row(
                      children: List.generate(5, (index) {
                        return Padding(
                          padding: const EdgeInsets.only(right: 4),
                          child: Icon(
                            FontAwesomeIcons.solidStar,
                            size: 14,
                            color: index < review.score.round() ? Colors.deepPurple : Colors.grey.shade700,
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
            const SizedBox(height: 12),
            Text(
              review.review.decodeString,
              style: const TextStyle(
                color: Colors.grey,
                fontSize: 14,
                height: 1.4,
              ),
            ),
          ],
          // Owner response
          if (review.response.isNotEmpty) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.3),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        widget.app.author,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (review.respondedAt != null) ...[
                        const SizedBox(width: 8),
                        Text(
                          timeago.format(review.respondedAt!),
                          style: TextStyle(
                            color: Colors.grey.shade600,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    review.response.decodeString,
                    style: TextStyle(
                      color: Colors.grey.shade300,
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
          ],
          // Reply button for owners
          if (isOwner) ...[
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: () => _showReplyDialog(review),
                icon: Icon(
                  review.response.isNotEmpty ? FontAwesomeIcons.pencil : FontAwesomeIcons.reply,
                  size: 12,
                  color: Colors.deepPurple,
                ),
                label: Text(
                  review.response.isNotEmpty ? 'Edit Reply' : 'Reply',
                  style: const TextStyle(color: Colors.deepPurple, fontSize: 13),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
