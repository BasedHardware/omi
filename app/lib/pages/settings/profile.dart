import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/settings/privacy.dart';
import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/persona/persona_profile.dart';

import 'delete_account.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  @override
  void initState() {
    super.initState();
  }

  Widget _buildSectionContainer({required List<Widget> children}) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: children,
      ),
    );
  }

  Widget _buildProfileItem({
    required String title,
    String? subtitle,
    required Widget icon,
    required VoidCallback onTap,
    bool showSubtitle = true,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              SizedBox(
                width: 24,
                height: 24,
                child: icon,
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    if (showSubtitle && subtitle != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: const TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 15,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const Icon(
                Icons.chevron_right,
                color: Color(0xFF3C3C43),
                size: 20,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPreferenceToggle({
    required String title,
    required bool value,
    required Function(bool) onChanged,
    required VoidCallback onInfoTap,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            SizedBox(
              width: 24,
              height: 24,
              child: FaIcon(FontAwesomeIcons.chartLine, color: Color(0xFF8E8E93), size: 20),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: GestureDetector(
                onTap: onInfoTap,
                child: Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
            GestureDetector(
              onTap: () => onChanged(!value),
              child: Container(
                decoration: BoxDecoration(
                  color: value ? const Color(0xFF007AFF) : Colors.transparent,
                  border: Border.all(
                    color: value ? const Color(0xFF007AFF) : const Color(0xFF8E8E93),
                    width: 2,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                width: 24,
                height: 24,
                child: value
                    ? const Icon(
                        Icons.check,
                        color: Colors.white,
                        size: 16,
                      )
                    : null,
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        title: const Text(
          'Profile',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
        backgroundColor: const Color(0xFF000000),
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          children: <Widget>[
            const SizedBox(height: 20),

            // YOUR INFORMATION SECTION
            _buildSectionContainer(
              children: [
                _buildProfileItem(
                  title: SharedPreferencesUtil().givenName.isEmpty ? 'Set Your Name' : 'Change Your Name',
                  subtitle: SharedPreferencesUtil().givenName.isEmpty ? 'Not set' : SharedPreferencesUtil().givenName,
                  icon: const FaIcon(FontAwesomeIcons.solidUser, color: Color(0xFF8E8E93), size: 20),
                  onTap: () async {
                    MixpanelManager().pageOpened('Profile Change Name');
                    await showDialog(
                      context: context,
                      builder: (BuildContext context) {
                        return const ChangeNameWidget();
                      },
                    ).whenComplete(() => setState(() {}));
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                Consumer<HomeProvider>(
                  builder: (context, homeProvider, _) {
                    final languageName = homeProvider.userPrimaryLanguage.isNotEmpty
                        ? homeProvider.availableLanguages.entries
                            .firstWhere(
                              (element) => element.value == homeProvider.userPrimaryLanguage,
                            )
                            .key
                        : 'Not set';

                    return _buildProfileItem(
                      title: 'Primary Language',
                      subtitle: languageName,
                      icon: const FaIcon(FontAwesomeIcons.globe, color: Color(0xFF8E8E93), size: 20),
                      onTap: () async {
                        MixpanelManager().pageOpened('Profile Change Language');
                        await LanguageSelectionDialog.show(context, isRequired: false, forceShow: true);
                        await homeProvider.setupUserPrimaryLanguage();
                        setState(() {});
                      },
                    );
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: 'Persona',
                  subtitle: 'Manage your Omi persona',
                  icon: const FaIcon(FontAwesomeIcons.solidCircleUser, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => const PersonaProfilePage(),
                        settings: const RouteSettings(
                          arguments: 'from_settings',
                        ),
                      ),
                    );
                    MixpanelManager().pageOpened('Profile Persona Settings');
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // VOICE & PEOPLE SECTION
            _buildSectionContainer(
              children: [
                _buildProfileItem(
                  title: 'Speech Profile',
                  subtitle: 'Teach Omi your voice',
                  icon: const FaIcon(FontAwesomeIcons.microphone, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const SpeechProfilePage());
                    MixpanelManager().pageOpened('Profile Speech Profile');
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: 'Identifying Others',
                  subtitle: 'Tell Omi who said it 🗣️',
                  icon: const FaIcon(FontAwesomeIcons.users, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const UserPeoplePage());
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // PAYMENT SECTION
            _buildSectionContainer(
              children: [
                _buildProfileItem(
                  title: 'Payment Methods',
                  subtitle: 'Add or change your payment method',
                  icon: const FaIcon(FontAwesomeIcons.solidCreditCard, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const PaymentsPage());
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // PREFERENCES SECTION
            _buildPreferenceToggle(
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
            const SizedBox(height: 32),

            // ACCOUNT SECTION
            _buildSectionContainer(
              children: [
                _buildProfileItem(
                  title: 'User ID',
                  subtitle: SharedPreferencesUtil().uid,
                  icon: const FaIcon(FontAwesomeIcons.solidClipboard, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('User ID copied to clipboard')));
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: 'Delete Account',
                  subtitle: 'Delete your account and all data',
                  icon: const FaIcon(FontAwesomeIcons.exclamationTriangle, color: Colors.red, size: 20),
                  onTap: () {
                    MixpanelManager().pageOpened('Profile Delete Account Dialog');
                    Navigator.push(context, MaterialPageRoute(builder: (context) => const DeleteAccount()));
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }
}
