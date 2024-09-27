import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/facts/page.dart';
import 'package:friend_private/pages/settings/change_name_widget.dart';
import 'package:friend_private/pages/settings/privacy.dart';
import 'package:friend_private/pages/settings/recordings_storage_permission.dart';
import 'package:friend_private/pages/speech_profile/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:url_launcher/url_launcher.dart';

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
      body: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 4, 16),
        child: ListView(
          children: <Widget>[
            // getItemAddOn('Identifying Others', () {
            //   routeToPage(context, const UserPeoplePage());
            // }, icon: Icons.people),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title: Text(
                  SharedPreferencesUtil().givenName.isEmpty
                      ? 'About YOU'
                      : 'About ${SharedPreferencesUtil().givenName.toUpperCase()}',
                  style: const TextStyle(color: Colors.white)),
              subtitle: const Text('What Omi has learned about you 👀'),
              trailing: const Icon(Icons.self_improvement, size: 20),
              onTap: () {
                routeToPage(context, const FactsPage());
                MixpanelManager().pageOpened('Profile Facts');
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title: const Text('Speech Profile', style: TextStyle(color: Colors.white)),
              subtitle: const Text('Teach Omi your voice'),
              trailing: const Icon(Icons.multitrack_audio, size: 20),
              onTap: () {
                routeToPage(context, const SpeechProfilePage());
                MixpanelManager().pageOpened('Profile Speech Profile');
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title: Text(
                SharedPreferencesUtil().givenName.isEmpty ? 'Set Your Name' : 'Change Your Name',
                style: const TextStyle(color: Colors.white),
              ),
              subtitle: Text(SharedPreferencesUtil().givenName.isEmpty ? 'Not set' : SharedPreferencesUtil().givenName),
              trailing: const Icon(Icons.person, size: 20),
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
            const SizedBox(height: 24),
            // Divider(color: Colors.grey.shade300, height: 1),
            const SizedBox(height: 32),
            const Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'PREFERENCES',
                style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                textAlign: TextAlign.start,
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              child: InkWell(
                onTap: () {
                  setState(() {
                    SharedPreferencesUtil().optInAnalytics = !SharedPreferencesUtil().optInAnalytics;
                    SharedPreferencesUtil().optInAnalytics
                        ? MixpanelManager().optInTracking()
                        : MixpanelManager().optOutTracking();
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12.0),
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
                            'Help improve Friend by sharing anonymized analytics data',
                            style: TextStyle(
                              color: Colors.grey,
                              fontSize: 16,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(
                        width: 16,
                      ),
                      Container(
                        decoration: BoxDecoration(
                          color: SharedPreferencesUtil().optInAnalytics
                              ? const Color.fromARGB(255, 150, 150, 150)
                              : Colors.transparent, // Fill color when checked
                          border: Border.all(
                            color: const Color.fromARGB(255, 150, 150, 150),
                            width: 2,
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        width: 22,
                        height: 22,
                        child: SharedPreferencesUtil().optInAnalytics // Show the icon only when checked
                            ? const Icon(
                                Icons.check,
                                color: Colors.white, // Tick color
                                size: 18,
                              )
                            : null, // No icon when unchecked
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 32),
            // Divider(color: Colors.grey.shade300, height: 1),
            const SizedBox(height: 24),
            const Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'OTHER',
                style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                textAlign: TextAlign.start,
              ),
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title: const Text('Your User ID', style: TextStyle(color: Colors.white)),
              subtitle: Text(SharedPreferencesUtil().uid),
              trailing: const Icon(Icons.copy_rounded, size: 20, color: Colors.white),
              onTap: () {
                Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('User ID copied to clipboard')));
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title: const Text('Delete Account', style: TextStyle(color: Colors.white)),
              subtitle: const Text('Delete your account and all data'),
              trailing: const Icon(
                Icons.warning,
                size: 20,
              ),
              onTap: () {
                MixpanelManager().pageOpened('Profile Delete Account Dialog');
                showDialog(
                    context: context,
                    builder: (ctx) {
                      return getDialog(
                        context,
                            () => Navigator.of(context).pop(),
                            () => launchUrl(Uri.parse('mailto:team@basedhardware.com?subject=Delete%20My%20Account')),
                        'Deleting Account?',
                        'Please send us an email at team@basedhardware.com',
                        okButtonText: 'Open Email',
                        singleButton: false,
                      );
                    });
              },
            )
          ],
        ),
      ),
    );
  }
}
