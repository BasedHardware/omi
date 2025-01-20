import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/apps/app_detail/reviews_list_page.dart';
import 'package:friend_private/pages/browser/page.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:friend_private/pages/apps/app_detail/widgets/add_review_widget.dart';
import 'package:friend_private/pages/apps/markdown_viewer.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/animated_loading_button.dart';
import 'package:friend_private/widgets/confirmation_dialog.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:skeletonizer/skeletonizer.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:async';

import '../../../backend/schema/app.dart';
import '../widgets/show_app_options_sheet.dart';
import 'widgets/app_analytics_widget.dart';
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
  WebViewController? webViewController;
  bool isWebViewLoading = true;
  bool showDetails = false;

  Future<void> initWebView() async {
    if (!app.enabled || !app.worksExternally() || app.externalIntegration?.authSteps.isEmpty == true) {
      return;
    }

    final baseUrl = app.externalIntegration!.authSteps.first.url.trim();
    if (baseUrl.isEmpty) {
      return;
    }
    
    final finalUrl = baseUrl.startsWith('http') ? baseUrl : 'https://$baseUrl';
    final uri = Uri.parse(finalUrl);
    final urlWithUid = uri.replace(queryParameters: {
      ...uri.queryParameters,
      'uid': SharedPreferencesUtil().uid,
    }).toString();

    setState(() {
      isWebViewLoading = true;
    });

    webViewController = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.grey[900]!)
      ..enableZoom(false)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (String url) {
            if (mounted) {
              setState(() {
                isWebViewLoading = false;
              });
            }
          },
          onWebResourceError: (WebResourceError error) {
            if (mounted) {
              setState(() {
                isWebViewLoading = false;
              });
            }
          },
        ),
      )
      ..loadRequest(Uri.parse(urlWithUid));

    // Enable cookie persistence
    await WebViewCookieManager().setCookie(
      WebViewCookie(
        name: '.AspNetCore.Cookies',
        value: SharedPreferencesUtil().uid,
        domain: Uri.parse(urlWithUid).host,
      ),
    );
  }

  void checkSetupCompleted() {
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
    super.initState();
    app = widget.app;
    showInstallAppConfirmation = SharedPreferencesUtil().showInstallAppConfirmation;

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      setIsLoading(true);
      var res = await context.read<AppProvider>().getAppDetails(app.id);
      if (mounted && res != null) {
        // Preserve pinned state when updating app details
        final wasPinned = app.pinned;
        setState(() {
          app = res;
          app.pinned = wasPinned;
        });
        if (app.enabled) {
          initWebView();
        }
      }
      setIsLoading(false);
      if (mounted) {
        context.read<AppProvider>().checkIsAppOwner(app.uid);
        context.read<AppProvider>().setIsAppPublicToggled(!app.private);
      }
    });

    if (app.worksExternally()) {
      if (app.externalIntegration!.setupInstructionsFilePath.isNotEmpty) {
        if (app.externalIntegration!.setupInstructionsFilePath.contains('raw.githubusercontent.com')) {
          getAppMarkdown(app.externalIntegration!.setupInstructionsFilePath).then((value) {
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
  }

  @override
  void dispose() {
    _paymentCheckTimer?.cancel();
    super.dispose();
  }

  Future<void> _checkPaymentStatus(String appId) async {
    MixpanelManager().appPurchaseStarted(appId);
    _paymentCheckTimer = Timer.periodic(const Duration(seconds: 5), (timer) async {
      var prefs = SharedPreferencesUtil();
      setState(() => appLoading = true);
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
          initWebView();
        } else {
          debugPrint('Payment not made yet');
        }
      }
    });
  }

  List<Widget> _buildAppBarActions() {
    final actions = <Widget>[];

    // Show pin toggle if app is enabled or already pinned
    if (app.enabled || app.pinned) {
      actions.add(
        Consumer<AppProvider>(
          builder: (context, provider, _) {
            final currentApp = provider.apps.firstWhere((a) => a.id == app.id);
            return IconButton(
              icon: Icon(
                currentApp.pinned ? Icons.push_pin : Icons.push_pin_outlined,
                color: currentApp.pinned ? Colors.deepPurple : null,
              ),
              padding: const EdgeInsets.symmetric(horizontal: 16),
              onPressed: () => provider.toggleAppPin(app.id, context),
            );
          },
        ),
      );
    }

    // Add WebView toggle if available
    if (app.enabled && app.externalIntegration?.authSteps.isNotEmpty == true) {
      actions.add(
        IconButton(
          icon: Icon(showDetails ? Icons.web : Icons.info_outline),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          onPressed: () => setState(() => showDetails = !showDetails),
        ),
      );
    }

    // Add share/settings based on ownership
    if (context.read<AppProvider>().isAppOwner) {
      // Show popup menu for owners with share and settings
      actions.add(
        PopupMenuButton<String>(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemBuilder: (context) => [
            const PopupMenuItem(
              value: 'share',
              child: Row(
                children: [
                  Icon(Icons.share),
                  SizedBox(width: 8),
                  Text('Share'),
                ],
              ),
            ),
            const PopupMenuItem(
              value: 'settings',
              child: Row(
                children: [
                  Icon(Icons.settings),
                  SizedBox(width: 8),
                  Text('Settings'),
                ],
              ),
            ),
          ],
          onSelected: (value) async {
            if (value == 'share') {
              MixpanelManager().track('App Shared', properties: {'appId': app.id});
              Share.share(
                'Check out this app on Omi AI: ${app.name} by ${app.author} \n\n${app.description.decodeString}\n\n\nhttps://h.omi.me/apps/${app.id}',
                subject: app.name,
              );
            } else if (value == 'settings') {
              await showModalBottomSheet(
                context: context,
                shape: const RoundedRectangleBorder(
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(16),
                    topRight: Radius.circular(16),
                  ),
                ),
                builder: (context) => ShowAppOptionsSheet(app: app),
              );
            }
          },
        ),
      );
    } else {
      // Show just share button for non-owners
      actions.add(
        IconButton(
          icon: const Icon(Icons.share),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          onPressed: () {
            MixpanelManager().track('App Shared', properties: {'appId': app.id});
            Share.share(
              'Check out this app on Omi AI: ${app.name} by ${app.author} \n\n${app.description.decodeString}\n\n\nhttps://h.omi.me/apps/${app.id}',
              subject: app.name,
            );
          },
        ),
      );
    }

    return actions;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        actions: _buildAppBarActions(),
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: app.enabled && !showDetails && app.worksExternally() && app.externalIntegration?.authSteps.isNotEmpty == true
          ? SizedBox.expand(
              child: Container(
                color: Colors.grey[900],
                child: Stack(
                  children: [
                    if (webViewController != null)
                      WebViewWidget(controller: webViewController!),
                    if (isWebViewLoading)
                      const Center(
                        child: CircularProgressIndicator(),
                      ),
                  ],
                ),
              ),
            )
          : SingleChildScrollView(
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
                              app.author,
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
                    if (!app.enabled && !isLoading) ...[
                      if (app.externalIntegration?.setupCompletedUrl?.isNotEmpty == true && app.externalIntegration?.authSteps.isNotEmpty == true)
                        Center(
                          child: Padding(
                            padding: const EdgeInsets.all(8.0),
                            child: AnimatedLoadingButton(
                              width: MediaQuery.of(context).size.width * 0.9,
                              text: 'Setup App',
                              onPressed: () async {
                                await Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (context) => BrowserPage(
                                      initialUrl: app.externalIntegration!.authSteps.first.url,
                                    ),
                                  ),
                                );
                                return;
                              },
                              color: Colors.blue,
                            ),
                          ),
                        ),
                      Center(
                        child: Padding(
                          padding: const EdgeInsets.all(8.0),
                          child: AnimatedLoadingButton(
                            width: MediaQuery.of(context).size.width * 0.9,
                            text: app.isPaid && !app.isUserPaid ? 'Subscribe' : 'Install App',
                            onPressed: () async {
                              if (app.isPaid && !app.isUserPaid && app.paymentLink != null && app.paymentLink!.isNotEmpty) {
                                _checkPaymentStatus(app.id);
                                await launchUrl(Uri.parse(app.paymentLink!));
                              } else if (app.worksExternally()) {
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
                                        updateCheckboxValue: (value) {
                                          if (value != null) {
                                            setState(() {
                                              showInstallAppConfirmation = !value;
                                              SharedPreferencesUtil().showInstallAppConfirmation = !value;
                                            });
                                          }
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
                                await _toggleApp(app.id, true);
                              }
                            },
                            color: Colors.green,
                          ),
                        ),
                      ),
                    ],
                    if (app.enabled)
                      Center(
                        child: Padding(
                          padding: const EdgeInsets.all(8.0),
                          child: AnimatedLoadingButton(
                            width: MediaQuery.of(context).size.width * 0.9,
                            text: 'Uninstall App',
                            onPressed: () => _toggleApp(app.id, false),
                            color: Colors.red,
                          ),
                        ),
                      ),
                    InfoCardWidget(
                      onTap: () {
                        if (app.description.decodeString.characters.length > 200) {
                          routeToPage(
                              context, MarkdownViewer(title: 'About the App', markdown: app.description.decodeString));
                        }
                      },
                      title: 'About the App',
                      description: app.description,
                      showChips: true,
                      chips: app
                          .getCapabilitiesFromIds(context.read<AddAppProvider>().capabilities)
                          .map((e) => e.title)
                          .toList(),
                    ),
                    if (app.conversationPrompt != null)
                      InfoCardWidget(
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
                      ),
                    if (app.chatPrompt != null)
                      InfoCardWidget(
                        onTap: () {
                          if (app.chatPrompt!.decodeString.characters.length > 200) {
                            routeToPage(context,
                                MarkdownViewer(title: 'Chat Personality', markdown: app.chatPrompt!.decodeString));
                          }
                        },
                        title: 'Chat Personality',
                        description: app.chatPrompt!,
                        showChips: false,
                      ),
                    GestureDetector(
                      onTap: () {
                        if (app.reviews.isNotEmpty) {
                          routeToPage(context, ReviewsListPage(app: app));
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
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (!app.isOwner(SharedPreferencesUtil().uid) && (app.enabled || app.userReview != null))
                      AddReviewWidget(app: app),
                    if (!app.private)
                      AppAnalyticsWidget(
                          installs: app.installs, moneyMade: app.isPaid ? ((app.price ?? 0) * app.installs) : 0),
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
    try {
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
        if (mounted) {
          setState(() {
            app.enabled = isEnabled;
            appLoading = false;
          });
          initWebView();
        }
      } else {
        prefs.disableApp(appId);
        var res = await disableAppServer(appId);
        print(res);
        MixpanelManager().appDisabled(appId);
        if (mounted) {
          setState(() {
            app.enabled = isEnabled;
            appLoading = false;
            webViewController = null;
            isWebViewLoading = true;
          });
        }
      }
      context.read<AppProvider>().setApps();
    } catch (e) {
      debugPrint('Error toggling app: $e');
      if (mounted) {
        setState(() => appLoading = false);
      }
    }
    return;
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
                        const SizedBox(width: 8),
                        Text(
                          timeago.format(reviews[index].ratedAt),
                          style: const TextStyle(color: Color.fromARGB(255, 176, 174, 174), fontSize: 12),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      reviews[index].review.length > 100
                          ? '${reviews[index].review.characters.take(100).toString().decodeString.trim()}...'
                          : reviews[index].review.decodeString,
                      style: const TextStyle(color: Colors.white),
                    ),
                    const SizedBox(height: 6),
                    if (reviews[index].response.isNotEmpty)
                      Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Divider(color: Color.fromARGB(255, 92, 92, 92)),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Text(
                                'Response from $appAuthor',
                                style: const TextStyle(color: Colors.white, fontSize: 14),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                timeago.format(reviews[index].ratedAt),
                                style: const TextStyle(color: Color.fromARGB(255, 176, 174, 174), fontSize: 12),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            reviews[index].response.length > 100
                                ? '${reviews[index].response.characters.take(100).toString().decodeString.trim()}...'
                                : reviews[index].response.decodeString,
                            style: const TextStyle(color: Colors.white),
                          ),
                        ],
                      ),
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
