import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/apps/analytics.dart';
import 'package:friend_private/pages/apps/app_detail/reviews_list_page.dart';
import 'package:friend_private/pages/apps/app_detail/widgets/add_review_widget.dart';
import 'package:friend_private/pages/apps/markdown_viewer.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/animated_loading_button.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../backend/schema/app.dart';
import '../widgets/show_app_options_sheet.dart';
import 'widgets/info_card_widget.dart';

import 'package:timeago/timeago.dart' as timeago;

class AppDetailPage extends StatefulWidget {
  final App app;

  const AppDetailPage({super.key, required this.app});

  @override
  State<AppDetailPage> createState() => _AppDetailPageState();
}

class _AppDetailPageState extends State<AppDetailPage> {
  String? instructionsMarkdown;
  bool setupCompleted = false;
  bool appLoading = false;

  checkSetupCompleted() {
    // TODO: move check to backend
    isAppSetupCompleted(widget.app.externalIntegration!.setupCompletedUrl).then((value) {
      if (mounted) {
        setState(() => setupCompleted = value);
      }
    });
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppProvider>().checkIsAppOwner(widget.app.uid);
      context.read<AppProvider>().setIsAppPublicToggled(!widget.app.private);
    });
    if (widget.app.worksExternally()) {
      if (widget.app.externalIntegration!.setupInstructionsFilePath.isNotEmpty) {
        getAppMarkdown(widget.app.externalIntegration!.setupInstructionsFilePath).then((value) {
          value = value.replaceAll(
            '](assets/',
            '](https://raw.githubusercontent.com/BasedHardware/Omi/main/plugins/instructions/${widget.app.id}/assets/',
          );
          setState(() => instructionsMarkdown = value);
        });
      }
      checkSetupCompleted();
    }

    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    bool isIntegration = widget.app.worksExternally();
    bool hasSetupInstructions =
        isIntegration && widget.app.externalIntegration?.setupInstructionsFilePath.isNotEmpty == true;
    bool hasAuthSteps = isIntegration && widget.app.externalIntegration?.authSteps.isNotEmpty == true;
    int stepsCount = widget.app.externalIntegration?.authSteps.length ?? 0;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        actions: [
          context.watch<AppProvider>().isAppOwner
              ? IconButton(
                  icon: const Icon(Icons.settings),
                  onPressed: () async {
                    await showModalBottomSheet(
                      context: context,
                      shape: const RoundedRectangleBorder(
                        borderRadius: BorderRadius.only(
                          topLeft: Radius.circular(16),
                          topRight: Radius.circular(16),
                        ),
                      ),
                      builder: (context) {
                        return ShowAppOptionsSheet(
                          app: widget.app,
                        );
                      },
                    );
                  },
                )
              : const SizedBox.shrink(),
        ],
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 20),
            Row(
              children: [
                const SizedBox(width: 20),
                CachedNetworkImage(
                  imageUrl: widget.app.getImageUrl(),
                  imageBuilder: (context, imageProvider) => Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      shape: BoxShape.rectangle,
                      borderRadius: BorderRadius.circular(8),
                      image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                    ),
                  ),
                  placeholder: (context, url) => const CircularProgressIndicator(),
                  errorWidget: (context, url, error) => const Icon(Icons.error),
                ),
                const SizedBox(width: 20),
                Column(
                  mainAxisAlignment: MainAxisAlignment.start,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: MediaQuery.of(context).size.width * 0.6,
                      child: Text(
                        widget.app.name.decodeString,
                        style: const TextStyle(color: Colors.white, fontSize: 20),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      widget.app.author,
                      style: const TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Spacer(),
                widget.app.ratingCount == 0
                    ? const Column(
                        children: [
                          Text(
                            '0.0',
                            style: TextStyle(
                              fontSize: 16,
                            ),
                          ),
                          SizedBox(height: 4),
                          Text("no reviews"),
                        ],
                      )
                    : Column(
                        children: [
                          Row(
                            children: [
                              Text(
                                widget.app.getRatingAvg() ?? '0.0',
                                style: const TextStyle(
                                  fontSize: 16,
                                ),
                              ),
                              RatingBar.builder(
                                initialRating: widget.app.ratingAvg ?? 0,
                                minRating: 1,
                                ignoreGestures: true,
                                direction: Axis.horizontal,
                                allowHalfRating: true,
                                itemCount: 1,
                                itemSize: 20,
                                tapOnlyMode: false,
                                itemPadding: const EdgeInsets.symmetric(horizontal: 0),
                                itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.deepPurple),
                                maxRating: 5.0,
                                onRatingUpdate: (rating) {},
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text('${widget.app.ratingCount}+ reviews'),
                        ],
                      ),
                const Spacer(),
                const SizedBox(
                  height: 36,
                  child: VerticalDivider(
                    color: Colors.white,
                    endIndent: 2,
                    indent: 2,
                    width: 4,
                  ),
                ),
                const Spacer(),
                Column(
                  children: [
                    Text(
                      '${(widget.app.installs / 10).round() * 10}+',
                      style: const TextStyle(
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text("installs"),
                  ],
                ),
                const Spacer(),
                const SizedBox(
                  height: 36,
                  child: VerticalDivider(
                    color: Colors.white,
                    endIndent: 2,
                    indent: 2,
                    width: 4,
                  ),
                ),
                const Spacer(),
                Column(
                  children: [
                    Text(
                      widget.app.private ? 'Private' : 'Public',
                      style: const TextStyle(
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text("app"),
                  ],
                ),
                const Spacer(),
              ],
            ),
            const SizedBox(height: 24),
            widget.app.enabled
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: AnimatedLoadingButton(
                        text: 'Uninstall App',
                        width: MediaQuery.of(context).size.width * 0.9,
                        onPressed: () => _toggleApp(widget.app.id, false),
                        color: Colors.red,
                      ),
                    ),
                  )
                : Center(
                    child: Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: AnimatedLoadingButton(
                        width: MediaQuery.of(context).size.width * 0.9,
                        text: 'Install App',
                        onPressed: () => _toggleApp(widget.app.id, true),
                        color: Colors.green,
                      ),
                    ),
                  ),
            widget.app.isUnderReview() && !widget.app.private && widget.app.isOwner(SharedPreferencesUtil().uid)
                ? Column(
                    children: [
                      const SizedBox(
                        height: 10,
                      ),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.info_outline,
                            color: Colors.grey,
                            size: 18,
                          ),
                          const SizedBox(width: 10),
                          SizedBox(
                            width: MediaQuery.of(context).size.width * 0.78,
                            child: const Text(
                                'Your app is under review and visible only to you. It will be public once approved.',
                                style: TextStyle(color: Colors.grey)),
                          ),
                        ],
                      ),
                    ],
                  )
                : const SizedBox.shrink(),
            widget.app.isRejected()
                ? Column(
                    children: [
                      const SizedBox(
                        height: 10,
                      ),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.error_outline,
                            color: Colors.grey,
                            size: 18,
                          ),
                          const SizedBox(width: 10),
                          SizedBox(
                            width: MediaQuery.of(context).size.width * 0.78,
                            child: const Text(
                              'Your app has been rejected. Please update the app details and resubmit for review.',
                              style: TextStyle(color: Colors.grey),
                            ),
                          ),
                        ],
                      ),
                    ],
                  )
                : const SizedBox.shrink(),
            const SizedBox(height: 16),
            (hasAuthSteps && stepsCount > 0)
                ? Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Setup Steps',
                          style: TextStyle(color: Colors.white, fontSize: 18),
                        ),
                        setupCompleted
                            ? const Padding(
                                padding: EdgeInsets.only(right: 12.0),
                                child: Text(
                                  '✅',
                                  style: TextStyle(color: Colors.grey, fontSize: 18),
                                ),
                              )
                            : const SizedBox(),
                      ],
                    ),
                  )
                : const SizedBox.shrink(),
            ...(hasAuthSteps
                ? widget.app.externalIntegration!.authSteps.mapIndexed<Widget>((i, step) {
                    String title = stepsCount == 0 ? step.name : '${i + 1}. ${step.name}';
                    // String title = stepsCount == 1 ? step.name : '${i + 1}. ${step.name}';
                    return ListTile(
                        title: Text(
                          title,
                          style: const TextStyle(fontSize: 17),
                        ),
                        onTap: () async {
                          await launchUrl(Uri.parse("${step.url}?uid=${SharedPreferencesUtil().uid}"));
                          checkSetupCompleted();
                        },
                        trailing: const Padding(
                          padding: EdgeInsets.only(right: 12.0),
                          child: Icon(Icons.arrow_forward_ios, size: 20, color: Colors.grey),
                        ));
                  }).toList()
                : <Widget>[const SizedBox.shrink()]),
            !hasAuthSteps && hasSetupInstructions
                ? ListTile(
                    onTap: () async {
                      if (widget.app.externalIntegration != null) {
                        if (widget.app.externalIntegration!.setupInstructionsFilePath
                            .contains('raw.githubusercontent.com')) {
                          await routeToPage(
                            context,
                            MarkdownViewer(title: 'Setup Instructions', markdown: instructionsMarkdown ?? ''),
                          );
                        } else {
                          if (widget.app.externalIntegration!.isInstructionsUrl) {
                            await launchUrl(Uri.parse(widget.app.externalIntegration!.setupInstructionsFilePath));
                          } else {
                            var m = widget.app.externalIntegration!.setupInstructionsFilePath;
                            routeToPage(context, MarkdownViewer(title: 'Setup Instructions', markdown: m));
                          }
                        }
                      }
                      checkSetupCompleted();
                    },
                    trailing: const Padding(
                      padding: EdgeInsets.only(right: 12.0),
                      child: Icon(Icons.arrow_forward_ios, size: 20, color: Colors.grey),
                    ),
                    title: const Text(
                      'Integration Instructions',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                  )
                : const SizedBox.shrink(),
            InfoCardWidget(
              onTap: () {
                if (widget.app.description.decodeString.characters.length > 200) {
                  routeToPage(
                      context, MarkdownViewer(title: 'About the App', markdown: widget.app.description.decodeString));
                }
              },
              title: 'About the App',
              description: widget.app.description,
              showChips: true,
              chips: widget.app
                  .getCapabilitiesFromIds(context.read<AddAppProvider>().capabilities)
                  .map((e) => e.title)
                  .toList(),
            ),

            widget.app.memoryPrompt != null
                ? InfoCardWidget(
                    onTap: () {
                      if (widget.app.memoryPrompt!.decodeString.characters.length > 200) {
                        routeToPage(context,
                            MarkdownViewer(title: 'Memory Prompt', markdown: widget.app.memoryPrompt!.decodeString));
                      }
                    },
                    title: 'Memory Prompt',
                    description: widget.app.memoryPrompt!,
                    showChips: false,
                  )
                : const SizedBox.shrink(),

            widget.app.chatPrompt != null
                ? InfoCardWidget(
                    onTap: () {
                      if (widget.app.chatPrompt!.decodeString.characters.length > 200) {
                        routeToPage(context,
                            MarkdownViewer(title: 'Chat Persoality', markdown: widget.app.chatPrompt!.decodeString));
                      }
                    },
                    title: 'Chat Personality',
                    description: widget.app.chatPrompt!,
                    showChips: false,
                  )
                : const SizedBox.shrink(),
            GestureDetector(
              onTap: () {
                if (widget.app.reviews.isNotEmpty) {
                  routeToPage(context, ReviewsListPage(app: widget.app));
                }
              },
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(18.0),
                margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
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
                        const Text('Ratings & Reviews', style: TextStyle(color: Colors.white, fontSize: 18)),
                        const Spacer(),
                        widget.app.reviews.isNotEmpty
                            ? const Icon(
                                Icons.arrow_forward,
                                size: 20,
                              )
                            : const SizedBox.shrink(),
                      ],
                    ),
                    const SizedBox(height: 20),
                    Row(
                      children: [
                        Text(widget.app.getRatingAvg() ?? '0.0',
                            style: const TextStyle(fontSize: 38, fontWeight: FontWeight.bold)),
                        const Spacer(),
                        Column(
                          children: [
                            RatingBar.builder(
                              initialRating: 4.2,
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
                            const SizedBox(height: 4),
                            Text("${widget.app.ratingCount}+ ratings"),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    RecentReviewsSection(
                      reviews: widget.app.reviews.sorted((a, b) => b.ratedAt.compareTo(a.ratedAt)).take(3).toList(),
                      appAuthor: widget.app.author,
                    )
                  ],
                ),
              ),
            ),
            !widget.app.isOwner(SharedPreferencesUtil().uid)
                ? AddReviewWidget(app: widget.app)
                : const SizedBox.shrink(),
            // isIntegration ? const SizedBox(height: 16) : const SizedBox.shrink(),
            // widget.plugin.worksExternally() ? const SizedBox(height: 16) : const SizedBox.shrink(),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
              child: GestureDetector(
                onTap: () {
                  routeToPage(context, AppAnalytics(app: widget.app));
                },
                child: const Text(
                  'App Analytics',
                  style: TextStyle(color: Colors.white, fontSize: 14, decoration: TextDecoration.underline),
                ),
              ),
            ),
            const SizedBox(height: 60),
          ],
        ),
      ),
    );
  }

  Future<void> _toggleApp(String appId, bool isEnabled) async {
    var prefs = SharedPreferencesUtil();
    setState(() => appLoading = true);
    if (isEnabled) {
      var enabled = await enableAppServer(appId);
      if (!enabled) {
        if (mounted) {
          showDialog(
            context: context,
            builder: (c) => getDialog(
              context,
              () => Navigator.pop(context),
              () => Navigator.pop(context),
              'Error activating the app',
              'If this is an integration app, make sure the setup is completed.',
              singleButton: true,
            ),
          );
        }

        setState(() => appLoading = false);
        return;
      }

      prefs.enableApp(appId);
      MixpanelManager().appEnabled(appId);
    } else {
      prefs.disableApp(appId);
      await enableAppServer(appId);
      MixpanelManager().appDisabled(appId);
    }
    context.read<AppProvider>().setApps();
    setState(() => widget.app.enabled = isEnabled);
    setState(() => appLoading = false);
  }
}

class RecentReviewsSection extends StatelessWidget {
  final List<AppReview> reviews;
  final String appAuthor;
  const RecentReviewsSection({super.key, required this.reviews, required this.appAuthor});

  @override
  Widget build(BuildContext context) {
    if (reviews.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        const SizedBox(height: 12),
        const Text(
          'Most Recent Reviews',
          style: TextStyle(color: Colors.white, fontSize: 16),
        ),
        const SizedBox(height: 16),
        ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: reviews.any((e) => e.response.isNotEmpty)
                ? MediaQuery.of(context).size.height * 0.24
                : MediaQuery.of(context).size.height * 0.138,
          ),
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            shrinkWrap: true,
            itemCount: reviews.length,
            itemBuilder: (context, index) {
              return Container(
                width: reviews.length == 1
                    ? MediaQuery.of(context).size.width * 0.84
                    : MediaQuery.of(context).size.width * 0.78,
                padding: const EdgeInsets.all(16.0),
                margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 0, bottom: 6),
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
                          width: 8,
                        ),
                        Text(
                          timeago.format(reviews[index].ratedAt),
                          style: const TextStyle(color: Color.fromARGB(255, 176, 174, 174), fontSize: 12),
                        ),
                      ],
                    ),
                    const SizedBox(
                      height: 8,
                    ),
                    Text(
                      reviews[index].review.length > 100
                          ? '${reviews[index].review.characters.take(100).toString().decodeString.trim()}...'
                          : reviews[index].review.decodeString,
                      style: const TextStyle(
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(
                      height: 6,
                    ),
                    reviews[index].response.isNotEmpty
                        ? Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Divider(
                                color: Color.fromARGB(255, 92, 92, 92),
                              ),
                              const SizedBox(height: 6),
                              Row(
                                children: [
                                  Text(
                                    'Response from $appAuthor',
                                    style: const TextStyle(color: Colors.white, fontSize: 14),
                                  ),
                                  const SizedBox(
                                    width: 8,
                                  ),
                                  Text(
                                    timeago.format(reviews[index].ratedAt),
                                    style: const TextStyle(color: Color.fromARGB(255, 176, 174, 174), fontSize: 12),
                                  ),
                                ],
                              ),
                              const SizedBox(
                                height: 8,
                              ),
                              Text(
                                reviews[index].response.length > 100
                                    ? '${reviews[index].response.characters.take(100).toString().decodeString.trim()}...'
                                    : reviews[index].response.decodeString,
                                style: const TextStyle(
                                  color: Colors.white,
                                ),
                              ),
                            ],
                          )
                        : const SizedBox.shrink(),
                  ],
                ),
              );
            },
            separatorBuilder: (context, index) => const SizedBox(width: 2),
          ),
        ),
      ],
    );
  }
}
