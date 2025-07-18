import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/widgets/photos_grid.dart';
import 'package:provider/provider.dart';

class ConversationCapturingPage extends StatefulWidget {
  final String? topConversationId;

  const ConversationCapturingPage({
    super.key,
    this.topConversationId,
  });

  @override
  State<ConversationCapturingPage> createState() => _ConversationCapturingPageState();
}

class _ConversationCapturingPageState extends State<ConversationCapturingPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  TabController? _controller;
  late bool showSummarizeConfirmation;
  late AnimationController _animationController;

  @override
  void initState() {
    _controller = TabController(length: 2, vsync: this, initialIndex: 0);
    _controller!.addListener(() => setState(() {}));
    showSummarizeConfirmation = SharedPreferencesUtil().showSummarizeConfirmation;
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat(reverse: true);
    super.initState();
  }

  @override
  void dispose() {
    _controller?.dispose();
    _animationController.dispose();
    super.dispose();
  }

  int convertDateTimeToSeconds(DateTime dateTime) {
    DateTime now = DateTime.now();
    Duration difference = now.difference(dateTime);

    return difference.inSeconds;
  }

  String convertToHHMMSS(int seconds) {
    int hours = seconds ~/ 3600;
    int minutes = (seconds % 3600) ~/ 60;
    int remainingSeconds = seconds % 60;

    String twoDigits(int n) => n.toString().padLeft(2, '0');

    return '${twoDigits(hours)}:${twoDigits(minutes)}:${twoDigits(remainingSeconds)}';
  }

  void _pushNewConversation(BuildContext context, conversation) async {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (c) => ConversationDetailPage(
          conversation: conversation,
        ),
      ));
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            key: scaffoldKey,
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              automaticallyImplyLeading: false,
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: Row(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: () {
                      Navigator.pop(context);
                      return;
                    },
                    icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
                  ),
                  const SizedBox(width: 4),
                  Text(provider.photos.isNotEmpty ? "📸" : "🎙️"),
                  const SizedBox(width: 4),
                  const Expanded(child: Text("Listening")),
                  !provider.isSpeakerSuggestionReady
                      ? Tooltip(
                          message: 'Calibrating speaker identification...',
                          child: FadeTransition(
                              opacity: _animationController,
                              child: Image.asset(
                                Assets.images.speaker0Icon.path,
                                width: 24,
                                height: 24,
                              )),
                        )
                      : const SizedBox.shrink(),
                ],
              ),
            ),
            body: Column(
              children: [
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: TabBarView(
                      controller: _controller,
                      physics: const NeverScrollableScrollPhysics(),
                      children: [
                        // Transcripts, photos
                        provider.segments.isEmpty && provider.photos.isEmpty
                            ? const Center(
                                child: Padding(
                                  padding: EdgeInsets.only(top: 50.0),
                                  child: Text("Waiting for transcript or photos..."),
                                ),
                              )
                            : getTranscriptWidget(
                                false,
                                provider.segments,
                                provider.photos,
                                deviceProvider.connectedDevice,
                                suggestions: provider.suggestionsBySegmentId,
                                onAcceptSuggestion: (suggestion) {
                                  provider.assignSpeakerToConversation(suggestion.speakerId, suggestion.personId,
                                      suggestion.personName, [suggestion.segmentId]);
                                },
                                editSegment: (segmentId, speakerId) {
                                  final connectivityProvider =
                                      Provider.of<ConnectivityProvider>(context, listen: false);
                                  if (!connectivityProvider.isConnected) {
                                    ConnectivityProvider.showNoInternetDialog(context);
                                    return;
                                  }
                                  showModalBottomSheet(
                                    context: context,
                                    isScrollControlled: true,
                                    backgroundColor: Colors.black,
                                    shape: const RoundedRectangleBorder(
                                      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                    ),
                                    builder: (context) {
                                      final suggestion = provider.suggestionsBySegmentId.values.firstWhere(
                                          (s) => s.speakerId == speakerId,
                                          orElse: () => SpeakerLabelSuggestionEvent.empty());
                                      return NameSpeakerBottomSheet(
                                        speakerId: speakerId,
                                        segmentId: segmentId,
                                        segments: provider.segments,
                                        suggestion: suggestion,
                                        isCapturing: true,
                                        people: context.read<PeopleProvider>().people,
                                        userName: SharedPreferencesUtil().givenName,
                                        onSpeakerAssigned: (speakerId, personId, personName, segmentIds) async {
                                          await provider.assignSpeakerToConversation(
                                              speakerId, personId, personName, segmentIds);
                                        },
                                      );
                                    },
                                  );
                                },
                              ),
                        // Summary Tab
                        Center(
                          child: Padding(
                            padding:
                                const EdgeInsets.symmetric(horizontal: 32.0).copyWith(bottom: 50.0), // Adjust padding
                            child: Text(
                              provider.segments.isEmpty && provider.photos.isEmpty
                                  ? "No summary yet"
                                  : "Conversation is summarized after 2 minutes of no speech 🤫",
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: provider.segments.isEmpty ? 16 : 22),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
            floatingActionButton: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                (provider.segments.isEmpty && provider.photos.isEmpty)
                    ? const SizedBox()
                    : ConversationBottomBar(
                        mode: ConversationBottomBarMode.recording,
                        selectedTab: _controller!.index == 0 ? ConversationTab.transcript : ConversationTab.summary,
                        hasSegments: provider.segments.isNotEmpty || provider.photos.isNotEmpty,
                        onTabSelected: (tab) {
                          _controller!.animateTo(tab == ConversationTab.transcript ? 0 : 1);
                          setState(() {});
                        },
                        onStopPressed: () {
                          if (provider.segments.isNotEmpty || provider.photos.isNotEmpty) {
                            if (!showSummarizeConfirmation) {
                              context.read<CaptureProvider>().forceProcessingCurrentConversation();
                              Navigator.of(context).pop();
                              return;
                            }
                            showDialog(
                              context: context,
                              builder: (context) {
                                return StatefulBuilder(
                                  builder: (context, setState) {
                                    return ConfirmationDialog(
                                      title: "Finished Conversation?",
                                      description:
                                          "Are you sure you want to stop recording and summarize the conversation now?\n\nHints: Conversation is summarized after 2 minutes of no speech.",
                                      checkboxValue: !showSummarizeConfirmation,
                                      checkboxText: "Don't ask me again",
                                      onCheckboxChanged: (value) {
                                        setState(() {
                                          showSummarizeConfirmation = !value;
                                        });
                                      },
                                      onCancel: () {
                                        Navigator.of(context).pop();
                                      },
                                      onConfirm: () {
                                        SharedPreferencesUtil().showSummarizeConfirmation = showSummarizeConfirmation;
                                        context.read<CaptureProvider>().forceProcessingCurrentConversation();
                                        Navigator.of(context).pop();
                                        Navigator.of(context).pop();
                                      },
                                    );
                                  },
                                );
                              },
                            );
                          }
                        },
                      ),
              ],
            ),
          ),
        );
      },
    );
  }
}

String transcriptElapsedTime(String timepstamp) {
  timepstamp = timepstamp.split(' - ')[1];
  return timepstamp;
}
