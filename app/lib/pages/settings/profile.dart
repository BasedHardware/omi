import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/facts/page.dart';
import 'package:friend_private/pages/settings/change_name_widget.dart';
import 'package:friend_private/pages/settings/privacy.dart';
import 'package:friend_private/pages/speech_profile/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/services/translation_service.dart';

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
        title:  Text(TranslationService.translate( 'Profile')),
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
                      ? TranslationService.translate( 'About YOU')
                      : TranslationService.translate( 'About')+' '+SharedPreferencesUtil().givenName.toUpperCase(),
                  style: const TextStyle(color: Colors.white)),
              subtitle:  Text(TranslationService.translate( 'What Omi has learned about you 👀')),
              trailing: const Icon(Icons.self_improvement, size: 20),
              onTap: () {
                routeToPage(context, const FactsPage());
                MixpanelManager().pageOpened(TranslationService.translate( 'Profile Facts'));
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title:  Text(TranslationService.translate( 'Speech Profile'), style: TextStyle(color: Colors.white)),
              subtitle:  Text(TranslationService.translate( 'Teach Omi your voice')),
              trailing: const Icon(Icons.multitrack_audio, size: 20),
              onTap: () {
                routeToPage(context, const SpeechProfilePage());
                MixpanelManager().pageOpened('Profile Speech Profile');
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title: Text(
                SharedPreferencesUtil().givenName.isEmpty ? TranslationService.translate( 'Set Your Name') : TranslationService.translate( 'Change Your Name'),
                style: const TextStyle(color: Colors.white),
              ),
              subtitle: Text(SharedPreferencesUtil().givenName.isEmpty ? TranslationService.translate( 'Not set') : SharedPreferencesUtil().givenName),
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
             Align(
              alignment: Alignment.centerLeft,
              child: Text(
                TranslationService.translate( 'PREFERENCES'),
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
                          child:  Text(
                            TranslationService.translate( 'Help improve Friend by sharing anonymized analytics data'),
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
             Align(
              alignment: Alignment.centerLeft,
              child: Text(
                TranslationService.translate( 'OTHER'),
                style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                textAlign: TextAlign.start,
              ),
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title:  Text(TranslationService.translate( 'Your User ID'), style: TextStyle(color: Colors.white)),
              subtitle: Text(SharedPreferencesUtil().uid),
              trailing: const Icon(Icons.copy_rounded, size: 20, color: Colors.white),
              onTap: () {
                Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                ScaffoldMessenger.of(context).showSnackBar( SnackBar(content: Text(TranslationService.translate( 'User ID copied to clipboard'))));
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(0, 0, 24, 0),
              title:  Text(TranslationService.translate( 'Delete Account'), style: TextStyle(color: Colors.white)),
              subtitle:  Text(TranslationService.translate( 'Delete your account and all data')),
              trailing: const Icon(
                Icons.warning,
                size: 20,
              ),
              onTap: () {
                MixpanelManager().pageOpened('Profile Delete Account Dialog');
                Navigator.push(context, MaterialPageRoute(builder: (context) => const DeleteAccount()));
              },
            )
          ],
        ),
      ),
    );
  }
}
