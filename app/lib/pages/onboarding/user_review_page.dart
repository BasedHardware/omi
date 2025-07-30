import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:in_app_review/in_app_review.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class UserReviewPage extends StatefulWidget {
  final VoidCallback goNext;

  const UserReviewPage({super.key, required this.goNext});

  @override
  State<UserReviewPage> createState() => _UserReviewPageState();
}

class _UserReviewPageState extends State<UserReviewPage> {
  bool _isLoading = false;
  final InAppReview _inAppReview = InAppReview.instance;

  Future<void> _requestReview() async {
    setState(() {
      _isLoading = true;
    });

    try {
      HapticFeedback.mediumImpact();

      // Check if the in-app review is available
      if (await _inAppReview.isAvailable()) {
        // Request the review and wait for completion
        await _inAppReview.requestReview();
        MixpanelManager().track('App Review Requested', properties: {'source': 'onboarding'});

        // Add a small delay to ensure the review dialog has been processed
        await Future.delayed(const Duration(milliseconds: 1000));
      } else {
        // Fallback to opening the store directly
        await _inAppReview.openStoreListing(
          appStoreId: Platform.isIOS ? '6651027111' : null, // Replace with actual App Store ID
        );
        MixpanelManager().track('App Store Opened', properties: {'source': 'onboarding'});

        // Add delay for store opening
        await Future.delayed(const Duration(milliseconds: 500));
      }
    } catch (e) {
      debugPrint('Error requesting review: $e');
      // Show a friendly message or continue silently
    } finally {
      setState(() {
        _isLoading = false;
      });

      // Continue to next page after review interaction is complete
      widget.goNext();
    }
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
                  'Help us reach more people by leaving a review in the ${Platform.isIOS ? 'App Store' : 'Google Play Store'}. Your feedback means the world to us!',
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
                                'Rate on ${Platform.isIOS ? 'App Store' : 'Google Play'}',
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
                  child: const Text(
                    'Maybe later',
                    style: TextStyle(
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
