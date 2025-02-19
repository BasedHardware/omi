import 'package:flutter/material.dart';
import 'package:friend_private/pages/persona/persona_provider.dart';
import 'package:friend_private/pages/persona/twitter/clone_success_sceen.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

class VerifyIdentityScreen extends StatefulWidget {
  const VerifyIdentityScreen({
    super.key,
  });

  @override
  _VerifyIdentityScreenState createState() => _VerifyIdentityScreenState();
}

class _VerifyIdentityScreenState extends State<VerifyIdentityScreen> {
  bool _isVerifying = false;
  String? _verificationError;

  @override
  void initState() {
    super.initState();
  }

  Future<void> _openTwitterToTweet(BuildContext context) async {
    var provider = context.read<PersonaProvider>();
    var handle = provider.usernameController.text;
    if (handle.isEmpty) {
      handle = provider.twitterProfile['profile'];
    }
    final tweetText = Uri.encodeComponent('Verifying my clone: https://persona.omi.me/u/$handle');
    final twitterUrl = 'https://twitter.com/intent/tweet?text=$tweetText';

    if (await canLaunchUrl(Uri.parse(twitterUrl))) {
      await launchUrl(Uri.parse(twitterUrl), mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _verifyTweet() async {
    if (_isVerifying) return;

    setState(() {
      _isVerifying = true;
      _verificationError = null;
    });

    try {
      final handle = context.read<PersonaProvider>().twitterProfile['profile'];
      final isVerified = await context.read<PersonaProvider>().verifyTweet(handle);
      if (isVerified) {
        routeToPage(context, CloneSuccessScreen());
      } else {
        // Show error dialog
        if (mounted) {
          showDialog(
            context: context,
            builder: (BuildContext context) {
              return AlertDialog(
                backgroundColor: Colors.grey[900],
                title: const Text(
                  'Verification Not Complete',
                  style: TextStyle(color: Colors.white),
                ),
                content: const Text(
                  'We couldn\'t find your verification tweet. Please make sure you\'ve posted the tweet and try again.',
                  style: TextStyle(color: Colors.white70),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text(
                      'OK',
                      style: TextStyle(color: Colors.white),
                    ),
                  ),
                ],
              );
            },
          );
        }
      }
    } catch (e) {
      if (mounted) {
        showDialog(
          context: context,
          builder: (BuildContext context) {
            return AlertDialog(
              backgroundColor: Colors.grey[900],
              title: const Text(
                'Verification Error',
                style: TextStyle(color: Colors.white),
              ),
              content: const Text(
                'An error occurred while verifying your tweet. Please try again. Did you post the tweet?',
                style: TextStyle(color: Colors.white70),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text(
                    'OK',
                    style: TextStyle(color: Colors.white),
                  ),
                ),
              ],
            );
          },
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isVerifying = false;
        });
      }
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
            appBar: AppBar(
              backgroundColor: Colors.transparent,
              elevation: 0,
            ),
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const SizedBox(height: 0),
                    Column(
                      children: [
                        const Center(
                          child: Icon(
                            Icons.verified,
                            color: Colors.blue,
                            size: 48,
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'Let\'s prevent\nimpersonation!',
                          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                            shadows: [
                              Shadow(
                                offset: const Offset(0, 1),
                                blurRadius: 15,
                                color: Colors.white.withOpacity(1),
                              ),
                              Shadow(
                                offset: const Offset(0, 0),
                                blurRadius: 15,
                                color: Colors.white.withOpacity(0.3),
                              ),
                            ],
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Please verify you\'re the owner of\nthis account to prevent\nimpersonation',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: Colors.white.withOpacity(0.8),
                            shadows: [
                              Shadow(
                                offset: const Offset(0, 1),
                                blurRadius: 3,
                                color: Colors.white.withOpacity(0.25),
                              ),
                            ],
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 32),
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
                        const SizedBox(height: 16),
                        Column(
                          children: [
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
                      ],
                    ),
                    Column(
                      children: [
                        if (_verificationError != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 16.0),
                            child: Text(
                              _verificationError!,
                              style: const TextStyle(
                                color: Colors.red,
                                fontSize: 14,
                              ),
                              textAlign: TextAlign.center,
                            ),
                          ),
                        ElevatedButton(
                          onPressed: () => _openTwitterToTweet(context),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.grey[900],
                            foregroundColor: Colors.white,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(28),
                            ),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Image.asset(
                                'assets/images/x_logo.png',
                                width: 20,
                                height: 20,
                              ),
                              const SizedBox(width: 8),
                              const Text(
                                'Verify it\'s me',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: _isVerifying ? null : _verifyTweet,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.transparent,
                            foregroundColor: Colors.white,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(28),
                              side: BorderSide(color: Colors.white.withOpacity(0.2)),
                            ),
                          ),
                          child: _isVerifying
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                  ),
                                )
                              : const Text(
                                  'I have verified',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                        ),
                        const SizedBox(height: 40),
                      ],
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
