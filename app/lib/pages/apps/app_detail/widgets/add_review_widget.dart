import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/animated_loading_button.dart';
import 'package:provider/provider.dart';

class AddReviewWidget extends StatefulWidget {
  final App app;
  const AddReviewWidget({super.key, required this.app});

  @override
  State<AddReviewWidget> createState() => _AddReviewWidgetState();
}

class _AddReviewWidgetState extends State<AddReviewWidget> {
  bool showReviewField = false;
  double rating = 0;
  late TextEditingController reviewController;
  bool showButton = false;
  bool isLoading = false;

  void setShowReviewField(bool value) {
    if (mounted) {
      if (value != showReviewField) {
        setState(() => showReviewField = value);
      }
    }
  }

  void setIsLoading(bool value) {
    if (mounted) {
      if (value != isLoading) {
        setState(() => isLoading = value);
      }
    }
  }

  void updateRating(double value) {
    if (mounted) {
      if (value != rating) {
        setState(() => rating = value);
      }
    }
  }

  void updateShowButton(bool value) {
    if (mounted) {
      if (value != showButton) {
        setState(() => showButton = value);
      }
    }
  }

  @override
  void initState() {
    reviewController = TextEditingController();
    if (widget.app.userReview != null) {
      reviewController.text = widget.app.userReview!.review;
      rating = widget.app.userReview!.score;
      showReviewField = true;
      showButton = false;
    } else {
      rating = 0;
    }
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16.0),
      margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Row(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(left: 6.0),
                child: Text(widget.app.userReview?.score == null ? 'Rate and Review this App' : 'Your Review',
                    style: const TextStyle(color: Colors.white, fontSize: 16)),
              ),
              const SizedBox(height: 14),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: RatingBar.builder(
                  initialRating: rating,
                  minRating: 1,
                  direction: Axis.horizontal,
                  allowHalfRating: true,
                  itemCount: 5,
                  itemSize: 34,
                  itemPadding: const EdgeInsets.symmetric(horizontal: 18),
                  itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.deepPurple),
                  maxRating: 5.0,
                  onRatingUpdate: (rating) {
                    if (isLoading) return;
                    setShowReviewField(true);
                    updateRating(rating);
                    updateShowButton(true);
                  },
                ),
              ),
              const SizedBox(
                height: 20,
              ),
              ClipRRect(
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  height: showReviewField
                      ? (showButton
                          ? MediaQuery.sizeOf(context).height * 0.2
                          : MediaQuery.sizeOf(context).height * 0.132)
                      : 0,
                  child: !showReviewField
                      ? null
                      : SingleChildScrollView(
                          physics: const NeverScrollableScrollPhysics(),
                          child: Column(
                            children: [
                              SizedBox(
                                width: MediaQuery.sizeOf(context).width * 0.88,
                                child: TextFormField(
                                  controller: reviewController,
                                  enabled: isLoading ? false : true,
                                  maxLength: 250,
                                  onChanged: (value) {
                                    if (value.isEmpty) {
                                      if (value == widget.app.userReview?.review) {
                                        updateShowButton(false);
                                      } else {
                                        updateShowButton(true);
                                      }
                                    } else {
                                      updateShowButton(true);
                                    }
                                  },
                                  decoration: InputDecoration(
                                    hintText: 'Write a review (optional)',
                                    hintStyle: const TextStyle(color: Colors.grey),
                                    border: const OutlineInputBorder(
                                      borderRadius: BorderRadius.all(Radius.circular(8)),
                                      borderSide: BorderSide(color: Colors.grey),
                                    ),
                                    enabledBorder: OutlineInputBorder(
                                      borderRadius: const BorderRadius.all(Radius.circular(8)),
                                      borderSide: BorderSide(color: Colors.grey[700]!),
                                    ),
                                    focusedBorder: const OutlineInputBorder(
                                      borderRadius: BorderRadius.all(Radius.circular(8)),
                                      borderSide: BorderSide(color: Colors.grey),
                                    ),
                                  ),
                                  style: const TextStyle(color: Colors.white),
                                  maxLines: 3,
                                ),
                              ),
                              const SizedBox(
                                height: 20,
                              ),
                              showButton
                                  ? AnimatedLoadingButton(
                                      loaderColor: Colors.black,
                                      text: widget.app.userReview != null ? 'Update Review' : 'Submit Review',
                                      textStyle: const TextStyle(color: Colors.black, fontSize: 16),
                                      onPressed: () async {
                                        FocusScope.of(context).unfocus();
                                        if (rating == widget.app.userReview?.score &&
                                            reviewController.text == widget.app.userReview?.review) {
                                          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                            content: Text("No changes in review to update."),
                                          ));
                                          return;
                                        }
                                        final connectivityProvider =
                                            Provider.of<ConnectivityProvider>(context, listen: false);
                                        if (connectivityProvider.isConnected) {
                                          bool isSuccessful = false;
                                          var rev = AppReview(
                                            uid: SharedPreferencesUtil().uid,
                                            review: reviewController.text,
                                            score: rating,
                                            ratedAt: widget.app.userReview?.ratedAt ?? DateTime.now(),
                                            response: widget.app.userReview?.response ?? '',
                                            username: widget.app.userReview?.username ?? '',
                                          );
                                          if (widget.app.userReview == null) {
                                            isSuccessful = await reviewApp(widget.app.id, rev);
                                            widget.app.ratingCount += 1;
                                            widget.app.userReview = rev;
                                          } else {
                                            isSuccessful = await updateAppReview(widget.app.id, rev);
                                            widget.app.userReview = rev;
                                          }
                                          if (isSuccessful) {
                                            updateShowButton(false);
                                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                              content: Text("Review added successfully 🚀"),
                                            ));
                                            bool hadReview = widget.app.userReview != null;
                                            if (!hadReview) widget.app.ratingCount += 1;
                                            widget.app.userReview = AppReview(
                                              uid: SharedPreferencesUtil().uid,
                                              ratedAt: DateTime.now(),
                                              review: reviewController.text,
                                              score: rating,
                                            );
                                            var appsList = SharedPreferencesUtil().appsList;
                                            var index = appsList.indexWhere((element) => element.id == widget.app.id);
                                            appsList[index] = widget.app;
                                            SharedPreferencesUtil().appsList = appsList;
                                            MixpanelManager().appRated(widget.app.id.toString(), rating);
                                            debugPrint('Refreshed apps list.');
                                            setState(() {});
                                          } else {
                                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                              content: Text("Failed to review the app. Please try again later."),
                                            ));
                                          }
                                        } else {
                                          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                            content: Text("Can't rate app without internet connection."),
                                          ));
                                        }
                                      },
                                      color: Colors.white,
                                    )
                                  : const SizedBox(),
                            ],
                          ),
                        ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
