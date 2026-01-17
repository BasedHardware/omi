import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/settings/webview.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopAboutOmiPage extends StatefulWidget {
  const DesktopAboutOmiPage({super.key});

  @override
  State<DesktopAboutOmiPage> createState() => _DesktopAboutOmiPageState();
}

class _DesktopAboutOmiPageState extends State<DesktopAboutOmiPage> {
  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      body: Stack(
        children: [
          Padding(
            padding: EdgeInsets.all(responsive.spacing(baseSpacing: 24)),
            child: Column(
              children: [
                _buildHeader(responsive),
                SizedBox(height: responsive.spacing(baseSpacing: 24)),
                Expanded(child: _buildContent(responsive)),
              ],
            ),
          ),
        ],
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
          'About Omi',
          style: responsive.headlineLarge.copyWith(
            fontWeight: FontWeight.w400,
          ),
        ),
      ],
    );
  }

  Widget _buildContent(ResponsiveHelper responsive) {
    return SingleChildScrollView(
      child: Column(
        children: [
          Container(
            margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 8)),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
            child: ListTile(
              contentPadding: EdgeInsets.symmetric(
                horizontal: responsive.spacing(baseSpacing: 16),
                vertical: responsive.spacing(baseSpacing: 4),
              ),
              title: Text(
                'Privacy Policy',
                style: responsive.bodyLarge.copyWith(
                  color: ResponsiveHelper.textPrimary,
                  fontWeight: FontWeight.w500,
                ),
              ),
              trailing: const Icon(
                Icons.privacy_tip_outlined,
                size: 20,
                color: ResponsiveHelper.textSecondary,
              ),
              onTap: () {
                MixpanelManager().pageOpened('About Privacy Policy');
                launchUrl(Uri.parse('https://www.omi.me/pages/privacy'));
              },
            ),
          ),
          Container(
            margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 8)),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
            child: ListTile(
              contentPadding: EdgeInsets.symmetric(
                horizontal: responsive.spacing(baseSpacing: 16),
                vertical: responsive.spacing(baseSpacing: 4),
              ),
              title: Text(
                'Visit Website',
                style: responsive.bodyLarge.copyWith(
                  color: ResponsiveHelper.textPrimary,
                  fontWeight: FontWeight.w500,
                ),
              ),
              subtitle: Text(
                'https://omi.me',
                style: responsive.bodyMedium.copyWith(
                  color: ResponsiveHelper.textSecondary,
                ),
              ),
              trailing: const Icon(
                Icons.language_outlined,
                size: 20,
                color: ResponsiveHelper.textSecondary,
              ),
              onTap: () {
                MixpanelManager().pageOpened('About Visit Website');
                launchUrl(Uri.parse('https://www.omi.me/'));
              },
            ),
          ),
          Container(
            margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 8)),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
            child: ListTile(
              contentPadding: EdgeInsets.symmetric(
                horizontal: responsive.spacing(baseSpacing: 16),
                vertical: responsive.spacing(baseSpacing: 4),
              ),
              title: Text(
                'Help or Inquiries?',
                style: responsive.bodyLarge.copyWith(
                  color: ResponsiveHelper.textPrimary,
                  fontWeight: FontWeight.w500,
                ),
              ),
              subtitle: Text(
                'team@basedhardware.com',
                style: responsive.bodyMedium.copyWith(
                  color: ResponsiveHelper.textSecondary,
                ),
              ),
              trailing: const Icon(
                Icons.email_outlined,
                color: ResponsiveHelper.textSecondary,
                size: 20,
              ),
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
          ),
          Container(
            margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 8)),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
            child: ListTile(
              contentPadding: EdgeInsets.symmetric(
                horizontal: responsive.spacing(baseSpacing: 16),
                vertical: responsive.spacing(baseSpacing: 4),
              ),
              title: Text(
                'Join the community!',
                style: responsive.bodyLarge.copyWith(
                  color: ResponsiveHelper.textPrimary,
                  fontWeight: FontWeight.w500,
                ),
              ),
              subtitle: Text(
                '8000+ members and counting.',
                style: responsive.bodyMedium.copyWith(
                  color: ResponsiveHelper.textSecondary,
                ),
              ),
              trailing: const Icon(
                Icons.discord,
                color: ResponsiveHelper.purplePrimary,
                size: 20,
              ),
              onTap: () {
                MixpanelManager().pageOpened('About Join Discord');
                launchUrl(Uri.parse('http://discord.omi.me'));
              },
            ),
          ),
        ],
      ),
    );
  }
}
