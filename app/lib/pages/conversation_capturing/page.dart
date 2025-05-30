import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:provider/provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/widgets/image_dialog.dart';

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

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        var conversationSource = ConversationSource.omi;
        
        // Check for content from BOTH legacy and in-progress sources
        bool hasLegacyContent = provider.segments.isNotEmpty || provider.allImages.isNotEmpty;
        bool hasInProgressContent = provider.inProgressSegments.isNotEmpty || provider.inProgressImages.isNotEmpty;
        bool hasAnyContent = hasLegacyContent || hasInProgressContent;
        
        return PopScope(
          canPop: true,
          child: Scaffold(
            key: scaffoldKey,
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              backgroundColor: Colors.transparent,
              automaticallyImplyLeading: true,
              title: Text(
                conversationSource == ConversationSource.omi ? 'In Progress...' : 'OpenGlass Recording',
                style: const TextStyle(color: Colors.white, fontSize: 16),
              ),
              centerTitle: true,
              actions: [
                // Add refresh camera button for OpenGlass users
                if (deviceProvider.connectedDevice?.type == DeviceType.openglass) ...[
                  IconButton(
                    icon: const Icon(Icons.refresh, color: Colors.white),
                    onPressed: () async {
                      final device = deviceProvider.connectedDevice;
                      if (device != null) {
                        // Show loading indicator
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('📷 Refreshing camera...'),
                            duration: Duration(seconds: 2),
                          ),
                        );
                        
                        // Clear existing local images to prevent confusion
                        provider.clearLocalImages();
                        
                        // Refresh the OpenGlass camera
                        try {
                          // Use the ServiceManager to trigger a camera refresh
                          final connection = await ServiceManager.instance().device.ensureConnection(device.id);
                          if (connection != null) {
                            // Send stop command
                            await connection.cameraStopPhotoController();
                            await Future.delayed(Duration(milliseconds: 300));
                            
                            // Send start command to trigger new capture
                            await connection.cameraStartPhotoController();
                            
                            debugPrint('🔄 OpenGlass camera refreshed manually');
                          }
                        } catch (e) {
                          debugPrint('Error refreshing OpenGlass camera: $e');
                        }
                      }
                    },
                  ),
                ],
              ],
            ),
            body: SafeArea(
              child: Column(
                children: [
                  Expanded(
                    child: hasAnyContent
                        ? _buildActiveConversationContent(provider)
                        : _buildEmptyState(),
                  ),
                ],
              ),
            ),
            floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
            floatingActionButton: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Show conversation bottom bar if we have ANY content (segments or images)
                (provider.segments.isEmpty && provider.inProgressSegments.isEmpty && 
                 provider.allImages.isEmpty && (provider.inProgressImages?.isEmpty ?? true))
                    ? const SizedBox()
                    : ConversationBottomBar(
                        mode: ConversationBottomBarMode.recording,
                        selectedTab: _controller!.index == 0 ? ConversationTab.transcript : ConversationTab.summary,
                        hasSegments: provider.segments.isNotEmpty || provider.inProgressSegments.isNotEmpty,
                        onTabSelected: (tab) {
                          _controller!.animateTo(tab == ConversationTab.transcript ? 0 : 1);
                          setState(() {});
                        },
                        onStopPressed: () {
                          // Check both segments and images for content
                          bool hasContent = provider.segments.isNotEmpty || 
                                          provider.inProgressSegments.isNotEmpty ||
                                          provider.allImages.isNotEmpty ||
                                          (provider.inProgressImages?.isNotEmpty ?? false);
                          
                          if (hasContent) {
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

  Widget _buildActiveConversationContent(CaptureProvider provider) {
    // Combine both legacy and in-progress content for unified timeline
    final legacySegments = provider.segments;
    final inProgressSegments = provider.inProgressSegments ?? [];
    
    // Combine segments, avoiding duplicates by checking segment IDs
    final allSegments = <TranscriptSegment>[];
    allSegments.addAll(legacySegments);
    
    // Add in-progress segments that aren't already in legacy segments
    for (final inProgressSegment in inProgressSegments) {
      bool alreadyExists = legacySegments.any((seg) => seg.id == inProgressSegment.id);
      if (!alreadyExists) {
        allSegments.add(inProgressSegment);
      }
    }
    
    final legacyImages = provider.allImages; // This includes both local and cloud images
    final inProgressImages = provider.inProgressImages ?? [];
    
    // Combine images, avoiding duplicates by checking IDs
    final allImages = <Map<String, dynamic>>[];
    allImages.addAll(legacyImages);
    
    // Add in-progress images that aren't already in legacy images
    for (final inProgressImage in inProgressImages) {
      final inProgressId = inProgressImage['id'];
      bool alreadyExists = legacyImages.any((img) => img['id'] == inProgressId);
      if (!alreadyExists) {
        allImages.add(inProgressImage);
      }
    }
    
    if (allSegments.isEmpty && allImages.isEmpty) {
      return _buildEmptyState();
    }

    // Create TRUE real-time interleaved timeline: speech, image, speech, image, etc.
    // Mix segments and images based on their actual creation/arrival timestamps
    final List<Map<String, dynamic>> timelineItems = [];
    
    // Add transcript segments with their actual timestamps
    for (final segment in allSegments) {
      // Use segment start time or current time as fallback
      final segmentTime = segment.start > 0 
          ? DateTime.fromMillisecondsSinceEpoch((segment.start * 1000).toInt())
          : DateTime.now();
      
      timelineItems.add({
        'type': 'transcript',
        'data': segment,
        'timestamp': segmentTime,
      });
    }
    
    // Add images with their actual timestamps
    for (final image in allImages) {
      DateTime imageTime;
      try {
        if (image['timestamp'] is DateTime) {
          imageTime = image['timestamp'];
        } else if (image['created_at'] is DateTime) {
          imageTime = image['created_at'];
        } else if (image['timestamp'] is String) {
          imageTime = DateTime.parse(image['timestamp']);
        } else if (image['created_at'] is String) {
          imageTime = DateTime.parse(image['created_at']);
        } else {
          // For local images without timestamps, use current time
          imageTime = DateTime.now();
        }
      } catch (e) {
        imageTime = DateTime.now();
      }
      
      timelineItems.add({
        'type': 'image',
        'data': image,
        'timestamp': imageTime,
      });
    }
    
    // Sort by actual timestamp for true chronological real-time order
    timelineItems.sort((a, b) {
      final aTime = a['timestamp'] as DateTime;
      final bTime = b['timestamp'] as DateTime;
      return aTime.compareTo(bTime);
    });

    // Group consecutive images together for horizontal scroll
    final List<Map<String, dynamic>> groupedTimelineItems = [];
    List<Map<String, dynamic>> currentImageGroup = [];
    
    for (int i = 0; i < timelineItems.length; i++) {
      final item = timelineItems[i];
      
      if (item['type'] == 'image') {
        currentImageGroup.add(item);
      } else {
        // If we have accumulated images, add them as a group
        if (currentImageGroup.isNotEmpty) {
          groupedTimelineItems.add({
            'type': 'image_group',
            'data': currentImageGroup.map((img) => img['data'] as Map<String, dynamic>).toList(),
            'timestamp': currentImageGroup.first['timestamp'],
          });
          currentImageGroup = [];
        }
        // Add the non-image item
        groupedTimelineItems.add(item);
      }
    }
    
    // Don't forget any remaining images at the end
    if (currentImageGroup.isNotEmpty) {
      groupedTimelineItems.add({
        'type': 'image_group',
        'data': currentImageGroup.map((img) => img['data'] as Map<String, dynamic>).toList(),
        'timestamp': currentImageGroup.first['timestamp'],
      });
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0),
      child: ListView.builder(
        itemCount: groupedTimelineItems.length,
        itemBuilder: (context, index) {
          final item = groupedTimelineItems[index];
          final type = item['type'] as String;
          
          try {
            if (type == 'transcript') {
              return _buildTimelineTranscriptItem(item['data'] as TranscriptSegment);
            } else if (type == 'image_group') {
              final rawData = item['data'];
              
              final images = rawData as List<Map<String, dynamic>>;
              
              final result = _buildTimelineImageGroupItem(images);
              return result;
            } else {
              return _buildTimelineImageItem(item['data'] as Map<String, dynamic>);
            }
          } catch (e, stackTrace) {
            return Container(
              margin: const EdgeInsets.only(bottom: 12.0),
              padding: const EdgeInsets.all(12.0),
              decoration: BoxDecoration(
                color: Colors.red.shade800,
                borderRadius: BorderRadius.circular(8.0),
              ),
              child: Text(
                'Error building timeline item: $e',
                style: const TextStyle(color: Colors.white),
              ),
            );
          }
        },
      ),
    );
  }

  Widget _buildTimelineTranscriptItem(TranscriptSegment segment) {
    final userName = SharedPreferencesUtil().givenName.isNotEmpty 
        ? SharedPreferencesUtil().givenName 
        : 'You';
    final speakerName = segment.isUser 
        ? userName 
        : segment.personId != null
            ? _getPersonName(segment.personId)
            : 'Speaker ${segment.speakerId}';
    final speakerColor = segment.isUser 
        ? Colors.green 
        : _getSpeakerColor(segment.speakerId);
    
    return Container(
      margin: const EdgeInsets.only(bottom: 12.0),
      padding: const EdgeInsets.all(12.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8.0),
        border: Border.all(color: speakerColor.withOpacity(0.3), width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Speaker header with proper speaker icons
          GestureDetector(
            onTap: () {
              // Add segment editing functionality if needed in live capture
              debugPrint('Tapped segment: ${segment.id}');
            },
            child: Row(
              children: [
                Image.asset(
                  segment.isUser
                      ? Assets.images.speaker0Icon.path
                      : segment.personId != null
                          ? _getSpeakerAssetPath(segment.personId!)
                          : Assets.images.speaker1Icon.path,
                  width: 24,
                  height: 24,
                  errorBuilder: (context, error, stackTrace) {
                    // Fallback to icon if asset not found
                    return Container(
                      padding: const EdgeInsets.all(4.0),
                      decoration: BoxDecoration(
                        color: speakerColor,
                        borderRadius: BorderRadius.circular(4.0),
                      ),
                      child: Icon(
                        segment.isUser ? Icons.person : Icons.person_outline, 
                        color: Colors.white, 
                        size: 16
                      ),
                    );
                  },
                ),
                const SizedBox(width: 12),
                Text(
                  speakerName,
                  style: TextStyle(
                    color: speakerColor,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const Spacer(),
                Text(
                  segment.getTimestampString(),
                  style: const TextStyle(
                    color: Colors.grey,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          
          // Transcript text with selection capability
          SelectionArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _getDecodedText(segment.text ?? ''),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    height: 1.4,
                    letterSpacing: 0.0,
                  ),
                ),
                // Translation support
                if (segment.translations.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  ...segment.translations.map((translation) => Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          _getDecodedText(translation.text),
                          style: const TextStyle(
                            letterSpacing: 0.0, 
                            color: Colors.grey,
                            fontSize: 14,
                            height: 1.4,
                          ),
                          textAlign: TextAlign.left,
                        ),
                      )),
                  const SizedBox(height: 4),
                  _buildTranslationNotice(),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _getPersonName(String? personId) {
    if (personId == null) return 'Unknown';
    final person = SharedPreferencesUtil().getPersonById(personId);
    return person?.name ?? 'Deleted Person';
  }

  String _getSpeakerAssetPath(String personId) {
    final person = SharedPreferencesUtil().getPersonById(personId);
    if (person?.colorIdx != null) {
      // Use alternating speaker icons based on color index
      final colorIdx = person!.colorIdx!;
      return colorIdx % 2 == 0 
          ? Assets.images.speaker0Icon.path 
          : Assets.images.speaker1Icon.path;
    }
    return Assets.images.speaker1Icon.path;
  }

  String _getDecodedText(String text) {
    try {
      return text; // For now, keep it simple. Can add UTF-8 decoding if needed
    } catch (e) {
      return text;
    }
  }

  Widget _buildTranslationNotice() {
    return GestureDetector(
      onTap: () {
        showDialog(
          context: context,
          builder: (BuildContext context) {
            return AlertDialog(
              title: const Text('Translation Notice'),
              content: const Text(
                'Omi translates conversations into your primary language. Update it anytime in Settings →  Profiles.',
                style: TextStyle(fontSize: 14),
              ),
              actions: [
                TextButton(
                  child: const Text('OK'),
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                ),
              ],
            );
          },
        );
      },
      child: Opacity(
        opacity: 0.5,
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.check_circle,
              size: 12,
              color: Colors.grey,
            ),
            SizedBox(width: 4),
            Text(
              'translated by omi',
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Color _getSpeakerColor(int speakerId) {
    // Return different colors for different speakers
    const colors = [
      Colors.blue,    // Speaker 0
      Colors.orange,  // Speaker 1  
      Colors.purple,  // Speaker 2
      Colors.teal,    // Speaker 3
      Colors.pink,    // Speaker 4
      Colors.amber,   // Speaker 5
    ];
    return colors[speakerId % colors.length];
  }

  Widget _buildTimelineImageGroupItem(List<Map<String, dynamic>> images) {
    if (images.isEmpty) {
      return const SizedBox.shrink();
    }
    
    return Container(
      margin: const EdgeInsets.only(bottom: 12.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header showing image count
          Padding(
            padding: const EdgeInsets.only(bottom: 8.0),
            child: Row(
              children: [
                const Icon(Icons.camera_alt, color: Colors.blue, size: 16),
                const SizedBox(width: 8),
                Text(
                  '${images.length} image${images.length == 1 ? '' : 's'}',
                  style: const TextStyle(
                    color: Colors.blue,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const Spacer(),
                const Text(
                  'Swipe to view →',
                  style: TextStyle(
                    color: Colors.grey,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          
          // Horizontal scroll view of images
          SizedBox(
            height: 200,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemCount: images.length,
              itemBuilder: (context, index) {
                try {
                  final image = images[index];
                  if (image == null) {
                    return _buildErrorImageContainer('Null Image Data');
                  }
                  
                  final isLocalImage = image['data'] != null;
                  final imageId = image['id']?.toString() ?? 'unknown';
                  
                  return Container(
                    width: 300, // Fixed width for each image
                    margin: EdgeInsets.only(
                      right: index < images.length - 1 ? 12.0 : 0,
                    ),
                    child: GestureDetector(
                      onTap: () => _showSimpleImageDialog(image),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8.0),
                        child: Container(
                          width: 300,
                          height: 200,
                          child: isLocalImage 
                            ? Image.memory(
                                image['data'] as Uint8List,
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) {
                                  return _buildErrorImageContainer('Local Image Error');
                                },
                              )
                            : Image.network(
                                image['thumbnail_url']?.toString() ?? '',
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) {
                                  return _buildErrorImageContainer('Network Image Error');
                                },
                                loadingBuilder: (context, child, loadingProgress) {
                                  if (loadingProgress == null) return child;
                                  return Container(
                                    color: Colors.grey.shade700,
                                    child: const Center(
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    ),
                                  );
                                },
                              ),
                        ),
                      ),
                    ),
                  );
                } catch (e, stackTrace) {
                  return _buildErrorImageContainer('Exception: $e');
                }
              },
            ),
          ),
        ],
      ),
    );
  }
  
  Widget _buildErrorImageContainer(String errorMessage) {
    return Container(
      width: 300,
      height: 200,
      margin: const EdgeInsets.only(right: 12.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade700,
        borderRadius: BorderRadius.circular(8.0),
        border: Border.all(color: Colors.red.withOpacity(0.5), width: 1),
      ),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error, color: Colors.white, size: 32),
            const SizedBox(height: 8),
            Text(
              errorMessage,
              style: const TextStyle(color: Colors.white, fontSize: 12),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTimelineImageItem(Map<String, dynamic> image) {
    try {
      final isLocalImage = image['data'] != null;
      
      return Container(
        margin: const EdgeInsets.only(bottom: 12.0),
        child: GestureDetector(
          onTap: () => _showSimpleImageDialog(image),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8.0),
            child: Container(
              height: 200,
              width: double.infinity,
              child: isLocalImage 
                ? Image.memory(
                    image['data'] as Uint8List,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      return Container(
                        color: Colors.grey.shade700,
                        child: const Center(
                          child: Icon(Icons.error, color: Colors.white),
                        ),
                      );
                    },
                  )
                : Image.network(
                    image['thumbnail_url'] ?? '',
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      return Container(
                        color: Colors.grey.shade700,
                        child: const Center(
                          child: Icon(Icons.error, color: Colors.white),
                        ),
                      );
                    },
                    loadingBuilder: (context, child, loadingProgress) {
                      if (loadingProgress == null) return child;
                      return Container(
                        color: Colors.grey.shade700,
                        child: const Center(
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      );
                    },
                  ),
            ),
          ),
        ),
      );
    } catch (e) {
      return Container(
        margin: const EdgeInsets.only(bottom: 12.0),
        padding: const EdgeInsets.all(12.0),
        decoration: BoxDecoration(
          color: Colors.grey.shade800,
          borderRadius: BorderRadius.circular(8.0),
        ),
        child: const Text(
          'Error displaying image',
          style: TextStyle(color: Colors.red),
        ),
      );
    }
  }

  void _showSimpleImageDialog(Map<String, dynamic> image) {
    try {
      showDialog(
        context: context,
        builder: (context) => ImageDialog(image: image),
      );
    } catch (e) {
      // Still try to close any open dialog
      Navigator.of(context).pop();
    }
  }

  Widget _buildEmptyState() {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(32.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.mic_off,
              size: 64,
              color: Colors.grey,
            ),
            SizedBox(height: 16),
            Text(
              'Start recording to capture audio and images',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                color: Colors.grey,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String transcriptElapsedTime(String timepstamp) {
  timepstamp = timepstamp.split(' - ')[1];
  return timepstamp;
}
