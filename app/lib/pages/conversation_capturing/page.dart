import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

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

  @override
  void dispose() {
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

  Widget _buildErrorWidget() {
    return Container(
      color: Colors.grey.shade800,
      child: const Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.image_not_supported, color: Colors.white54, size: 32),
          SizedBox(height: 8),
          Text(
            'Error loading image',
            style: TextStyle(color: Colors.white70, fontSize: 12),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        var conversationSource = ConversationSource.omi;
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
                  const Text("🎙️"),
                  const SizedBox(width: 4),
                  const Expanded(child: Text("In progress")),
                  if (SharedPreferencesUtil().devModeJoanFollowUpEnabled)
                    IconButton(
                      onPressed: () async {
                        getFollowUpQuestion().then((v) {
                          debugPrint('Follow up question: $v');
                        });
                      },
                      icon: const Icon(Icons.question_answer),
                    )
                ],
              ),
            ),
            body: Column(
              children: [
                if (provider.segments.isNotEmpty || provider.allImages.isNotEmpty) ...[
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16.0),
                      child: SingleChildScrollView(
                        child: Column(
                          children: [
                            // Display all images (local + cloud)
                            if (provider.allImages.isNotEmpty) ...[
                              const SizedBox(height: 16),
                              Row(
                                children: [
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: Colors.blue.withOpacity(0.2),
                                      borderRadius: BorderRadius.circular(12),
                                      border: Border.all(color: Colors.blue.withOpacity(0.3)),
                                    ),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        const Icon(Icons.camera_alt, color: Colors.blue, size: 16),
                                        const SizedBox(width: 6),
                                        Text(
                                          'Live Images',
                                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                            fontWeight: FontWeight.bold,
                                            color: Colors.blue,
                                            fontSize: 14,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: Colors.grey.withOpacity(0.2),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Text(
                                      '${provider.allImages.length}',
                                      style: const TextStyle(
                                        color: Colors.white70,
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 16),
                              // Enhanced grid layout with animations
                              AnimatedContainer(
                                duration: const Duration(milliseconds: 300),
                                child: GridView.builder(
                                  shrinkWrap: true,
                                  physics: const NeverScrollableScrollPhysics(),
                                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                                    crossAxisCount: 2,
                                    crossAxisSpacing: 16,
                                    mainAxisSpacing: 16,
                                    childAspectRatio: 1.1,
                                  ),
                                  itemCount: provider.allImages.length,
                                  itemBuilder: (context, index) {
                                    final image = provider.allImages[index];
                                    final isLocalImage = image['type'] != 'cloud';
                                    
                                    return AnimatedContainer(
                                      duration: Duration(milliseconds: 300 + (index * 100)),
                                      curve: Curves.easeOutCubic,
                                      child: GestureDetector(
                                        onTap: () {
                                          // Enhanced full screen image view
                                          showGeneralDialog(
                                            context: context,
                                            barrierDismissible: true,
                                            barrierLabel: 'Image Viewer',
                                            barrierColor: Colors.black87,
                                            transitionDuration: const Duration(milliseconds: 300),
                                            pageBuilder: (context, animation, secondaryAnimation) {
                                              return FadeTransition(
                                                opacity: animation,
                                                child: ScaleTransition(
                                                  scale: Tween<double>(begin: 0.8, end: 1.0).animate(
                                                    CurvedAnimation(parent: animation, curve: Curves.easeOutCubic),
                                                  ),
                                                  child: Scaffold(
                                                    backgroundColor: Colors.black,
                                                    body: Stack(
                                                      children: [
                                                        // Background blur effect
                                                        Positioned.fill(
                                                          child: Container(
                                                            decoration: BoxDecoration(
                                                              gradient: RadialGradient(
                                                                center: Alignment.center,
                                                                colors: [
                                                                  Colors.black.withOpacity(0.7),
                                                                  Colors.black,
                                                                ],
                                                              ),
                                                            ),
                                                          ),
                                                        ),
                                                        // Image content
                                                        Center(
                                                          child: Container(
                                                            margin: const EdgeInsets.all(20),
                                                            decoration: BoxDecoration(
                                                              borderRadius: BorderRadius.circular(20),
                                                              boxShadow: [
                                                                BoxShadow(
                                                                  color: Colors.black.withOpacity(0.5),
                                                                  blurRadius: 20,
                                                                  spreadRadius: 5,
                                                                ),
                                                              ],
                                                            ),
                                                            child: ClipRRect(
                                                              borderRadius: BorderRadius.circular(20),
                                                              child: InteractiveViewer(
                                                                maxScale: 4.0,
                                                                minScale: 0.5,
                                                                child: isLocalImage 
                                                                  ? Image.memory(
                                                                      image['data'] as Uint8List,
                                                                      fit: BoxFit.contain,
                                                                      errorBuilder: (context, error, stackTrace) {
                                                                        return _buildErrorWidget();
                                                                      },
                                                                    )
                                                                  : Image.network(
                                                                      image['thumbnail_url'],
                                                                      fit: BoxFit.contain,
                                                                      loadingBuilder: (context, child, loadingProgress) {
                                                                        if (loadingProgress == null) return child;
                                                                        return Center(
                                                                          child: CircularProgressIndicator(
                                                                            value: loadingProgress.expectedTotalBytes != null
                                                                                ? loadingProgress.cumulativeBytesLoaded / loadingProgress.expectedTotalBytes!
                                                                                : null,
                                                                            color: Colors.blue,
                                                                          ),
                                                                        );
                                                                      },
                                                                      errorBuilder: (context, error, stackTrace) {
                                                                        return _buildErrorWidget();
                                                                      },
                                                                    ),
                                                              ),
                                                            ),
                                                          ),
                                                        ),
                                                        // Top bar with title and close button
                                                        Positioned(
                                                          top: MediaQuery.of(context).padding.top + 10,
                                                          left: 20,
                                                          right: 20,
                                                          child: Row(
                                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                            children: [
                                                              Container(
                                                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                                                decoration: BoxDecoration(
                                                                  color: Colors.black.withOpacity(0.7),
                                                                  borderRadius: BorderRadius.circular(20),
                                                                  border: Border.all(color: Colors.white.withOpacity(0.2)),
                                                                ),
                                                                child: Text(
                                                                  'Image ${index + 1} of ${provider.allImages.length}',
                                                                  style: const TextStyle(
                                                                    color: Colors.white,
                                                                    fontSize: 16,
                                                                    fontWeight: FontWeight.w600,
                                                                  ),
                                                                ),
                                                              ),
                                                              Container(
                                                                decoration: BoxDecoration(
                                                                  color: Colors.black.withOpacity(0.7),
                                                                  borderRadius: BorderRadius.circular(25),
                                                                  border: Border.all(color: Colors.white.withOpacity(0.2)),
                                                                ),
                                                                child: IconButton(
                                                                  onPressed: () => Navigator.pop(context),
                                                                  icon: const Icon(
                                                                    Icons.close,
                                                                    color: Colors.white,
                                                                    size: 24,
                                                                  ),
                                                                ),
                                                              ),
                                                            ],
                                                          ),
                                                        ),
                                                        // Bottom info bar
                                                        Positioned(
                                                          bottom: MediaQuery.of(context).padding.bottom + 20,
                                                          left: 20,
                                                          right: 20,
                                                          child: Container(
                                                            padding: const EdgeInsets.all(16),
                                                            decoration: BoxDecoration(
                                                              color: Colors.black.withOpacity(0.7),
                                                              borderRadius: BorderRadius.circular(20),
                                                              border: Border.all(color: Colors.white.withOpacity(0.2)),
                                                            ),
                                                            child: Row(
                                                              children: [
                                                                Container(
                                                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                                                  decoration: BoxDecoration(
                                                                    color: isLocalImage ? Colors.green.withOpacity(0.2) : Colors.blue.withOpacity(0.2),
                                                                    borderRadius: BorderRadius.circular(8),
                                                                    border: Border.all(
                                                                      color: isLocalImage ? Colors.green.withOpacity(0.5) : Colors.blue.withOpacity(0.5),
                                                                    ),
                                                                  ),
                                                                  child: Row(
                                                                    mainAxisSize: MainAxisSize.min,
                                                                    children: [
                                                                      Icon(
                                                                        Icons.fiber_manual_record,
                                                                        color: isLocalImage ? Colors.green : Colors.blue,
                                                                        size: 8,
                                                                      ),
                                                                      const SizedBox(width: 4),
                                                                      Text(
                                                                        isLocalImage ? 'LOCAL' : 'CLOUD',
                                                                        style: TextStyle(
                                                                          color: isLocalImage ? Colors.green : Colors.blue,
                                                                          fontSize: 10,
                                                                          fontWeight: FontWeight.bold,
                                                                        ),
                                                                      ),
                                                                    ],
                                                                  ),
                                                                ),
                                                                const SizedBox(width: 12),
                                                                Expanded(
                                                                  child: Text(
                                                                    'Captured: ${(image['timestamp'] as DateTime? ?? image['created_at'] as DateTime).toString().split('.')[0]}',
                                                                    style: const TextStyle(
                                                                      color: Colors.white70,
                                                                      fontSize: 12,
                                                                    ),
                                                                  ),
                                                                ),
                                                              ],
                                                            ),
                                                          ),
                                                        ),
                                                      ],
                                                    ),
                                                  ),
                                                ),
                                              );
                                            },
                                          );
                                        },
                                        child: Hero(
                                          tag: 'image_${image['id']}',
                                          child: Container(
                                            decoration: BoxDecoration(
                                              borderRadius: BorderRadius.circular(16),
                                              border: Border.all(
                                                color: isLocalImage 
                                                    ? Colors.green.withOpacity(0.4) 
                                                    : Colors.blue.withOpacity(0.4),
                                                width: 2,
                                              ),
                                              boxShadow: [
                                                BoxShadow(
                                                  color: (isLocalImage ? Colors.green : Colors.blue).withOpacity(0.2),
                                                  blurRadius: 8,
                                                  spreadRadius: 2,
                                                  offset: const Offset(0, 4),
                                                ),
                                                BoxShadow(
                                                  color: Colors.black.withOpacity(0.3),
                                                  blurRadius: 12,
                                                  offset: const Offset(0, 6),
                                                ),
                                              ],
                                            ),
                                            child: ClipRRect(
                                              borderRadius: BorderRadius.circular(14),
                                              child: Stack(
                                                fit: StackFit.expand,
                                                children: [
                                                  // Background gradient
                                                  Container(
                                                    decoration: BoxDecoration(
                                                      gradient: LinearGradient(
                                                        begin: Alignment.topLeft,
                                                        end: Alignment.bottomRight,
                                                        colors: [
                                                          Colors.grey.shade800,
                                                          Colors.grey.shade900,
                                                        ],
                                                      ),
                                                    ),
                                                  ),
                                                  // Image
                                                  isLocalImage 
                                                    ? Image.memory(
                                                        image['data'] as Uint8List,
                                                        fit: BoxFit.cover,
                                                        errorBuilder: (context, error, stackTrace) {
                                                          return _buildErrorWidget();
                                                        },
                                                      )
                                                    : Image.network(
                                                        image['thumbnail_url'],
                                                        fit: BoxFit.cover,
                                                        loadingBuilder: (context, child, loadingProgress) {
                                                          if (loadingProgress == null) return child;
                                                          return Center(
                                                            child: CircularProgressIndicator(
                                                              value: loadingProgress.expectedTotalBytes != null
                                                                  ? loadingProgress.cumulativeBytesLoaded / loadingProgress.expectedTotalBytes!
                                                                  : null,
                                                              color: Colors.blue,
                                                              strokeWidth: 2,
                                                            ),
                                                          );
                                                        },
                                                        errorBuilder: (context, error, stackTrace) {
                                                          return _buildErrorWidget();
                                                        },
                                                      ),
                                                  // Gradient overlay
                                                  Container(
                                                    decoration: BoxDecoration(
                                                      gradient: LinearGradient(
                                                        begin: Alignment.topCenter,
                                                        end: Alignment.bottomCenter,
                                                        colors: [
                                                          Colors.transparent,
                                                          Colors.transparent,
                                                          Colors.black.withOpacity(0.1),
                                                          Colors.black.withOpacity(0.6),
                                                        ],
                                                        stops: const [0.0, 0.4, 0.7, 1.0],
                                                      ),
                                                    ),
                                                  ),
                                                  // Bottom timestamp
                                                  Positioned(
                                                    bottom: 8,
                                                    left: 8,
                                                    right: 8,
                                                    child: Text(
                                                      '${(image['timestamp'] as DateTime? ?? image['created_at'] as DateTime).toString().split(' ')[1].split('.')[0]}',
                                                      style: const TextStyle(
                                                        color: Colors.white,
                                                        fontSize: 11,
                                                        fontWeight: FontWeight.w600,
                                                        shadows: [
                                                          Shadow(
                                                            color: Colors.black,
                                                            blurRadius: 4,
                                                          ),
                                                        ],
                                                      ),
                                                      textAlign: TextAlign.center,
                                                    ),
                                                  ),
                                                  // Top status indicator
                                                  Positioned(
                                                    top: 8,
                                                    right: 8,
                                                    child: Container(
                                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                                                      decoration: BoxDecoration(
                                                        color: (isLocalImage ? Colors.green : Colors.blue).withOpacity(0.9),
                                                        borderRadius: BorderRadius.circular(8),
                                                        boxShadow: [
                                                          BoxShadow(
                                                            color: Colors.black.withOpacity(0.3),
                                                            blurRadius: 4,
                                                          ),
                                                        ],
                                                      ),
                                                      child: Row(
                                                        mainAxisSize: MainAxisSize.min,
                                                        children: [
                                                          Icon(
                                                            Icons.fiber_manual_record,
                                                            color: Colors.white,
                                                            size: 6,
                                                          ),
                                                          const SizedBox(width: 3),
                                                          Text(
                                                            isLocalImage ? 'LOCAL' : 'CLOUD',
                                                            style: const TextStyle(
                                                              color: Colors.white,
                                                              fontSize: 8,
                                                              fontWeight: FontWeight.bold,
                                                            ),
                                                          ),
                                                        ],
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          ),
                                        ),
                                      ),
                                    );
                                  },
                                ),
                              ),
                              const SizedBox(height: 20),
                              Divider(
                                color: Colors.blue.withOpacity(0.3),
                                thickness: 1,
                                indent: 20,
                                endIndent: 20,
                              ),
                            ],
                            // Display transcripts
                            if (provider.segments.isNotEmpty) ...[
                              const SizedBox(height: 16),
                              TranscriptWidget(
                                segments: provider.segments,
                                images: [], // Pass empty list since we're handling images above
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),
                ] else ...[
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: TabBarView(
                        controller: _controller,
                        physics: const NeverScrollableScrollPhysics(),
                        children: [
                          // Transcript Tab
                          provider.segments.isEmpty
                              ? Center(
                                  child: Padding(
                                    padding: const EdgeInsets.only(bottom: 50.0),
                                    child: Text(
                                      conversationSource == ConversationSource.omi ? "No transcript" : "Empty",
                                    ),
                                  ),
                                )
                              : Padding(
                                  padding: const EdgeInsets.only(bottom: 80),
                                  child: getTranscriptWidget(
                                    false,
                                    provider.segments,
                                    [],
                                    deviceProvider.connectedDevice,
                                  ),
                                ),
                          // Summary Tab
                          Center(
                            child: Padding(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 32.0).copyWith(bottom: 50.0), // Adjust padding
                              child: Text(
                                provider.segments.isEmpty
                                    ? "No summary"
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
              ],
            ),
            floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
            floatingActionButton: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                provider.segments.isEmpty
                    ? const SizedBox()
                    : ConversationBottomBar(
                        mode: ConversationBottomBarMode.recording,
                        selectedTab: _controller!.index == 0 ? ConversationTab.transcript : ConversationTab.summary,
                        hasSegments: provider.segments.isNotEmpty,
                        onTabSelected: (tab) {
                          _controller!.animateTo(tab == ConversationTab.transcript ? 0 : 1);
                          setState(() {});
                        },
                        onStopPressed: () {
                          if (provider.segments.isNotEmpty) {
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
                                        if (value != null) {
                                          setState(() {
                                            showSummarizeConfirmation = !value;
                                          });
                                        }
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
