import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Extra space under the wrapper progress bar (screen y=90) so the heading
/// sits in the content, not against the top chrome.
const double kOnboardingKnowledgeGraphTitleTopPadding = 120;

class OnboardingKnowledgeGraphStep extends StatelessWidget {
  final VoidCallback onContinue;

  const OnboardingKnowledgeGraphStep({super.key, required this.onContinue});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: Padding(
          key: const Key('onboardingKnowledgeGraphPadding'),
          // Sit well below the wrapper's progress bar (top: 90) —
          // SafeArea already consumed the status bar.
          padding: const EdgeInsets.fromLTRB(24, kOnboardingKnowledgeGraphTitleTopPadding, 24, 24),
          child: Column(
            children: [
              SizedBox(
                width: double.infinity,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    context.l10n.onboardingWhatIKnowAboutYouTitle,
                    maxLines: 1,
                    softWrap: false,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      height: 1.2,
                      fontFamily: 'Manrope',
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: MemoryGraphPage(
                    embedded: true,
                    flat2d: true,
                    pollWhileEmpty: true,
                    loadFallbackGraph: () {
                      SpeechProfileProvider? speech;
                      try {
                        speech = context.read<SpeechProfileProvider>();
                      } catch (_) {
                        speech = null;
                      }
                      final spoken = _onboardingSpeechProfileText(speech);
                      if (spoken.isEmpty) {
                        return Future<Map<String, dynamic>>.value({'nodes': <dynamic>[], 'edges': <dynamic>[]});
                      }
                      String? userName;
                      try {
                        userName = SharedPreferencesUtil().givenName;
                      } catch (_) {}
                      return KnowledgeGraphApi.extractKnowledgeGraph(spoken, userName: userName);
                    },
                    trackOpenEvent: false,
                    showAppBar: false,
                    showShareButton: false,
                    initialZoom: 1.0,
                  ),
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton(
                  onPressed: onContinue,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                    elevation: 0,
                  ),
                  child: Text(
                    context.l10n.continueAction,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _onboardingSpeechProfileText(SpeechProfileProvider? speech) {
  if (speech == null) return '';
  final live = speech.text.trim();
  if (live.isNotEmpty) return live;
  return speech.segments.where((s) => s.speakerId != omiSpeakerId).map((s) => s.text).join(' ').trim();
}
