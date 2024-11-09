import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/apps/analytics.dart';
import 'package:friend_private/pages/apps/markdown_viewer.dart';
import 'package:friend_private/pages/apps/update_app.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/animated_loading_button.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../backend/schema/app.dart';

class ShowAppOptionsSheet extends StatelessWidget {
  final App app;
  const ShowAppOptionsSheet({super.key, required this.app});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: const BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      child: Consumer<AppProvider>(builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: Text(
                app.name,
                style: Theme.of(context).textTheme.labelLarge,
              ),
              leading: const Icon(Icons.apps),
              trailing: IconButton(
                icon: const Icon(Icons.cancel_outlined),
                onPressed: () {
                  Navigator.of(context).pop(true);
                },
              ),
            ),
            Card(
              shape: const RoundedRectangleBorder(
                borderRadius: BorderRadius.all(Radius.circular(8)),
              ),
              child: ListTile(
                title: const Text(
                  'Keep App Public',
                  style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                ),
                trailing: Switch(
                  value: provider.appPublicToggled,
                  onChanged: (value) {
                    if (value) {
                      showDialog(
                        context: context,
                        builder: (c) => getDialog(
                          context,
                          () => Navigator.pop(context),
                          () {
                            provider.toggleAppPublic(app.id, value);
                            Navigator.pop(context);
                            Navigator.pop(context);
                            Navigator.pop(context);
                          },
                          'Make App Public?',
                          'If you make the app public, it can be used by everyone',
                          okButtonText: 'Confirm',
                        ),
                      );
                    } else {
                      showDialog(
                        context: context,
                        builder: (c) => getDialog(
                          context,
                          () => Navigator.pop(context),
                          () {
                            provider.toggleAppPublic(app.id, value);
                            Navigator.pop(context);
                            Navigator.pop(context);
                            Navigator.pop(context);
                          },
                          'Make App Private?',
                          'If you make the app private now, it will stop working for everyone and will be visible only to you',
                          okButtonText: 'Confirm',
                        ),
                      );
                    }
                  },
                ),
              ),
            ),
            Card(
              shape: const RoundedRectangleBorder(
                borderRadius: BorderRadius.all(Radius.circular(8)),
              ),
              child: Column(
                children: [
                  ListTile(
                    title: const Text('Update App Details'),
                    leading: const Icon(Icons.edit),
                    onTap: () {
                      routeToPage(
                          context,
                          UpdateAppPage(
                            app: app,
                          ));
                    },
                  ),
                  ListTile(
                    title: const Text('Delete App'),
                    leading: const Icon(
                      Icons.delete,
                    ),
                    onTap: () {
                      showDialog(
                        context: context,
                        builder: (c) => getDialog(
                          context,
                          () => Navigator.pop(context),
                          () {
                            provider.deleteApp(app.id);
                            Navigator.pop(context);
                            Navigator.pop(context);
                            Navigator.pop(context);
                          },
                          'Delete App',
                          'Are you sure you want to delete this app? This action cannot be undone.',
                          okButtonText: 'Confirm',
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 40),
          ],
        );
      }),
    );
  }
}

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
      getAppMarkdown(widget.app.externalIntegration!.setupInstructionsFilePath).then((value) {
        value = value.replaceAll(
          '](assets/',
          '](https://raw.githubusercontent.com/BasedHardware/Omi/main/plugins/instructions/${widget.app.id}/assets/',
        );
        setState(() => instructionsMarkdown = value);
      });
      checkSetupCompleted();
    }

    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    bool isMemoryPrompt = widget.app.worksWithMemories();
    bool isChatPrompt = widget.app.worksWithChat();
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
                      // open bottom sheet
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
                          onPressed: () => _toggleApp(widget.app.id, true),
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
              widget.app.isUnderReview() && !widget.app.private
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
              GestureDetector(
                onTap: () {
                  if (widget.app.description.decodeString.characters.length > 200) {
                    routeToPage(
                        context, MarkdownViewer(title: 'About the App', markdown: widget.app.description.decodeString));
                  }
                },
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16.0),
                  margin: const EdgeInsets.only(left: 6.0, right: 6.0, top: 12, bottom: 6),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Text('About the App', style: TextStyle(color: Colors.white, fontSize: 14)),
                          const Spacer(),
                          widget.app.description.decodeString.characters.length > 200
                              ? const Icon(
                                  Icons.arrow_forward,
                                  size: 20,
                                )
                              : const SizedBox.shrink(),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Text(
                        widget.app.description.decodeString.characters.length > 200
                            ? '${widget.app.description.decodeString.characters.take(200).toString().trim()}...'
                            : widget.app.description.decodeString,
                        style: const TextStyle(color: Colors.grey, fontSize: 15, height: 1.4),
                      ),
                    ],
                  ),
                ),
              ),
              widget.app.memoryPrompt != null
                  ? GestureDetector(
                      onTap: () {
                        if (widget.app.memoryPrompt!.decodeString.characters.length > 200) {
                          routeToPage(context,
                              MarkdownViewer(title: 'Memory Prompt', markdown: widget.app.memoryPrompt!.decodeString));
                        }
                      },
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16.0),
                        margin: const EdgeInsets.only(left: 6.0, right: 6.0, top: 10, bottom: 6),
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: BorderRadius.circular(16.0),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Text('Memory Prompt', style: TextStyle(color: Colors.white, fontSize: 14)),
                                const Spacer(),
                                widget.app.memoryPrompt!.characters.length > 200
                                    ? const Icon(
                                        Icons.arrow_forward,
                                        size: 20,
                                      )
                                    : const SizedBox.shrink(),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Text(
                              widget.app.memoryPrompt!.decodeString.characters.length > 200
                                  ? '${widget.app.memoryPrompt!.decodeString.characters.take(200).toString().trim()}...'
                                  : widget.app.memoryPrompt!.decodeString,
                              style: const TextStyle(color: Colors.grey, fontSize: 15, height: 1.4),
                            ),
                          ],
                        ),
                      ),
                    )
                  : const SizedBox.shrink(),
              widget.app.chatPrompt != null
                  ? GestureDetector(
                      onTap: () {
                        if (widget.app.chatPrompt!.decodeString.characters.length > 200) {
                          routeToPage(context,
                              MarkdownViewer(title: 'Chat Prompt', markdown: widget.app.chatPrompt!.decodeString));
                        }
                      },
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16.0),
                        margin: const EdgeInsets.only(left: 6.0, right: 6.0, top: 10, bottom: 6),
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: BorderRadius.circular(16.0),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Text('Chat Personality', style: TextStyle(color: Colors.white, fontSize: 14)),
                                const Spacer(),
                                widget.app.chatPrompt!.characters.length > 200
                                    ? const Icon(
                                        Icons.arrow_forward,
                                        size: 20,
                                      )
                                    : const SizedBox.shrink(),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Text(
                              widget.app.chatPrompt!.decodeString.characters.length > 200
                                  ? '${widget.app.chatPrompt!.decodeString.characters.take(200).toString().trim()}...'
                                  : widget.app.chatPrompt!.decodeString,
                              style: const TextStyle(color: Colors.grey, fontSize: 15, height: 1.4),
                            ),
                          ],
                        ),
                      ),
                    )
                  : const SizedBox.shrink(),
              // isIntegration ? const SizedBox(height: 16) : const SizedBox.shrink(),
              // widget.plugin.worksExternally() ? const SizedBox(height: 16) : const SizedBox.shrink(),
              const SizedBox(height: 80),
              Divider(
                color: Colors.grey.shade300,
                height: 1,
              ),
              const SizedBox(height: 32),
              Row(
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      widget.app.userReview?.score == null ? 'Rate App:' : 'Your rating:',
                      style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 0),
                    child: RatingBar.builder(
                      initialRating: widget.app.userReview?.score ?? 0,
                      minRating: 1,
                      direction: Axis.horizontal,
                      allowHalfRating: true,
                      itemCount: 5,
                      itemSize: 24,
                      itemPadding: const EdgeInsets.symmetric(horizontal: 2),
                      itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.deepPurple),
                      maxRating: 5.0,
                      onRatingUpdate: (rating) {
                        final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                        if (connectivityProvider.isConnected) {
                          reviewApp(widget.app.id, rating);
                          bool hadReview = widget.app.userReview != null;
                          if (!hadReview) widget.app.ratingCount += 1;
                          widget.app.userReview = AppReview(
                            uid: SharedPreferencesUtil().uid,
                            ratedAt: DateTime.now(),
                            review: '',
                            score: rating,
                          );
                          var appsList = SharedPreferencesUtil().appsList;
                          var index = appsList.indexWhere((element) => element.id == widget.app.id);
                          appsList[index] = widget.app;
                          SharedPreferencesUtil().appsList = appsList;
                          MixpanelManager().appRated(widget.app.id.toString(), rating);
                          debugPrint('Refreshed apps list.');
                          // TODO: refresh ratings on app
                          setState(() {});
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                            content: Text("Can't rate app without internet connection."),
                          ));
                        }
                      },
                    ),
                  ),
                ],
              ),
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
              const SizedBox(height: 16),
            ],
          ),
        ));
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
    setState(() => widget.app.enabled = isEnabled);
    setState(() => appLoading = false);
  }
}
