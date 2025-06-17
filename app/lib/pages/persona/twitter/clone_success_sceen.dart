import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/chat/clone_chat_page.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/utils/other/string_utils.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:provider/provider.dart';

import '../persona_profile.dart';

class CloneSuccessScreen extends StatefulWidget {
  final String message;
  final PersonaProfileRouting routing;
  const CloneSuccessScreen({
    super.key,
    required this.message,
    this.routing = PersonaProfileRouting.no_device,
  });

  @override
  State<CloneSuccessScreen> createState() => _CloneSuccessScreenState();
}

class _CloneSuccessScreenState extends State<CloneSuccessScreen> {
  void _handleNavigation() async {
    final user = FirebaseAuth.instance.currentUser;

    // If user is not anonymous (signed in with Google/Apple), they came from create/update flow
    if (user != null && !user.isAnonymous) {
      Posthog().capture(eventName: 'x_connected', properties: {'existing_omi_user': true});
      Navigator.pop(context);
      Navigator.pop(context);
      Navigator.pop(context);
    } else {
      // Anonymous user, just go to profile
      Posthog().capture(eventName: 'x_connected', properties: {'existing_omi_user': false});
      Provider.of<PersonaProvider>(context, listen: false).setRouting(widget.routing);
      routeToPage(context, const PersonaProfilePage(), replace: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PersonaProvider>(builder: (context, provider, child) {
      return Stack(
        children: [
          // Background image
          Positioned.fill(
            child: Image.asset(
              Assets.images.newBackground.path,
              fit: BoxFit.cover,
            ),
          ),
          Scaffold(
            backgroundColor: Colors.transparent,
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24.0),
                child: Column(
                  children: [
                    const Spacer(flex: 2),
                    SvgPicture.asset(Assets.images.checkbox),
                    const SizedBox(height: 24),
                    Text(
                      FirebaseAuth.instance.currentUser?.isAnonymous == false
                          ? 'X Connected Successfully!'
                          : 'Your Omi clone is\nverified and live!',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const Spacer(flex: 1),
                    Column(
                      children: [
                        Stack(
                          children: [
                            Container(
                              width: 80,
                              height: 80,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: const Color(0xFF494947),
                                  width: 2.5,
                                ),
                              ),
                              child: ClipOval(
                                child: Image.network(
                                  provider.twitterProfile['avatar'],
                                  fit: BoxFit.cover,
                                  errorBuilder: (context, error, stackTrace) {
                                    return Container(
                                      color: Colors.grey[900],
                                      child: Icon(
                                        Icons.person,
                                        size: 40,
                                        color: Colors.white.withOpacity(0.5),
                                      ),
                                    );
                                  },
                                ),
                              ),
                            ),
                            Positioned(
                              right: 4,
                              bottom: 2,
                              child: Container(
                                width: 18,
                                height: 18,
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
                        const SizedBox(height: 14),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            Padding(
                              padding: const EdgeInsets.only(bottom: 2.0),
                              child: Text(
                                tryDecodingText(provider.twitterProfile['name']),
                                style: TextStyle(
                                  color: Colors.white.withOpacity(0.74),
                                  fontSize: 20,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                            const SizedBox(width: 4),
                            const Icon(
                              Icons.verified,
                              color: Color(0xFF0073FF),
                              size: 20,
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 34),
                    widget.message.isNotEmpty
                        ? Container(
                            width: MediaQuery.sizeOf(context).width * 0.65,
                            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
                            decoration: BoxDecoration(
                              color: Colors.white.withOpacity(0.2),
                              borderRadius: const BorderRadius.only(
                                topLeft: Radius.circular(18),
                                topRight: Radius.circular(18),
                                bottomRight: Radius.circular(18),
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  widget.message.decodeString,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w400,
                                  ),
                                )
                              ],
                            ),
                          )
                        : const SizedBox(),
                    const Spacer(flex: 2),
                    if (FirebaseAuth.instance.currentUser?.isAnonymous == true)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: ElevatedButton(
                          onPressed: () async {
                            routeToPage(context, const CloneChatPage(), replace: true);
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.transparent,
                            foregroundColor: Colors.white,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(16),
                              side: BorderSide(color: Colors.white.withOpacity(0.12), width: 4),
                            ),
                          ),
                          child: const Text(
                            'Start chatting!',
                            style: TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ),
                    TextButton(
                      onPressed: () {
                        _handleNavigation();
                        provider.onTwitterVerifiedCompleted();
                      },
                      child: Text(
                        FirebaseAuth.instance.currentUser?.isAnonymous == false
                            ? 'Continue creating your persona'
                            : 'Share public link',
                        style: TextStyle(
                          fontSize: 18,
                          color: Colors.white.withOpacity(0.6),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const Spacer(flex: 1),
                  ],
                ),
              ),
            ),
          ),
        ],
      );
    });
  }
}
