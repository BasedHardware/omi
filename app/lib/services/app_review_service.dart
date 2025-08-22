import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:in_app_review/in_app_review.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppReviewService {
  static final AppReviewService _instance = AppReviewService._internal();
  factory AppReviewService() => _instance;
  AppReviewService._internal();

  final InAppReview _inAppReview = InAppReview.instance;
  static const String _hasCompletedFirstActionItemKey = 'has_completed_first_action_item';
  static const String _hasShownReviewPromptKey = 'has_shown_review_prompt';
  static const String _hasFirstConversationKey = 'has_first_conversation';
  static const String _hasShownReviewForConversationKey = 'has_shown_review_for_conversation';
  static const String _hasShownReviewForActionItemKey = 'has_shown_review_for_action_item';

  // Checks if the user has completed their first action item
  Future<bool> hasCompletedFirstActionItem() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_hasCompletedFirstActionItemKey) ?? false;
  }

  // Marks that the user has completed their first action item
  Future<void> markFirstActionItemCompleted() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_hasCompletedFirstActionItemKey, true);
  }

  // Checks if the review prompt has already been shown
  Future<bool> hasShownReviewPrompt() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_hasShownReviewPromptKey) ?? false;
  }

  // Marks that the review prompt has been shown
  Future<void> markReviewPromptShown() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_hasShownReviewPromptKey, true);
  }

  // Checks if this is the user's first conversation
  Future<bool> isFirstConversation() async {
    final prefs = await SharedPreferences.getInstance();
    return !(prefs.getBool(_hasFirstConversationKey) ?? false);
  }

  // Marks that the user has had their first conversation
  Future<void> markFirstConversation() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_hasFirstConversationKey, true);
  }

  // Checks if review prompt has been shown for conversation
  Future<bool> hasShownReviewForConversation() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_hasShownReviewForConversationKey) ?? false;
  }

  // Marks that review prompt has been shown for conversation
  Future<void> markReviewShownForConversation() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_hasShownReviewForConversationKey, true);
  }

  // Checks if review prompt has been shown for action item
  Future<bool> hasShownReviewForActionItem() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_hasShownReviewForActionItemKey) ?? false;
  }

  // Marks that review prompt has been shown for action item
  Future<void> markReviewShownForActionItem() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_hasShownReviewForActionItemKey, true);
  }

  // Shows the review prompt if conditions are met
  Future<bool> showReviewPromptIfNeeded(BuildContext context, {bool isProcessingFirstConversation = false}) async {
    final hasCompleted = await hasCompletedFirstActionItem();
    final isFirst = await isFirstConversation();
    
    bool shouldShow = false;
    
    if (isProcessingFirstConversation && isFirst) {
      final hasShownForConversation = await hasShownReviewForConversation();
      if (!hasShownForConversation) {
        shouldShow = true;
        await markFirstConversation();
        await markReviewShownForConversation();
      }
    } else if (hasCompleted) {
      final hasShownForActionItem = await hasShownReviewForActionItem();
      if (!hasShownForActionItem) {
        shouldShow = true;
        await markReviewShownForActionItem();
      }
    }

    if (shouldShow) {
      await markReviewPromptShown();
      _showReviewDialog(context);
      return true;
    }
    return false;
  }

  // Shows a dialog asking the user to review the app
  Future<void> _showReviewDialog(BuildContext context) async {
    HapticFeedback.mediumImpact();

    return showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return Dialog(
          backgroundColor: Colors.transparent,
          elevation: 0,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: Colors.grey.shade800, width: 1),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Loving Omi?',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                Text(
                  'Help us reach more people by leaving a review in the ${Platform.isIOS ? 'App Store' : 'Google Play Store'}. Your feedback means the world to us!',
                  style: const TextStyle(
                    color: Colors.grey,
                    fontSize: 16,
                    height: 1.4,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                Column(
                  children: [
                    ElevatedButton(
                      onPressed: () async {
                        HapticFeedback.mediumImpact();
                        Navigator.of(context).pop();

                        try {
                          // Check if the in-app review is available
                          if (await _inAppReview.isAvailable()) {
                            // Request the review
                            await _inAppReview.requestReview();
                            MixpanelManager()
                                .track('App Review Requested', properties: {'source': 'action_item_completion'});
                          } else {
                            await _inAppReview.openStoreListing(
                              appStoreId: Platform.isIOS ? '6651027111' : null,
                            );
                            MixpanelManager()
                                .track('App Store Opened', properties: {'source': 'action_item_completion'});
                          }
                        } catch (e) {
                          debugPrint('Error requesting review: $e');
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.deepPurple,
                        foregroundColor: Colors.white,
                        minimumSize: const Size(double.infinity, 48),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(20),
                        ),
                      ),
                      child: Row(
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
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () {
                        HapticFeedback.lightImpact();
                        MixpanelManager().track('App Review Skipped', properties: {'source': 'action_item_completion'});
                        Navigator.of(context).pop();
                      },
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
              ],
            ),
          ),
        );
      },
    );
  }
}
