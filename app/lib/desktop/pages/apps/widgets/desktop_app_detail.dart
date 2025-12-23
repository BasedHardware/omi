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
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:skeletonizer/skeletonizer.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:async';

import '../../../../backend/schema/app.dart';
import '../../../../pages/apps/widgets/show_app_options_sheet.dart';

import 'package:timeago/timeago.dart' as timeago;

class DesktopAppDetail extends StatefulWidget {
  final App app;
  final VoidCallback onClose;

  const DesktopAppDetail({
    super.key,
    required this.app,
    required this.onClose,
  });

  @override
  State<DesktopAppDetail> createState() => _DesktopAppDetailState();
}

class _DesktopAppDetailState extends State<DesktopAppDetail> with SingleTickerProviderStateMixin {
  String? instructionsMarkdown;
  bool setupCompleted = false;
  bool appLoading = false;
  bool isLoading = false;
  Timer? _paymentCheckTimer;
  late App app;
  late AnimationController _animationController;
  late Animation<Offset> _slideAnimation;

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

    super.initState();

    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(1.0, 0.0),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutCubic,
    ));

    _animationController.forward();

    _initializeAppData();
  }

  Future<void> _initializeAppData() async {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
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
      }
    });

    if (app.worksExternally()) {
      checkSetupCompleted();
    }
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

  Future<void> _handleClose() async {
    await _animationController.reverse();
    widget.onClose();
  }

  @override
  void dispose() {
    _paymentCheckTimer?.cancel();
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return SlideTransition(
      position: _slideAnimation,
      child: Container(
        width: responsive.responsiveWidth(
          baseWidth: 650,
          minWidth: 500,
          maxWidth: 800,
        ),
        height: double.infinity,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundPrimary,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.4),
              blurRadius: 24,
              offset: const Offset(-6, 0),
            ),
            BoxShadow(
              color: Colors.black.withOpacity(0.2),
              blurRadius: 40,
              offset: const Offset(-12, 0),
            ),
          ],
        ),
        child: Column(
          children: [
            _buildHeader(responsive),
            Expanded(
              child: _buildContent(responsive),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(ResponsiveHelper responsive) {
    return Container(
      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 24)),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
        border: Border(
          bottom: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          // App icon
          CachedNetworkImage(
            imageUrl: app.getImageUrl(),
            imageBuilder: (context, imageProvider) => Container(
              width: responsive.responsiveWidth(baseWidth: 56),
              height: responsive.responsiveWidth(baseWidth: 56),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                image: DecorationImage(
                  image: imageProvider,
                  fit: BoxFit.cover,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.2),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
            ),
            placeholder: (context, url) => Container(
              width: responsive.responsiveWidth(baseWidth: 56),
              height: responsive.responsiveWidth(baseWidth: 56),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Center(
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.textQuaternary),
                ),
              ),
            ),
            errorWidget: (context, url, error) => Container(
              width: responsive.responsiveWidth(baseWidth: 56),
              height: responsive.responsiveWidth(baseWidth: 56),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(
                Icons.apps,
                color: ResponsiveHelper.textQuaternary,
                size: 28,
              ),
            ),
          ),

          SizedBox(width: responsive.spacing(baseSpacing: 16)),

          // App info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  app.name.decodeString,
                  style: responsive.headlineMedium.copyWith(
                    color: ResponsiveHelper.textPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                SizedBox(height: responsive.spacing(baseSpacing: 4)),
                Text(
                  app.author.decodeString,
                  style: responsive.bodyLarge.copyWith(
                    color: ResponsiveHelper.textTertiary,
                  ),
                ),
                SizedBox(height: responsive.spacing(baseSpacing: 8)),

                // Rating row
                if (app.ratingAvg != null)
                  Row(
                    children: [
                      const Icon(
                        Icons.star_rounded,
                        color: ResponsiveHelper.purplePrimary,
                        size: 16,
                      ),
                      SizedBox(width: responsive.spacing(baseSpacing: 4)),
                      Text(
                        app.getRatingAvg()!,
                        style: responsive.bodyMedium.copyWith(
                          color: ResponsiveHelper.textSecondary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      SizedBox(width: responsive.spacing(baseSpacing: 8)),
                      Text(
                        '•',
                        style: responsive.bodyMedium.copyWith(
                          color: ResponsiveHelper.textQuaternary,
                        ),
                      ),
                      SizedBox(width: responsive.spacing(baseSpacing: 8)),
                      Text(
                        '${(app.installs / 10).round() * 10}+ installs',
                        style: responsive.bodyMedium.copyWith(
                          color: ResponsiveHelper.textTertiary,
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ),

          // Action buttons
          Row(
            children: [
              // Chat button
              if (app.enabled && app.worksWithChat())
                _buildActionButton(
                  responsive,
                  icon: Icons.chat_rounded,
                  onTap: () => _handleChatTap(),
                ),

              // Web app button
              if (app.enabled && app.externalIntegration?.appHomeUrl?.isNotEmpty == true)
                _buildActionButton(
                  responsive,
                  icon: Icons.open_in_browser_rounded,
                  onTap: () => _handleWebAppTap(),
                ),

              // Share button
              if (!app.private)
                _buildActionButton(
                  responsive,
                  icon: Icons.share_rounded,
                  onTap: () => _handleShareTap(),
                ),

              // Settings button (for app owners)
              if (context.watch<AppProvider>().isAppOwner && !isLoading)
                _buildActionButton(
                  responsive,
                  icon: Icons.settings_rounded,
                  onTap: () => _handleSettingsTap(),
                ),

              SizedBox(width: responsive.spacing(baseSpacing: 8)),

              // Close button
              Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: _handleClose,
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    padding: EdgeInsets.all(responsive.spacing(baseSpacing: 8)),
                    child: const Icon(
                      Icons.close_rounded,
                      color: ResponsiveHelper.textTertiary,
                      size: 20,
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

  Widget _buildActionButton(ResponsiveHelper responsive, {required IconData icon, required VoidCallback onTap}) {
    return Padding(
      padding: EdgeInsets.only(right: responsive.spacing(baseSpacing: 8)),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Container(
            padding: EdgeInsets.all(responsive.spacing(baseSpacing: 8)),
            child: Icon(
              icon,
              color: ResponsiveHelper.textSecondary,
              size: 20,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildContent(ResponsiveHelper responsive) {
    bool isIntegration = app.worksExternally();
    bool hasSetupInstructions = isIntegration && app.externalIntegration?.setupInstructionsFilePath?.isNotEmpty == true;
    bool hasAuthSteps = isIntegration && app.externalIntegration?.authSteps.isNotEmpty == true;
    int stepsCount = app.externalIntegration?.authSteps.length ?? 0;

    return Skeletonizer(
      enabled: isLoading,
      child: SingleChildScrollView(
        padding: EdgeInsets.all(responsive.spacing(baseSpacing: 24)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Install/uninstall section
            _buildInstallSection(responsive),

            SizedBox(height: responsive.spacing(baseSpacing: 24)),

            // Status notifications
            _buildStatusNotifications(responsive),

            // Setup steps (for integrations)
            if (hasAuthSteps && stepsCount > 0) _buildSetupSteps(responsive, stepsCount),

            // Setup instructions
            if (!hasAuthSteps && hasSetupInstructions) _buildSetupInstructions(responsive),

            // Preview images
            if (app.thumbnailUrls.isNotEmpty) _buildPreviewSection(responsive),

            // App description
            _buildDescriptionSection(responsive),

            // Conversation prompt
            if (app.conversationPrompt != null)
              _buildPromptSection(responsive, 'Conversation Prompt', app.conversationPrompt!),

            // Chat prompt
            if (app.chatPrompt != null) _buildPromptSection(responsive, 'Chat Personality', app.chatPrompt!),

            // Reviews section
            _buildReviewsSection(responsive),

            // Add review
            if (!app.isOwner(SharedPreferencesUtil().uid) && (app.enabled || app.userReview != null))
              AddReviewWidget(app: app),

            SizedBox(height: responsive.spacing(baseSpacing: 32)),
          ],
        ),
      ),
    );
  }

  // Install/Uninstall section with desktop styling
  Widget _buildInstallSection(ResponsiveHelper responsive) {
    if (isLoading) {
      return Container(
        width: double.infinity,
        height: responsive.responsiveHeight(baseHeight: 48),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          borderRadius: BorderRadius.circular(12),
        ),
      );
    }

    if (app.enabled) {
      return SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: () => _toggleApp(app.id, false),
          icon: const Icon(Icons.delete_outline, size: 18),
          label: Text(
            'Uninstall App',
            style: responsive.labelLarge.copyWith(
              fontWeight: FontWeight.w500,
            ),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: ResponsiveHelper.errorColor.withValues(alpha: 0.15),
            foregroundColor: ResponsiveHelper.errorColor,
            elevation: 0,
            padding: EdgeInsets.symmetric(
              vertical: responsive.spacing(baseSpacing: 16),
            ),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: BorderSide(
                color: ResponsiveHelper.errorColor.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
          ),
        ),
      );
    }

    if (app.isPaid && !app.isUserPaid) {
      return SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: () async {
            MixpanelManager().appDetailSubscribeClicked(
              appId: app.id,
              appName: app.name,
            );
            if (app.paymentLink != null && app.paymentLink!.isNotEmpty) {
              _checkPaymentStatus(app.id);
              await launchUrl(Uri.parse(app.paymentLink!));
            } else {
              await _toggleApp(app.id, true);
            }
          },
          icon: const Icon(Icons.payment, size: 18),
          label: Text(
            'Subscribe',
            style: responsive.labelLarge.copyWith(
              fontWeight: FontWeight.w500,
            ),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: ResponsiveHelper.successColor.withValues(alpha: 0.15),
            foregroundColor: ResponsiveHelper.successColor,
            elevation: 0,
            padding: EdgeInsets.symmetric(
              vertical: responsive.spacing(baseSpacing: 16),
            ),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: BorderSide(
                color: ResponsiveHelper.successColor.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
          ),
        ),
      );
    }

    return SizedBox(
      width: double.infinity,
      child: ElevatedButton.icon(
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
        icon: const Icon(Icons.download, size: 18),
        label: Text(
          'Install App',
          style: responsive.labelLarge.copyWith(
            fontWeight: FontWeight.w500,
          ),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
          foregroundColor: ResponsiveHelper.purplePrimary,
          elevation: 0,
          padding: EdgeInsets.symmetric(
            vertical: responsive.spacing(baseSpacing: 16),
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(
              color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
        ),
      ),
    );
  }

  // I'll continue with the rest of the methods in the next parts due to length constraints...

  Widget _buildStatusNotifications(ResponsiveHelper responsive) {
    List<Widget> notifications = [];

    if ((app.isUnderReview() || app.private) && !app.isOwner(SharedPreferencesUtil().uid)) {
      notifications.add(_buildNotification(
        responsive,
        icon: Icons.info_outline,
        text: 'You are a beta tester for this app. It is not public yet. It will be public once approved.',
        color: ResponsiveHelper.infoColor,
      ));
    }

    if (app.isUnderReview() && !app.private && app.isOwner(SharedPreferencesUtil().uid)) {
      notifications.add(_buildNotification(
        responsive,
        icon: Icons.info_outline,
        text: 'Your app is under review and visible only to you. It will be public once approved.',
        color: ResponsiveHelper.infoColor,
      ));
    }

    if (app.isRejected()) {
      notifications.add(_buildNotification(
        responsive,
        icon: Icons.error_outline,
        text: 'Your app has been rejected. Please update the app details and resubmit for review.',
        color: ResponsiveHelper.errorColor,
      ));
    }

    if (notifications.isEmpty) return const SizedBox.shrink();

    return Column(
      children: [
        ...notifications,
        SizedBox(height: responsive.spacing(baseSpacing: 16)),
      ],
    );
  }

  Widget _buildNotification(ResponsiveHelper responsive,
      {required IconData icon, required String text, required Color color}) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
      margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 12)),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: color.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 20),
          SizedBox(width: responsive.spacing(baseSpacing: 12)),
          Expanded(
            child: Text(
              text,
              style: responsive.bodyMedium.copyWith(
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSetupSteps(ResponsiveHelper responsive, int stepsCount) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'Setup Steps',
              style: responsive.titleLarge.copyWith(
                color: ResponsiveHelper.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Spacer(),
            if (setupCompleted)
              Container(
                padding: EdgeInsets.symmetric(
                  horizontal: responsive.spacing(baseSpacing: 8),
                  vertical: responsive.spacing(baseSpacing: 4),
                ),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.successColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  'Completed',
                  style: responsive.bodySmall.copyWith(
                    color: ResponsiveHelper.successColor,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
          ],
        ),
        SizedBox(height: responsive.spacing(baseSpacing: 16)),
        ...app.externalIntegration!.authSteps.mapIndexed<Widget>((i, step) {
          String title = stepsCount == 0 ? step.name : '${i + 1}. ${step.name}';
          return Container(
            margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 8)),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () async {
                  await launchUrl(Uri.parse("${step.url}?uid=${SharedPreferencesUtil().uid}"));
                  checkSetupCompleted();
                },
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                      width: 1,
                    ),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          title,
                          style: responsive.bodyLarge.copyWith(
                            color: ResponsiveHelper.textPrimary,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                      const Icon(
                        Icons.arrow_forward_ios,
                        size: 16,
                        color: ResponsiveHelper.textTertiary,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }).toList(),
        SizedBox(height: responsive.spacing(baseSpacing: 24)),
      ],
    );
  }

  Widget _buildSetupInstructions(ResponsiveHelper responsive) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () async {
              if (app.externalIntegration != null) {
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
              checkSetupCompleted();
            },
            borderRadius: BorderRadius.circular(12),
            child: Container(
              padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Integration Instructions',
                      style: responsive.bodyLarge.copyWith(
                        color: ResponsiveHelper.textPrimary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                  const Icon(
                    Icons.arrow_forward_ios,
                    size: 16,
                    color: ResponsiveHelper.textTertiary,
                  ),
                ],
              ),
            ),
          ),
        ),
        SizedBox(height: responsive.spacing(baseSpacing: 24)),
      ],
    );
  }

  Widget _buildPreviewSection(ResponsiveHelper responsive) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Preview',
          style: responsive.titleLarge.copyWith(
            color: ResponsiveHelper.textPrimary,
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: responsive.spacing(baseSpacing: 16)),
        SizedBox(
          height: responsive.responsiveHeight(baseHeight: 200),
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: app.thumbnailUrls.length,
            separatorBuilder: (context, index) => SizedBox(width: responsive.spacing(baseSpacing: 12)),
            itemBuilder: (context, index) {
              return GestureDetector(
                onTap: () {
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
                child: CachedNetworkImage(
                  imageUrl: app.thumbnailUrls[index],
                  imageBuilder: (context, imageProvider) => Container(
                    width: responsive.responsiveWidth(baseWidth: 120),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                        width: 1,
                      ),
                      image: DecorationImage(
                        image: imageProvider,
                        fit: BoxFit.cover,
                      ),
                    ),
                  ),
                  placeholder: (context, url) => Shimmer.fromColors(
                    baseColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                    highlightColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.1),
                    child: Container(
                      width: responsive.responsiveWidth(baseWidth: 120),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                  errorWidget: (context, url, error) => Container(
                    width: responsive.responsiveWidth(baseWidth: 120),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(Icons.error),
                  ),
                ),
              );
            },
          ),
        ),
        SizedBox(height: responsive.spacing(baseSpacing: 24)),
      ],
    );
  }

  Widget _buildDescriptionSection(ResponsiveHelper responsive) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              if (app.description.decodeString.characters.length > 200) {
                routeToPage(
                  context,
                  MarkdownViewer(
                    title: 'About the ${app.isNotPersona() ? 'App' : 'Persona'}',
                    markdown: app.description.decodeString,
                  ),
                );
              }
            },
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                  width: 1,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        'About the ${app.isNotPersona() ? 'App' : 'Persona'}',
                        style: responsive.titleMedium.copyWith(
                          color: ResponsiveHelper.textPrimary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const Spacer(),
                      if (app.description.decodeString.characters.length > 200)
                        const Icon(
                          Icons.arrow_forward_ios,
                          size: 16,
                          color: ResponsiveHelper.textTertiary,
                        ),
                    ],
                  ),
                  SizedBox(height: responsive.spacing(baseSpacing: 12)),
                  Text(
                    app.description.decodeString.characters.length > 200
                        ? '${app.description.decodeString.characters.take(200)}...'
                        : app.description.decodeString,
                    style: responsive.bodyLarge.copyWith(
                      color: ResponsiveHelper.textSecondary,
                      height: 1.5,
                    ),
                  ),

                  // Capability chips
                  if (app.getCapabilitiesFromIds(context.read<AddAppProvider>().capabilities).isNotEmpty) ...[
                    SizedBox(height: responsive.spacing(baseSpacing: 16)),
                    Wrap(
                      spacing: responsive.spacing(baseSpacing: 8),
                      runSpacing: responsive.spacing(baseSpacing: 8),
                      children: app
                          .getCapabilitiesFromIds(context.read<AddAppProvider>().capabilities)
                          .map((capability) => Container(
                                padding: EdgeInsets.symmetric(
                                  horizontal: responsive.spacing(baseSpacing: 8),
                                  vertical: responsive.spacing(baseSpacing: 4),
                                ),
                                decoration: BoxDecoration(
                                  color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  capability.title,
                                  style: responsive.bodySmall.copyWith(
                                    color: ResponsiveHelper.purplePrimary,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ))
                          .toList(),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
        SizedBox(height: responsive.spacing(baseSpacing: 16)),
      ],
    );
  }

  Widget _buildPromptSection(ResponsiveHelper responsive, String title, String prompt) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              if (prompt.decodeString.characters.length > 200) {
                routeToPage(
                  context,
                  MarkdownViewer(title: title, markdown: prompt.decodeString),
                );
              }
            },
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                  width: 1,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        title,
                        style: responsive.titleMedium.copyWith(
                          color: ResponsiveHelper.textPrimary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const Spacer(),
                      if (prompt.decodeString.characters.length > 200)
                        const Icon(
                          Icons.arrow_forward_ios,
                          size: 16,
                          color: ResponsiveHelper.textTertiary,
                        ),
                    ],
                  ),
                  SizedBox(height: responsive.spacing(baseSpacing: 12)),
                  Text(
                    prompt.decodeString.characters.length > 200
                        ? '${prompt.decodeString.characters.take(200)}...'
                        : prompt.decodeString,
                    style: responsive.bodyLarge.copyWith(
                      color: ResponsiveHelper.textSecondary,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        SizedBox(height: responsive.spacing(baseSpacing: 16)),
      ],
    );
  }

  Widget _buildReviewsSection(ResponsiveHelper responsive) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              if (app.reviews.isNotEmpty) {
                MixpanelManager().appDetailReviewsOpened(
                  appId: app.id,
                  reviewCount: app.reviews.length,
                );
                routeToPage(context, ReviewsListPage(app: app));
              }
            },
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                  width: 1,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        'Ratings & Reviews',
                        style: responsive.titleMedium.copyWith(
                          color: ResponsiveHelper.textPrimary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const Spacer(),
                      if (app.reviews.isNotEmpty)
                        const Icon(
                          Icons.arrow_forward_ios,
                          size: 16,
                          color: ResponsiveHelper.textTertiary,
                        ),
                    ],
                  ),
                  SizedBox(height: responsive.spacing(baseSpacing: 16)),
                  Row(
                    children: [
                      Text(
                        app.getRatingAvg() ?? '0.0',
                        style: responsive.displayMedium.copyWith(
                          color: ResponsiveHelper.textPrimary,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const Spacer(),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          RatingBar.builder(
                            initialRating: app.ratingAvg ?? 0,
                            minRating: 1,
                            ignoreGestures: true,
                            direction: Axis.horizontal,
                            allowHalfRating: true,
                            itemCount: 5,
                            itemSize: 16,
                            tapOnlyMode: false,
                            itemPadding: EdgeInsets.zero,
                            itemBuilder: (context, _) => const Icon(
                              Icons.star,
                              color: ResponsiveHelper.purplePrimary,
                            ),
                            maxRating: 5.0,
                            onRatingUpdate: (rating) {},
                          ),
                          SizedBox(height: responsive.spacing(baseSpacing: 4)),
                          Text(
                            app.ratingCount <= 0 ? "no ratings" : "${app.ratingCount}+ ratings",
                            style: responsive.bodySmall.copyWith(
                              color: ResponsiveHelper.textTertiary,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),

                  // Recent reviews preview
                  if (app.reviews.isNotEmpty) ...[
                    SizedBox(height: responsive.spacing(baseSpacing: 16)),
                    const Divider(color: ResponsiveHelper.backgroundTertiary),
                    SizedBox(height: responsive.spacing(baseSpacing: 16)),
                    ...app.reviews
                        .sorted((a, b) => b.ratedAt.compareTo(a.ratedAt))
                        .take(2)
                        .map((review) => Container(
                              margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 12)),
                              padding: EdgeInsets.all(responsive.spacing(baseSpacing: 12)),
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      RatingBar.builder(
                                        initialRating: review.score.toDouble(),
                                        minRating: 1,
                                        ignoreGestures: true,
                                        direction: Axis.horizontal,
                                        allowHalfRating: true,
                                        itemCount: 5,
                                        itemSize: 12,
                                        tapOnlyMode: false,
                                        itemPadding: EdgeInsets.zero,
                                        itemBuilder: (context, _) => const Icon(
                                          Icons.star,
                                          color: ResponsiveHelper.purplePrimary,
                                        ),
                                        maxRating: 5.0,
                                        onRatingUpdate: (rating) {},
                                      ),
                                      SizedBox(width: responsive.spacing(baseSpacing: 8)),
                                      Text(
                                        timeago.format(review.ratedAt),
                                        style: responsive.bodySmall.copyWith(
                                          color: ResponsiveHelper.textQuaternary,
                                        ),
                                      ),
                                    ],
                                  ),
                                  SizedBox(height: responsive.spacing(baseSpacing: 8)),
                                  Text(
                                    review.review.length > 100
                                        ? '${review.review.characters.take(100).toString().decodeString.trim()}...'
                                        : review.review.decodeString,
                                    style: responsive.bodyMedium.copyWith(
                                      color: ResponsiveHelper.textSecondary,
                                    ),
                                  ),
                                ],
                              ),
                            ))
                        .toList(),
                  ],
                ],
              ),
            ),
          ),
        ),
        SizedBox(height: responsive.spacing(baseSpacing: 16)),
      ],
    );
  }

  // Action handlers
  void _handleChatTap() async {
    MixpanelManager().appDetailChatClicked(
      appId: app.id,
      appName: app.name,
    );
    await _handleClose();
    // Same logic as mobile
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
  }

  void _handleWebAppTap() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => AppHomeWebPage(app: app),
      ),
    );
  }

  void _handleShareTap() {
    MixpanelManager().appDetailShared(
      appId: app.id,
      appName: app.name,
    );
    if (app.isNotPersona()) {
      Share.share(
        'https://h.omi.me/apps/${app.id}',
        subject: app.name,
      );
    } else {
      Share.share(
        'Check out this Persona on Omi AI: ${app.name} by ${app.author} \n\n${app.description.decodeString}\n\n\nhttps://personas.omi.me/u/${app.username}',
        subject: app.name,
      );
    }
  }

  void _handleSettingsTap() async {
    MixpanelManager().appDetailSettingsOpened(
      appId: app.id,
    );
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
  }

  Future<void> _toggleApp(String appId, bool isEnabled) async {
    // Same toggle logic as mobile
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
    // context.read<AppProvider>().setApps();
    setState(() => app.enabled = isEnabled);
    setState(() => appLoading = false);
  }
}
