import 'dart:async';

import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
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
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/animated_loading_button.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/http/api/payment.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/show_app_options_sheet.dart';
import 'widgets/capabilities_card.dart';
import 'widgets/info_card_widget.dart';

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
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.couldNotOpenUrl)));
        }
        return false;
      }
    }
  }

  checkSetupCompleted({bool autoInstallIfCompleted = false}) {
    if (app.externalIntegration == null) return;
    // TODO: move check to backend
    isAppSetupCompleted(app.externalIntegration!.setupCompletedUrl).then((value) {
      if (mounted) {
        setState(() => setupCompleted = value);

        if (autoInstallIfCompleted && value && !app.enabled) {
          _tryAutoInstallAfterSetup();
        }
      }
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
            Navigator.push(context, MaterialPageRoute(builder: (context) => AppHomeWebPage(app: app)));
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

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(context.l10n.subscriptionCancelledSuccessfully), backgroundColor: Colors.green),
          );
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(context.l10n.failedToCancelSubscription), backgroundColor: Colors.red));
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.errorWithMessage(readableError(e))), backgroundColor: Colors.red),
        );
      }
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
        Navigator.push(context, MaterialPageRoute(builder: (context) => AppHomeWebPage(app: app)));
      }
      // Load details
      await _refreshAppDetails();
    });
    if (app.worksExternally()) {
      checkSetupCompleted();
      if (app.externalIntegration!.setupInstructionsFilePath?.isNotEmpty == true) {
        if (app.externalIntegration!.setupInstructionsFilePath?.contains('raw.githubusercontent.com') == true) {
          getAppMarkdown(app.externalIntegration!.setupInstructionsFilePath ?? '').then((value) {
            value = value.replaceAll(
              '](assets/',
              '](https://raw.githubusercontent.com/BasedHardware/Omi/main/plugins/instructions/${app.id}/assets/',
            );
            if (mounted) setState(() => instructionsMarkdown = value);
          });
        }
      }
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

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Refresh app details when returning to this page (e.g., after updating)
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      // Check if app has been updated in the provider
      final appProvider = context.read<AppProvider>();
      final updatedApp = appProvider.apps.firstWhereOrNull((a) => a.id == app.id);
      if (updatedApp != null) {
        // Compare critical fields to detect if app was updated
        final appHomeUrlChanged = updatedApp.externalIntegration?.appHomeUrl != app.externalIntegration?.appHomeUrl;
        final nameChanged = updatedApp.name != app.name;
        final descriptionChanged = updatedApp.description != app.description;

        if (appHomeUrlChanged || nameChanged || descriptionChanged) {
          // App was updated, refresh the details
          await _refreshAppDetails();
        }
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

  Widget _buildPermissionsCard(App app) {
    if (!app.worksExternally()) {
      return const SizedBox.shrink();
    }

    final actions = app.externalIntegration?.actions ?? [];
    final trigger = app.externalIntegration?.getTriggerOnString();

    final List<_PermissionItem> permissionItems = [];

    // Read permissions
    if (actions.any((a) => a.action == 'read_conversations')) {
      permissionItems.add(
        _PermissionItem(
          title: context.l10n.permissionReadConversations,
          type: context.l10n.permissionTypeAccess,
          description: context.l10n.permissionDescReadConversations,
        ),
      );
    }
    if (actions.any((a) => a.action == 'read_memories')) {
      permissionItems.add(
        _PermissionItem(
          title: context.l10n.permissionReadMemories,
          type: context.l10n.permissionTypeAccess,
          description: context.l10n.permissionDescReadMemories,
        ),
      );
    }
    if (actions.any((a) => a.action == 'read_tasks')) {
      permissionItems.add(
        _PermissionItem(
          title: context.l10n.permissionReadTasks,
          type: context.l10n.permissionTypeAccess,
          description: context.l10n.permissionDescReadTasks,
        ),
      );
    }

    // Create permissions
    if (actions.any((a) => a.action == 'create_conversation')) {
      permissionItems.add(
        _PermissionItem(
          title: context.l10n.permissionCreateConversations,
          type: context.l10n.permissionTypeCreate,
          description: context.l10n.permissionDescCreateConversations,
        ),
      );
    }
    if (actions.any((a) => a.action == 'create_facts')) {
      permissionItems.add(
        _PermissionItem(
          title: context.l10n.permissionCreateMemories,
          type: context.l10n.permissionTypeCreate,
          description: context.l10n.permissionDescCreateMemories,
        ),
      );
    }

    // Trigger
    if (trigger != null && trigger != 'Unknown') {
      final displayTrigger = trigger == 'Transcript Segment Processed' ? context.l10n.realtimeListening : trigger;
      permissionItems.add(
        _PermissionItem(
          title: displayTrigger,
          type: context.l10n.permissionTypeTrigger,
          description: 'This app runs automatically when: $displayTrigger',
        ),
      );
    }

    if (permissionItems.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16.0),
      margin: EdgeInsets.only(
        left: MediaQuery.of(context).size.width * 0.05,
        right: MediaQuery.of(context).size.width * 0.05,
        top: 12,
        bottom: 6,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25).withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.permissionsAndTriggers,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 18),
          ...permissionItems.asMap().entries.map((entry) {
            final permission = entry.value;
            final isLast = entry.key == permissionItems.length - 1;
            return _buildPermissionItem(permission, isLast);
          }).toList(),
        ],
      ),
    );
  }

  Widget _buildPermissionItem(_PermissionItem permission, bool isLast) {
    return Container(
      margin: EdgeInsets.only(bottom: isLast ? 0 : 8),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: _getPermissionTypeColor(permission.type).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              permission.type,
              style: TextStyle(
                color: _getPermissionTypeColor(permission.type).withValues(alpha: 0.8),
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              permission.title,
              style: const TextStyle(color: Colors.grey, fontSize: 14, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }

  Color _getPermissionTypeColor(String type) {
    switch (type.toLowerCase()) {
      case 'access':
        return Colors.green;
      case 'create':
        return Colors.orange;
      case 'trigger':
        return Colors.blue;
      default:
        return Colors.blue;
    }
  }

  /// Converts snake_case to Title Case (e.g., "send_slack_message" -> "Send Slack Message")
  String _formatToolName(String name) {
    return name
        .split('_')
        .map((word) => word.isNotEmpty ? '${word[0].toUpperCase()}${word.substring(1).toLowerCase()}' : '')
        .join(' ');
  }

  Widget _buildChatToolsCard(App app) {
    if (app.chatTools == null || app.chatTools!.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16.0),
      margin: EdgeInsets.only(
        left: MediaQuery.of(context).size.width * 0.05,
        right: MediaQuery.of(context).size.width * 0.05,
        top: 12,
        bottom: 6,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25).withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.chatFeatures,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
          Wrap(spacing: 12, runSpacing: 12, children: app.chatTools!.map((tool) => _buildChatToolChip(tool)).toList()),
        ],
      ),
    );
  }

  Widget _buildChatToolChip(ChatTool tool) {
    const color = Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(12)),
      child: Text(
        _formatToolName(tool.name),
        style: const TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w500),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Watch for changes to the app in AppProvider and update local state
    return Consumer<AppProvider>(
      builder: (context, appProvider, child) {
        // Check if app has been updated in the provider
        final updatedApp = appProvider.apps.firstWhereOrNull((a) => a.id == app.id);
        if (updatedApp != null) {
          // Compare critical fields to detect if app was actually updated
          final appHomeUrlChanged = updatedApp.externalIntegration?.appHomeUrl != app.externalIntegration?.appHomeUrl;
          final nameChanged = updatedApp.name != app.name;
          final descriptionChanged = updatedApp.description != app.description;

          if (appHomeUrlChanged || nameChanged || descriptionChanged) {
            // Update local app state when provider's app changes
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) {
                setState(() {
                  app = updatedApp;
                });
              }
            });
          }
        }

        bool isIntegration = app.worksExternally();
        bool hasSetupInstructions =
            isIntegration && app.externalIntegration?.setupInstructionsFilePath?.isNotEmpty == true;
        bool hasAuthSteps = isIntegration && app.externalIntegration?.authSteps.isNotEmpty == true;
        return Scaffold(
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            elevation: 0,
            automaticallyImplyLeading: false,
            leading: Container(
              width: 36,
              height: 36,
              margin: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
              child: IconButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  HapticFeedback.mediumImpact();
                  Navigator.pop(context);
                },
                icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16.0, color: Colors.white),
              ),
            ),
            actions: [
              if (app.enabled && app.worksWithChat()) ...[
                Container(
                  width: 36,
                  height: 36,
                  margin: const EdgeInsets.only(right: 8),
                  decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
                  child: IconButton(
                    padding: EdgeInsets.zero,
                    onPressed: chatButtonLoading
                        ? null
                        : () async {
                            HapticFeedback.mediumImpact();

                            // Prevent multiple clicks
                            if (chatButtonLoading) return;

                            setState(() => chatButtonLoading = true);

                            try {
                              // Navigate directly to chat page with this app selected
                              var appId = app.id;
                              var appProvider = Provider.of<AppProvider>(context, listen: false);
                              var messageProvider = Provider.of<MessageProvider>(context, listen: false);

                              // Set the selected app
                              appProvider.setSelectedChatAppId(appId);

                              // Refresh messages and get the selected app
                              await messageProvider.refreshMessages();
                              App? selectedApp = await appProvider.getAppFromId(appId);

                              // Send initial message if chat is empty
                              if (messageProvider.messages.isEmpty) {
                                messageProvider.sendInitialAppMessage(selectedApp);
                              }

                              // Track chat button clicked
                              PlatformManager.instance.analytics.appDetailChatClicked(appId: app.id, appName: app.name);

                              // Navigate directly to chat page
                              if (context.mounted) {
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(builder: (context) => const ChatPage(isPivotBottom: false)),
                                );
                              }
                            } finally {
                              if (mounted) {
                                setState(() => chatButtonLoading = false);
                              }
                            }
                          },
                    icon: chatButtonLoading
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 1.5,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const FaIcon(FontAwesomeIcons.solidComments, size: 16.0, color: Colors.white),
                  ),
                ),
              ],
              if (app.enabled && app.externalIntegration?.appHomeUrl?.isNotEmpty == true) ...[
                Container(
                  width: 36,
                  height: 36,
                  margin: const EdgeInsets.only(right: 8),
                  decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
                  child: IconButton(
                    padding: EdgeInsets.zero,
                    icon: const FaIcon(FontAwesomeIcons.gear, size: 16.0, color: Colors.white),
                    onPressed: () {
                      HapticFeedback.mediumImpact();
                      Navigator.push(context, MaterialPageRoute(builder: (context) => AppHomeWebPage(app: app)));
                    },
                  ),
                ),
              ],
              isLoading || app.private
                  ? const SizedBox.shrink()
                  : Builder(
                      builder: (BuildContext context) {
                        return Container(
                          width: 36,
                          height: 36,
                          margin: const EdgeInsets.only(right: 8),
                          decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            icon: const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16.0, color: Colors.white),
                            onPressed: () async {
                              HapticFeedback.mediumImpact();
                              PlatformManager.instance.analytics.track('App Shared', properties: {'appId': app.id});

                              // Track share button clicked
                              PlatformManager.instance.analytics.appDetailShared(appId: app.id, appName: app.name);

                              // Get the position of the share button for iOS
                              final RenderBox? box = context.findRenderObject() as RenderBox?;
                              final Rect? sharePositionOrigin =
                                  box != null ? box.localToGlobal(Offset.zero) & box.size : null;

                              await Share.share(
                                appShareUrl(app.id),
                                subject: app.name,
                                sharePositionOrigin: sharePositionOrigin,
                              );
                            },
                          ),
                        );
                      },
                    ),
              appProvider.isAppOwner
                  ? (isLoading
                      ? const SizedBox.shrink()
                      : Container(
                          width: 36,
                          height: 36,
                          margin: const EdgeInsets.only(right: 8),
                          decoration: BoxDecoration(
                            color: Colors.grey.withValues(alpha: 0.3),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            icon: const FaIcon(FontAwesomeIcons.edit, size: 16.0, color: Colors.white),
                            onPressed: () async {
                              HapticFeedback.mediumImpact();
                              await showModalBottomSheet(
                                context: context,
                                shape: const RoundedRectangleBorder(
                                  borderRadius: BorderRadius.only(
                                    topLeft: Radius.circular(16),
                                    topRight: Radius.circular(16),
                                  ),
                                ),
                                builder: (context) {
                                  return ShowAppOptionsSheet(app: app);
                                },
                              );
                            },
                          ),
                        ))
                  : const SizedBox(width: 8),
            ],
          ),
          backgroundColor: Theme.of(context).colorScheme.primary,
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
                            borderRadius: BorderRadius.circular(24),
                            image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                          ),
                        ),
                        placeholder: (context, url) => const CircularProgressIndicator(),
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
                          action: isLoading
                              ? AnimatedLoadingButton(
                                  text: '',
                                  width: 32,
                                  height: 32,
                                  onPressed: () async {},
                                  color: const Color(0xFF35343B),
                                )
                              : app.enabled
                                  ? AnimatedLoadingButton(
                                      text: 'Disable',
                                      width: 90,
                                      height: 32,
                                      onPressed: () => _toggleApp(app.id, false),
                                      color: Colors.grey.shade700,
                                    )
                                  : (app.isPaid && !app.isUserPaid
                                      ? AnimatedLoadingButton(
                                          width: 100,
                                          height: 32,
                                          text: "Subscribe",
                                          onPressed: () async {
                                            // Track subscribe button clicked
                                            PlatformManager.instance.analytics.appDetailSubscribeClicked(
                                              appId: app.id,
                                              appName: app.name,
                                            );

                                            if (app.paymentLink != null && app.paymentLink!.isNotEmpty) {
                                              final uri = Uri.tryParse(app.paymentLink!);
                                              if (uri == null) {
                                                ScaffoldMessenger.of(context).showSnackBar(
                                                  SnackBar(content: Text(context.l10n.invalidPaymentUrl)),
                                                );
                                                return;
                                              }
                                              _checkPaymentStatus(app.id);
                                              await _launchUrlSafely(uri);
                                            } else {
                                              await _toggleApp(app.id, true);
                                            }
                                          },
                                          color: Colors.white,
                                          // AnimatedLoadingButton defaults both to white; on a
                                          // white surface the label and spinner vanish.
                                          textStyle: const TextStyle(fontSize: 16, color: Colors.black),
                                          loaderColor: Colors.black,
                                        )
                                      : AnimatedLoadingButton(
                                          width: 75,
                                          height: 32,
                                          text: 'Enable',
                                          onPressed: () async {
                                            if (app.worksExternally()) {
                                              showDialog(
                                                context: context,
                                                builder: (ctx) {
                                                  return StatefulBuilder(
                                                    builder: (ctx, setState) {
                                                      return ConfirmationDialog(
                                                        title: context.l10n.dataAccessNotice,
                                                        description: context.l10n.dataAccessNoticeDescription,
                                                        onConfirm: () {
                                                          _toggleApp(app.id, true);
                                                          Navigator.pop(context);
                                                        },
                                                        onCancel: () {
                                                          Navigator.pop(context);
                                                        },
                                                      );
                                                    },
                                                  );
                                                },
                                              );
                                            } else {
                                              _toggleApp(app.id, true);
                                            }
                                          },
                                          color: Colors.white,
                                          // AnimatedLoadingButton defaults both to white; on a
                                          // white surface the label and spinner vanish.
                                          textStyle: const TextStyle(fontSize: 16, color: Colors.black),
                                          loaderColor: Colors.black,
                                        )),
                        ),
                      ),
                      const SizedBox(width: 20),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Cancel Subscription
                  !isLoading && !app.private && app.isPaid && _hasActiveSubscription() && !appProvider.isAppOwner
                      ? Padding(
                          padding: const EdgeInsets.only(top: 16),
                          child: InkWell(
                            onTap: _isCancelingSubscription
                                ? null
                                : () {
                                    showDialog(
                                      context: context,
                                      builder: (c) => getDialog(
                                        context,
                                        () => Navigator.pop(context),
                                        () async {
                                          Navigator.pop(context);
                                          await _cancelSubscription();
                                        },
                                        'Cancel Subscription?',
                                        'Are you sure you want to cancel your subscription? You will continue to have access until the end of your current billing period.',
                                        okButtonText: 'Cancel Subscription',
                                      ),
                                    );
                                  },
                            borderRadius: BorderRadius.circular(4),
                            child: Container(
                              width: double.infinity,
                              padding: const EdgeInsets.only(top: 12),
                              child: _isCancelingSubscription
                                  ? const Row(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        SizedBox(
                                          width: 16,
                                          height: 16,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            valueColor: AlwaysStoppedAnimation<Color>(Colors.red),
                                          ),
                                        ),
                                        SizedBox(width: 8),
                                        Text(
                                          'Cancelling...',
                                          style: TextStyle(
                                            color: Colors.red,
                                            fontSize: 16,
                                            fontWeight: FontWeight.w500,
                                          ),
                                        ),
                                      ],
                                    )
                                  : const Text(
                                      'Cancel Subscription',
                                      textAlign: TextAlign.center,
                                      style: TextStyle(color: Colors.red, fontSize: 16, fontWeight: FontWeight.w500),
                                    ),
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),

                  (app.isUnderReview() || app.private) && !app.isOwner(SharedPreferencesUtil().uid)
                      ? Column(
                          children: [
                            const SizedBox(height: 10),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const FaIcon(FontAwesomeIcons.circleInfo, color: Colors.grey, size: 18),
                                const SizedBox(width: 10),
                                SizedBox(
                                  width: MediaQuery.of(context).size.width * 0.78,
                                  child: const Text(
                                    'You are a beta tester for this app. It is not public yet. It will be public once approved.',
                                    style: TextStyle(color: Colors.grey),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        )
                      : const SizedBox.shrink(),
                  app.isUnderReview() && !app.private && app.isOwner(SharedPreferencesUtil().uid)
                      ? Column(
                          children: [
                            const SizedBox(height: 10),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const FaIcon(FontAwesomeIcons.circleInfo, color: Colors.grey, size: 18),
                                const SizedBox(width: 10),
                                SizedBox(
                                  width: MediaQuery.of(context).size.width * 0.78,
                                  child: const Text(
                                    'Your app is under review and visible only to you. It will be public once approved.',
                                    style: TextStyle(color: Colors.grey),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        )
                      : const SizedBox.shrink(),
                  app.isRejected()
                      ? Column(
                          children: [
                            const SizedBox(height: 10),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const FaIcon(FontAwesomeIcons.circleExclamation, color: Colors.grey, size: 18),
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
                  app.isDisabled() ? _buildDisabledNotice() : const SizedBox.shrink(),
                  const SizedBox(height: 24),
                  ...(hasAuthSteps
                      ? app.externalIntegration!.authSteps.mapIndexed<Widget>((i, step) {
                          return Container(
                            margin: EdgeInsets.only(
                              left: MediaQuery.of(context).size.width * 0.05,
                              right: MediaQuery.of(context).size.width * 0.05,
                              bottom: 6,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1F1F25).withValues(alpha: 0.8),
                              borderRadius: BorderRadius.circular(16.0),
                              border: Border.all(
                                color: setupCompleted ? Colors.green.withValues(alpha: 0.3) : Colors.transparent,
                                width: 1,
                              ),
                            ),
                            child: Material(
                              color: Colors.transparent,
                              child: InkWell(
                                borderRadius: BorderRadius.circular(16.0),
                                onTap: () async {
                                  final rawUrl = "${step.url}?uid=${SharedPreferencesUtil().uid}";
                                  final uri = Uri.tryParse(rawUrl);
                                  if (uri == null) {
                                    ScaffoldMessenger.of(
                                      context,
                                    ).showSnackBar(SnackBar(content: Text(context.l10n.invalidIntegrationUrl)));
                                    return;
                                  }
                                  await _launchUrlSafely(uri);
                                  checkSetupCompleted(autoInstallIfCompleted: true);
                                },
                                child: Padding(
                                  padding: const EdgeInsets.all(16.0),
                                  child: Row(
                                    children: [
                                      Container(
                                        width: 32,
                                        height: 32,
                                        decoration: BoxDecoration(
                                          color: setupCompleted
                                              ? Colors.green.withValues(alpha: 0.2)
                                              : Colors.grey.withValues(alpha: 0.2),
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                        child: Center(
                                          child: setupCompleted
                                              ? const FaIcon(FontAwesomeIcons.check, size: 14, color: Colors.green)
                                              : Text(
                                                  '${i + 1}',
                                                  style: TextStyle(
                                                    color: Colors.grey.shade400,
                                                    fontWeight: FontWeight.bold,
                                                  ),
                                                ),
                                        ),
                                      ),
                                      const SizedBox(width: 16),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              step.name,
                                              style: const TextStyle(
                                                fontSize: 16,
                                                fontWeight: FontWeight.w600,
                                                color: Colors.white,
                                              ),
                                            ),
                                            const SizedBox(height: 4),
                                            Text(
                                              setupCompleted ? context.l10n.setupCompleted : context.l10n.tapToComplete,
                                              style: TextStyle(
                                                fontSize: 13,
                                                color: setupCompleted ? Colors.green : Colors.grey.shade500,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                      FaIcon(
                                        FontAwesomeIcons.arrowUpRightFromSquare,
                                        size: 16,
                                        color: Colors.grey.shade500,
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          );
                        }).toList()
                      : <Widget>[const SizedBox.shrink()]),
                  !hasAuthSteps && hasSetupInstructions
                      ? ListTile(
                          onTap: () async {
                            if (app.externalIntegration != null) {
                              if (app.externalIntegration!.setupInstructionsFilePath?.contains(
                                    'raw.githubusercontent.com',
                                  ) ==
                                  true) {
                                await routeToPage(
                                  context,
                                  MarkdownViewer(
                                    title: context.l10n.setupInstructions,
                                    markdown: instructionsMarkdown ?? '',
                                  ),
                                );
                              } else {
                                if (app.externalIntegration!.isInstructionsUrl == true) {
                                  final uri = Uri.tryParse(app.externalIntegration!.setupInstructionsFilePath ?? '');
                                  if (uri == null) {
                                    ScaffoldMessenger.of(
                                      context,
                                    ).showSnackBar(SnackBar(content: Text(context.l10n.invalidSetupInstructionsUrl)));
                                    return;
                                  }
                                  await _launchUrlSafely(uri);
                                } else {
                                  var m = app.externalIntegration!.setupInstructionsFilePath;
                                  routeToPage(
                                    context,
                                    MarkdownViewer(title: context.l10n.setupInstructions, markdown: m ?? ''),
                                  );
                                }
                              }
                            }
                            checkSetupCompleted();
                          },
                          trailing: const Padding(
                            padding: EdgeInsets.only(right: 12.0),
                            child: FaIcon(FontAwesomeIcons.chevronRight, size: 20, color: Colors.grey),
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
                      child: Text('Preview', style: TextStyle(color: Colors.white, fontSize: 18)),
                    ),
                    SizedBox(
                      height: 250,
                      child: ListView.builder(
                        padding: EdgeInsets.zero,
                        scrollDirection: Axis.horizontal,
                        itemCount: app.thumbnailUrls.length,
                        itemBuilder: (context, index) {
                          return GestureDetector(
                            onTap: () {
                              // Track preview image viewed
                              PlatformManager.instance.analytics.appDetailPreviewImageViewed(
                                appId: app.id,
                                imageIndex: index,
                              );

                              Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (context) => MediaViewerPage(
                                    items: app.thumbnailUrls
                                        .map((url) => MediaViewerItem(
                                              imageUrl: url,
                                            ))
                                        .toList(),
                                    initialIndex: index,
                                    maxScaleMultiplier: 2,
                                    showCloseButton: true,
                                    wrapBodyInSafeArea: false,
                                  ),
                                ),
                              );
                            },
                            child: Container(
                              margin: EdgeInsets.only(
                                left: index == 0 ? 16 : 8,
                                right: index == app.thumbnailUrls.length - 1 ? 16 : 8,
                              ),
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(12),
                                child: Container(
                                  decoration: BoxDecoration(
                                    border: Border.all(color: const Color(0xFF424242), width: 1),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: ClipRRect(
                                    borderRadius: BorderRadius.circular(11),
                                    child: CachedNetworkImage(
                                      imageUrl: app.thumbnailUrls[index],
                                      fit: BoxFit.contain,
                                      placeholder: (context, url) => SizedBox(
                                        width: 150,
                                        child: ShimmerWithTimeout(
                                          baseColor: Colors.grey[900]!,
                                          highlightColor: Colors.grey[800]!,
                                          child: Container(
                                            decoration: BoxDecoration(
                                              color: Colors.black,
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                          ),
                                        ),
                                      ),
                                      errorWidget: (context, url, error) => Container(
                                        width: 150,
                                        decoration: BoxDecoration(
                                          color: Colors.grey[900],
                                          borderRadius: BorderRadius.circular(12),
                                        ),
                                        child: const FaIcon(FontAwesomeIcons.circleExclamation),
                                      ),
                                    ),
                                  ),
                                ),
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
                          MarkdownViewer(title: 'Description', markdown: app.description.decodeString),
                        );
                      }
                    },
                    title: 'Description',
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
                  app.chatTools != null && app.chatTools!.isNotEmpty
                      ? _buildChatToolsCard(app)
                      : const SizedBox.shrink(),
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
                  _buildPermissionsCard(app),
                  Builder(
                    builder: (context) {
                      final canAddReview = !app.isOwner(SharedPreferencesUtil().uid) && app.enabled;
                      return (app.ratingCount > 0 || app.reviews.isNotEmpty || canAddReview)
                          ? GestureDetector(
                              onTap: () {
                                if (app.reviews.isNotEmpty) {
                                  // Track reviews page opened
                                  PlatformManager.instance.analytics.appDetailReviewsOpened(
                                    appId: app.id,
                                    reviewCount: app.reviews.length,
                                  );

                                  routeToPage(context, ReviewsListPage(app: app));
                                }
                              },
                              child: Container(
                                key: _reviewsSectionKey,
                                width: double.infinity,
                                padding: const EdgeInsets.all(16.0),
                                margin: EdgeInsets.only(
                                  left: MediaQuery.of(context).size.width * 0.05,
                                  right: MediaQuery.of(context).size.width * 0.05,
                                  top: 12,
                                  bottom: 6,
                                ),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF1F1F25).withValues(alpha: 0.8),
                                  borderRadius: BorderRadius.circular(16.0),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Row(
                                      children: [
                                        const Text(
                                          'Reviews',
                                          style: TextStyle(
                                            color: Colors.white,
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        const Spacer(),
                                        app.reviews.isNotEmpty
                                            ? const Icon(Icons.arrow_forward, size: 20)
                                            : const SizedBox.shrink(),
                                      ],
                                    ),
                                    const SizedBox(height: 20),
                                    RatingDistributionWidget(
                                      ratingAvg: app.ratingAvg ?? 0,
                                      ratingCount: app.ratingCount,
                                      reviews: app.reviews,
                                    ),
                                    const SizedBox(height: 16),
                                    RecentReviewsSection(
                                      reviews:
                                          app.reviews.sorted((a, b) => b.ratedAt.compareTo(a.ratedAt)).take(3).toList(),
                                      userReview: app.userReview,
                                      app: app,
                                      onReviewUpdated: () {
                                        setState(() {});
                                      },
                                    ),
                                  ],
                                ),
                              ),
                            )
                          : const SizedBox.shrink();
                    },
                  ),
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
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const FaIcon(FontAwesomeIcons.triangleExclamation, color: Colors.grey, size: 18),
            const SizedBox(width: 10),
            SizedBox(
              width: MediaQuery.of(context).size.width * 0.78,
              child: Text(
                '${context.l10n.appDisabledTitle} $reason$when$lastError',
                style: const TextStyle(color: Colors.grey),
              ),
            ),
          ],
        ),
        if (isOwner) ...[
          const SizedBox(height: 12),
          SizedBox(
            width: MediaQuery.of(context).size.width * 0.78,
            child: Text(
              context.l10n.appDisabledOwnerHint,
              style: const TextStyle(color: Colors.grey, fontSize: 13),
            ),
          ),
          const SizedBox(height: 10),
          TextButton(
            onPressed: _reEnabling ? null : _reEnableApp,
            style: TextButton.styleFrom(
              backgroundColor: Colors.grey.shade900,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: _reEnabling
                ? const SizedBox(
                    width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : Text(context.l10n.appReEnable, style: const TextStyle(color: Colors.white)),
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
    showDialog(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context),
        () => Navigator.pop(context),
        context.l10n.appReEnableFailedTitle,
        detail.isNotEmpty ? detail : context.l10n.appReEnableFailedBody,
        singleButton: true,
      ),
    );
  }

  Future<void> _navigateToSetup() async {
    bool isIntegration = app.worksExternally();
    bool hasSetupInstructions = isIntegration && app.externalIntegration?.setupInstructionsFilePath?.isNotEmpty == true;
    bool hasAuthSteps = isIntegration && app.externalIntegration?.authSteps.isNotEmpty == true;

    if (hasAuthSteps && app.externalIntegration!.authSteps.isNotEmpty) {
      final firstStep = app.externalIntegration!.authSteps.first;
      final rawUrl = "${firstStep.url}?uid=${SharedPreferencesUtil().uid}";
      final uri = Uri.tryParse(rawUrl);
      if (uri == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.invalidIntegrationUrl)));
        }
        return;
      }
      await _launchUrlSafely(uri);
    } else if (hasSetupInstructions) {
      if (app.externalIntegration!.setupInstructionsFilePath?.contains('raw.githubusercontent.com') == true) {
        await routeToPage(
          context,
          MarkdownViewer(title: context.l10n.setupInstructions, markdown: instructionsMarkdown ?? ''),
        );
      } else {
        if (app.externalIntegration!.isInstructionsUrl == true) {
          final uri = Uri.tryParse(app.externalIntegration!.setupInstructionsFilePath ?? '');
          if (uri == null) {
            if (mounted) {
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(SnackBar(content: Text(context.l10n.invalidSetupInstructionsUrl)));
            }
            return;
          }
          await _launchUrlSafely(uri);
        } else {
          var m = app.externalIntegration!.setupInstructionsFilePath;
          routeToPage(context, MarkdownViewer(title: context.l10n.setupInstructions, markdown: m ?? ''));
        }
      }
    }
    _startSetupCompletionCheck();
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

  Future<void> _toggleApp(String appId, bool isEnabled) async {
    var prefs = SharedPreferencesUtil();
    setState(() => appLoading = true);

    if (isEnabled) {
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
          showDialog(
            context: context,
            builder: (c) => getDialog(
              context,
              () => Navigator.pop(context),
              () => Navigator.pop(context),
              context.l10n.errorActivatingApp,
              detail.isNotEmpty ? detail : context.l10n.issueActivatingApp,
              singleButton: true,
            ),
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
            Navigator.push(context, MaterialPageRoute(builder: (context) => AppHomeWebPage(app: app)));
          }
        });
      }
    } else {
      prefs.disableApp(appId);
      var res = await disableAppServer(appId);
      print(res);
      PlatformManager.instance.analytics.appDisabled(appId);

      if (!mounted) return;

      context.read<AppProvider>().filterApps();
      setState(() {
        app.enabled = false;
        appLoading = false;
      });
    }
  }
}

class _PermissionItem {
  final String title;
  final String type;
  final String description;

  _PermissionItem({required this.title, required this.type, required this.description});
}
