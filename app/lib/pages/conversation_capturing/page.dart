import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
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

  @override
  void initState() {
    _controller = TabController(length: 2, vsync: this, initialIndex: 0);
    _controller!.addListener(() => setState(() {}));
    showSummarizeConfirmation = SharedPreferencesUtil().showSummarizeConfirmation;
    super.initState();
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
                  const Expanded(child: Text("In progress")),
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
