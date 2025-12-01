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
import 'package:omi/pages/apps/app_detail/widgets/add_review_widget.dart';
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
  Set<String> _expandedChatTools = {};
  Set<String> _expandedPermissions = {};

  String _getPricingText(App app) {
    if (!app.isPaid || app.price == null || app.price == 0) {
      return 'Free';
    }
    if (app.paymentPlan == 'monthly_recurring') {
      return '\$${app.price!.toStringAsFixed(app.price! % 1 == 0 ? 0 : 2)} / mo';
    }
    return '\$${app.price!.toStringAsFixed(app.price! % 1 == 0 ? 0 : 2)}';
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
      if (!app.enabled) {
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
      permissionItems.add(_PermissionItem(
        title: trigger,
        type: 'Trigger',
        description: 'This app runs automatically when: $trigger',
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
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Permissions & Triggers',
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
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
    final isExpanded = _expandedPermissions.contains(permission.title);

    return GestureDetector(
      onTap: () {
        setState(() {
          if (isExpanded) {
            _expandedPermissions.remove(permission.title);
          } else {
            _expandedPermissions.add(permission.title);
          }
        });
      },
      child: Container(
        margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFF2A2A2F),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: const Color(0xFF35343B)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: _getPermissionTypeColor(permission.type).withOpacity(0.2),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: _getPermissionTypeColor(permission.type).withOpacity(0.5)),
                  ),
                  child: Text(
                    permission.type,
                    style: TextStyle(
                      color: _getPermissionTypeColor(permission.type),
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    permission.title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  isExpanded ? Icons.expand_less : Icons.expand_more,
                  color: Colors.grey,
                  size: 20,
                ),
              ],
            ),
            if (isExpanded) ...[
              const SizedBox(height: 12),
              Text(
                permission.description,
                style: const TextStyle(
                  color: Colors.grey,
                  fontSize: 14,
                  height: 1.4,
                ),
              ),
            ],
          ],
        ),
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
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Chat Tools',
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
          ...app.chatTools!.asMap().entries.map((entry) {
            final tool = entry.value;
            final isLast = entry.key == app.chatTools!.length - 1;
            return _buildChatToolItem(tool, isLast);
          }).toList(),
        ],
      ),
    );
  }

  Widget _buildChatToolItem(ChatTool tool, bool isLast) {
    final isExpanded = _expandedChatTools.contains(tool.name);

    return GestureDetector(
      onTap: () {
        setState(() {
          if (isExpanded) {
            _expandedChatTools.remove(tool.name);
          } else {
            _expandedChatTools.add(tool.name);
          }
        });
      },
      child: Container(
        margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFF2A2A2F),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: const Color(0xFF35343B)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.blue.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: Colors.blue.withOpacity(0.5)),
                  ),
                  child: Text(
                    tool.method,
                    style: const TextStyle(
                      color: Colors.blue,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    tool.name,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  isExpanded ? Icons.expand_less : Icons.expand_more,
                  color: Colors.grey,
                  size: 20,
                ),
              ],
            ),
            if (isExpanded) ...[
              const SizedBox(height: 12),
              Text(
                tool.description,
                style: const TextStyle(
                  color: Colors.grey,
                  fontSize: 14,
                  height: 1.4,
                ),
              ),
              if (tool.statusMessage != null && tool.statusMessage!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(
                      Icons.info_outline,
                      size: 14,
                      color: Colors.grey.shade400,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'Status: ${tool.statusMessage}',
                        style: TextStyle(
                          color: Colors.grey.shade400,
                          fontSize: 12,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 8),
              Text(
                tool.endpoint,
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 12,
                  fontFamily: 'monospace',
                ),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
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
      int stepsCount = app.externalIntegration?.authSteps.length ?? 0;
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

                            // Get the position of the share button for iOS
                            final RenderBox? box = context.findRenderObject() as RenderBox?;
                            final Rect? sharePositionOrigin =
                                box != null ? box.localToGlobal(Offset.zero) & box.size : null;

                            if (app.isNotPersona()) {
                              await Share.share(
                                'Check out this app on Omi AI: ${app.name} by ${app.author} \n\n${app.description.decodeString}\n\n\nhttps://h.omi.me/apps/${app.id}',
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
                      errorWidget: (context, url, error) => const Icon(FontAwesomeIcons.circleExclamation),
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
                                  const SizedBox(width: 4),
                                  RatingBar.builder(
                                    initialRating: app.ratingAvg ?? 0,
                                    minRating: 1,
                                    ignoreGestures: true,
                                    direction: Axis.horizontal,
                                    allowHalfRating: true,
                                    itemCount: 1,
                                    itemSize: 16,
                                    tapOnlyMode: false,
                                    itemPadding: const EdgeInsets.symmetric(horizontal: 1),
                                    itemBuilder: (context, _) =>
                                        const Icon(FontAwesomeIcons.solidStar, color: Colors.deepPurple),
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
                          _getPricingText(app),
                          style: const TextStyle(
                            fontSize: 16,
                          ),
                        ),
                        const SizedBox(height: 4),
                        const Text("pricing"),
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
                            color: const Color(0xFF35343B),
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
                              child: Icon(FontAwesomeIcons.chevronRight, size: 20, color: Colors.grey),
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
                  showChips: true,
                  capabilityChips: app
                      .getCapabilitiesFromIds(context.read<AddAppProvider>().capabilities)
                      .map((e) => e.title)
                      .toList(),
                  connectionChips: app.getConnectedAccountNames(),
                ),
                _buildPermissionsCard(app),
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
                app.chatTools != null && app.chatTools!.isNotEmpty ? _buildChatToolsCard(app) : const SizedBox.shrink(),
                (app.ratingCount > 0 || app.reviews.isNotEmpty)
                    ? GestureDetector(
                        onTap: () {
                          if (app.reviews.isNotEmpty) {
                            routeToPage(context, ReviewsListPage(app: app));
                          }
                        },
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(16.0),
                          margin: EdgeInsets.only(
                            left: MediaQuery.of(context).size.width * 0.05,
                            right: MediaQuery.of(context).size.width * 0.05,
                            top: 12,
                            bottom: 6,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1F1F25),
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
                                          FontAwesomeIcons.arrowRight,
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
                                          itemSize: 16,
                                          tapOnlyMode: false,
                                          itemPadding: const EdgeInsets.symmetric(horizontal: 2),
                                          itemBuilder: (context, _) =>
                                              const Icon(FontAwesomeIcons.solidStar, color: Colors.deepPurple),
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
                      )
                    : const SizedBox.shrink(),
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
    });
  }

  Future<void> _navigateToSetup() async {
    bool isIntegration = app.worksExternally();
    bool hasSetupInstructions = isIntegration && app.externalIntegration?.setupInstructionsFilePath?.isNotEmpty == true;
    bool hasAuthSteps = isIntegration && app.externalIntegration?.authSteps.isNotEmpty == true;

    if (hasAuthSteps && app.externalIntegration!.authSteps.isNotEmpty) {
      final firstStep = app.externalIntegration!.authSteps.first;
      await launchUrl(Uri.parse("${firstStep.url}?uid=${SharedPreferencesUtil().uid}"));
    } else if (hasSetupInstructions) {
      if (app.externalIntegration!.setupInstructionsFilePath?.contains('raw.githubusercontent.com') == true) {
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
                ? MediaQuery.of(context).size.height * 0.28
                : (MediaQuery.of(context).size.height < 680
                    ? MediaQuery.of(context).size.height * 0.22
                    : MediaQuery.of(context).size.height * 0.16),
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
                          itemSize: 16,
                          tapOnlyMode: false,
                          itemPadding: const EdgeInsets.symmetric(horizontal: 2),
                          itemBuilder: (context, _) => const Icon(FontAwesomeIcons.solidStar, color: Colors.deepPurple),
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
