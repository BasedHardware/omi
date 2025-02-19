import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/pages/persona/persona_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

import '../persona_profile.dart';

class CloneSuccessScreen extends StatefulWidget {
  const CloneSuccessScreen({
    super.key,
  });

  @override
  State<CloneSuccessScreen> createState() => _CloneSuccessScreenState();
}

class _CloneSuccessScreenState extends State<CloneSuccessScreen> {
  bool _isLoading = false;

  void _handleNavigation() {
    final user = FirebaseAuth.instance.currentUser;

    // If user is not anonymous (signed in with Google/Apple), they came from create/update flow
    if (user != null && !user.isAnonymous) {
      Navigator.pop(context);
      Navigator.pop(context);
      Navigator.pop(context);
    } else {
      // Anonymous user, just go to profile
      routeToPage(context, const PersonaProfilePage());
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
              'assets/images/new_background.png',
              fit: BoxFit.cover,
            ),
          ),
          Scaffold(
            backgroundColor: Colors.transparent,
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const SizedBox(height: 24),
                    Container(
                      margin: const EdgeInsets.only(top: 40),
                      padding: const EdgeInsets.fromLTRB(40, 60, 40, 24),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Column(
                        children: [
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
                                        color: Colors.white.withOpacity(0.2),
                                        width: 2,
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
                                    right: 0,
                                    bottom: 0,
                                    child: Container(
                                      width: 20,
                                      height: 20,
                                      decoration: BoxDecoration(
                                        color: const Color.fromARGB(255, 85, 184, 88),
                                        shape: BoxShape.circle,
                                        border: Border.all(
                                          color: Colors.white.withOpacity(0.3),
                                          width: 2,
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              Text(
                                provider.twitterProfile['name'],
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 20,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 24),
                          if (FirebaseAuth.instance.currentUser?.isAnonymous == false) ...[
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Image.asset(
                                  'assets/images/x_logo_mini.png',
                                  width: 16,
                                  height: 16,
                                ),
                                const SizedBox(width: 8),
                                const Text(
                                  'Twitter Connected',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 14,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                const Icon(
                                  Icons.check_circle,
                                  color: Color.fromARGB(255, 85, 184, 88),
                                  size: 16,
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                          ],
                          Text(
                            FirebaseAuth.instance.currentUser?.isAnonymous == false
                                ? 'Twitter Connected Successfully!'
                                : 'Your Omi Clone is live!',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            FirebaseAuth.instance.currentUser?.isAnonymous == false
                                ? 'Your Twitter data has been connected\nto enhance your persona'
                                : 'Share it with anyone who\nneeds to hear back from you',
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.8),
                              fontSize: 14,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 32),
                          FirebaseAuth.instance.currentUser?.isAnonymous == false
                              ? Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                  decoration: BoxDecoration(
                                    color: Colors.white.withOpacity(0.1),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(
                                        Icons.link,
                                        color: Colors.white.withOpacity(0.5),
                                        size: 20,
                                      ),
                                      const SizedBox(width: 8),
                                      Text(
                                        'personas.omi.me/u/${provider.twitterProfile['profile']}',
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 16,
                                        ),
                                      ),
                                    ],
                                  ),
                                )
                              : Container(),
                        ],
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 50),
                      child: ElevatedButton(
                        onPressed: _handleNavigation,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.transparent,
                          foregroundColor: Colors.white,
                          minimumSize: const Size(double.infinity, 56),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                            side: const BorderSide(color: Colors.grey),
                          ),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            if (_isLoading)
                              const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              )
                            else ...[
                              Text(
                                FirebaseAuth.instance.currentUser?.isAnonymous == false
                                    ? 'Continue creating your persona'
                                    : 'Check out your persona',
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
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
