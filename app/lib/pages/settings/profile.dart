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
      body: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 4, 16),
        child: ListView(
          children: <Widget>[
            // getItemAddOn('Identifying Others', () {
            //   routeToPage(context, const UserPeoplePage());
            // }, icon: Icons.people),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
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
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
              title: const Text('Speech Profile', style: TextStyle(color: Colors.white)),
              subtitle: const Text('Teach Omi your voice'),
              trailing: const Icon(Icons.multitrack_audio, size: 20),
              onTap: () {
                routeToPage(context, const SpeechProfilePage());
                MixpanelManager().pageOpened('Profile Speech Profile');
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
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
            Divider(color: Colors.grey.shade300, height: 1),
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
            Padding(
              padding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              child: InkWell(
                onTap: () async {
                  MixpanelManager().pageOpened('Profile Authorize Saving Recordings');
                  await routeToPage(context, const RecordingsStoragePermission());
                  setState(() {});
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12.0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Authorize saving recordings',
                        style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        decoration: BoxDecoration(
                          color: SharedPreferencesUtil().permissionStoreRecordingsEnabled
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
                        child:
                            SharedPreferencesUtil().permissionStoreRecordingsEnabled // Show the icon only when checked
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
            const SizedBox(height: 24),
            Divider(color: Colors.grey.shade300, height: 1),
            const SizedBox(height: 24),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
              title: const Text('Delete Account', style: TextStyle(color: Colors.white)),
              trailing: const Icon(
                Icons.warning,
                size: 20,
              ),
              onTap: () {
                MixpanelManager().pageOpened('Profile Delete Account Dialog');
                Navigator.push(context, MaterialPageRoute(builder: (context) => const DeleteAccount()));
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
              title: const Text('Your User Id', style: TextStyle(color: Colors.white)),
              subtitle: Text(SharedPreferencesUtil().uid),
              trailing: const Icon(Icons.copy_rounded, size: 20, color: Colors.white),
              onTap: () {
                MixpanelManager().pageOpened('Authorize Saving Recordings');
                Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('UID copied to clipboard')));
              },
            ),
          ],
        ),
      ),
    );
  }
}
