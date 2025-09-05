import 'package:flutter/material.dart';
import 'package:omi/pages/settings/webview.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:url_launcher/url_launcher.dart';

class DesktopAboutOmiPage extends StatefulWidget {
  const DesktopAboutOmiPage({super.key});

  @override
  State<DesktopAboutOmiPage> createState() => _DesktopAboutOmiPageState();
}

class _DesktopAboutOmiPageState extends State<DesktopAboutOmiPage> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('About Omi'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
              title: const Text('Privacy Policy', style: TextStyle(color: Colors.white)),
              trailing: const Icon(Icons.privacy_tip_outlined, size: 20, color: Colors.white),
              onTap: () {
                MixpanelManager().pageOpened('About Privacy Policy');
                launchUrl(Uri.parse('https://www.omi.me/pages/privacy'));
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
              title: const Text('Visit Website', style: TextStyle(color: Colors.white)),
              subtitle: const Text('https://omi.me', style: TextStyle(color: Colors.white70)),
              trailing: const Icon(Icons.language_outlined, size: 20, color: Colors.white),
              onTap: () {
                MixpanelManager().pageOpened('About Visit Website');
                launchUrl(Uri.parse('https://www.omi.me/'));
              },
            ),
            ListTile(
              title: const Text('Help or Inquiries?', style: TextStyle(color: Colors.white)),
              subtitle: const Text('team@basedhardware.com', style: TextStyle(color: Colors.white70)),
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
              trailing: const Icon(Icons.email_outlined, color: Colors.white, size: 20),
              onTap: () async {
                final Uri emailUri = Uri(
                  scheme: 'mailto',
                  path: 'team@basedhardware.com',
                  query: 'subject=Omi Desktop App Inquiry',
                );
                if (await canLaunchUrl(emailUri)) {
                  await launchUrl(emailUri);
                }
              },
            ),
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
              title: const Text('Join the community!', style: TextStyle(color: Colors.white)),
              subtitle: const Text('7000+ members and counting.', style: TextStyle(color: Colors.white70)),
              trailing: const Icon(Icons.discord, color: Colors.purple, size: 20),
              onTap: () {
                MixpanelManager().pageOpened('About Join Discord');
                launchUrl(Uri.parse('https://discord.gg/omi'));
              },
            ),
          ],
        ),
      ),
    );
  }
}
