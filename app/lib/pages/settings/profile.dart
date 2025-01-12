import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/facts/page.dart';
import 'package:friend_private/pages/settings/change_name_widget.dart';
import 'package:friend_private/pages/settings/privacy.dart';
import 'package:friend_private/pages/speech_profile/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/pages/settings/widgets.dart';

import 'delete_account.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Profile'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            CustomListTile(
              title: SharedPreferencesUtil().givenName.isEmpty
                  ? 'About YOU'
                  : 'About ${SharedPreferencesUtil().givenName.toUpperCase()}',
              onTap: () {
                routeToPage(context, const FactsPage());
                MixpanelManager().pageOpened('Profile Facts');
              },
              icon: Icons.self_improvement,
              showChevron: true,
            ),
            const SizedBox(height: 12),
            CustomListTile(
              title: 'Speech Profile',
              onTap: () {
                routeToPage(context, const SpeechProfilePage());
                MixpanelManager().pageOpened('Profile Speech Profile');
              },
              icon: Icons.multitrack_audio,
              showChevron: true,
            ),
            const SizedBox(height: 12),
            CustomListTile(
              title: SharedPreferencesUtil().givenName.isEmpty ? 'Set Your Name' : 'Change Your Name',
              onTap: () async {
                MixpanelManager().pageOpened('Profile Change Name');
                await showDialog(
                  context: context,
                  builder: (BuildContext context) {
                    return const ChangeNameWidget();
                  },
                ).whenComplete(() => setState(() {}));
              },
              icon: Icons.person,
              showChevron: true,
            ),

            // Preferences Section
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 32, 0, 12),
              child: Text(
                'PREFERENCES',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.5),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
            ),

            // Analytics Opt-in Container
            Container(
              decoration: BoxDecoration(
                color: const Color.fromARGB(255, 18, 18, 18),
                borderRadius: BorderRadius.circular(12.0),
                border: Border.all(
                  color: Colors.white.withOpacity(0.15),
                  width: 1,
                ),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: InkWell(
                onTap: () {
                  setState(() {
                    SharedPreferencesUtil().optInAnalytics = !SharedPreferencesUtil().optInAnalytics;
                    SharedPreferencesUtil().optInAnalytics
                        ? MixpanelManager().optInTracking()
                        : MixpanelManager().optOutTracking();
                  });
                },
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: GestureDetector(
                        onTap: () {
                          routeToPage(context, const PrivacyInfoPage());
                          MixpanelManager().pageOpened('Share Analytics Data Details');
                        },
                        child: const Text(
                          'Help improve Omi by sharing anonymized analytics data',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w400,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Container(
                      decoration: BoxDecoration(
                        color: SharedPreferencesUtil().optInAnalytics
                            ? const Color.fromARGB(255, 28, 28, 28)
                            : Colors.transparent,
                        border: Border.all(
                          color: Colors.white.withOpacity(0.15),
                          width: 1,
                        ),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      width: 22,
                      height: 22,
                      child: SharedPreferencesUtil().optInAnalytics
                          ? const Icon(
                              Icons.check,
                              color: Colors.white,
                              size: 18,
                            )
                          : null,
                    ),
                  ],
                ),
              ),
            ),

            // Other Section
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 32, 0, 12),
              child: Text(
                'OTHER',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.5),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
            ),
            CustomListTile(
              title: 'Your User ID (UID)',
              onTap: () {
                Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                ScaffoldMessenger.of(context)
                    .showSnackBar(const SnackBar(content: Text('User ID copied to clipboard')));
              },
              icon: Icons.badge_outlined,
              subtitle: SharedPreferencesUtil().uid,
              trailingIcon: Icons.copy_rounded,
              showChevron: false,
            ),
            const SizedBox(height: 12),
            CustomListTile(
              title: 'Delete Account',
              onTap: () {
                MixpanelManager().pageOpened('Profile Delete Account Dialog');
                Navigator.push(context, MaterialPageRoute(builder: (context) => const DeleteAccount()));
              },
              icon: Icons.warning,
              showChevron: false,
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }
}
