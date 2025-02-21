import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:friend_private/gen/assets.gen.dart';
import 'package:friend_private/pages/chat/clone_chat_page.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'package:friend_private/pages/persona/persona_provider.dart';
import 'package:friend_private/pages/persona/update_persona.dart';
import 'package:friend_private/providers/auth_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/other/string_utils.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

class PersonaProfilePage extends StatefulWidget {
  const PersonaProfilePage({
    super.key,
  });

  @override
  State<PersonaProfilePage> createState() => _PersonaProfilePageState();
}

class _PersonaProfilePageState extends State<PersonaProfilePage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final provider = Provider.of<PersonaProvider>(context, listen: false);
      await provider.getVerifiedUserPersona();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PersonaProvider>(builder: (context, provider, child) {
      return Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              Assets.images.newBackground.path,
              fit: BoxFit.cover,
            ),
          ),
          Scaffold(
            backgroundColor: Colors.transparent,
            appBar: AppBar(
              backgroundColor: Colors.transparent,
              leading: GestureDetector(
                onTap: () {
                  routeToPage(context, const CloneChatPage(), replace: false);
                },
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: SvgPicture.asset(
                    Assets.images.icCloneChat.path,
                    width: 24,
                    height: 24,
                  ),
                ),
              ),
            ),
            body: provider.isLoading || provider.userPersona == null
                ? const Center(
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation(Colors.white),
                    ),
                  )
                : SingleChildScrollView(
                    child: Column(
                      children: [
                        Stack(
                          alignment: Alignment.center,
                          children: [
                            Container(
                              width: 100,
                              height: 100,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: const Color(0xFF494947),
                                  width: 2.5,
                                ),
                              ),
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(50),
                                child: provider.userPersona == null
                                    ? Image.asset(Assets.images.logoTransparentV2.path)
                                    : Image.network(
                                        provider.userPersona!.image,
                                        fit: BoxFit.cover,
                                      ),
                              ),
                            ),
                            Positioned(
                              right: 10,
                              bottom: 4,
                              child: Container(
                                width: 16,
                                height: 16,
                                decoration: BoxDecoration(
                                  color: const Color(0xFF00FF29),
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: const Color(0xFF494947),
                                    width: 2.5,
                                    strokeAlign: BorderSide.strokeAlignOutside,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const SizedBox(width: 4),
                            Text(
                              provider.userPersona!.getName(),
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(width: 4),
                            const Icon(
                              Icons.verified,
                              color: Colors.blue,
                              size: 20,
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          "25% Cloned",
                          style: TextStyle(
                            color: Colors.grey[600],
                            fontSize: 16,
                          ),
                        ),
                        const SizedBox(height: 24),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: TextButton(
                            onPressed: () async {
                              await Posthog().capture(eventName: 'share_persona_clicked', properties: {
                                'persona_username': provider.userPersona!.username ?? '',
                              });
                              Share.share(
                                'Check out this Persona on Omi AI: ${provider.userPersona!.name} by me \n\nhttps://personas.omi.me/u/${provider.userPersona!.username}',
                                subject: '${provider.userPersona!.getName()} Persona',
                              );
                            },
                            style: TextButton.styleFrom(
                              backgroundColor: Colors.white.withOpacity(0.08),
                              minimumSize: const Size(double.infinity, 50),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(30),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                SvgPicture.asset(Assets.images.linkIcon.path),
                                const SizedBox(width: 14),
                                Text(
                                  'Share Public Link',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.86),
                                    fontWeight: FontWeight.bold,
                                    fontSize: 18,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 24),
                        InkWell(
                          onTap: () {
                            showModalBottomSheet(
                              context: context,
                              backgroundColor: Colors.transparent,
                              isScrollControlled: true,
                              builder: (context) => Stack(
                                children: [
                                  Positioned.fill(
                                    child: Image.asset(
                                      'assets/images/new_background.png',
                                      fit: BoxFit.cover,
                                    ),
                                  ),
                                  Container(
                                    height: MediaQuery.of(context).size.height * 0.45,
                                    decoration: const BoxDecoration(
                                      color: Colors.transparent,
                                      borderRadius: BorderRadius.only(
                                        topLeft: Radius.circular(32),
                                        topRight: Radius.circular(32),
                                      ),
                                    ),
                                    child: Column(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        const SizedBox(height: 12),
                                        Container(
                                          width: 40,
                                          height: 4,
                                          decoration: BoxDecoration(
                                            color: Colors.white.withOpacity(0.2),
                                            borderRadius: BorderRadius.circular(2),
                                          ),
                                        ),
                                        const Spacer(),
                                        const SizedBox(height: 24),
                                        const Text(
                                          'Get Omi Device',
                                          style: TextStyle(
                                            color: Colors.white,
                                            fontSize: 24,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                        const SizedBox(height: 8),
                                        Text(
                                          'Create a more accurate clone with\nyour personal conversations',
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                            color: Colors.white.withOpacity(0.6),
                                            fontSize: 16,
                                          ),
                                        ),
                                        const Spacer(),
                                        Padding(
                                          padding: const EdgeInsets.symmetric(horizontal: 24),
                                          child: Column(
                                            children: [
                                              ElevatedButton(
                                                onPressed: () async {
                                                  await Posthog().capture(eventName: 'i_dont_have_device_clicked');
                                                  await launchUrl(
                                                      Uri.parse('https://www.omi.me/?_ref=omi_persona_flow'));
                                                },
                                                style: ElevatedButton.styleFrom(
                                                  backgroundColor: Colors.transparent,
                                                  foregroundColor: Colors.white,
                                                  minimumSize: const Size(double.infinity, 56),
                                                  shape: RoundedRectangleBorder(
                                                    borderRadius: BorderRadius.circular(16),
                                                    side: BorderSide(
                                                      color: Colors.white.withOpacity(0.12),
                                                      width: 4,
                                                    ),
                                                  ),
                                                ),
                                                child: const Text(
                                                  'Get Omi',
                                                  style: TextStyle(
                                                    fontSize: 17,
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(height: 16),
                                              TextButton(
                                                onPressed: () {
                                                  Navigator.pop(context);
                                                  routeToPage(context, const OnboardingWrapper());
                                                },
                                                child: Text(
                                                  'I have Omi device',
                                                  style: TextStyle(
                                                    fontSize: 18,
                                                    color: Colors.white.withOpacity(0.6),
                                                    fontWeight: FontWeight.bold,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        const SizedBox(height: 40),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                          child: Container(
                            margin: const EdgeInsets.symmetric(horizontal: 16),
                            width: double.infinity,
                            padding: const EdgeInsets.all(20),
                            decoration: BoxDecoration(
                              image: DecorationImage(
                                image: AssetImage(Assets.images.gradientCard.path),
                                fit: BoxFit.fill,
                                opacity: 0.9,
                              ),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                const Text(
                                  'Clone from device',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 20,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Create a clone from\nconversations',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.6),
                                    fontSize: 16,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 28),
                        Container(
                          margin: const EdgeInsets.symmetric(horizontal: 16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(left: 8.0, bottom: 12),
                                child: Text(
                                  'Connected Knowledge Data',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.65),
                                    fontSize: 18,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                              _buildSocialLink(
                                icon: Assets.images.xLogoMini.path,
                                text: provider.userPersona!.username ?? 'username',
                                isConnected: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: Assets.images.instagramLogo.path,
                                text: '@username',
                                isComingSoon: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: Assets.images.linkedinLogo.path,
                                text: 'linkedin.com/in/username',
                                isComingSoon: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: Assets.images.notionLogo.path,
                                text: 'notion.so/username',
                                isComingSoon: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: Assets.images.calendarLogo.path,
                                text: 'calendar Id',
                                isComingSoon: true,
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 40),
                      ],
                    ),
                  ),
          ),
        ],
      );
    });
  }

  Widget _buildSocialLink({
    required String icon,
    required String text,
    bool isConnected = false,
    bool isComingSoon = false,
    bool showConnect = false,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        // color: Colors.grey[900],
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withOpacity(0.22),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Image.asset(
            icon,
            width: 24,
            height: 24,
          ),
          const SizedBox(width: 12),
          Text(
            text,
            style: TextStyle(
              color: isComingSoon ? Colors.grey[600] : Colors.white,
              fontSize: 16,
            ),
          ),
          const Spacer(),
          if (isComingSoon)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF373737),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Text(
                'Coming soon',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                ),
              ),
            )
          else if (showConnect)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF373737),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Text(
                'Connect',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                ),
              ),
            )
          else if (isConnected)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF373737),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Text(
                'Connected',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
