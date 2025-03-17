import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/pages/persona/twitter/clone_success_sceen.dart';
import 'package:omi/utils/other/string_utils.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

class VerifyIdentityScreen extends StatefulWidget {
  final PersonaProfileRouting routing;
  const VerifyIdentityScreen({
    super.key,
    this.routing = PersonaProfileRouting.no_device,
  });

  @override
  _VerifyIdentityScreenState createState() => _VerifyIdentityScreenState();
}

class _VerifyIdentityScreenState extends State<VerifyIdentityScreen> {
  bool _isVerifying = false;
  bool _isLoading = false;
  bool postTweetClicked = false;

  @override
  void initState() {
    super.initState();
  }

  void setPostTweetClicked(bool value) {
    if (postTweetClicked == value) return;
    if (mounted) {
      setState(() {
        postTweetClicked = value;
      });
    }
  }

  Future<void> _openTwitterToTweet(BuildContext context) async {
    setState(() {
      _isLoading = true;
    });
    var provider = context.read<PersonaProvider>();
    String? handle = provider.twitterProfile['profile'];
    if (handle == null) {
      return;
    }

    // username
    String? username = provider.twitterProfile['persona_username'];
    username ??= handle;
    if (username.startsWith("@")) {
      username = username.substring(1);
    }
    provider.updateUsername(username);

    final tweetText = Uri.encodeComponent('Verifying my clone($username): https://personas.omi.me/u/$username');
    final twitterUrl = 'https://twitter.com/intent/tweet?text=$tweetText';
    setPostTweetClicked(true);
    await Posthog().capture(eventName: 'post_tweet_clicked', properties: {
      'x_handle': handle,
      'persona_username': username,
    });
    setState(() {
      _isLoading = false;
    });
    if (await canLaunchUrl(Uri.parse(twitterUrl))) {
      await launchUrl(Uri.parse(twitterUrl), mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _verifyTweet() async {
    if (_isVerifying) return;

    setState(() {
      _isVerifying = true;
    });

    try {
      final handle = context.read<PersonaProvider>().twitterProfile['profile'];
      final username = context.read<PersonaProvider>().username;
      final isVerified = await context.read<PersonaProvider>().verifyTweet();
      if (isVerified) {
        final message = await getPersonaInitialMessage(username);
        await Posthog().capture(eventName: 'tweet_verified', properties: {'x_handle': handle});
        SharedPreferencesUtil().hasPersonaCreated = true;
        routeToPage(
            context,
            CloneSuccessScreen(
              message: message,
              routing: widget.routing,
            ));
      } else {
        if (mounted) {
          showDialog(
            context: context,
            builder: (BuildContext context) {
              return AlertDialog(
                backgroundColor: Colors.grey[900],
                title: const Text(
                  'Verification Failed',
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
                'An error occurred while verifying your tweet. Did you post the tweet? Please try again.',
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
              Assets.images.newBackground.path,
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
                            color: Color(0xFF0073FF),
                            size: 50,
                          ),
                        ),
                        const SizedBox(height: 14),
                        const Text(
                          'Let\'s prevent\nimpersonation!',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 26,
                            fontWeight: FontWeight.bold,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Please verify you\'re the owner of\nthis account',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.6),
                            fontSize: 16,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 32),
                        Container(
                          width: MediaQuery.of(context).size.width * 0.24,
                          height: MediaQuery.of(context).size.width * 0.24,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Colors.white.withOpacity(0.3),
                              width: 3,
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
                              tryDecodingText(provider.twitterProfile['name'] ?? ""),
                              style: TextStyle(
                                color: Colors.white.withOpacity(0.78),
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
                        ElevatedButton(
                          onPressed: () {
                            if (_isVerifying || _isLoading) {
                              return;
                            } else {
                              if (postTweetClicked) {
                                _verifyTweet();
                              } else {
                                _openTwitterToTweet(context);
                              }
                            }
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.white.withOpacity(0.12),
                            foregroundColor: Colors.white,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(28),
                            ),
                          ),
                          child: _isVerifying || _isLoading
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                  ),
                                )
                              : Text(
                                  postTweetClicked ? "Check my tweet" : "Verify it's me",
                                  style: const TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                        ),
                        const SizedBox(height: 16),
                        postTweetClicked
                            ? TextButton(
                                onPressed: () async {
                                  await _openTwitterToTweet(context);
                                },
                                child: Text(
                                  "Didn't post the tweet? click here",
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.8),
                                    fontSize: 14,
                                  ),
                                ),
                              )
                            : const SizedBox(),
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
