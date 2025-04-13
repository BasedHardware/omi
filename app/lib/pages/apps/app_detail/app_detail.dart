import 'package:cached_network_image/cached_network_image.dart';
import 'package:shimmer/shimmer.dart';
import 'package:omi/pages/apps/app_home_web_page.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/pages/apps/widgets/full_screen_image_viewer.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/apps/app_detail/reviews_list_page.dart';
import 'package:omi/pages/apps/app_detail/widgets/add_review_widget.dart';
import 'package:omi/pages/apps/markdown_viewer.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/animated_loading_button.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:skeletonizer/skeletonizer.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:async';

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
  bool isLoading = false;
  Timer? _paymentCheckTimer;
  late App app;
  late bool showInstallAppConfirmation;

  checkSetupCompleted() {
    // TODO: move check to backend
    isAppSetupCompleted(app.externalIntegration!.setupCompletedUrl).then((value) {
      if (mounted) {
        setState(() => setupCompleted = value);
      }
    });
  }

  void setIsLoading(bool value) {
    if (mounted && isLoading != value) {
      setState(() => isLoading = value);
    }
  }

  @override
  void initState() {
    app = widget.app;
    showInstallAppConfirmation = SharedPreferencesUtil().showInstallAppConfirmation;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Automatically open app home page if conditions are met
      if (app.enabled && app.externalIntegration?.appHomeUrl?.isNotEmpty == true) {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => AppHomeWebPage(app: app),
          ),
        );
      }
      // Load details
      setIsLoading(true);
      var res = await context.read<AppProvider>().getAppDetails(app.id);
      if (mounted) {
        setState(() {
          if (res != null) {
            app = res;
          }
        });
      }

      setIsLoading(false);
      context.read<AppProvider>().checkIsAppOwner(app.uid);
      context.read<AppProvider>().setIsAppPublicToggled(!app.private);
    });
    if (app.worksExternally()) {
      if (app.externalIntegration!.setupInstructionsFilePath?.isNotEmpty == true) {
        if (app.externalIntegration!.setupInstructionsFilePath?.contains('raw.githubusercontent.com') == true) {
          getAppMarkdown(app.externalIntegration!.setupInstructionsFilePath ?? '').then((value) {
            value = value.replaceAll(
              '](assets/',
              '](https://raw.githubusercontent.com/BasedHardware/Omi/main/plugins/instructions/${app.id}/assets/',
            );
            setState(() => instructionsMarkdown = value);
          });
        }
      }
      checkSetupCompleted();
    }

    super.initState();
  }

  @override
  void dispose() {
    _paymentCheckTimer?.cancel();
    super.dispose();
  }

  Future _checkPaymentStatus(String appId) async {
    MixpanelManager().appPurchaseStarted(appId);
    _paymentCheckTimer = Timer.periodic(const Duration(seconds: 5), (timer) async {
      var prefs = SharedPreferencesUtil();
      if (mounted) {
        setState(() => appLoading = true);
      }

      var details = await getAppDetailsServer(appId);
      if (details != null && details['is_user_paid']) {
        var enabled = await enableAppServer(appId);
        if (enabled) {
          MixpanelManager().appPurchaseCompleted(appId);
          prefs.enableApp(appId);
          MixpanelManager().appEnabled(appId);
          context.read<AppProvider>().setApps();
          setState(() {
            app.isUserPaid = true;
            app.enabled = true;
            appLoading = false;
          });
          timer.cancel();
          _paymentCheckTimer?.cancel();
        } else {
          debugPrint('Payment not made yet');
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    bool isIntegration = app.worksExternally();
    bool hasSetupInstructions = isIntegration && app.externalIntegration?.setupInstructionsFilePath?.isNotEmpty == true;
    bool hasAuthSteps = isIntegration && app.externalIntegration?.authSteps.isNotEmpty == true;
    int stepsCount = app.externalIntegration?.authSteps.length ?? 0;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        actions: [
          if (app.enabled && app.worksWithChat()) ...[
            GestureDetector(
              child: const Icon(Icons.question_answer),
              onTap: () async {
                Navigator.pop(context);
                context.read<HomeProvider>().setIndex(1);
                if (context.read<HomeProvider>().onSelectedIndexChanged != null) {
                  context.read<HomeProvider>().onSelectedIndexChanged!(1);
                }
                var appId = app.id;
                var appProvider = Provider.of<AppProvider>(context, listen: false);
                var messageProvider = Provider.of<MessageProvider>(context, listen: false);
                App? selectedApp;
                if (appId.isNotEmpty) {
                  selectedApp = await appProvider.getAppFromId(appId);
                }
                appProvider.setSelectedChatAppId(appId);
                await messageProvider.refreshMessages();
                if (messageProvider.messages.isEmpty) {
                  messageProvider.sendInitialAppMessage(selectedApp);
                }
              },
            ),
            const SizedBox(width: 24),
          ],
          if (app.enabled && app.externalIntegration?.appHomeUrl?.isNotEmpty == true) ...[
            GestureDetector(
              child: const Icon(
                Icons.open_in_browser_rounded,
                color: Colors.white,
              ),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => AppHomeWebPage(app: app),
                  ),
                );
              },
            ),
            const SizedBox(width: 24),
          ],
          isLoading || app.private
              ? const SizedBox.shrink()
              : GestureDetector(
                  child: const Icon(Icons.share),
                  onTap: () {
                    MixpanelManager().track('App Shared', properties: {'appId': app.id});
                    if (app.isNotPersona()) {
                      Share.share(
                        'Check out this app on Omi AI: ${app.name} by ${app.author} \n\n${app.description.decodeString}\n\n\nhttps://h.omi.me/apps/${app.id}',
                        subject: app.name,
                      );
                    } else {
                      Share.share(
                        'Check out this Persona on Omi AI: ${app.name} by ${app.author} \n\n${app.description.decodeString}\n\n\nhttps://personas.omi.me/u/${app.username}',
                        subject: app.name,
                      );
                    }
                  },
                ),
          !context.watch<AppProvider>().isAppOwner
              ? const SizedBox(
                  width: 24,
                )
              : const SizedBox(
                  width: 12,
                ),
          context.watch<AppProvider>().isAppOwner
              ? (isLoading
                  ? const SizedBox.shrink()
                  : IconButton(
                      icon: const Icon(Icons.settings),
                      padding: const EdgeInsets.only(right: 12),
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
                              app: app,
                            );
                          },
                        );
                      },
                    ))
              : const SizedBox.shrink(),
        ],
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SingleChildScrollView(
        child: Skeletonizer(
          enabled: isLoading,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 20),
              Row(
                children: [
                  const SizedBox(width: 20),
                  CachedNetworkImage(
                    imageUrl: app.getImageUrl(),
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
                          app.name.decodeString,
                          style: const TextStyle(color: Colors.white, fontSize: 20),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        app.author.decodeString,
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
                  app.ratingCount == 0
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
                                  app.getRatingAvg() ?? '0.0',
                                  style: const TextStyle(
                                    fontSize: 16,
                                  ),
                                ),
                                RatingBar.builder(
                                  initialRating: app.ratingAvg ?? 0,
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
                            Text('${app.ratingCount}+ reviews'),
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
                        '${(app.installs / 10).round() * 10}+',
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
                        app.private ? 'Private' : 'Public',
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
              isLoading
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(8.0),
                        child: AnimatedLoadingButton(
                          text: '',
                          width: MediaQuery.of(context).size.width * 0.9,
                          onPressed: () async {},
                          color: Colors.grey.shade800,
                        ),
                      ),
                    )
                  : app.enabled
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(8.0),
                            child: AnimatedLoadingButton(
                              text: 'Uninstall App',
                              width: MediaQuery.of(context).size.width * 0.9,
                              onPressed: () => _toggleApp(app.id, false),
                              color: Colors.red,
                            ),
                          ),
                        )
                      : (app.isPaid && !app.isUserPaid
                          ? Center(
                              child: Padding(
                                padding: const EdgeInsets.all(8.0),
                                child: AnimatedLoadingButton(
                                  width: MediaQuery.of(context).size.width * 0.9,
                                  text: "Subscribe",
                                  onPressed: () async {
                                    if (app.paymentLink != null && app.paymentLink!.isNotEmpty) {
                                      _checkPaymentStatus(app.id);
                                      await launchUrl(Uri.parse(app.paymentLink!));
                                    } else {
                                      await _toggleApp(app.id, true);
                                    }
                                  },
                                  color: Colors.green,
                                ),
                              ),
                            )
                          : Center(
                              child: Padding(
                                padding: const EdgeInsets.all(8.0),
                                child: AnimatedLoadingButton(
                                  width: MediaQuery.of(context).size.width * 0.9,
                                  text: 'Install App',
                                  onPressed: () async {
                                    if (app.worksExternally()) {
                                      showDialog(
                                        context: context,
                                        builder: (ctx) {
                                          return StatefulBuilder(builder: (ctx, setState) {
                                            return ConfirmationDialog(
                                              title: 'Data Access Notice',
                                              description:
                                                  'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app',
                                              checkboxText: "Don't show it again",
                                              checkboxValue: !showInstallAppConfirmation,
                                              onCheckboxChanged: (value) {
                                                setState(() {
                                                  showInstallAppConfirmation = !value;
                                                  SharedPreferencesUtil().showInstallAppConfirmation = !value;
                                                });
                                              },
                                              onConfirm: () {
                                                _toggleApp(app.id, true);
                                                Navigator.pop(context);
                                              },
                                              onCancel: () {
                                                Navigator.pop(context);
                                              },
                                            );
                                          });
                                        },
                                      );
                                    } else {
                                      _toggleApp(app.id, true);
                                    }
                                  },
                                  color: Colors.green,
                                ),
                              ),
                            )),

              (app.isUnderReview() || app.private) && !app.isOwner(SharedPreferencesUtil().uid)
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
                                  'You are a beta tester for this app. It is not public yet. It will be public once approved.',
                                  style: TextStyle(color: Colors.grey)),
                            ),
                          ],
                        ),
                      ],
                    )
                  : const SizedBox.shrink(),
              app.isUnderReview() && !app.private && app.isOwner(SharedPreferencesUtil().uid)
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
              app.isRejected()
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
                  ? app.externalIntegration!.authSteps.mapIndexed<Widget>((i, step) {
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
                        if (app.externalIntegration != null) {
                          if (app.externalIntegration!.setupInstructionsFilePath
                                  ?.contains('raw.githubusercontent.com') ==
                              true) {
                            await routeToPage(
                              context,
                              MarkdownViewer(title: 'Setup Instructions', markdown: instructionsMarkdown ?? ''),
                            );
                          } else {
                            if (app.externalIntegration!.isInstructionsUrl == true) {
                              await launchUrl(Uri.parse(app.externalIntegration!.setupInstructionsFilePath ?? ''));
                            } else {
                              var m = app.externalIntegration!.setupInstructionsFilePath;
                              routeToPage(context, MarkdownViewer(title: 'Setup Instructions', markdown: m ?? ''));
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
                        style: TextStyle(fontWeight: FontWeight.w500, fontSize: 18),
                      ),
                    )
                  : const SizedBox.shrink(),
              if (app.thumbnailUrls.isNotEmpty) ...[
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 16),
                  child: Text(
                    'Preview',
                    style: TextStyle(color: Colors.white, fontSize: 18),
                  ),
                ),
                SizedBox(
                  height: MediaQuery.of(context).size.width * 0.9,
                  child: ListView.builder(
                    padding: EdgeInsets.zero,
                    scrollDirection: Axis.horizontal,
                    itemCount: app.thumbnailUrls.length,
                    itemBuilder: (context, index) {
                      final screenWidth = MediaQuery.of(context).size.width;
                      // Calculate width to show 1.5 thumbnails
                      final width = screenWidth * 0.65;
                      // Calculate height to maintain 2:3 ratio (height = width * 1.5)
                      final height = width * 1.5;

                      return GestureDetector(
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (context) => FullScreenImageViewer(
                                imageUrl: app.thumbnailUrls[index],
                              ),
                            ),
                          );
                        },
                        child: CachedNetworkImage(
                          imageUrl: app.thumbnailUrls[index],
                          imageBuilder: (context, imageProvider) => Container(
                            width: width,
                            height: height,
                            clipBehavior: Clip.hardEdge,
                            margin: EdgeInsets.only(
                              left: index == 0 ? 16 : 8,
                              right: index == app.thumbnailUrls.length - 1 ? 16 : 8,
                            ),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: const Color(0xFF424242),
                                width: 1,
                              ),
                              image: DecorationImage(
                                image: imageProvider,
                                fit: BoxFit.cover,
                              ),
                            ),
                          ),
                          placeholder: (context, url) => Shimmer.fromColors(
                            baseColor: Colors.grey[900]!,
                            highlightColor: Colors.grey[800]!,
                            child: Container(
                              width: width,
                              height: height,
                              margin: EdgeInsets.only(
                                left: index == 0 ? 16 : 8,
                                right: index == app.thumbnailUrls.length - 1 ? 16 : 8,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.black,
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                          ),
                          errorWidget: (context, url, error) => Container(
                            width: width,
                            height: height,
                            margin: EdgeInsets.only(
                              left: index == 0 ? 16 : 8,
                              right: index == app.thumbnailUrls.length - 1 ? 16 : 8,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.grey[900],
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(Icons.error),
                          ),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 16),
              ],
              InfoCardWidget(
                onTap: () {
                  if (app.description.decodeString.characters.length > 200) {
                    routeToPage(
                        context,
                        MarkdownViewer(
                            title: 'About the ${app.isNotPersona() ? 'App' : 'Persona'}',
                            markdown: app.description.decodeString));
                  }
                },
                title: 'About the ${app.isNotPersona() ? 'App' : 'Persona'}',
                description: app.description,
                showChips: true,
                capabilityChips: app
                    .getCapabilitiesFromIds(context.read<AddAppProvider>().capabilities)
                    .map((e) => e.title)
                    .toList(),
                connectionChips: app.getConnectedAccountNames(),
              ),

              app.conversationPrompt != null
                  ? InfoCardWidget(
                      onTap: () {
                        if (app.conversationPrompt!.decodeString.characters.length > 200) {
                          routeToPage(
                              context,
                              MarkdownViewer(
                                  title: 'Conversation Prompt', markdown: app.conversationPrompt!.decodeString));
                        }
                      },
                      title: 'Conversation Prompt',
                      description: app.conversationPrompt!,
                      showChips: false,
                    )
                  : const SizedBox.shrink(),

              app.chatPrompt != null
                  ? InfoCardWidget(
                      onTap: () {
                        if (app.chatPrompt!.decodeString.characters.length > 200) {
                          routeToPage(context,
                              MarkdownViewer(title: 'Chat Personality', markdown: app.chatPrompt!.decodeString));
                        }
                      },
                      title: 'Chat Personality',
                      description: app.chatPrompt!,
                      showChips: false,
                    )
                  : const SizedBox.shrink(),
              GestureDetector(
                onTap: () {
                  if (app.reviews.isNotEmpty) {
                    routeToPage(context, ReviewsListPage(app: app));
                  }
                },
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16.0),
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
                          app.reviews.isNotEmpty
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
                          Text(app.getRatingAvg() ?? '0.0',
                              style: const TextStyle(fontSize: 38, fontWeight: FontWeight.bold)),
                          const Spacer(),
                          Column(
                            children: [
                              Skeleton.ignore(
                                child: RatingBar.builder(
                                  initialRating: app.ratingAvg ?? 0,
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
                              ),
                              const SizedBox(height: 4),
                              Text(app.ratingCount <= 0 ? "no ratings" : "${app.ratingCount}+ ratings"),
                            ],
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      RecentReviewsSection(
                        reviews: app.reviews.sorted((a, b) => b.ratedAt.compareTo(a.ratedAt)).take(3).toList(),
                        appAuthor: app.author,
                      )
                    ],
                  ),
                ),
              ),
              !app.isOwner(SharedPreferencesUtil().uid) && (app.enabled || app.userReview != null)
                  ? AddReviewWidget(app: app)
                  : const SizedBox.shrink(),
              // isIntegration ? const SizedBox(height: 16) : const SizedBox.shrink(),
              // widget.plugin.worksExternally() ? const SizedBox(height: 16) : const SizedBox.shrink(),
              // app.private
              //     ? const SizedBox.shrink()
              //     : AppAnalyticsWidget(
              //         installs: app.installs, moneyMade: app.isPaid ? ((app.price ?? 0) * app.installs) : 0),
              const SizedBox(height: 60),
            ],
          ),
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

      // Automatically open app home page after installation if available
      if (app.externalIntegration?.appHomeUrl?.isNotEmpty == true) {
        Future.delayed(const Duration(seconds: 1), () {
          if (mounted) {
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (context) => AppHomeWebPage(app: app),
              ),
            );
          }
        });
      }
    } else {
      prefs.disableApp(appId);
      var res = await disableAppServer(appId);
      print(res);
      MixpanelManager().appDisabled(appId);
    }
    context.read<AppProvider>().setApps();
    setState(() => app.enabled = isEnabled);
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
                : (MediaQuery.of(context).size.height < 680
                    ? MediaQuery.of(context).size.height * 0.2
                    : MediaQuery.of(context).size.height * 0.138),
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
