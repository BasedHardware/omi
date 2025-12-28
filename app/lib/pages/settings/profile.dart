import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/language_settings_page.dart';
import 'package:omi/pages/settings/custom_vocabulary_page.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/speech_profile/page.dart';

import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';


import 'package:omi/pages/settings/conversation_display_settings.dart';

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
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: children,
      ),
    );
  }

  Widget _buildProfileItem({
    required String title,
    String? subtitle,
    String? chipValue,
    required Widget icon,
    required VoidCallback onTap,
    bool showSubtitle = true,
    bool showBetaTag = false,
    bool showChevron = true,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
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
                    Row(
                      children: [
                        Text(
                          title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w400,
                          ),
                        ),
                        if (showBetaTag) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                            decoration: BoxDecoration(
                              color: Colors.orange.withOpacity(0.2),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: const Text(
                              'BETA',
                              style: TextStyle(
                                color: Colors.orange,
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (showSubtitle && subtitle != null && chipValue == null) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: const TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 12,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (chipValue != null) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2A2A2E),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    chipValue,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                if (showChevron) const SizedBox(width: 8),
              ],
              if (showChevron)
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        title: Text(
          context.l10n.profile,
          style: const TextStyle(
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
                  title: context.l10n.name,
                  chipValue: SharedPreferencesUtil().givenName.isEmpty
                      ? context.l10n.notSet
                      : SharedPreferencesUtil().givenName,
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
                _buildProfileItem(
                  title: context.l10n.email,
                  chipValue:
                      SharedPreferencesUtil().email.isEmpty ? context.l10n.notSet : SharedPreferencesUtil().email,
                  icon: const FaIcon(FontAwesomeIcons.solidEnvelope, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {},
                  showChevron: false,
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: context.l10n.language,
                  icon: const FaIcon(FontAwesomeIcons.globe, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const LanguageSettingsPage());
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: context.l10n.customVocabulary,
                  icon: const FaIcon(FontAwesomeIcons.book, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const CustomVocabularyPage());
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // VOICE & PEOPLE SECTION
            _buildSectionContainer(
              children: [
                _buildProfileItem(
                  title: context.l10n.speechProfile,
                  icon: const FaIcon(FontAwesomeIcons.microphone, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const SpeechProfilePage());
                    MixpanelManager().pageOpened('Profile Speech Profile');
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: context.l10n.identifyingOthers,
                  icon: const FaIcon(FontAwesomeIcons.users, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const UserPeoplePage());
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // PAYMENT & PRIVACY SECTION
            _buildSectionContainer(
              children: [
                _buildProfileItem(
                  title: context.l10n.paymentMethods,
                  icon: const FaIcon(FontAwesomeIcons.solidCreditCard, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const PaymentsPage());
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: context.l10n.conversationDisplay,
                  icon: const FaIcon(FontAwesomeIcons.list, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const ConversationDisplaySettings());
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: context.l10n.dataPrivacy,
                  icon: const FaIcon(FontAwesomeIcons.shield, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => const DataPrivacyPage(),
                      ),
                    );
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // ACCOUNT SECTION
            _buildSectionContainer(
              children: [
                Builder(
                  builder: (context) {
                    final uid = SharedPreferencesUtil().uid;
                    final truncatedUid =
                        uid.length > 6 ? '${uid.substring(0, 3)}•••••${uid.substring(uid.length - 3)}' : uid;
                    return _buildProfileItem(
                      title: context.l10n.userId,
                      chipValue: truncatedUid,
                      icon: const FaIcon(FontAwesomeIcons.solidClipboard, color: Color(0xFF8E8E93), size: 20),
                      onTap: () {
                        Clipboard.setData(ClipboardData(text: uid));
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.userIdCopied)));
                      },
                    );
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildProfileItem(
                  title: context.l10n.deleteAccountTitle,
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
