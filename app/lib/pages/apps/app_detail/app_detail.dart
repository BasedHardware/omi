import 'package:cached_network_image/cached_network_image.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:shimmer/shimmer.dart';
import 'package:omi/pages/apps/app_home_web_page.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/pages/apps/widgets/full_screen_image_viewer.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/apps/app_detail/reviews_list_page.dart';
import 'package:omi/pages/apps/markdown_viewer.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/app_provider.dart';
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
import '../../../backend/http/api/payment.dart';
import '../widgets/show_app_options_sheet.dart';
import 'widgets/capabilities_card.dart';
import 'widgets/info_card_widget.dart';
import 'package:timeago/timeago.dart' as timeago;

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
  Map<String, dynamic>? _subscriptionData;
  bool _isCancelingSubscription = false;
  Timer? _paymentCheckTimer;
  Timer? _setupCheckTimer;
  late App app;
  final ScrollController _scrollController = ScrollController();
  final GlobalKey _reviewsSectionKey = GlobalKey();

  String _getPricingText(App app) {
    if (!app.isPaid || app.price == null || app.price == 0) {
      return 'Free';
    }
    if (app.paymentPlan == 'monthly_recurring') {
      return '\$${app.price!.toStringAsFixed(app.price! % 1 == 0 ? 0 : 2)} / mo';
    }
    return '\$${app.price!.toStringAsFixed(app.price! % 1 == 0 ? 0 : 2)}';
  }

  IconData _getCategoryIcon(String category) {
    switch (category) {
      case 'conversation-analysis':
        return FontAwesomeIcons.solidComments;
      case 'personality-emulation':
        return FontAwesomeIcons.solidUser;
      case 'health-and-wellness':
        return FontAwesomeIcons.solidHeart;
      case 'education-and-learning':
        return FontAwesomeIcons.graduationCap;
      case 'communication-improvement':
        return FontAwesomeIcons.solidMessage;
      case 'emotional-and-mental-support':
        return FontAwesomeIcons.brain;
      case 'productivity-and-organization':
        return FontAwesomeIcons.listCheck;
      case 'entertainment-and-fun':
        return FontAwesomeIcons.gamepad;
      case 'financial':
        return FontAwesomeIcons.solidCreditCard;
      case 'travel-and-exploration':
        return FontAwesomeIcons.plane;
      case 'safety-and-security':
        return FontAwesomeIcons.shieldHalved;
      case 'shopping-and-commerce':
        return FontAwesomeIcons.cartShopping;
      case 'social-and-relationships':
        return FontAwesomeIcons.userGroup;
      case 'news-and-information':
        return FontAwesomeIcons.solidNewspaper;
      case 'utilities-and-tools':
        return FontAwesomeIcons.toolbox;
      case 'popular':
        return FontAwesomeIcons.fire;
      default:
        return FontAwesomeIcons.solidCircleQuestion;
    }
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    final day = date.day;
    final month = months[date.month - 1];
    if (date.year == now.year) {
      return '$day $month';
    }
    return '$day $month ${date.year}';
  }

  checkSetupCompleted() {
    // TODO: move check to backend
    isAppSetupCompleted(app.externalIntegration!.setupCompletedUrl).then((value) {
      if (mounted) {
        setState(() => setupCompleted = value);

        if (value && !app.enabled) {
          _tryAutoInstallAfterSetup();
        }
      }
    });
  }

  Future<void> _tryAutoInstallAfterSetup() async {
    if (!mounted) return;

    setState(() => appLoading = true);
    var prefs = SharedPreferencesUtil();
    var enabled = await enableAppServer(app.id);

    if (!mounted) return;

    if (enabled) {
      prefs.enableApp(app.id);
      MixpanelManager().appEnabled(app.id);
      context.read<AppProvider>().filterApps();

      setState(() {
        app.enabled = true;
        appLoading = false;
      });

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
        MixpanelManager().appDetailSubscriptionCancelled(
          appId: widget.app.id,
          appName: widget.app.name,
        );

        await _loadSubscriptionData();

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                  'Subscription cancelled successfully. It will remain active until the end of the current billing period.'),
              backgroundColor: Colors.green,
            ),
          );
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Failed to cancel subscription. Please try again.'),
              backgroundColor: Colors.red,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: ${e.toString()}'),
            backgroundColor: Colors.red,
          ),
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
    MixpanelManager().appDetailViewed(
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
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => AppHomeWebPage(app: app),
          ),
        );
      }
      // Load details
      await _refreshAppDetails();
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
      // Always check setup completed status when there are auth steps
      if (app.externalIntegration?.authSteps.isNotEmpty == true) {
        checkSetupCompleted();
      } else if (!app.enabled) {
        checkSetupCompleted();
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
          debugPrint('Payment not made yet');
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
      permissionItems.add(_PermissionItem(
        title: 'Read Conversations',
        type: 'Access',
        description: 'This app can access your conversations.',
      ));
    }
    if (actions.any((a) => a.action == 'read_memories')) {
      permissionItems.add(_PermissionItem(
        title: 'Read Memories',
        type: 'Access',
        description: 'This app can access your memories.',
      ));
    }

    // Create permissions
    if (actions.any((a) => a.action == 'create_conversation')) {
      permissionItems.add(_PermissionItem(
        title: 'Create Conversations',
        type: 'Create',
        description: 'This app can create new conversations.',
      ));
    }
    if (actions.any((a) => a.action == 'create_facts')) {
      permissionItems.add(_PermissionItem(
        title: 'Create Memories',
        type: 'Create',
        description: 'This app can create new memories.',
      ));
    }

    // Trigger
    if (trigger != null && trigger != 'Unknown') {
      final displayTrigger = trigger == 'Transcript Segment Processed' ? 'Realtime Listening' : trigger;
      permissionItems.add(_PermissionItem(
        title: displayTrigger,
        type: 'Trigger',
        description: 'This app runs automatically when: $displayTrigger',
      ));
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
        color: const Color(0xFF1F1F25).withOpacity(0.8),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Permissions & Triggers',
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
              color: _getPermissionTypeColor(permission.type).withOpacity(0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              permission.type,
              style: TextStyle(
                color: _getPermissionTypeColor(permission.type).withOpacity(0.8),
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              permission.title,
              style: const TextStyle(
                color: Colors.grey,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
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
        color: const Color(0xFF1F1F25).withOpacity(0.8),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Chat Features',
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: app.chatTools!.map((tool) => _buildChatToolChip(tool)).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildChatToolChip(ChatTool tool) {
    final color = Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        _formatToolName(tool.name),
        style: TextStyle(
          color: color,
          fontSize: 13,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Watch for changes to the app in AppProvider and update local state
    return Consumer<AppProvider>(builder: (context, appProvider, child) {
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
            decoration: BoxDecoration(
              color: Colors.grey.withOpacity(0.3),
              shape: BoxShape.circle,
            ),
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
                decoration: BoxDecoration(
                  color: Colors.grey.withOpacity(0.3),
                  shape: BoxShape.circle,
                ),
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
                            MixpanelManager().appDetailChatClicked(
                              appId: app.id,
                              appName: app.name,
                            );

                            // Navigate directly to chat page
                            if (mounted) {
                              Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (context) => const ChatPage(isPivotBottom: false),
                                ),
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
                decoration: BoxDecoration(
                  color: Colors.grey.withOpacity(0.3),
                  shape: BoxShape.circle,
                ),
                child: IconButton(
                  padding: EdgeInsets.zero,
                  icon: const FaIcon(FontAwesomeIcons.gear, size: 16.0, color: Colors.white),
                  onPressed: () {
                    HapticFeedback.mediumImpact();
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (context) => AppHomeWebPage(app: app),
                      ),
                    );
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
                        decoration: BoxDecoration(
                          color: Colors.grey.withOpacity(0.3),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16.0, color: Colors.white),
                          onPressed: () async {
                            HapticFeedback.mediumImpact();
                            MixpanelManager().track('App Shared', properties: {'appId': app.id});

                            // Track share button clicked
                            MixpanelManager().appDetailShared(
                              appId: app.id,
                              appName: app.name,
                            );

                            // Get the position of the share button for iOS
                            final RenderBox? box = context.findRenderObject() as RenderBox?;
                            final Rect? sharePositionOrigin =
                                box != null ? box.localToGlobal(Offset.zero) & box.size : null;

                            if (app.isNotPersona()) {
                              await Share.share(
                                'https://h.omi.me/apps/${app.id}',
                                subject: app.name,
                                sharePositionOrigin: sharePositionOrigin,
                              );
                            } else {
                              await Share.share(
                                'Check out this Persona on Omi AI: ${app.name} by ${app.author} \n\n${app.description.decodeString}\n\n\nhttps://personas.omi.me/u/${app.username}',
                                subject: app.name,
                                sharePositionOrigin: sharePositionOrigin,
                              );
                            }
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
                          color: Colors.grey.withOpacity(0.3),
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
                                return ShowAppOptionsSheet(
                                  app: app,
                                );
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
                      errorWidget: (context, url, error) => const Icon(FontAwesomeIcons.circleExclamation),
                    ),
                    const SizedBox(width: 20),
                    Expanded(
                      child: SizedBox(
                        height: 108,
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  app.name.decodeString,
                                  style:
                                      const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  app.author.decodeString,
                                  style: const TextStyle(color: Colors.grey, fontSize: 16),
                                ),
                              ],
                            ),
                            isLoading
                                ? AnimatedLoadingButton(
                                    text: '',
                                    width: 32,
                                    height: 32,
                                    onPressed: () async {},
                                    color: const Color(0xFF35343B),
                                  )
                                : app.enabled
                                    ? AnimatedLoadingButton(
                                        text: 'Uninstall',
                                        width: 90,
                                        height: 32,
                                        onPressed: () => _toggleApp(app.id, false),
                                        color: Colors.red,
                                      )
                                    : (app.isPaid && !app.isUserPaid
                                        ? AnimatedLoadingButton(
                                            width: 100,
                                            height: 32,
                                            text: "Subscribe",
                                            onPressed: () async {
                                              // Track subscribe button clicked
                                              MixpanelManager().appDetailSubscribeClicked(
                                                appId: app.id,
                                                appName: app.name,
                                              );

                                              if (app.paymentLink != null && app.paymentLink!.isNotEmpty) {
                                                final uri = Uri.tryParse(app.paymentLink!);
                                                if (uri == null) {
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    const SnackBar(content: Text('Invalid payment URL')),
                                                  );
                                                  return;
                                                }
                                                _checkPaymentStatus(app.id);
                                                await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
                                              } else {
                                                await _toggleApp(app.id, true);
                                              }
                                            },
                                            color: Colors.green,
                                          )
                                        : AnimatedLoadingButton(
                                            width: 75,
                                            height: 32,
                                            text: 'Install',
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
                                          )),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 20),
                  ],
                ),
                const SizedBox(height: 32),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          // Ratings section - App Store style
                          GestureDetector(
                            onTap: () {
                              if ((app.ratingCount > 0 || app.reviews.isNotEmpty) &&
                                  _reviewsSectionKey.currentContext != null) {
                                Scrollable.ensureVisible(
                                  _reviewsSectionKey.currentContext!,
                                  duration: const Duration(milliseconds: 300),
                                  curve: Curves.easeInOut,
                                );
                              }
                            },
                            child: Column(
                              children: [
                                Text(
                                  app.ratingCount == 0 ? 'NO RATINGS' : '${app.ratingCount}+ RATINGS',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: Colors.grey.shade500,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 0.5,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  app.getRatingAvg() ?? '0.0',
                                  style: TextStyle(
                                    fontSize: 22,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.grey.shade400,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                RatingBar.builder(
                                  initialRating: app.ratingAvg ?? 0,
                                  minRating: 1,
                                  ignoreGestures: true,
                                  direction: Axis.horizontal,
                                  allowHalfRating: true,
                                  itemCount: 5,
                                  itemSize: 12,
                                  tapOnlyMode: false,
                                  itemPadding: const EdgeInsets.symmetric(horizontal: 1),
                                  itemBuilder: (context, _) => Icon(
                                    FontAwesomeIcons.solidStar,
                                    color: Colors.grey.shade500,
                                  ),
                                  maxRating: 5.0,
                                  onRatingUpdate: (rating) {},
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 20),
                          VerticalDivider(
                            color: Colors.grey.shade800,
                            width: 4,
                          ),
                          const SizedBox(width: 20),
                          // Installs
                          Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                '${(app.installs / 10).round() * 10}+',
                                style: TextStyle(
                                  fontSize: 22,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.grey.shade400,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                'INSTALLS',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Colors.grey.shade500,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.5,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(width: 20),
                          VerticalDivider(
                            color: Colors.grey.shade800,
                            width: 4,
                          ),
                          const SizedBox(width: 20),
                          // Pricing
                          Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                _getPricingText(app),
                                style: TextStyle(
                                  fontSize: 22,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.grey.shade400,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                'PRICE',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Colors.grey.shade500,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.5,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(width: 20),
                          VerticalDivider(
                            color: Colors.grey.shade800,
                            width: 4,
                          ),
                          const SizedBox(width: 20),
                          // Category
                          Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              FaIcon(
                                _getCategoryIcon(app.category),
                                size: 20,
                                color: Colors.grey.shade400,
                              ),
                              const SizedBox(height: 12),
                              Text(
                                app.getCategoryName().split(' ').first.toUpperCase(),
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Colors.grey.shade500,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.5,
                                ),
                              ),
                            ],
                          ),
                          if (app.getLastUpdatedDate() != null) ...[
                            const SizedBox(width: 20),
                            VerticalDivider(
                              color: Colors.grey.shade800,
                              width: 4,
                            ),
                            const SizedBox(width: 20),
                            // Updated/Created
                            Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(
                                  _formatDate(app.getLastUpdatedDate()!),
                                  style: TextStyle(
                                    fontSize: 22,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.grey.shade400,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  app.updatedAt != null ? 'UPDATED' : 'CREATED',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: Colors.grey.shade500,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 0.5,
                                  ),
                                ),
                              ],
                            ),
                          ],
                          if (app.isPopular == true) ...[
                            const SizedBox(width: 20),
                            VerticalDivider(
                              color: Colors.grey.shade800,
                              width: 4,
                            ),
                            const SizedBox(width: 20),
                            // Featured
                            Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                FaIcon(
                                  FontAwesomeIcons.trophy,
                                  size: 20,
                                  color: Colors.grey.shade400,
                                ),
                                const SizedBox(height: 12),
                                Text(
                                  'FEATURED',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: Colors.grey.shade500,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 0.5,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
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
                                    style: TextStyle(
                                      color: Colors.red,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                          ),
                        ),
                      )
                    : const SizedBox.shrink(),

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
                                FontAwesomeIcons.circleInfo,
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
                                FontAwesomeIcons.circleInfo,
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
                                FontAwesomeIcons.circleExclamation,
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
                            color: const Color(0xFF1F1F25).withOpacity(0.8),
                            borderRadius: BorderRadius.circular(16.0),
                            border: Border.all(
                              color: setupCompleted ? Colors.green.withOpacity(0.3) : Colors.transparent,
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
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(content: Text('Invalid integration URL')),
                                  );
                                  return;
                                }
                                await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
                                checkSetupCompleted();
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
                                            ? Colors.green.withOpacity(0.2)
                                            : Colors.grey.withOpacity(0.2),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Center(
                                        child: setupCompleted
                                            ? const FaIcon(
                                                FontAwesomeIcons.check,
                                                size: 14,
                                                color: Colors.green,
                                              )
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
                                            setupCompleted ? 'Completed' : 'Tap to complete',
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
                            if (app.externalIntegration!.setupInstructionsFilePath
                                    ?.contains('raw.githubusercontent.com') ==
                                true) {
                              await routeToPage(
                                context,
                                MarkdownViewer(title: 'Setup Instructions', markdown: instructionsMarkdown ?? ''),
                              );
                            } else {
                              if (app.externalIntegration!.isInstructionsUrl == true) {
                                final uri = Uri.tryParse(app.externalIntegration!.setupInstructionsFilePath ?? '');
                                if (uri == null) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(content: Text('Invalid setup instructions URL')),
                                  );
                                  return;
                                }
                                await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
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
                          child: Icon(FontAwesomeIcons.chevronRight, size: 20, color: Colors.grey),
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
                    height: 250,
                    child: ListView.builder(
                      padding: EdgeInsets.zero,
                      scrollDirection: Axis.horizontal,
                      itemCount: app.thumbnailUrls.length,
                      itemBuilder: (context, index) {
                        return GestureDetector(
                          onTap: () {
                            // Track preview image viewed
                            MixpanelManager().appDetailPreviewImageViewed(
                              appId: app.id,
                              imageIndex: index,
                            );

                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (context) => FullScreenImageViewer(
                                  imageUrl: app.thumbnailUrls[index],
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
                                  border: Border.all(
                                    color: const Color(0xFF424242),
                                    width: 1,
                                  ),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(11),
                                  child: CachedNetworkImage(
                                    imageUrl: app.thumbnailUrls[index],
                                    fit: BoxFit.contain,
                                    placeholder: (context, url) => SizedBox(
                                      width: 150,
                                      child: Shimmer.fromColors(
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
                                      child: const Icon(FontAwesomeIcons.circleExclamation),
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
                          MarkdownViewer(
                              title: 'About the ${app.isNotPersona() ? 'App' : 'Persona'}',
                              markdown: app.description.decodeString));
                    }
                  },
                  title: 'About the ${app.isNotPersona() ? 'App' : 'Persona'}',
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
                          AppCapability(
                            title: 'Push to Talk',
                            id: 'push_to_talk',
                          ),
                        ];
                      }
                    }

                    // Filter out external_integration capability
                    capabilitiesList = capabilitiesList.where((cap) => cap.id != 'external_integration').toList();

                    return CapabilitiesCard(capabilities: capabilitiesList);
                  },
                ),
                app.chatTools != null && app.chatTools!.isNotEmpty ? _buildChatToolsCard(app) : const SizedBox.shrink(),
                app.conversationPrompt != null
                    ? InfoCardWidget(
                        onTap: () {
                          routeToPage(context,
                              MarkdownViewer(title: 'Summary Prompt', markdown: app.conversationPrompt!.decodeString));
                        },
                        title: 'Summary Prompt',
                        description: app.conversationPrompt!,
                        showChips: false,
                        maxLines: 3,
                      )
                    : const SizedBox.shrink(),

                app.chatPrompt != null
                    ? InfoCardWidget(
                        onTap: () {
                          routeToPage(context,
                              MarkdownViewer(title: 'Chat Personality', markdown: app.chatPrompt!.decodeString));
                        },
                        title: 'Chat Personality',
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
                                MixpanelManager().appDetailReviewsOpened(
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
                                color: const Color(0xFF1F1F25).withOpacity(0.8),
                                borderRadius: BorderRadius.circular(16.0),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Row(
                                    children: [
                                      const Text('Ratings & Reviews',
                                          style: TextStyle(
                                              color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
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
                                  )
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
    });
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
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Invalid integration URL')),
          );
        }
        return;
      }
      await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
    } else if (hasSetupInstructions) {
      if (app.externalIntegration!.setupInstructionsFilePath?.contains('raw.githubusercontent.com') == true) {
        await routeToPage(
          context,
          MarkdownViewer(title: 'Setup Instructions', markdown: instructionsMarkdown ?? ''),
        );
      } else {
        if (app.externalIntegration!.isInstructionsUrl == true) {
          final uri = Uri.tryParse(app.externalIntegration!.setupInstructionsFilePath ?? '');
          if (uri == null) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Invalid setup instructions URL')),
              );
            }
            return;
          }
          await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
        } else {
          var m = app.externalIntegration!.setupInstructionsFilePath;
          routeToPage(context, MarkdownViewer(title: 'Setup Instructions', markdown: m ?? ''));
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
      var enabled = await enableAppServer(appId);

      if (!mounted) return;

      if (!enabled) {
        if (app.worksExternally()) {
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
              'Error activating the app',
              'There was an issue activating this app. Please try again.',
              singleButton: true,
            ),
          );
          setState(() => appLoading = false);
          return;
        }
      }

      prefs.enableApp(appId);
      MixpanelManager().appEnabled(appId);
      context.read<AppProvider>().filterApps();

      setState(() {
        app.enabled = true;
        appLoading = false;
      });

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

  _PermissionItem({
    required this.title,
    required this.type,
    required this.description,
  });
}

class RatingDistributionWidget extends StatelessWidget {
  final double ratingAvg;
  final int ratingCount;
  final List<AppReview> reviews;

  const RatingDistributionWidget({
    super.key,
    required this.ratingAvg,
    required this.ratingCount,
    required this.reviews,
  });

  Map<int, int> _getRatingDistribution() {
    final distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0};
    for (final review in reviews) {
      final score = review.score.round().clamp(1, 5);
      distribution[score] = (distribution[score] ?? 0) + 1;
    }
    return distribution;
  }

  @override
  Widget build(BuildContext context) {
    final distribution = _getRatingDistribution();

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Left side - Large rating number with stars
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              ratingAvg.toStringAsFixed(1),
              style: TextStyle(
                fontSize: 48,
                fontWeight: FontWeight.bold,
                color: Colors.grey.shade400,
                height: 1,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: List.generate(5, (index) {
                return Padding(
                  padding: EdgeInsets.only(right: index < 4 ? 4 : 0),
                  child: Icon(
                    FontAwesomeIcons.solidStar,
                    size: 14,
                    color: index < ratingAvg.round() ? Colors.deepPurple : Colors.grey.shade700,
                  ),
                );
              }),
            ),
            const SizedBox(height: 6),
            Text(
              ratingCount == 1 ? '1 rating' : '$ratingCount ratings',
              style: TextStyle(
                fontSize: 13,
                color: Colors.grey.shade500,
              ),
            ),
          ],
        ),
        const SizedBox(width: 24),
        // Right side - Rating distribution bars
        Expanded(
          child: Column(
            children: [5, 4, 3, 2, 1].map((star) {
              final count = distribution[star] ?? 0;
              final percentage = ratingCount > 0 ? count / ratingCount : 0.0;

              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Text(
                      '$star',
                      style: TextStyle(
                        fontSize: 13,
                        color: Colors.grey.shade400,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(width: 4),
                    const Icon(
                      FontAwesomeIcons.solidStar,
                      size: 10,
                      color: Colors.deepPurple,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Container(
                        height: 8,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade800,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: FractionallySizedBox(
                          alignment: Alignment.centerLeft,
                          widthFactor: percentage,
                          child: Container(
                            decoration: BoxDecoration(
                              color: Colors.deepPurple,
                              borderRadius: BorderRadius.circular(4),
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 20,
                      child: Text(
                        '$count',
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.grey.shade500,
                        ),
                        textAlign: TextAlign.right,
                      ),
                    ),
                  ],
                ),
              );
            }).toList(),
          ),
        ),
      ],
    );
  }
}

class RecentReviewsSection extends StatefulWidget {
  final List<AppReview> reviews;
  final AppReview? userReview;
  final App app;
  final VoidCallback? onReviewUpdated;

  const RecentReviewsSection({
    super.key,
    required this.reviews,
    required this.app,
    this.userReview,
    this.onReviewUpdated,
  });

  @override
  State<RecentReviewsSection> createState() => _RecentReviewsSectionState();
}

class _RecentReviewsSectionState extends State<RecentReviewsSection> {
  bool isEditing = false;
  double editRating = 0;
  late TextEditingController reviewController;
  bool isSubmitting = false;

  @override
  void initState() {
    super.initState();
    reviewController = TextEditingController(text: widget.userReview?.review ?? '');
    editRating = widget.userReview?.score ?? 0;
  }

  @override
  void dispose() {
    reviewController.dispose();
    super.dispose();
  }

  String _getAvatarUrl(String seed, String? username) {
    // Using Avatar Placeholder API for random avatars
    // If username is available, use username-based avatar for consistency
    if (username != null && username.isNotEmpty) {
      return 'https://avatar.iran.liara.run/username?username=${Uri.encodeComponent(username)}';
    }
    // Otherwise use a seeded random avatar
    return 'https://avatar.iran.liara.run/public/${seed.hashCode % 100}';
  }

  Future<void> _submitReview() async {
    if (editRating == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select a rating')),
      );
      return;
    }

    setState(() => isSubmitting = true);

    try {
      final prefs = SharedPreferencesUtil();
      final userName = widget.userReview?.username.isNotEmpty == true
          ? widget.userReview!.username
          : prefs.fullName.isNotEmpty
              ? prefs.fullName
              : prefs.givenName;

      final rev = AppReview(
        uid: prefs.uid,
        review: reviewController.text,
        score: editRating,
        ratedAt: widget.userReview?.ratedAt ?? DateTime.now(),
        response: widget.userReview?.response ?? '',
        username: userName,
      );

      bool isSuccessful;
      if (widget.userReview == null) {
        isSuccessful = await reviewApp(widget.app.id, rev);
        if (isSuccessful) {
          widget.app.ratingCount += 1;
        }
      } else {
        isSuccessful = await updateAppReview(widget.app.id, rev);
      }

      if (isSuccessful) {
        widget.app.userReview = AppReview(
          uid: prefs.uid,
          ratedAt: DateTime.now(),
          review: reviewController.text,
          score: editRating,
          username: userName,
          response: widget.userReview?.response ?? '',
        );

        var appsList = SharedPreferencesUtil().appsList;
        var index = appsList.indexWhere((element) => element.id == widget.app.id);
        if (index != -1) {
          appsList[index] = widget.app;
          SharedPreferencesUtil().appsList = appsList;
        }

        MixpanelManager().appRated(widget.app.id, editRating);

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text(
                    widget.userReview == null ? 'Review added successfully 🚀' : 'Review updated successfully 🚀')),
          );
          setState(() => isEditing = false);
          widget.onReviewUpdated?.call();
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Failed to submit review. Please try again.')),
          );
        }
      }
    } finally {
      if (mounted) {
        setState(() => isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // Filter out user's review from the list if it exists
    final filteredReviews = widget.userReview != null
        ? widget.reviews.where((r) => r.uid != widget.userReview!.uid).take(3).toList()
        : widget.reviews.take(3).toList();

    final showUserReviewSection =
        widget.userReview != null || (!widget.app.isOwner(SharedPreferencesUtil().uid) && widget.app.enabled);

    if (filteredReviews.isEmpty && !showUserReviewSection) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Recent reviews from others
        ...filteredReviews.map((review) => _buildReviewItem(review)),
        // User's review section (editable)
        if (showUserReviewSection) ...[
          if (filteredReviews.isNotEmpty) const SizedBox(height: 8),
          _buildUserReviewSection(),
        ],
      ],
    );
  }

  Widget _buildUserReviewSection() {
    final userReview = widget.userReview;

    if (isEditing || userReview == null) {
      // Edit mode or no review yet
      return _buildEditableReview();
    } else {
      // Display mode with tap to edit
      return GestureDetector(
        onTap: () {
          setState(() {
            isEditing = true;
            reviewController.text = userReview.review;
            editRating = userReview.score;
          });
        },
        child: _buildReviewItem(userReview, isUserReview: true),
      );
    }
  }

  Widget _buildEditableReview() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.deepPurple.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.deepPurple.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                widget.userReview == null ? 'Add Your Review' : 'Edit Your Review',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const Spacer(),
              if (widget.userReview != null)
                GestureDetector(
                  onTap: () {
                    setState(() {
                      isEditing = false;
                      reviewController.text = widget.userReview?.review ?? '';
                      editRating = widget.userReview?.score ?? 0;
                    });
                  },
                  child: Text(
                    'Cancel',
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 12,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          // Star rating
          Row(
            children: List.generate(5, (index) {
              return GestureDetector(
                onTap: () {
                  setState(() => editRating = index + 1.0);
                },
                child: Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Icon(
                    FontAwesomeIcons.solidStar,
                    size: 24,
                    color: index < editRating ? Colors.deepPurple : Colors.grey.shade600,
                  ),
                ),
              );
            }),
          ),
          const SizedBox(height: 12),
          // Review text field
          TextField(
            controller: reviewController,
            maxLines: 3,
            maxLength: 250,
            style: const TextStyle(color: Colors.white, fontSize: 14),
            decoration: InputDecoration(
              hintText: 'Write a review (optional)',
              hintStyle: TextStyle(color: Colors.grey.shade500),
              filled: true,
              fillColor: Colors.black.withOpacity(0.3),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.all(12),
              counterStyle: TextStyle(color: Colors.grey.shade500),
            ),
          ),
          const SizedBox(height: 12),
          // Submit button
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: isSubmitting ? null : _submitReview,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.deepPurple,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
              child: isSubmitting
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    )
                  : Text(widget.userReview == null ? 'Submit Review' : 'Update Review'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildReviewItem(AppReview review, {bool isUserReview = false}) {
    final displayName =
        isUserReview ? 'Your Review' : (review.username.isNotEmpty ? review.username : 'Anonymous User');
    final avatarSeed = review.uid.isNotEmpty ? review.uid : review.username;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Random Avatar
              ClipOval(
                child: Container(
                  width: 36,
                  height: 36,
                  color: Colors.grey.shade800,
                  child: Image.network(
                    _getAvatarUrl(avatarSeed, review.username),
                    width: 36,
                    height: 36,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      final initial = review.username.isNotEmpty ? review.username[0].toUpperCase() : 'A';
                      return Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: isUserReview ? Colors.deepPurple.withOpacity(0.2) : Colors.grey.shade800,
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: Text(
                            initial,
                            style: TextStyle(
                              color: isUserReview ? Colors.deepPurple : Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
              const SizedBox(width: 12),
              // Name, date, and stars
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          displayName,
                          style: TextStyle(
                            color: isUserReview ? Colors.deepPurple : Colors.grey,
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          timeago.format(review.ratedAt),
                          style: TextStyle(
                            color: Colors.grey.shade700,
                            fontSize: 12,
                          ),
                        ),
                        if (isUserReview) ...[
                          const Spacer(),
                          Icon(
                            Icons.edit,
                            size: 14,
                            color: Colors.grey.shade500,
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 8),
                    // Star rating
                    Row(
                      children: List.generate(5, (index) {
                        return Padding(
                          padding: const EdgeInsets.only(right: 4),
                          child: Icon(
                            FontAwesomeIcons.solidStar,
                            size: 14,
                            color: index < review.score.round() ? Colors.deepPurple : Colors.grey.shade700,
                          ),
                        );
                      }),
                    ),
                  ],
                ),
              ),
            ],
          ),
          // Review text - limited to 2 lines
          if (review.review.isNotEmpty) ...[
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.only(left: 48),
              child: Text(
                review.review.decodeString,
                style: const TextStyle(
                  color: Colors.grey,
                  fontSize: 14,
                  height: 1.4,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
