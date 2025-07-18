import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/settings/privacy.dart';
import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_info_card.dart';
import 'package:omi/ui/atoms/omi_profile_avatar.dart';
import 'package:omi/ui/atoms/omi_section.dart';
import 'package:omi/ui/atoms/omi_settings_tile.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class DesktopProfilePage extends StatefulWidget {
  const DesktopProfilePage({super.key});

  @override
  State<DesktopProfilePage> createState() => _DesktopProfilePageState();
}

class _DesktopProfilePageState extends State<DesktopProfilePage> with TickerProviderStateMixin {
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOutCubic),
    );
    _fadeController.forward();
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);
    final userName = SharedPreferencesUtil().givenName;
    final userEmail = SharedPreferencesUtil().email;

    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      body: FadeTransition(
        opacity: _fadeAnimation,
        child: Container(
          width: double.infinity,
          height: double.infinity,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                ResponsiveHelper.backgroundPrimary,
                ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
              ],
            ),
          ),
          child: Row(
            children: [
              // Main content area
              Expanded(
                child: Container(
                  padding: responsive.contentPadding(basePadding: 32),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Header with back button
                      _buildHeader(responsive),

                      const SizedBox(height: 32),

                      // Main content
                      Expanded(
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Left column - Profile info
                            Expanded(
                              flex: 1,
                              child: _buildProfileInfoCard(responsive, userName, userEmail),
                            ),

                            const SizedBox(width: 24),

                            // Right column - Settings sections
                            Expanded(
                              flex: 2,
                              child: _buildSettingsSections(responsive),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(ResponsiveHelper responsive) {
    return Row(
      children: [
        OmiIconButton(
          icon: FontAwesomeIcons.arrowLeft,
          style: OmiIconButtonStyle.outline,
          size: 40,
          iconSize: 16,
          borderRadius: 12,
          onPressed: () => Navigator.of(context).pop(),
        ),
        const SizedBox(width: 16),
        Text(
          'Profile Settings',
          style: responsive.headlineLarge.copyWith(
            fontWeight: FontWeight.w400,
          ),
        ),
      ],
    );
  }

  Widget _buildProfileInfoCard(ResponsiveHelper responsive, String userName, String userEmail) {
    return OmiInfoCard(
      children: [
        // Large profile avatar
        OmiProfileAvatar(
          size: 120,
          fallbackText: userName.isNotEmpty ? userName[0].toUpperCase() : 'U',
        ),

        const SizedBox(height: 24),

        // User name
        Text(
          userName.isNotEmpty ? userName : 'User',
          style: responsive.headlineMedium.copyWith(
            fontWeight: FontWeight.w600,
          ),
          textAlign: TextAlign.center,
        ),

        const SizedBox(height: 8),

        // User email
        Text(
          userEmail.isNotEmpty ? userEmail : 'No email set',
          style: responsive.bodyLarge.copyWith(
            color: ResponsiveHelper.textTertiary,
          ),
          textAlign: TextAlign.center,
        ),

        const SizedBox(height: 24),

        // User ID section
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'User ID',
                style: responsive.bodySmall.copyWith(
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textTertiary,
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      SharedPreferencesUtil().uid,
                      style: responsive.bodyMedium.copyWith(
                        fontFamily: 'monospace',
                        color: ResponsiveHelper.textSecondary,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  OmiIconButton(
                    icon: FontAwesomeIcons.copy,
                    style: OmiIconButtonStyle.neutral,
                    size: 32,
                    iconSize: 12,
                    borderRadius: 8,
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: const Text('User ID copied to clipboard'),
                          backgroundColor: ResponsiveHelper.backgroundTertiary,
                          behavior: SnackBarBehavior.floating,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          duration: const Duration(seconds: 2),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSettingsSections(ResponsiveHelper responsive) {
    return SingleChildScrollView(
      child: Column(
        children: [
          // Your Information Section
          OmiSection(
            title: 'Your Information',
            icon: FontAwesomeIcons.user,
            children: [
              OmiSettingsTile(
                title: SharedPreferencesUtil().givenName.isEmpty ? 'Set Your Name' : 'Change Your Name',
                subtitle: SharedPreferencesUtil().givenName.isEmpty ? 'Not set' : SharedPreferencesUtil().givenName,
                icon: FontAwesomeIcons.user,
                onTap: () async {
                  MixpanelManager().pageOpened('Profile Change Name');
                  await showDialog(
                    context: context,
                    builder: (BuildContext context) => const ChangeNameWidget(),
                  ).whenComplete(() => setState(() {}));
                },
              ),
              Consumer<HomeProvider>(
                builder: (context, homeProvider, _) {
                  final languageName = homeProvider.userPrimaryLanguage.isNotEmpty
                      ? homeProvider.availableLanguages.entries
                          .firstWhere(
                            (element) => element.value == homeProvider.userPrimaryLanguage,
                          )
                          .key
                      : 'Not set';

                  return OmiSettingsTile(
                    title: 'Primary Language',
                    subtitle: languageName,
                    icon: FontAwesomeIcons.language,
                    onTap: () async {
                      MixpanelManager().pageOpened('Profile Change Language');
                      await LanguageSelectionDialog.show(context, isRequired: false, forceShow: true);
                      await homeProvider.setupUserPrimaryLanguage();
                      setState(() {});
                    },
                  );
                },
              ),
              OmiSettingsTile(
                title: 'Persona',
                subtitle: 'Manage your Omi persona',
                icon: FontAwesomeIcons.userGear,
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const PersonaProfilePage(),
                      settings: const RouteSettings(arguments: 'from_settings'),
                    ),
                  );
                  MixpanelManager().pageOpened('Profile Persona Settings');
                },
              ),
            ],
          ),

          const SizedBox(height: 32),

          // Voice & People Section
          OmiSection(
            title: 'Voice & People',
            icon: FontAwesomeIcons.microphone,
            children: [
              OmiSettingsTile(
                title: 'Speech Profile',
                subtitle: 'Teach Omi your voice',
                icon: FontAwesomeIcons.waveSquare,
                onTap: () {
                  routeToPage(context, const SpeechProfilePage());
                  MixpanelManager().pageOpened('Profile Speech Profile');
                },
              ),
              OmiSettingsTile(
                title: 'Identifying Others',
                subtitle: 'Tell Omi who said it 🗣️',
                icon: FontAwesomeIcons.users,
                onTap: () {
                  routeToPage(context, const UserPeoplePage());
                },
              ),
            ],
          ),

          const SizedBox(height: 32),

          // Payment Section
          OmiSection(
            title: 'Payment',
            icon: FontAwesomeIcons.creditCard,
            children: [
              OmiSettingsTile(
                title: 'Payment Methods',
                subtitle: 'Add or change your payment method',
                icon: FontAwesomeIcons.wallet,
                onTap: () {
                  routeToPage(context, const PaymentsPage());
                },
              ),
            ],
          ),

          const SizedBox(height: 32),

          // Preferences Section
          OmiSection(
            title: 'Preferences',
            icon: FontAwesomeIcons.sliders,
            children: [
              _buildPreferenceTile(
                title: 'Help improve Omi by sharing anonymized analytics data',
                value: SharedPreferencesUtil().optInAnalytics,
                onChanged: (value) {
                  setState(() {
                    SharedPreferencesUtil().optInAnalytics = value;
                    value ? MixpanelManager().optInTracking() : MixpanelManager().optOutTracking();
                  });
                },
                onInfoTap: () {
                  routeToPage(context, const PrivacyInfoPage());
                  MixpanelManager().pageOpened('Share Analytics Data Details');
                },
              ),
            ],
          ),

          const SizedBox(height: 32),

          // Account Section
          OmiSection(
            title: 'Account',
            icon: FontAwesomeIcons.userShield,
            children: [
              OmiSettingsTile(
                title: 'Delete Account',
                subtitle: 'Delete your account and all data',
                icon: FontAwesomeIcons.triangleExclamation,
                iconColor: ResponsiveHelper.errorColor,
                textColor: ResponsiveHelper.errorColor,
                onTap: () {
                  MixpanelManager().pageOpened('Profile Delete Account Dialog');
                  Navigator.push(context, MaterialPageRoute(builder: (context) => const DeleteAccount()));
                },
              ),
            ],
          ),

          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildPreferenceTile({
    required String title,
    required bool value,
    required Function(bool) onChanged,
    required VoidCallback onInfoTap,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.transparent,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.infoColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(
                  FontAwesomeIcons.chartLine,
                  size: 18,
                  color: ResponsiveHelper.infoColor,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: GestureDetector(
                  onTap: onInfoTap,
                  child: Text(
                    title,
                    style: const TextStyle(
                      color: ResponsiveHelper.textSecondary,
                      fontSize: 14,
                      decoration: TextDecoration.underline,
                      decorationColor: ResponsiveHelper.textTertiary,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              OmiCheckbox(
                value: value,
                onChanged: onChanged,
                size: 20,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
