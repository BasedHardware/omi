import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/app_detail/widgets/app_owner_review_card.dart';
import 'package:friend_private/pages/apps/app_detail/widgets/user_review_card.dart';

class ReviewsListPage extends StatefulWidget {
  final App app;
  const ReviewsListPage({super.key, required this.app});

  @override
  State<ReviewsListPage> createState() => _ReviewsListPageState();
}

class _ReviewsListPageState extends State<ReviewsListPage> {
  List<AppReview> filteredReviews = [];
  int selectedRating = 0;
  late TextEditingController replyController;

  @override
  void initState() {
    filteredReviews = widget.app.reviews;
    replyController = TextEditingController();
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
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Text('${widget.app.name} Reviews'),
        elevation: 0,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(width: 12),
                  ...List.generate(6, (index) {
                    if (index == 0) {
                      return Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: ChoiceChip(
                          label: const Text("All"),
                          selected: selectedRating == 0,
                          showCheckmark: true,
                          backgroundColor: Colors.transparent,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                          onSelected: (bool selected) {
                            filterReviews(0);
                          },
                        ),
                      );
                    }
                    return Padding(
                      padding: const EdgeInsets.only(right: 8.0),
                      child: ChoiceChip(
                        label: Text("$index Star"),
                        selected: (selectedRating) == index,
                        showCheckmark: true,
                        backgroundColor: Colors.transparent,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        onSelected: (bool selected) {
                          filterReviews(index);
                        },
                      ),
                    );
                  }),
                ],
              ),
            ),
            const SizedBox(
              height: 12,
            ),
            filteredReviews.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.only(top: 60.0),
                      child: Text('No Reviews Found', style: TextStyle(color: Colors.white)),
                    ),
                  )
                : ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: filteredReviews.length,
                    itemBuilder: (context, index) {
                      if (!widget.app.isOwner(SharedPreferencesUtil().uid)) {
                        return AppOwnerReviewCard(
                          review: filteredReviews[index],
                          appId: widget.app.id,
                          ownerName: widget.app.author,
                        );
                      } else {
                        return UserReviewCard(
                          review: filteredReviews[index],
                          ownerName: widget.app.author,
                        );
                      }
                    },
                    separatorBuilder: (context, index) => const SizedBox(width: 6),
                  ),
          ],
        ),
      ),
    );
  }
}
