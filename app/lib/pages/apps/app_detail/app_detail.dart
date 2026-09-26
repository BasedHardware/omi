import 'dart:async';

import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:skeletonizer/skeletonizer.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/share_links.dart';
import 'package:omi/pages/apps/app_detail/reviews_list_page.dart';
import 'package:omi/pages/apps/app_detail/reviews_section.dart';
import 'package:omi/pages/apps/app_detail/app_summary.dart';
import 'package:omi/pages/apps/app_home_web_page.dart';
import 'package:omi/pages/apps/markdown_viewer.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/http/api/payment.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail_config.dart';
import 'package:omi/pages/apps/widgets/show_app_options_sheet.dart';
import 'widgets/capabilities_card.dart';
import 'widgets/info_card_widget.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/widgets/app_permissions_card.dart';
import 'package:omi/pages/apps/app_detail/widgets/app_preview_gallery.dart';
import 'package:omi/pages/apps/app_detail/widgets/app_setup_steps.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/ui/ui.dart';

class AppDetailPage extends StatefulWidget {
  final App app;
  final bool preventAutoOpenHomePage;

  const AppDetailPage({super.key, required this.app, this.preventAutoOpenHomePage = false});

  @override
  State<AppDetailPage> createState() => _AppDetailPageState();
}

class _AppDetailPageState extends State<AppDetailPage> {
  String? instructionsMarkdown;
  bool setupCompleted = false;
  bool appLoading = false;
  bool isLoading = false;
  bool chatButtonLoading = false;
  bool _reEnabling = false;
  Map<String, dynamic>? _subscriptionData;
  bool _isCancelingSubscription = false;
  Timer? _paymentCheckTimer;
  Timer? _setupCheckTimer;
  int _setupCheckGeneration = 0;
  int _markdownLoadGeneration = 0;
  late App app;
  final ScrollController _scrollController = ScrollController();
  final GlobalKey _reviewsSectionKey = GlobalKey();

  /// Safely launches a URL with fallback from in-app browser to external browser.
  /// Returns true if the URL was launched successfully, false otherwise.
  Future<bool> _launchUrlSafely(Uri uri) async {
    final supportsInAppBrowser = uri.scheme == 'http' || uri.scheme == 'https';

    try {
      if (supportsInAppBrowser) {
        await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
      } else {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
      return true;
    } catch (e) {
      Logger.warning('Failed to launch URL with in-app browser: $e');
      // Fall back to external browser
      try {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return true;
      } catch (e) {
        Logger.warning('Failed to launch URL with external browser: $e');
        if (mounted) {
          OmiFeedback.error(context, context.l10n.couldNotOpenUrl);
        }
        return false;
      }
    }
  }

  checkSetupCompleted({bool autoInstallIfCompleted = false}) {
    if (app.externalIntegration == null) {
      _setupCheckGeneration++;
      return;
    }
    // TODO: move check to backend
    final generation = ++_setupCheckGeneration;
    final requestedUrl = app.externalIntegration!.setupCompletedUrl;
    isAppSetupCompleted(requestedUrl).then((value) {
      if (!mounted) return;
      if (generation != _setupCheckGeneration) return;
      if (app.externalIntegration?.setupCompletedUrl != requestedUrl) return;

      setState(() => setupCompleted = value);

      if (autoInstallIfCompleted && value && !app.enabled) {
        _tryAutoInstallAfterSetup();
      }
    });
  }

  void _loadSetupInstructionsMarkdown() {
    final generation = ++_markdownLoadGeneration;
    final path = app.externalIntegration?.setupInstructionsFilePath;
    if (path == null || path.isEmpty || !path.contains('raw.githubusercontent.com')) {
      return;
    }

    final appId = app.id;
    getAppMarkdown(path).then((value) {
      if (!mounted) return;
      if (generation != _markdownLoadGeneration) return;
      if (app.externalIntegration?.setupInstructionsFilePath != path) return;

      value = value.replaceAll(
        '](assets/',
        '](https://raw.githubusercontent.com/BasedHardware/Omi/main/plugins/instructions/$appId/assets/',
      );
      setState(() => instructionsMarkdown = value);
    });
  }

  Future<void> _tryAutoInstallAfterSetup() async {
    if (!mounted) return;

    setState(() => appLoading = true);
    var prefs = SharedPreferencesUtil();
    var (enabled, _) = await enableAppServer(app.id);

    if (!mounted) return;

    if (enabled) {
      prefs.enableApp(app.id);
      PlatformManager.instance.analytics.appEnabled(app.id);
      context.read<AppProvider>().filterApps();

      setState(() {
        app.enabled = true;
        appLoading = false;
      });

      if (app.externalIntegration?.appHomeUrl?.isNotEmpty == true) {
        Future.delayed(const Duration(seconds: 1), () {
          if (mounted) {
            routeToPage(context, AppHomeWebPage(app: app));
          }
        });
      }
    } else {
      setState(() => appLoading = false);
    }
  }

  void setIsLoading(bool value) {
    if (mounted && isLoading != value) {
      setState(() => isLoading = value);
    }
  }

  Future<void> _loadSubscriptionData() async {
    if (widget.app.isPaid) {
      final subscriptionResponse = await getAppSubscription(widget.app.id);
      if (mounted) {
        setState(() {
          _subscriptionData = subscriptionResponse;
        });
      }
    }
  }

  Future<void> _cancelSubscription() async {
    setState(() => _isCancelingSubscription = true);

    try {
      final result = await cancelAppSubscription(widget.app.id);
      if (result != null && result['status'] == 'success') {
        // Track subscription cancellation
        PlatformManager.instance.analytics.appDetailSubscriptionCancelled(
          appId: widget.app.id,
          appName: widget.app.name,
        );

        await _loadSubscriptionData();

        if (mounted) OmiFeedback.confirm(context, context.l10n.subscriptionCancelledSuccessfully);
      } else {
        if (mounted) OmiFeedback.error(context, context.l10n.failedToCancelSubscription);
      }
    } catch (e) {
      if (mounted) OmiFeedback.error(context, context.l10n.errorWithMessage(readableError(e)));
    } finally {
      if (mounted) {
        setState(() => _isCancelingSubscription = false);
      }
    }
  }

  bool _hasActiveSubscription() {
    if (_subscriptionData == null || _subscriptionData!['subscription'] == null) {
      return false;
    }
    final subscription = _subscriptionData!['subscription'];
    return subscription['status'] == 'active' && subscription['cancel_at_period_end'] == false;
  }

  @override
  void initState() {
    app = widget.app;

    // Track app detail page viewed
    PlatformManager.instance.analytics.appDetailViewed(
      appId: app.id,
      appName: app.name,
      category: app.category,
      rating: app.ratingAvg,
      installs: app.installs,
      isInstalled: app.enabled,
    );

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Automatically open app home page if conditions are met
      if (!widget.preventAutoOpenHomePage && app.enabled && app.externalIntegration?.appHomeUrl?.isNotEmpty == true) {
        routeToPage(context, AppHomeWebPage(app: app));
      }
      // Load details
      await _refreshAppDetails();
    });
    if (app.worksExternally()) {
      checkSetupCompleted();
      _loadSetupInstructionsMarkdown();
    }

    super.initState();
  }

  Future<void> _refreshAppDetails() async {
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
    if (mounted) {
      context.read<AppProvider>().checkIsAppOwner(app.uid);
      context.read<AppProvider>().setIsAppPublicToggled(!app.private);
      if (app.isPaid) {
        _loadSubscriptionData();
      }
    }
  }

  void _onExternalIntegrationUpdated() {
    if (!app.worksExternally()) {
      _setupCheckGeneration++;
      _markdownLoadGeneration++;
      return;
    }
    checkSetupCompleted();
    _loadSetupInstructionsMarkdown();
  }

  void _applyProviderAppUpdate(App updatedApp) {
    setState(() {
      app = updatedApp;
    });
    _onExternalIntegrationUpdated();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Refresh app details when returning to this page (e.g., after updating)
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      // Check if app has been updated in the provider
      final appProvider = context.read<AppProvider>();
      final updatedApp = appProvider.apps.firstWhereOrNull((a) => a.id == app.id);
      if (updatedApp != null && hasAppDetailConfigChanged(app, updatedApp)) {
        // App was updated, refresh the details
        await _refreshAppDetails();
        _onExternalIntegrationUpdated();
      }
    });
  }

  @override
  void dispose() {
    _paymentCheckTimer?.cancel();
    _setupCheckTimer?.cancel();
    _scrollController.dispose();
    super.dispose();
  }

  Future _checkPaymentStatus(String appId) async {
    PlatformManager.instance.analytics.appPurchaseStarted(appId);
    _paymentCheckTimer = Timer.periodic(const Duration(seconds: 5), (timer) async {
      var prefs = SharedPreferencesUtil();
      if (mounted) {
        setState(() => appLoading = true);
      }

      var details = await getAppDetailsServer(appId);
      if (details != null && details['is_user_paid']) {
        var (enabled, _) = await enableAppServer(appId);
        if (enabled) {
          PlatformManager.instance.analytics.appPurchaseCompleted(appId);
          prefs.enableApp(appId);
          PlatformManager.instance.analytics.appEnabled(appId);

          if (!mounted) {
            timer.cancel();
            _paymentCheckTimer?.cancel();
            return;
          }

          context.read<AppProvider>().filterApps();
          setState(() {
            app.isUserPaid = true;
            app.enabled = true;
            appLoading = false;
          });
          timer.cancel();
          _paymentCheckTimer?.cancel();
        } else {
          Logger.debug('Payment not made yet');
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    // Watch for changes to the app in AppProvider and update local state
    return Consumer<AppProvider>(
      builder: (context, appProvider, child) {
        // Check if app has been updated in the provider
        final updatedApp = appProvider.apps.firstWhereOrNull((a) => a.id == app.id);
        if (updatedApp != null && hasAppDetailConfigChanged(app, updatedApp)) {
          // Update local app state when provider's app changes
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              _applyProviderAppUpdate(updatedApp);
            }
          });
        }

        final l10n = context.l10n;
        bool isIntegration = app.worksExternally();
        bool hasSetupInstructions =
            isIntegration && app.externalIntegration?.setupInstructionsFilePath?.isNotEmpty == true;
        bool hasAuthSteps = isIntegration && app.externalIntegration?.authSteps.isNotEmpty == true;
        return Scaffold(
          appBar: AppBar(
            elevation: 0,
            automaticallyImplyLeading: false,
            leading: const Center(child: OmiBackButton.circled()),
            actions: [
              if (app.enabled && app.worksWithChat())
                OmiIconButton.filled(
                  icon: chatButtonLoading
                      ? const OmiSpinner(size: OmiSpinnerSize.small)
                      : const FaIcon(FontAwesomeIcons.solidComments, size: 16),
                  label: l10n.chatWithApp(app.name.decodeString),
                  onPressed: chatButtonLoading ? null : _openChatWithApp,
                ),
              if (app.enabled && app.externalIntegration?.appHomeUrl?.isNotEmpty == true)
                OmiIconButton.filled(
                  icon: const FaIcon(FontAwesomeIcons.gear, size: 16),
                  label: l10n.appSettingsLabel(app.name.decodeString),
                  onPressed: () => routeToPage(context, AppHomeWebPage(app: app)),
                ),
              if (!isLoading && !app.private)
                Builder(
                  builder: (context) => OmiIconButton.filled(
                    icon: const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16),
                    label: l10n.share,
                    onPressed: () => _shareApp(context),
                  ),
                ),
              if (appProvider.isAppOwner && !isLoading)
                OmiIconButton.filled(
                  icon: const FaIcon(FontAwesomeIcons.penToSquare, size: 16),
                  label: l10n.appOptions,
                  onPressed: () => showAppOptionsSheet(context, app),
                ),
              const SizedBox(width: OmiSpacing.xxs),
            ],
          ),
          body: SingleChildScrollView(
            controller: _scrollController,
            child: Skeletonizer(
              enabled: isLoading,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 20),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(width: 20),
                      CachedNetworkImage(
                        imageUrl: app.getImageUrl(),
                        imageBuilder: (context, imageProvider) => Container(
                          width: 108,
                          height: 108,
                          decoration: BoxDecoration(
                            shape: BoxShape.rectangle,
                            borderRadius: OmiRadius.xlAll,
                            image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                          ),
                        ),
                        placeholder: (context, url) => const SizedBox.square(
                          dimension: 108,
                          child: Center(child: OmiSpinner()),
                        ),
                        errorWidget: (context, url, error) => const FaIcon(FontAwesomeIcons.circleExclamation),
                      ),
                      const SizedBox(width: 20),
                      Expanded(
                        child: AppDetailSummary(
                          name: app.name.decodeString,
                          author: app.author.decodeString,
                          official: app.official,
                          ratingCount: app.ratingCount,
                          rating: app.getRatingAvg(),
                          installs: app.installs,
                          onRatingTap: () {
                            if (app.ratingCount > 0 && _reviewsSectionKey.currentContext != null) {
                              Scrollable.ensureVisible(
                                _reviewsSectionKey.currentContext!,
                                duration: const Duration(milliseconds: 300),
                                curve: Curves.easeInOut,
                              );
                            }
                          },
                          action: _buildPrimaryAction(l10n),
                        ),
                      ),
                      const SizedBox(width: 20),
                    ],
                  ),
                  const SizedBox(height: 16),
                  if (!isLoading && !app.private && app.isPaid && _hasActiveSubscription() && !appProvider.isAppOwner)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.md, OmiSpacing.lg, 0),
                      child: OmiButton.destructive(
                        label: l10n.cancelSubscriptionButton,
                        isLoading: _isCancelingSubscription,
                        expand: true,
                        onPressed: () {
                          _confirmCancelSubscription();
                        },
                      ),
                    ),
                  if ((app.isUnderReview() || app.private) && !app.isOwner(SharedPreferencesUtil().uid))
                    AppDetailNotice(icon: FontAwesomeIcons.circleInfo, text: l10n.betaTesterMessage),
                  if (app.isUnderReview() && !app.private && app.isOwner(SharedPreferencesUtil().uid))
                    AppDetailNotice(icon: FontAwesomeIcons.circleInfo, text: l10n.appUnderReviewMessage),
                  if (app.isRejected())
                    AppDetailNotice(icon: FontAwesomeIcons.circleExclamation, text: l10n.appRejectedMessage),
                  if (app.isDisabled()) _buildDisabledNotice(),
                  const SizedBox(height: OmiSpacing.xl),
                  if (hasAuthSteps)
                    AppSetupSteps(
                      steps: app.externalIntegration!.authSteps,
                      completed: setupCompleted,
                      onStepTap: (step) async {
                        final uri = Uri.tryParse(appSetupUrlWithUid(step.url, SharedPreferencesUtil().uid));
                        if (uri == null) {
                          OmiFeedback.error(context, l10n.invalidIntegrationUrl);
                          return;
                        }
                        await _launchUrlSafely(uri);
                        checkSetupCompleted(autoInstallIfCompleted: true);
                      },
                    ),
                  if (!hasAuthSteps && hasSetupInstructions)
                    ListTile(
                      onTap: () async {
                        await _openSetupInstructions();
                        checkSetupCompleted();
                      },
                      trailing: const Padding(
                        padding: EdgeInsets.only(right: OmiSpacing.sm),
                        child: FaIcon(FontAwesomeIcons.chevronRight, size: 20, color: OmiColors.textTertiary),
                      ),
                      title: Text(l10n.integrationInstructions, style: OmiType.headline),
                    ),
                  if (app.thumbnailUrls.isNotEmpty)
                    AppPreviewGallery(
                      imageUrls: app.thumbnailUrls,
                      onImageOpened: (index) => PlatformManager.instance.analytics.appDetailPreviewImageViewed(
                        appId: app.id,
                        imageIndex: index,
                      ),
                    ),
                  InfoCardWidget(
                    onTap: () {
                      if (app.description.decodeString.characters.length > 200) {
                        routeToPage(
                          context,
                          MarkdownViewer(title: l10n.descriptionLabel, markdown: app.description.decodeString),
                        );
                      }
                    },
                    title: l10n.descriptionLabel,
                    description: app.description,
                    showChips: false,
                  ),
                  Builder(
                    builder: (context) {
                      final allCapabilities = context.read<AddAppProvider>().capabilities;
                      var capabilitiesList = app.getCapabilitiesFromIds(allCapabilities);

                      // If app has chat tools, add chat capability if not already present
                      if (app.chatTools != null && app.chatTools!.isNotEmpty) {
                        final hasChatCapability = capabilitiesList.any((cap) => cap.id == 'chat');
                        if (!hasChatCapability) {
                          final chatCapability = allCapabilities.firstWhereOrNull((cap) => cap.id == 'chat');
                          if (chatCapability != null) {
                            capabilitiesList = [...capabilitiesList, chatCapability];
                          }
                        }

                        // Add "Push to Talk" capability
                        final hasPushToTalkCapability = capabilitiesList.any((cap) => cap.id == 'push_to_talk');
                        if (!hasPushToTalkCapability) {
                          capabilitiesList = [
                            ...capabilitiesList,
                            AppCapability(title: context.l10n.pushToTalk, id: 'push_to_talk'),
                          ];
                        }
                      }

                      // Filter out external_integration capability
                      capabilitiesList = capabilitiesList.where((cap) => cap.id != 'external_integration').toList();

                      return CapabilitiesCard(capabilities: capabilitiesList);
                    },
                  ),
                  AppChatToolsCard(app: app),
                  app.conversationPrompt != null
                      ? InfoCardWidget(
                          onTap: () {
                            routeToPage(
                              context,
                              MarkdownViewer(
                                title: context.l10n.summaryPrompt,
                                markdown: app.conversationPrompt!.decodeString,
                              ),
                            );
                          },
                          title: context.l10n.summaryPrompt,
                          description: app.conversationPrompt!,
                          showChips: false,
                          maxLines: 3,
                        )
                      : const SizedBox.shrink(),
                  app.chatPrompt != null
                      ? InfoCardWidget(
                          onTap: () {
                            routeToPage(
                              context,
                              MarkdownViewer(
                                title: context.l10n.chatPersonality,
                                markdown: app.chatPrompt!.decodeString,
                              ),
                            );
                          },
                          title: context.l10n.chatPersonality,
                          description: app.chatPrompt!,
                          showChips: false,
                          maxLines: 3,
                        )
                      : const SizedBox.shrink(),
                  AppPermissionsCard(app: app),
                  Builder(
                    builder: (context) {
                      final canAddReview = !app.isOwner(SharedPreferencesUtil().uid) && app.enabled;
                      return (app.ratingCount > 0 || app.reviews.isNotEmpty || canAddReview)
                          ? GestureDetector(
                              key: _reviewsSectionKey,
                              onTap: () {
                                if (app.reviews.isNotEmpty) {
                                  PlatformManager.instance.analytics.appDetailReviewsOpened(
                                    appId: app.id,
                                    reviewCount: app.reviews.length,
                                  );
                                  routeToPage(context, ReviewsListPage(app: app));
                                }
                              },
                              child: AppDetailSectionCard(
                                title: l10n.ratingsAndReviews,
                                trailing: app.reviews.isNotEmpty
                                    ? const ExcludeSemantics(child: Icon(Icons.arrow_forward, size: 20))
                                    : null,
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    const SizedBox(height: OmiSpacing.xxs),
                                    RatingDistributionWidget(
                                      ratingAvg: app.ratingAvg ?? 0,
                                      ratingCount: app.ratingCount,
                                      reviews: app.reviews,
                                    ),
                                    const SizedBox(height: OmiSpacing.md),
                                    RecentReviewsSection(
                                      reviews:
                                          app.reviews.sorted((a, b) => b.ratedAt.compareTo(a.ratedAt)).take(3).toList(),
                                      userReview: app.userReview,
                                      app: app,
                                      onReviewUpdated: () => setState(() {}),
                                    ),
                                  ],
                                ),
                              ),
                            )
                          : const SizedBox.shrink();
                    },
                  ),
                  const SizedBox(height: 60),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  /// Shown when the backend has latched `disabled` on the app.
  ///
  /// Nothing surfaced this state before, so a disabled app read as healthy here
  /// while every install failed, and the owner had no control that could clear it.
  Widget _buildDisabledNotice() {
    final isOwner = app.isOwner(SharedPreferencesUtil().uid);
    final reason = app.disabledReason == 'webhook_failures'
        ? context.l10n.appDisabledWebhookFailures
        : context.l10n.appDisabledGeneric;
    final when = app.disabledAt != null && app.disabledAt!.length >= 10
        ? ' ${context.l10n.appDisabledOn(app.disabledAt!.substring(0, 10))}'
        : '';
    final lastError = app.disabledError != null && app.disabledError!.isNotEmpty
        ? ' ${context.l10n.appDisabledLastError(app.disabledError!)}'
        : '';

    return Column(
      children: [
        AppDetailNotice(
          icon: FontAwesomeIcons.triangleExclamation,
          text: '${context.l10n.appDisabledTitle} $reason$when$lastError',
        ),
        if (isOwner) ...[
          const SizedBox(height: OmiSpacing.sm),
          SizedBox(
            width: MediaQuery.sizeOf(context).width * 0.78,
            child: Text(
              context.l10n.appDisabledOwnerHint,
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ),
          const SizedBox(height: 10),
          OmiButton.secondary(
            label: context.l10n.appReEnable,
            size: OmiButtonSize.compact,
            isLoading: _reEnabling,
            onPressed: _reEnabling ? null : _reEnableApp,
          ),
        ],
      ],
    );
  }

  Future<void> _reEnableApp() async {
    setState(() => _reEnabling = true);
    final (ok, detail) = await reEnableAppServer(app.id);
    if (!mounted) return;
    setState(() => _reEnabling = false);

    if (ok) {
      setState(() {
        app.disabled = false;
        app.disabledReason = null;
        app.disabledAt = null;
        app.disabledError = null;
      });
      context.read<AppProvider>().getApps();
      return;
    }

    // The rejection names the URL to fix, so it is shown verbatim rather than
    // replaced with a generic retry prompt.
    showOmiAlert(
      context,
      title: context.l10n.appReEnableFailedTitle,
      message: detail.isNotEmpty ? detail : context.l10n.appReEnableFailedBody,
    );
  }

  Future<void> _navigateToSetup() async {
    final authSteps = app.externalIntegration?.authSteps ?? const [];
    if (app.worksExternally() && authSteps.isNotEmpty) {
      final uri = Uri.tryParse(appSetupUrlWithUid(authSteps.first.url, SharedPreferencesUtil().uid));
      if (uri == null) {
        if (mounted) OmiFeedback.error(context, context.l10n.invalidIntegrationUrl);
        return;
      }
      await _launchUrlSafely(uri);
    } else {
      await _openSetupInstructions();
    }
    _startSetupCompletionCheck();
  }

  /// Opens an integration's setup instructions: rendered markdown, an external link, or inline text.
  Future<void> _openSetupInstructions() async {
    final integration = app.externalIntegration;
    final path = integration?.setupInstructionsFilePath;
    if (integration == null || path == null || path.isEmpty) return;
    final title = context.l10n.setupInstructions;
    if (path.contains('raw.githubusercontent.com')) {
      await routeToPage(context, MarkdownViewer(title: title, markdown: instructionsMarkdown ?? ''));
    } else if (integration.isInstructionsUrl == true) {
      final uri = Uri.tryParse(path);
      if (uri == null) {
        OmiFeedback.error(context, context.l10n.invalidSetupInstructionsUrl);
        return;
      }
      await _launchUrlSafely(uri);
    } else {
      await routeToPage(context, MarkdownViewer(title: title, markdown: path));
    }
  }

  void _startSetupCompletionCheck() {
    // Cancel any existing timer
    _setupCheckTimer?.cancel();

    _setupCheckTimer = Timer.periodic(const Duration(seconds: 3), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }

      checkSetupCompleted();

      // Stop checking after 5 minutes
      if (timer.tick > 100) {
        timer.cancel();
      }

      // Stop checking if app becomes enabled
      if (app.enabled) {
        timer.cancel();
      }
    });
  }

  Future<void> _enableApp(String appId) async {
    var prefs = SharedPreferencesUtil();
    setState(() => appLoading = true);

    var (enabled, detail) = await enableAppServer(appId);

    if (!mounted) return;

    if (!enabled) {
      // Setup is only the right guess when the backend gave no reason. A
      // disabled app used to land here and get sent to setup instructions,
      // so the developer re-ran a setup that was never the problem.
      if (app.worksExternally() && detail.isEmpty) {
        setState(() => appLoading = false);
        await _navigateToSetup();
        return;
      } else {
        showOmiAlert(
          context,
          title: context.l10n.errorActivatingApp,
          message: detail.isNotEmpty ? detail : context.l10n.issueActivatingApp,
        );
        setState(() => appLoading = false);
        return;
      }
    }

    prefs.enableApp(appId);
    PlatformManager.instance.analytics.appEnabled(appId);
    context.read<AppProvider>().filterApps();

    setState(() {
      app.enabled = true;
      appLoading = false;
    });
    if (app.worksExternally()) {
      checkSetupCompleted();
    }

    // Automatically open app home page after installation if available
    if (app.externalIntegration?.appHomeUrl?.isNotEmpty == true) {
      Future.delayed(const Duration(seconds: 1), () {
        if (mounted) {
          routeToPage(context, AppHomeWebPage(app: app));
        }
      });
    }
  }

  /// Disable is immediate with a 5 s Undo (docs/ux-contract.md §4); re-enabling needs no setup.
  Future<void> _disableApp() async {
    await disableAppWithUndo(
      context,
      app,
      onHidden: () => setState(() => app.enabled = false),
      onRestored: () {
        if (mounted) setState(() => app.enabled = true);
      },
    );
  }

  /// Enable (after the data-access question for external apps), Subscribe, or Disable.
  Widget _buildPrimaryAction(AppLocalizations l10n) {
    if (isLoading) {
      return OmiButton(label: l10n.enable, size: OmiButtonSize.compact, isLoading: true, onPressed: null);
    }
    // Handlers return nothing to the button on purpose: it spins for [appLoading] (the server
    // call), not while a question or an Undo toast is up.
    if (app.enabled) {
      return OmiButton.secondary(
        label: l10n.disable,
        size: OmiButtonSize.compact,
        onPressed: () {
          _disableApp();
        },
      );
    }
    if (app.isPaid && !app.isUserPaid) {
      return OmiButton(
        label: l10n.subscribe,
        size: OmiButtonSize.compact,
        isLoading: appLoading,
        onPressed: () {
          _subscribe();
        },
      );
    }
    return OmiButton(
      label: l10n.enable,
      size: OmiButtonSize.compact,
      isLoading: appLoading,
      onPressed: () {
        _enableWithConsent();
      },
    );
  }

  Future<void> _enableWithConsent() async {
    if (!await confirmAppDataAccess(context, app)) return;
    if (mounted) await _enableApp(app.id);
  }

  Future<void> _subscribe() async {
    PlatformManager.instance.analytics.appDetailSubscribeClicked(appId: app.id, appName: app.name);
    final link = app.paymentLink;
    if (link == null || link.isEmpty) {
      await _enableApp(app.id);
      return;
    }
    final uri = Uri.tryParse(link);
    if (uri == null) {
      OmiFeedback.error(context, context.l10n.invalidPaymentUrl);
      return;
    }
    _checkPaymentStatus(app.id);
    await _launchUrlSafely(uri);
  }

  Future<void> _confirmCancelSubscription() async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.cancelSubscriptionQuestion,
      message: l10n.cancelSubscriptionKeepAccessMessage,
      confirmLabel: l10n.cancelSubscriptionButton,
      cancelLabel: l10n.keepSubscription,
      destructive: true,
    );
    if (confirmed) await _cancelSubscription();
  }

  Future<void> _openChatWithApp() async {
    setState(() => chatButtonLoading = true);
    try {
      final appProvider = context.read<AppProvider>();
      final messageProvider = context.read<MessageProvider>();
      appProvider.setSelectedChatAppId(app.id);
      await messageProvider.refreshMessages();
      final selectedApp = await appProvider.getAppFromId(app.id);
      if (messageProvider.messages.isEmpty) {
        messageProvider.sendInitialAppMessage(selectedApp);
      }
      PlatformManager.instance.analytics.appDetailChatClicked(appId: app.id, appName: app.name);
      if (mounted) await routeToPage(context, const ChatPage(isPivotBottom: false));
    } finally {
      if (mounted) setState(() => chatButtonLoading = false);
    }
  }

  Future<void> _shareApp(BuildContext buttonContext) async {
    PlatformManager.instance.analytics.track('App Shared', properties: {'appId': app.id});
    PlatformManager.instance.analytics.appDetailShared(appId: app.id, appName: app.name);
    // iPad needs the share button's position for the popover.
    final box = buttonContext.findRenderObject() as RenderBox?;
    final origin = box != null ? box.localToGlobal(Offset.zero) & box.size : null;
    await SharePlus.instance
        .share(ShareParams(text: appShareUrl(app.id), subject: app.name, sharePositionOrigin: origin));
  }
}
