import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

class UserReviewPage extends StatefulWidget {
  final VoidCallback goNext;

  const UserReviewPage({super.key, required this.goNext});

  @override
  State<UserReviewPage> createState() => _UserReviewPageState();
}

class _UserReviewPageState extends State<UserReviewPage> {
  bool _isLoading = false;

  Future<void> _requestReview() async {
    setState(() {
      _isLoading = true;
    });

    HapticFeedback.mediumImpact();

    final Uri reviewUrl = Platform.isIOS
        ? Uri.parse('https://apps.apple.com/app/id6502156163?action=write-review')
        : Uri.parse('https://play.google.com/store/apps/details?id=com.friend.ios');

    if (await canLaunchUrl(reviewUrl)) {
      await launchUrl(reviewUrl, mode: LaunchMode.externalApplication);
      MixpanelManager().track('App Review Opened', properties: {'source': 'onboarding'});
      await Future.delayed(const Duration(milliseconds: 500));
    } else {
      Logger.debug('Could not launch review URL');
    }

    setState(() {
      _isLoading = false;
    });

    // Continue to next page after review interaction is complete
    widget.goNext();
  }

  Future<void> _skipReview() async {
    HapticFeedback.lightImpact();
    MixpanelManager().track('App Review Skipped', properties: {'source': 'onboarding'});
    widget.goNext();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Background area - takes remaining space
        Expanded(
          child: Container(), // Just takes up space for background image
        ),

        // Bottom drawer card - wraps content
        Container(
          width: double.infinity,
          padding: EdgeInsets.fromLTRB(32, 8, 32, 4),
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(40),
              topRight: Radius.circular(40),
            ),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 32),

                // Main title
                const Text(
                  'Loving Omi?',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 32,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),

                const SizedBox(height: 16),

                // Subtitle
                Text(
                  Platform.isIOS ? context.l10n.leaveReviewIos : context.l10n.leaveReviewAndroid,
                  style: const TextStyle(
                    color: Colors.grey,
                    fontSize: 16,
                    height: 1.4,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),

                const SizedBox(height: 32),

                // Review button
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _isLoading ? null : _requestReview,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.deepPurple,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(28),
                      ),
                      disabledBackgroundColor: Colors.deepPurple.withOpacity(0.5),
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 2,
                            ),
                          )
                        : Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              FaIcon(
                                Platform.isIOS ? FontAwesomeIcons.appStoreIos : FontAwesomeIcons.googlePlay,
                                size: 20,
                              ),
                              const SizedBox(width: 12),
                              Text(
                                Platform.isIOS ? context.l10n.rateOnAppStore : context.l10n.rateOnGooglePlay,
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                  ),
                ),

                // Skip button
                TextButton(
                  onPressed: _isLoading ? null : _skipReview,
                  child: Text(
                    context.l10n.maybeLater,
                    style: const TextStyle(
                      color: Colors.grey,
                      fontSize: 16,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
