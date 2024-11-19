import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:timeago/timeago.dart' as timeago;

class AppOwnerReviewCard extends StatefulWidget {
  final AppReview review;
  final String appId;
  final String ownerName;
  const AppOwnerReviewCard({super.key, required this.review, required this.appId, required this.ownerName});

  @override
  State<AppOwnerReviewCard> createState() => _AppOwnerReviewCardState();
}

class _AppOwnerReviewCardState extends State<AppOwnerReviewCard> {
  bool showReplyField = false;
  bool showButton = false;
  late TextEditingController replyController;
  bool isLoading = false;

  @override
  void initState() {
    replyController = TextEditingController();
    if (widget.review.response.isNotEmpty) {
      replyController.text = widget.review.response;
    }
    super.initState();
  }

  void updateShowButton(bool value) {
    setState(() {
      showButton = value;
    });
  }

  void updateShowReplyField(bool value) {
    setState(() {
      showReplyField = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
      },
      child: Container(
        width: MediaQuery.of(context).size.width * 0.78,
        padding: const EdgeInsets.all(16.0),
        margin: const EdgeInsets.only(left: 12.0, right: 12.0, top: 2, bottom: 6),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(16.0),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                RatingBar.builder(
                  initialRating: widget.review.score.toDouble(),
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
                  timeago.format(widget.review.ratedAt),
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
              widget.review.review.decodeString,
              style: const TextStyle(
                color: Colors.white,
              ),
            ),
            const SizedBox(
              height: 16,
            ),
            ClipRRect(
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                padding: const EdgeInsets.only(top: 6),
                height: showReplyField ? MediaQuery.sizeOf(context).height * 0.21 : 0,
                child: isLoading
                    ? const Center(
                        child: CircularProgressIndicator(
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : (!showReplyField
                        ? null
                        : SingleChildScrollView(
                            physics: const NeverScrollableScrollPhysics(),
                            child: Column(
                              children: [
                                SizedBox(
                                  width: MediaQuery.sizeOf(context).width * 0.88,
                                  child: TextFormField(
                                    controller: replyController,
                                    enabled: isLoading ? false : true,
                                    keyboardType: TextInputType.multiline,
                                    maxLength: 250,
                                    onChanged: (value) {
                                      if (value.isEmpty) {
                                        if (value == widget.review.review) {
                                          updateShowButton(false);
                                        } else {
                                          updateShowButton(true);
                                        }
                                      } else {
                                        updateShowButton(true);
                                      }
                                    },
                                    decoration: InputDecoration(
                                      hintText: 'Write something',
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
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    SizedBox(
                                      width: MediaQuery.sizeOf(context).width * 0.36,
                                      child: OutlinedButton(
                                        style: OutlinedButton.styleFrom(
                                          side: const BorderSide(color: Colors.white),
                                          shape: RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(16),
                                          ),
                                        ),
                                        onPressed: () {
                                          updateShowReplyField(false);
                                        },
                                        child:
                                            const Text('Cancel', style: TextStyle(color: Colors.white, fontSize: 16)),
                                      ),
                                    ),
                                    const SizedBox(
                                      width: 30,
                                    ),
                                    SizedBox(
                                      width: MediaQuery.sizeOf(context).width * 0.36,
                                      child: OutlinedButton(
                                        style: OutlinedButton.styleFrom(
                                          side: const BorderSide(color: Colors.white),
                                          backgroundColor: Colors.white,
                                          shape: RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(16),
                                          ),
                                        ),
                                        onPressed: () async {
                                          if (replyController.text.isNotEmpty) {
                                            setState(() {
                                              isLoading = true;
                                            });
                                            await replyToAppReview(widget.appId, replyController.text);
                                            context.read<AppProvider>().updateLocalAppReviewResponse(
                                                widget.appId, replyController.text, widget.review.uid);
                                            setState(() {
                                              widget.review.response = replyController.text;
                                              isLoading = false;
                                              showReplyField = false;
                                            });
                                          }
                                        },
                                        child: const Text('Submit Reply',
                                            style: TextStyle(color: Colors.black, fontSize: 16)),
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          )),
              ),
            ),
            !showReplyField && widget.review.response.isNotEmpty
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Divider(
                        color: Color.fromARGB(255, 208, 207, 207),
                      ),
                      const SizedBox(
                        height: 8,
                      ),
                      Row(
                        children: [
                          Text(widget.ownerName, style: const TextStyle(color: Colors.white)),
                          const SizedBox(
                            width: 8,
                          ),
                          widget.review.respondedAt != null
                              ? Text(timeago.format(widget.review.respondedAt!),
                                  style: const TextStyle(color: Colors.grey, fontSize: 12))
                              : const SizedBox(),
                        ],
                      ),
                      const SizedBox(
                        height: 6,
                      ),
                      Text(widget.review.response, style: const TextStyle(color: Colors.white)),
                    ],
                  )
                : const SizedBox(),
            const SizedBox(
              height: 8,
            ),
            !showReplyField
                ? Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                        onPressed: () {
                          updateShowReplyField(!showReplyField);
                        },
                        child: Text(
                          widget.review.response.isNotEmpty ? 'Edit Your Reply' : 'Reply To Review',
                          style: const TextStyle(color: Colors.black),
                        ),
                      ),
                    ],
                  )
                : const SizedBox(),
          ],
        ),
      ),
    );
  }
}
