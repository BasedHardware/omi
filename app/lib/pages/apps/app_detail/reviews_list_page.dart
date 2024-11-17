import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/widgets/extensions/string.dart';

class ReviewsListPage extends StatelessWidget {
  final List<AppReview> reviews;
  const ReviewsListPage({super.key, required this.reviews});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: ListView.separated(
        shrinkWrap: true,
        itemCount: reviews.length,
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
                RatingBar.builder(
                  initialRating: reviews[index].score.toDouble(),
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
                  height: 8,
                ),
                Text(
                  reviews[index].review.decodeString,
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
    );
  }
}
