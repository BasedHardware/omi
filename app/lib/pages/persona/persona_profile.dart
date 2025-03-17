import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/chat/clone_chat_page.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/pages/persona/twitter/social_profile.dart';
import 'package:omi/pages/settings/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

class PersonaProfilePage extends StatefulWidget {
  final double? bottomMargin;

  const PersonaProfilePage({
    super.key,
    this.bottomMargin,
  });

  @override
  State<PersonaProfilePage> createState() => _PersonaProfilePageState();
}

class _PersonaProfilePageState extends State<PersonaProfilePage> {
  bool _isPersonaEditable(PersonaProfileRouting routing) {
    return routing == PersonaProfileRouting.apps_updates ||
        routing == PersonaProfileRouting.home ||
        routing == PersonaProfileRouting.create_my_clone;
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final provider = Provider.of<PersonaProvider>(context, listen: false);
      if (provider.routing == PersonaProfileRouting.apps_updates && provider.userPersona != null) {
        provider.prepareUpdatePersona(provider.userPersona!);
      } else {
        await provider.getVerifiedUserPersona();
      }
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PersonaProvider>(builder: (context, provider, child) {
      App? persona = provider.userPersona;
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
              leading: Consumer<PersonaProvider>(builder: (context, personaProvider, _) {
                return personaProvider.routing == PersonaProfileRouting.apps_updates
                    ? IconButton(
                        icon: const Icon(Icons.arrow_back, color: Colors.white),
                        onPressed: () {
                          Navigator.pop(context);
                        },
                      )
                    : GestureDetector(
                        onTap: () async {
                          if (personaProvider.routing == PersonaProfileRouting.no_device) {
                            routeToPage(context, const CloneChatPage(), replace: false);
                          } else {
                            context.read<HomeProvider>().setIndex(1);
                            if (context.read<HomeProvider>().onSelectedIndexChanged != null) {
                              context.read<HomeProvider>().onSelectedIndexChanged!(1);
                            }
                            var appId = persona!.id;
                            var appProvider = Provider.of<AppProvider>(context, listen: false);
                            var messageProvider = Provider.of<MessageProvider>(context, listen: false);
                            App? selectedApp;
                            if (appId.isNotEmpty) {
                              selectedApp = await appProvider.getAppFromId(appId);
                            }
                            appProvider.setSelectedChatAppId(appId);
                            await messageProvider.refreshMessages();
                            if (messageProvider.messages.isEmpty) {
                              messageProvider.sendInitialAppMessage(selectedApp);
                            }
                          }
                        },
                        child: Padding(
                          padding: const EdgeInsets.all(16.0),
                          child: SvgPicture.asset(
                            Assets.images.icCloneChat.path,
                            width: 24,
                            height: 24,
                          ),
                        ),
                      );
              }),
              actions: [
                // Only show settings icon for create_my_clone or home routing
                Consumer<PersonaProvider>(builder: (context, personaProvider, _) {
                  if (personaProvider.routing == PersonaProfileRouting.no_device) {
                    return Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: GestureDetector(
                        onTap: () async {
                          await routeToPage(context, const SettingsPage(mode: SettingsMode.no_device));
                        },
                        child: SvgPicture.asset(
                          Assets.images.icSettingPersona.path,
                          width: 44,
                          height: 44,
                        ),
                      ),
                    );
                  }
                  if (personaProvider.routing == PersonaProfileRouting.create_my_clone ||
                      personaProvider.routing == PersonaProfileRouting.home) {
                    return Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: GestureDetector(
                        onTap: () async {
                          MixpanelManager().pageOpened('Settings');
                          String language = SharedPreferencesUtil().recordingsLanguage;
                          bool hasSpeech = SharedPreferencesUtil().hasSpeakerProfile;
                          String transcriptModel = SharedPreferencesUtil().transcriptionModel;
                          await routeToPage(context, const SettingsPage());
                          if (language != SharedPreferencesUtil().recordingsLanguage ||
                              hasSpeech != SharedPreferencesUtil().hasSpeakerProfile ||
                              transcriptModel != SharedPreferencesUtil().transcriptionModel) {
                            if (context.mounted) {
                              context.read<CaptureProvider>().onRecordProfileSettingChanged();
                            }
                          }
                        },
                        child: SvgPicture.asset(
                          Assets.images.icSettingPersona.path,
                          width: 44,
                          height: 44,
                        ),
                      ),
                    );
                  }
                  return const SizedBox.shrink();
                }),
              ],
            ),
            body: persona == null
                ? const Center(
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation(Colors.white),
                    ),
                  )
                : Stack(
                    children: [
                      SingleChildScrollView(
                        padding: EdgeInsets.only(bottom: widget.bottomMargin ?? 0),
                        child: Column(
                          children: [
                            Stack(
                              alignment: Alignment.center,
                              children: [
                                GestureDetector(
                                  onTap: _isPersonaEditable(provider.routing) && !provider.isLoading
                                      ? () async {
                                          await provider.pickAndUpdateImage();
                                        }
                                      : null,
                                  child: Stack(
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
                                          child: provider.selectedImage != null
                                              ? Image.file(
                                                  provider.selectedImage!,
                                                  fit: BoxFit.cover,
                                                )
                                              : persona.image.isEmpty
                                                  ? Image.asset(Assets.images.logoTransparentV2.path)
                                                  : CachedNetworkImage(
                                                      imageUrl: persona.image,
                                                      imageBuilder: (context, imageProvider) => Container(
                                                        width: 48,
                                                        height: 48,
                                                        decoration: BoxDecoration(
                                                          shape: BoxShape.rectangle,
                                                          borderRadius: BorderRadius.circular(8),
                                                          image:
                                                              DecorationImage(image: imageProvider, fit: BoxFit.cover),
                                                        ),
                                                      ),
                                                      placeholder: (context, url) => const SizedBox(
                                                        width: 48,
                                                        height: 48,
                                                        child: CircularProgressIndicator(
                                                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                                        ),
                                                      ),
                                                      errorWidget: (context, url, error) => const SizedBox(
                                                        width: 48,
                                                        height: 48,
                                                        child: Icon(
                                                          Icons.error,
                                                          color: Colors.white,
                                                        ),
                                                      ),
                                                    ),
                                        ),
                                      ),
                                      if (_isPersonaEditable(provider.routing) && !provider.isLoading)
                                        Positioned.fill(
                                          child: Opacity(
                                            opacity: 1.0,
                                            child: Container(
                                              decoration: BoxDecoration(
                                                shape: BoxShape.circle,
                                                color: Colors.black.withOpacity(0.3),
                                              ),
                                              child: const Center(
                                                child: Icon(
                                                  Icons.camera_alt,
                                                  color: Colors.white,
                                                  size: 30,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                    ],
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
                            GestureDetector(
                              onTap: _isPersonaEditable(provider.routing)
                                  ? () {
                                      _showNameEditDialog(context, persona, provider);
                                    }
                                  : null,
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  const SizedBox(width: 4),
                                  Text(
                                    persona.getName(),
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
                                  if (_isPersonaEditable(provider.routing))
                                    Container(
                                      margin: const EdgeInsets.only(left: 8.0),
                                      padding: const EdgeInsets.all(4),
                                      child: const Icon(
                                        Icons.edit,
                                        color: Colors.white,
                                        size: 16,
                                      ),
                                    ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 24),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 16),
                              child: TextButton(
                                onPressed: () async {
                                  await Posthog().capture(eventName: 'share_persona_clicked', properties: {
                                    'persona_username': persona.username ?? '',
                                  });
                                  Share.share(
                                    'https://personas.omi.me/u/${persona.username}',
                                    subject: '${persona.getName()} Persona',
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
                            if (_isPersonaEditable(provider.routing)) ...[
                              const SizedBox(height: 16),
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 24.0),
                                child: Row(
                                  children: [
                                    Text(
                                      'Make Persona Public',
                                      style: TextStyle(
                                        color: Colors.white.withOpacity(0.65),
                                        fontSize: 18,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                    const Spacer(),
                                    Consumer<PersonaProvider>(
                                      builder: (context, provider, child) {
                                        return Switch(
                                          value: provider.makePersonaPublic,
                                          onChanged: (value) {
                                            provider.setPersonaPublic(value);
                                          },
                                          activeColor: Colors.deepPurple,
                                        );
                                      },
                                    ),
                                  ],
                                ),
                              )
                            ],
                            const SizedBox(height: 24),
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
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ),
                                  GestureDetector(
                                    onTap: () {
                                      if (provider.routing == PersonaProfileRouting.no_device &&
                                          provider.hasOmiConnection) {
                                        var provider = Provider.of<AuthenticationProvider>(context, listen: false);
                                        if (provider.user == null || provider.user!.isAnonymous) {
                                          routeToPage(context, const OnboardingWrapper());
                                        }
                                        return;
                                      }

                                      // else
                                      if (!provider.hasOmiConnection) {
                                        _showGetOmiDeviceBottomSheet(context);
                                      }
                                    },
                                    child: _buildSocialLink(
                                      icon: Assets.images.logoTransparent.path,
                                      text: provider.hasOmiConnection ? (persona.username ?? 'username') : 'omi',
                                      isConnected: provider.hasOmiConnection,
                                      showConnect: !provider.hasOmiConnection,
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  GestureDetector(
                                    onTap: () {
                                      if (!_isPersonaEditable(provider.routing)) {
                                        return;
                                      }
                                      if (!provider.hasTwitterConnection) {
                                        routeToPage(context, SocialHandleScreen(routing: provider.routing));
                                        return;
                                      }

                                      _showDisconnectTwitterConfirmation(context, provider);
                                    },
                                    child: _buildSocialLink(
                                      icon: Assets.images.xLogoMini.path,
                                      text: provider.twitterProfile?['username'] ?? '@username',
                                      isConnected: provider.hasTwitterConnection,
                                      showConnect: !provider.hasTwitterConnection,
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.notionLogo.path,
                                    text: 'notion.so/username',
                                    isComingSoon: true,
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.emailLogo.path,
                                    text: 'user@example.com',
                                    isComingSoon: true,
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.telegramLogo.path,
                                    text: '@username',
                                    isComingSoon: true,
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.whatsappLogo.path,
                                    text: '+1234567890',
                                    isComingSoon: true,
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.facebookLogo.path,
                                    text: 'facebook.com/username',
                                    isComingSoon: true,
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.instagramLogo.path,
                                    text: '@username',
                                    isComingSoon: true,
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.youtubeLogo.path,
                                    text: 'youtube.com/@username',
                                    isComingSoon: true,
                                  ),
                                  const SizedBox(height: 12),
                                  _buildSocialLink(
                                    icon: Assets.images.slackLogo.path,
                                    text: 'workspace.slack.com',
                                    isComingSoon: true,
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 40),
                          ],
                        ),
                      ),
                      if (provider.isLoading)
                        Container(
                          color: Colors.black.withOpacity(0.5),
                          child: const Center(
                            child: CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation(Colors.white),
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
        ],
      );
    });
  }

  void _showNameEditDialog(BuildContext context, App persona, PersonaProvider provider) {
    final TextEditingController nameController = provider.nameController;

    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('Edit Name', style: TextStyle(color: Colors.white)),
          content: TextField(
            controller: nameController,
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(
              hintText: 'Enter name',
              hintStyle: TextStyle(color: Colors.grey),
              enabledBorder: UnderlineInputBorder(
                borderSide: BorderSide(color: Colors.grey),
              ),
              focusedBorder: UnderlineInputBorder(
                borderSide: BorderSide(color: Colors.white),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
              },
              child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
            ),
            TextButton(
              onPressed: () {
                if (nameController.text.isNotEmpty) {
                  provider.updatePersonaName();
                  Navigator.of(context).pop();
                }
              },
              child: const Text('Save', style: TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );
  }

  void _showDisconnectTwitterConfirmation(BuildContext context, PersonaProvider provider) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: Theme.of(context).colorScheme.surface,
          title: const Text('Disconnect Twitter', style: TextStyle(color: Colors.white)),
          content: const Text(
            'Are you sure you want to disconnect your Twitter account? Your persona will no longer have access to your Twitter data.',
            style: TextStyle(color: Colors.white70),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
              },
              child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
            ),
            TextButton(
              onPressed: () {
                provider.disconnectTwitter();
                Navigator.of(context).pop();
              },
              child: const Text('Disconnect', style: TextStyle(color: Colors.redAccent)),
            ),
          ],
        );
      },
    );
  }

  void _showSignOutDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('Sign Out', style: TextStyle(color: Colors.white)),
          content: const Text(
            'Are you sure you want to sign out?',
            style: TextStyle(color: Colors.white70),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
              },
              child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
            ),
            TextButton(
              onPressed: () async {
                Navigator.of(context).pop();
                await SharedPreferencesUtil().clearUserPreferences();
                Provider.of<PersonaProvider>(context, listen: false).setRouting(PersonaProfileRouting.no_device);
                await signOut();
                Navigator.of(context).pop();
                routeToPage(context, const DeciderWidget(), replace: true);
              },
              child: const Text('Sign Out', style: TextStyle(color: Colors.redAccent)),
            ),
          ],
        );
      },
    );
  }

  void _showGetOmiDeviceBottomSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              Assets.images.newBackground.path,
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
                          await launchUrl(Uri.parse('https://www.omi.me/?_ref=omi_persona_flow'));
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
                            fontWeight: FontWeight.w500,
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
