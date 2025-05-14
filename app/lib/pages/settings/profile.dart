import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/memories/page.dart';
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

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(top: 18, bottom: 8),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          title,
          style: const TextStyle(
            color: Color(0xFFE0E0E0),
            fontSize: 14,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.2,
          ),
        ),
      ),
    );
  }

  Widget _buildProfileTile({
    required String title,
    required String subtitle,
    required IconData icon,
    required VoidCallback onTap,
    Color iconColor = Colors.white,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF1D1D1D),
        borderRadius: BorderRadius.circular(10),
      ),
      child: ListTile(
        dense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        title: Text(
          title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 15,
            fontWeight: FontWeight.w500,
          ),
        ),
        subtitle: Text(
          subtitle,
          style: const TextStyle(
            color: Color(0xFFAAAAAA),
            fontSize: 13,
          ),
        ),
        trailing: Icon(icon, size: 20, color: iconColor),
        onTap: onTap,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
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
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1D1D1D),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: GestureDetector(
              onTap: onInfoTap,
              child: Text(
                title,
                style: const TextStyle(
                  color: Color(0xFFAAAAAA),
                  fontSize: 14,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
          ),
          const SizedBox(width: 16),
          GestureDetector(
            onTap: () => onChanged(!value),
            child: Container(
              decoration: BoxDecoration(
                color: value ? const Color(0xFF4A90E2) : Colors.transparent,
                border: Border.all(
                  color: value ? const Color(0xFF4A90E2) : const Color(0xFFAAAAAA),
                  width: 2,
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              width: 20,
              height: 20,
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
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text(
          'Profile',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        child: ListView(
          children: <Widget>[
            // YOUR INFORMATION SECTION
            _buildSectionHeader('YOUR INFORMATION'),
            _buildProfileTile(
              title: SharedPreferencesUtil().givenName.isEmpty ? 'Set Your Name' : 'Change Your Name',
              subtitle: SharedPreferencesUtil().givenName.isEmpty ? 'Not set' : SharedPreferencesUtil().givenName,
              icon: Icons.person,
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
            Consumer<HomeProvider>(
              builder: (context, homeProvider, _) {
                final languageName = homeProvider.userPrimaryLanguage.isNotEmpty
                    ? homeProvider.availableLanguages.entries
                        .firstWhere(
                          (element) => element.value == homeProvider.userPrimaryLanguage,
                        )
                        .key
                    : 'Not set';

                return _buildProfileTile(
                  title: 'Primary Language',
                  subtitle: languageName,
                  icon: Icons.language,
                  onTap: () async {
                    MixpanelManager().pageOpened('Profile Change Language');
                    await LanguageSelectionDialog.show(context, isRequired: false, forceShow: true);
                    await homeProvider.setupUserPrimaryLanguage();
                    setState(() {});
                  },
                );
              },
            ),

            // VOICE & PEOPLE SECTION
            _buildSectionHeader('VOICE & PEOPLE'),
            _buildProfileTile(
              title: 'Speech Profile',
              subtitle: 'Teach Omi your voice',
              icon: Icons.multitrack_audio,
              onTap: () {
                routeToPage(context, const SpeechProfilePage());
                MixpanelManager().pageOpened('Profile Speech Profile');
              },
            ),
            _buildProfileTile(
              title: 'Identifying Others',
              subtitle: 'Tell Omi who said it 🗣️',
              icon: Icons.people,
              onTap: () {
                routeToPage(context, const UserPeoplePage());
              },
            ),

            // PAYMENT SECTION
            _buildSectionHeader('PAYMENT'),
            _buildProfileTile(
              title: 'Payment Methods',
              subtitle: 'Add or change your payment method',
              icon: Icons.attach_money_outlined,
              onTap: () {
                routeToPage(context, const PaymentsPage());
              },
            ),

            // PREFERENCES SECTION
            _buildSectionHeader('PREFERENCES'),
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

            // ACCOUNT SECTION
            _buildSectionHeader('ACCOUNT'),
            _buildProfileTile(
              title: 'User ID',
              subtitle: SharedPreferencesUtil().uid,
              icon: Icons.copy_rounded,
              onTap: () {
                Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('User ID copied to clipboard')));
              },
            ),
            _buildProfileTile(
              title: 'Delete Account',
              subtitle: 'Delete your account and all data',
              icon: Icons.warning,
              iconColor: Colors.red.shade300,
              onTap: () {
                MixpanelManager().pageOpened('Profile Delete Account Dialog');
                Navigator.push(context, MaterialPageRoute(builder: (context) => const DeleteAccount()));
              },
            ),
          ],
        ),
      ),
    );
  }
}
