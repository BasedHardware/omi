import 'dart:io';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi_private/backend/preferences.dart';
import 'package:omi_private/gen/assets.gen.dart';
import 'package:omi_private/pages/chat/clone_chat_page.dart';
import 'package:omi_private/pages/persona/persona_provider.dart';
import 'package:omi_private/pages/persona/update_persona.dart';
import 'package:omi_private/providers/auth_provider.dart';
import 'package:omi_private/utils/alerts/app_snackbar.dart';
import 'package:omi_private/utils/other/temp.dart';
import 'package:omi_private/widgets/sign_in_button.dart';
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
  void _showAccountLinkBottomSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) {
        return Container(
          padding: const EdgeInsets.only(top: 20),
          decoration: BoxDecoration(
            color: Colors.grey[900],
            borderRadius: const BorderRadius.vertical(
              top: Radius.circular(20),
            ),
          ),
          child: Consumer<AuthenticationProvider>(
            builder: (context, authProvider, child) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: Colors.grey[800],
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'Link Your Account',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Link your account to clone your persona from device',
                    style: TextStyle(
                      color: Colors.grey[400],
                      fontSize: 14,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 32),
                  Padding(
                    padding: EdgeInsets.only(
                      bottom: MediaQuery.of(context).viewInsets.bottom + 20,
                      left: 16,
                      right: 16,
                    ),
                    child: Column(
                      children: [
                        if (Platform.isIOS)
                          SignInButton(
                            title: 'Link with Apple',
                            assetPath: Assets.images.appleLogo.path,
                            onTap: () async {
                              try {
                                await Posthog().capture(eventName: 'link_with_apple_clicked');
                                await authProvider.linkWithApple();
                                if (mounted) {
                                  SharedPreferencesUtil().hasOmiDevice = true;
                                  var persona = context.read<PersonaProvider>().userPersona;
                                  Navigator.pop(context);
                                  routeToPage(context, UpdatePersonaPage(app: persona, fromNewFlow: true));
                                }
                              } catch (e) {
                                AppSnackbar.showSnackbarError('Failed to link Apple account: $e');
                              }
                            },
                            iconSpacing: 12,
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          ),
                        if (Platform.isIOS) const SizedBox(height: 12),
                        SignInButton(
                          title: 'Link with Google',
                          assetPath: Assets.images.googleLogo.path,
                          onTap: () async {
                            try {
                              await Posthog().capture(eventName: 'link_with_google_clicked');
                              await authProvider.linkWithGoogle();
                              if (mounted) {
                                SharedPreferencesUtil().hasOmiDevice = true;
                                var persona = context.read<PersonaProvider>().userPersona;
                                Navigator.pop(context);
                                routeToPage(context, UpdatePersonaPage(app: persona, fromNewFlow: true));
                              }
                            } catch (e) {
                              AppSnackbar.showSnackbarError('Failed to link Google account: $e');
                            }
                          },
                          iconSpacing: Platform.isIOS ? 12 : 10,
                          padding: Platform.isIOS
                              ? const EdgeInsets.symmetric(horizontal: 16, vertical: 12)
                              : const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextButton(
                    onPressed: () async {
                      await Posthog().capture(eventName: 'i_dont_have_device_clicked');
                      await launchUrl(Uri.parse('https://www.omi.me/?_ref=omi_persona_flow'));
                    },
                    child: Text(
                      "I don't have a device",
                      style: TextStyle(
                        color: Colors.grey[400],
                        fontSize: 14,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                  ),
                  const SizedBox(height: 32),
                ],
              );
            },
          ),
        );
      },
    );
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final provider = Provider.of<PersonaProvider>(context, listen: false);
      await provider.getUserPersona();
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
              'assets/images/new_background.png',
              fit: BoxFit.cover,
            ),
          ),
          Scaffold(
            backgroundColor: Colors.transparent,
            appBar: AppBar(
              backgroundColor: Colors.transparent,
              leading: GestureDetector(
                onTap: () {
                  if (mounted) {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (context) => const CloneChatPage(),
                      ),
                    );
                  }
                },
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: SvgPicture.asset(
                    'assets/images/ic_clone_chat.svg',
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
                              provider.userPersona!.name,
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
                                subject: '${provider.userPersona!.name} Persona',
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
                                SvgPicture.asset('assets/images/link_icon.svg'),
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
                            final user = FirebaseAuth.instance.currentUser;
                            if (user != null && user.isAnonymous) {
                              _showAccountLinkBottomSheet();
                            } else if (!user!.isAnonymous) {
                              SharedPreferencesUtil().hasOmiDevice = true;
                              var persona = context.read<PersonaProvider>().userPersona;
                              routeToPage(context, UpdatePersonaPage(app: persona, fromNewFlow: true));
                            }
                          },
                          child: Container(
                            margin: const EdgeInsets.symmetric(horizontal: 16),
                            width: double.infinity,
                            padding: const EdgeInsets.all(20),
                            decoration: BoxDecoration(
                              image: const DecorationImage(
                                image: AssetImage('assets/images/gradient_card.png'),
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
                                icon: 'assets/images/x_logo_mini.png',
                                text: provider.userPersona!.username ?? 'username',
                                isConnected: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: 'assets/images/instagram_logo.png',
                                text: '@username',
                                isComingSoon: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: 'assets/images/linkedin_logo.png',
                                text: 'linkedin.com/in/username',
                                isComingSoon: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: 'assets/images/notion_logo.png',
                                text: 'notion.so/username',
                                isComingSoon: true,
                              ),
                              const SizedBox(height: 12),
                              _buildSocialLink(
                                icon: 'assets/images/calendar_logo.png',
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
