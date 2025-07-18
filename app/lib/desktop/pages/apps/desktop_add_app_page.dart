import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/external_trigger_fields_widget.dart';
import 'package:omi/pages/apps/widgets/full_screen_image_viewer.dart';
import 'package:omi/pages/apps/widgets/payment_details_widget.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

// Desktop widgets
import 'widgets/desktop_app_metadata_widget.dart';
import 'widgets/desktop_capabilities_chips_widget.dart';
import 'widgets/desktop_prompt_text_field.dart';
import 'widgets/desktop_notification_scopes_chips_widget.dart';

class DesktopAddAppPage extends StatefulWidget {
  final VoidCallback? onNavigateBack;

  const DesktopAddAppPage({
    super.key,
    this.onNavigateBack,
  });

  @override
  State<DesktopAddAppPage> createState() => _DesktopAddAppPageState();
}

class _DesktopAddAppPageState extends State<DesktopAddAppPage> with TickerProviderStateMixin {
  late bool showSubmitAppConfirmation;

  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;

  @override
  void initState() {
    super.initState();
    showSubmitAppConfirmation = SharedPreferencesUtil().showSubmitAppConfirmation;

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _slideController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOutCubic),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _slideController, curve: Curves.easeOutCubic));

    _pulseAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _animationsInitialized = true;

    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await Provider.of<AddAppProvider>(context, listen: false).init();

      _fadeController.forward();
      _slideController.forward();
    });
  }

  @override
  void dispose() {
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        return Scaffold(
          backgroundColor: Colors.transparent,
          body: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  ResponsiveHelper.backgroundPrimary,
                  ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
                ],
              ),
            ),
            child: Stack(
              children: [
                _buildAnimatedBackground(),
                // Main content
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.02),
                  ),
                  child: Column(
                    children: [
                      _buildHeader(),
                      Expanded(
                        child: _animationsInitialized
                            ? FadeTransition(
                                opacity: _fadeAnimation,
                                child: SlideTransition(
                                  position: _slideAnimation,
                                  child: _buildMainContent(provider),
                                ),
                              )
                            : _buildMainContent(provider),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildAnimatedBackground() {
    if (!_animationsInitialized) {
      return Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 2.0,
            colors: [
              ResponsiveHelper.purplePrimary.withOpacity(0.05),
              Colors.transparent,
            ],
          ),
        ),
      );
    }

    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Container(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: Alignment.topRight,
              radius: 2.0,
              colors: [
                ResponsiveHelper.purplePrimary.withOpacity(0.05 + _pulseAnimation.value * 0.03),
                Colors.transparent,
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
        border: Border(
          bottom: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          // Back button
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () {
                if (widget.onNavigateBack != null) {
                  widget.onNavigateBack!();
                } else {
                  Navigator.pop(context);
                }
              },
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  FontAwesomeIcons.arrowLeft,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
              ),
            ),
          ),

          const SizedBox(width: 8),

          // Create app icon and title
          // Container(
          //   padding: const EdgeInsets.all(8),
          //   decoration: BoxDecoration(
          //     color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
          //     borderRadius: BorderRadius.circular(8),
          //   ),
          //   child: Icon(
          //     FontAwesomeIcons.plus,
          //     color: ResponsiveHelper.purplePrimary,
          //     size: 16,
          //   ),
          // ),

          const SizedBox(width: 12),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Create New App',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                    color: ResponsiveHelper.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  'Build and submit your custom Omi app',
                  style: TextStyle(
                    fontSize: 12,
                    color: ResponsiveHelper.textSecondary.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMainContent(AddAppProvider provider) {
    if (provider.isLoading || provider.isSubmitting) {
      return _buildLoadingState(provider);
    }

    return Container(
      padding: const EdgeInsets.all(20),
      child: Container(
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.1),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          children: [
            // Form content
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: GestureDetector(
                  onTap: () {
                    FocusScope.of(context).unfocus();
                  },
                  child: Form(
                    key: provider.formKey,
                    onChanged: () {
                      provider.checkValidity();
                    },
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Help section
                        _buildHelpSection(),

                        const SizedBox(height: 24),

                        // App metadata section - using desktop widget
                        _buildSectionCard(
                          title: 'App Details',
                          icon: FontAwesomeIcons.info,
                          child: DesktopAppMetadataWidget(
                            pickImage: () async {
                              await provider.pickImage();
                            },
                            generatingDescription: provider.isGenratingDescription,
                            allowPaidApps: provider.allowPaidApps,
                            appPricing: provider.isPaid ? 'Paid' : 'Free',
                            appNameController: provider.appNameController,
                            appDescriptionController: provider.appDescriptionController,
                            categories: provider.categories,
                            setAppCategory: provider.setAppCategory,
                            imageFile: provider.imageFile,
                            category: provider.mapCategoryIdToName(provider.appCategory),
                          ),
                        ),

                        // Payment details (if paid app)
                        if (provider.isPaid) ...[
                          const SizedBox(height: 24),
                          _buildSectionCard(
                            title: 'Payment Details',
                            icon: FontAwesomeIcons.creditCard,
                            child: PaymentDetailsWidget(
                              appPricingController: provider.priceController,
                              paymentPlan: provider.mapPaymentPlanIdToName(provider.selectePaymentPlan),
                            ),
                          ),
                        ],

                        const SizedBox(height: 24),

                        // Screenshots section
                        _buildScreenshotsSection(provider),

                        const SizedBox(height: 24),

                        // Capabilities section - using desktop widget
                        _buildSectionCard(
                          title: 'App Capabilities',
                          icon: FontAwesomeIcons.cogs,
                          child: const DesktopCapabilitiesChipsWidget(),
                        ),

                        // Prompts section (if applicable) - using desktop widgets
                        if (provider.isCapabilitySelectedById('chat') ||
                            provider.isCapabilitySelectedById('memories')) ...[
                          const SizedBox(height: 24),
                          _buildDesktopPromptsSection(provider),
                        ],

                        // External triggers
                        const SizedBox(height: 24),
                        const ExternalTriggerFieldsWidget(),

                        // Notification scopes (if applicable) - using desktop widget
                        if (provider.isCapabilitySelectedById('proactive_notification')) ...[
                          const SizedBox(height: 24),
                          _buildSectionCard(
                            title: 'Notification Scopes',
                            icon: FontAwesomeIcons.bell,
                            child: const DesktopNotificationScopesChipsWidget(),
                          ),
                        ],

                        const SizedBox(height: 24),

                        // Privacy section
                        _buildPrivacySection(provider),

                        const SizedBox(height: 40),
                      ],
                    ),
                  ),
                ),
              ),
            ),

            // Bottom submit section
            _buildSubmitSection(provider),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadingState(AddAppProvider provider) {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(40),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.1),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.1),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _animationsInitialized
                ? AnimatedBuilder(
                    animation: _pulseController,
                    builder: (context, child) {
                      return Transform.scale(
                        scale: 1.0 + (_pulseAnimation.value * 0.1),
                        child: Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.purplePrimary,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            strokeWidth: 2,
                          ),
                        ),
                      );
                    },
                  )
                : Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.purplePrimary,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      strokeWidth: 2,
                    ),
                  ),
            const SizedBox(height: 16),
            Text(
              provider.isSubmitting ? 'Submitting your app...' : 'Preparing the form for you...',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionCard({
    required String title,
    required IconData icon,
    required Widget child,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(12),
                topRight: Radius.circular(12),
              ),
              border: Border(
                bottom: BorderSide(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                  width: 1,
                ),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  icon,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: child,
          ),
        ],
      ),
    );
  }

  Widget _buildHelpSection() {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          MixpanelManager().pageOpened('App Submission Help');
          launchUrl(Uri.parse('https://omi.me/apps/introduction'));
        },
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          child: const Row(
            children: [
              Icon(
                FontAwesomeIcons.lightbulb,
                color: ResponsiveHelper.purplePrimary,
                size: 20,
              ),
              SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Need help getting started?',
                      style: TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'Click here for app building guides and documentation',
                      style: TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                FontAwesomeIcons.externalLink,
                color: ResponsiveHelper.purplePrimary,
                size: 16,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildScreenshotsSection(AddAppProvider provider) {
    return _buildSectionCard(
      title: 'Preview and Screenshots',
      icon: FontAwesomeIcons.images,
      child: SizedBox(
        height: 180,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          itemCount: provider.thumbnailUrls.length + 1,
          itemBuilder: (context, index) {
            final width = 120.0;
            final height = width * 1.5; // 2:3 ratio

            if (index == provider.thumbnailUrls.length) {
              return GestureDetector(
                onTap: provider.isUploadingThumbnail ? null : provider.pickThumbnail,
                child: Container(
                  width: width,
                  height: height,
                  margin: const EdgeInsets.only(right: 8),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                      width: 1,
                    ),
                  ),
                  child: provider.isUploadingThumbnail
                      ? Shimmer.fromColors(
                          baseColor: ResponsiveHelper.backgroundTertiary,
                          highlightColor: ResponsiveHelper.backgroundSecondary,
                          child: Container(
                            width: width,
                            height: height,
                            decoration: BoxDecoration(
                              color: ResponsiveHelper.backgroundTertiary,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Icon(Icons.photo, size: 32),
                          ),
                        )
                      : const Icon(
                          Icons.add_photo_alternate_outlined,
                          size: 32,
                          color: ResponsiveHelper.textTertiary,
                        ),
                ),
              );
            }
            return Stack(
              children: [
                GestureDetector(
                  onTap: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (context) => FullScreenImageViewer(
                          imageUrl: provider.thumbnailUrls[index],
                        ),
                      ),
                    );
                  },
                  child: CachedNetworkImage(
                    imageUrl: provider.thumbnailUrls[index],
                    imageBuilder: (context, imageProvider) => Container(
                      width: 120,
                      height: 180,
                      margin: const EdgeInsets.only(right: 8),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
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
                      baseColor: ResponsiveHelper.backgroundTertiary,
                      highlightColor: ResponsiveHelper.backgroundSecondary,
                      child: Container(
                        width: 120,
                        height: 180,
                        margin: const EdgeInsets.only(right: 8),
                        decoration: BoxDecoration(
                          color: ResponsiveHelper.backgroundTertiary,
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                    ),
                    errorWidget: (context, url, error) => Container(
                      width: 120,
                      height: 180,
                      margin: const EdgeInsets.only(right: 8),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.error),
                    ),
                  ),
                ),
                Positioned(
                  top: 4,
                  right: 12,
                  child: GestureDetector(
                    onTap: () => provider.removeThumbnail(index),
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.6),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.close, size: 16, color: Colors.white),
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildDesktopPromptsSection(AddAppProvider provider) {
    return _buildSectionCard(
      title: 'AI Prompts',
      icon: FontAwesomeIcons.brain,
      child: Form(
        key: provider.promptKey,
        onChanged: () {
          provider.checkValidity();
        },
        child: Column(
          children: [
            if (provider.isCapabilitySelectedById('chat'))
              DesktopPromptTextField(
                controller: provider.chatPromptController,
                label: 'Chat Prompt',
                hint: 'You are an awesome app, your job is to respond to the user queries and make them feel good...',
              ),
            if (provider.isCapabilitySelectedById('memories') && provider.isCapabilitySelectedById('chat'))
              const SizedBox(height: 20),
            if (provider.isCapabilitySelectedById('memories'))
              DesktopPromptTextField(
                controller: provider.conversationPromptController,
                label: 'Conversation Prompt',
                hint: 'You are an awesome app, you will be given transcript and summary of a conversation...',
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildPrivacySection(AddAppProvider provider) {
    return _buildSectionCard(
      title: 'App Privacy & Terms',
      icon: FontAwesomeIcons.shield,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Checkbox(
                value: provider.makeAppPublic,
                onChanged: (value) {
                  if (value != null) {
                    provider.setIsPrivate(value);
                  }
                },
                activeColor: ResponsiveHelper.purplePrimary,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              const Expanded(
                child: Text(
                  'Make my app public',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Checkbox(
                value: provider.termsAgreed,
                onChanged: provider.setTermsAgreed,
                activeColor: ResponsiveHelper.purplePrimary,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              const Expanded(
                child: Text(
                  'By submitting this app, I agree to the Omi AI Terms of Service and Privacy Policy',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    height: 1.4,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSubmitSection(AddAppProvider provider) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
        borderRadius: const BorderRadius.only(
          bottomLeft: Radius.circular(16),
          bottomRight: Radius.circular(16),
        ),
        border: Border(
          top: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: !provider.isValid ? null : () => _handleSubmit(provider),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                  decoration: BoxDecoration(
                    color: provider.isValid
                        ? ResponsiveHelper.purplePrimary
                        : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: provider.isValid
                        ? [
                            BoxShadow(
                              color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                              blurRadius: 8,
                              offset: const Offset(0, 4),
                            ),
                          ]
                        : [],
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        FontAwesomeIcons.paperPlane,
                        color: provider.isValid ? Colors.white : ResponsiveHelper.textQuaternary,
                        size: 16,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'Submit App',
                        style: TextStyle(
                          color: provider.isValid ? Colors.white : ResponsiveHelper.textQuaternary,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _handleSubmit(AddAppProvider provider) {
    var isValid = provider.validateForm();
    if (isValid) {
      showDialog(
        context: context,
        builder: (ctx) {
          return ConfirmationDialog(
            title: 'Submit App?',
            description: provider.makeAppPublic
                ? 'Your app will be reviewed and made public. You can start using it immediately, even during the review!'
                : 'Your app will be reviewed and made available to you privately. You can start using it immediately, even during the review!',
            checkboxText: "Don't show it again",
            checkboxValue: !showSubmitAppConfirmation,
            onCheckboxChanged: (value) {
              setState(() {
                showSubmitAppConfirmation = !value;
              });
            },
            onConfirm: () async {
              if (provider.makeAppPublic) {
                MixpanelManager().publicAppSubmitted({
                  'app_name': provider.appNameController.text,
                  'app_category': provider.appCategory,
                  'app_capabilities': provider.capabilities.map((e) => e.id).toList(),
                  'is_paid': provider.isPaid,
                });
              } else {
                MixpanelManager().privateAppSubmitted({
                  'app_name': provider.appNameController.text,
                  'app_category': provider.appCategory,
                  'app_capabilities': provider.capabilities.map((e) => e.id).toList(),
                  'is_paid': provider.isPaid,
                });
              }
              SharedPreferencesUtil().showSubmitAppConfirmation = showSubmitAppConfirmation;
              Navigator.pop(context);
              String? appId = await provider.submitApp();
              App? app;
              if (appId != null) {
                app = await context.read<AppProvider>().getAppFromId(appId);
              }
              var paymentProvider = context.read<PaymentMethodProvider>();
              paymentProvider.getPaymentMethodsStatus();

              if (app != null && mounted && context.mounted) {
                if (app.isPaid && paymentProvider.activeMethod == null) {
                  showCupertinoModalPopup(
                    context: context,
                    builder: (ctx) => Container(
                      padding: const EdgeInsets.all(20),
                      decoration: const BoxDecoration(
                        color: ResponsiveHelper.backgroundSecondary,
                        borderRadius: BorderRadius.vertical(
                          top: Radius.circular(20),
                        ),
                      ),
                      child: Material(
                        color: Colors.transparent,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 40,
                              height: 4,
                              margin: const EdgeInsets.only(bottom: 20),
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.textQuaternary,
                                borderRadius: BorderRadius.circular(2),
                              ),
                            ),
                            const SizedBox(height: 20),
                            const Text(
                              'Start Earning! 💰',
                              style: TextStyle(
                                color: ResponsiveHelper.textPrimary,
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 12),
                            const Text(
                              'Connect Stripe or PayPal to receive payments for your app.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: ResponsiveHelper.textSecondary,
                                fontSize: 16,
                              ),
                            ),
                            const SizedBox(height: 32),
                            CupertinoButton(
                              color: ResponsiveHelper.purplePrimary,
                              borderRadius: BorderRadius.circular(12),
                              onPressed: () {
                                Navigator.pop(ctx);
                                routeToPage(context, const PaymentsPage());
                              },
                              child: const Text(
                                'Connect Now',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                            const SizedBox(height: 8),
                            CupertinoButton(
                              onPressed: () => Navigator.pop(ctx),
                              child: const Text(
                                'Maybe Later',
                                style: TextStyle(
                                  color: ResponsiveHelper.textSecondary,
                                ),
                              ),
                            ),
                            SizedBox(height: MediaQuery.of(context).padding.bottom),
                          ],
                        ),
                      ),
                    ),
                  );
                } else {
                  // Navigate back to apps page
                  if (widget.onNavigateBack != null) {
                    widget.onNavigateBack!();
                  } else {
                    Navigator.pop(context);
                  }
                  routeToPage(context, AppDetailPage(app: app));
                }
              }
            },
            onCancel: () {
              Navigator.pop(context);
            },
          );
        },
      );
    }
  }
}
