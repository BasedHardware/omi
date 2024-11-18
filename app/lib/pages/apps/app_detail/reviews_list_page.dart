import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:timeago/timeago.dart' as timeago;

class ReviewsListPage extends StatefulWidget {
  final String appName;
  final List<AppReview> reviews;
  const ReviewsListPage({super.key, required this.reviews, required this.appName});

  @override
  State<ReviewsListPage> createState() => _ReviewsListPageState();
}

class _ReviewsListPageState extends State<ReviewsListPage> {
  List<AppReview> filteredReviews = [];
  int selectedRating = 0;

  @override
  void initState() {
    filteredReviews = widget.reviews;
    super.initState();
  }

  void filterReviews(int rating) {
    if (selectedRating == rating) return;
    if (rating == 0) {
      setState(() {
        selectedRating = 0;
        filteredReviews = widget.reviews;
      });
    } else {
      setState(() {
        selectedRating = rating;
        filteredReviews = widget.reviews
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
        title: Text('${widget.appName} Reviews'),
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
                    itemCount: filteredReviews.length,
                    itemBuilder: (context, index) {
                      return Container(
                        width: MediaQuery.of(context).size.width * 0.78,
                        padding: const EdgeInsets.all(16.0),
                        margin: const EdgeInsets.only(left: 12.0, right: 12.0, top: 2, bottom: 6),
                        decoration: BoxDecoration(
                          color: const Color.fromARGB(255, 25, 24, 24),
                          borderRadius: BorderRadius.circular(16.0),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Row(
                              children: [
                                RatingBar.builder(
                                  initialRating: filteredReviews[index].score.toDouble(),
                                  minRating: 1,
                                  ignoreGestures: true,
                                  direction: Axis.horizontal,
                                  allowHalfRating: true,
                                  itemCount: 5,
                                  itemSize: 20,
                                  tapOnlyMode: false,
                                  itemPadding: const EdgeInsets.symmetric(horizontal: 0),
                                  itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.deepPurple),
                                  maxRating: 5.0,
                                  onRatingUpdate: (rating) {},
                                ),
                                const SizedBox(
                                  width: 8,
                                ),
                                Text(
                                  timeago.format(filteredReviews[index].ratedAt),
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(
                              height: 8,
                            ),
                            Text(
                              filteredReviews[index].review.decodeString,
                              style: const TextStyle(
                                color: Colors.white,
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                    separatorBuilder: (context, index) => const SizedBox(width: 6),
                  ),
          ],
        ),
      ),
    );
  }
}
