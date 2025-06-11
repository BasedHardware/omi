import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
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

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        var conversationSource = ConversationSource.omi;
        
        // Check for content from BOTH legacy and in-progress sources
        bool hasLegacyContent = provider.segments.isNotEmpty || provider.allCapturedImages.isNotEmpty;
        bool hasInProgressContent = provider.inProgressSegments.isNotEmpty || provider.inProgressImages.isNotEmpty;
        
        // Use unified captured images approach - no more complex session management
        List<Map<String, dynamic>> relevantImages = provider.allCapturedImages;
        
        // Update content check to use relevant images
        hasLegacyContent = provider.segments.isNotEmpty || relevantImages.isNotEmpty;
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
                            content: Text('Refreshing camera...'),
                            duration: Duration(seconds: 2),
                          ),
                        );
                        
                        // Clear existing captured images to prevent confusion
                        provider.clearCapturedImages();
                        
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
                          }
                        } catch (e) {
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
                        ? _buildActiveConversationContent(provider, relevantImages)
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
                 relevantImages.isEmpty && (provider.inProgressImages?.isEmpty ?? true))
                    ? const SizedBox()
                    : ConversationBottomBar(
                        mode: ConversationBottomBarMode.recording,
                        selectedTab: _controller!.index == 0 ? ConversationTab.transcript : ConversationTab.summary,
                        hasSegments: provider.segments.isNotEmpty || 
                                   provider.inProgressSegments.isNotEmpty ||
                                   relevantImages.isNotEmpty ||
                                   provider.inProgressImages.isNotEmpty,
                        onTabSelected: (tab) {
                          _controller!.animateTo(tab == ConversationTab.transcript ? 0 : 1);
                        },
                        onStopPressed: () async {
                          // Prevent duplicate stop requests
                          if (provider.conversationCreating) return;
                          
                          // Set loading state to prevent duplicate requests and block new images
                          provider.setConversationCreating(true);
                          
                          // Simple unified approach - let the backend handle audio vs photo-only detection
                          bool hasPhotos = provider.allCapturedImages.isNotEmpty;
                          bool hasAudio = provider.segments.isNotEmpty;
                          
                          if (hasAudio || hasPhotos) {
                            try {
                              // Set flag immediately to prevent race conditions
                              provider.setConversationCreating(true);
                              await Future.delayed(const Duration(milliseconds: 100));
                              
                              // 2. Navigate IMMEDIATELY for best UX
                              if (mounted) {
                                Navigator.of(context).pushReplacement(
                                  MaterialPageRoute(
                                    builder: (context) => const HomePageWrapper(),
                                    settings: const RouteSettings(name: '/home'),
                                  )
                                );
                              }
                              
                              // 3. Do conversation processing in background AFTER navigation
                              _doBackgroundConversationProcessing(provider);
                              
                            } catch (e) {
                              provider.setConversationCreating(false);
                              
                              // Show user-friendly error message
                              if (mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Failed to process conversation. Please try again.'),
                                    backgroundColor: Colors.red,
                                  ),
                                );
                              }
                            }
                          } else {
                            provider.setConversationCreating(false);
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

  Widget _buildActiveConversationContent(CaptureProvider provider, List<Map<String, dynamic>> relevantImages) {
    // Combine segments, avoiding duplicates by checking segment IDs
    final legacySegments = provider.segments;
    final inProgressSegments = provider.inProgressSegments ?? [];
    
    final allSegments = <TranscriptSegment>[];
    allSegments.addAll(legacySegments);
    
    // Add in-progress segments that aren't already in legacy segments
    for (final inProgressSegment in inProgressSegments) {
      bool alreadyExists = legacySegments.any((seg) => seg.id == inProgressSegment.id);
      if (!alreadyExists) {
        allSegments.add(inProgressSegment);
      }
    }
    
    // Combine images, avoiding duplicates by checking IDs
    final legacyImages = relevantImages;
    final inProgressImages = provider.inProgressImages ?? [];
    
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
    
    // Show content if we have EITHER segments OR images
    if (allSegments.isEmpty && allImages.isEmpty) {
      return _buildEmptyState();
    }

    // NEW LAYOUT: Images gallery at top, transcript below
    return Column(
      children: [
        // Images gallery at the top (if any images exist)
        if (allImages.isNotEmpty) ...[
          _buildImageGallery(allImages),
          const SizedBox(height: 16),
        ],
        
        // Transcript section below images
        Expanded(
          child: allSegments.isEmpty 
            ? _buildNoTranscriptState()
            : _buildTranscriptList(allSegments),
        ),
      ],
    );
  }

  Widget _buildImageGallery(List<Map<String, dynamic>> images) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade800, // Same grey as transcript boxes
        borderRadius: BorderRadius.circular(8.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header showing image count
          Padding(
            padding: const EdgeInsets.all(12.0),
            child: Row(
              children: [
                const Icon(Icons.camera_alt, color: Colors.blue, size: 16),
                const SizedBox(width: 8),
                Text(
                  '${images.length} image${images.length == 1 ? '' : 's'} captured',
                  style: const TextStyle(
                    color: Colors.white,
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
              padding: const EdgeInsets.only(left: 12.0, right: 12.0, bottom: 12.0),
              itemCount: images.length,
              itemBuilder: (context, index) {
                try {
                  final image = images[index];
                  if (image == null) {
                    return _buildErrorImageContainer();
                  }
                  
                  final isLocalImage = image['data'] != null;
                  
                  return Container(
                    width: 280, // Fixed width for each image
                    margin: EdgeInsets.only(
                      right: index < images.length - 1 ? 12.0 : 0,
                    ),
                    child: GestureDetector(
                      onTap: () => _showSimpleImageDialog(image),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8.0),
                        child: Container(
                          width: 280,
                          height: 200,
                          child: isLocalImage 
                            ? Image.memory(
                                image['data'] as Uint8List,
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) {
                                  return _buildErrorImageContainer();
                                },
                              )
                            : Image.network(
                                image['url']?.toString() ?? '',
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) {
                                  return _buildErrorImageContainer();
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
                  return _buildErrorImageContainer();
                }
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTranscriptList(List<TranscriptSegment> segments) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0),
      child: ListView.builder(
        itemCount: segments.length,
        itemBuilder: (context, index) {
          final segment = segments[index];
          return _buildTimelineTranscriptItem(segment);
        },
      ),
    );
  }

  Widget _buildNoTranscriptState() {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(32.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.mic_outlined,
              size: 48,
              color: Colors.grey,
            ),
            SizedBox(height: 16),
            Text(
              'No speech detected yet',
              style: TextStyle(
                fontSize: 16,
                color: Colors.grey,
                fontWeight: FontWeight.w500,
              ),
            ),
            SizedBox(height: 8),
            Text(
              'Start speaking to see the transcript appear here',
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
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
      return text;
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


  
  Widget _buildErrorImageContainer() {
    return Container(
      width: 300,
      height: 200,
      margin: const EdgeInsets.only(right: 12.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade700,
        borderRadius: BorderRadius.circular(8.0),
      ),
      child: const Center(
        child: Icon(Icons.image_not_supported, color: Colors.grey, size: 32),
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
                          child: Icon(Icons.image_not_supported, color: Colors.grey),
                        ),
                      );
                    },
                  )
                : Image.network(
                    image['url'] ?? '',
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      return Container(
                        color: Colors.grey.shade700,
                        child: const Center(
                          child: Icon(Icons.image_not_supported, color: Colors.grey),
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
        height: 200,
        decoration: BoxDecoration(
          color: Colors.grey.shade700,
          borderRadius: BorderRadius.circular(8.0),
        ),
        child: const Center(
          child: Icon(Icons.image_not_supported, color: Colors.grey, size: 32),
        ),
      );
    }
  }

  void _showSimpleImageDialog(Map<String, dynamic> image) {
      showDialog(
        context: context,
        builder: (context) => ImageDialog(image: image),
      );
  }

  Widget _buildEmptyState() {
    return Consumer<CaptureProvider>(
      builder: (context, provider, child) {
        return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
              const Icon(
                Icons.mic_outlined,
                size: 80,
                color: Colors.grey,
              ),
              const SizedBox(height: 24),
              const Text(
                'No conversation in progress',
                style: TextStyle(
                  fontSize: 18,
                  color: Colors.grey,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Start recording or capturing photos to begin',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 32),
              const Text(
                'Photo sessions will start automatically\nwhen photos are captured without voice recording',
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey,
                ),
                textAlign: TextAlign.center,
            ),
          ],
        ),
        );
      },
    );
  }

  void _doBackgroundConversationProcessing(CaptureProvider provider) {
    // Process conversation asynchronously while keeping WebSocket alive for next session
    Future.microtask(() async {
      try {
        // 1. Process the current conversation WITHOUT stopping WebSocket
        CreateConversationResponse? conversationResponse = await processInProgressConversation();
        
        if (conversationResponse?.conversation != null) {
          // 2. Clear current conversation state but keep WebSocket alive
          await provider.finalizeInProgressConversation();
          
          // 3. CRITICAL: Explicitly reset all in-progress state for clean next session
          provider.clearInProgressConversation();
          
          // 4. Clear live transcription segments from UI for next session
          provider.clearTranscripts();
          
          provider.setConversationCreating(false);
          
          // 5. Reset for next recording session (WebSocket stays open)
        } else {
          // Reset flag on failure so user can try again
          provider.setConversationCreating(false);
        }
      } catch (e) {
        // Ensure cleanup happens even on error, but keep WebSocket alive
        try {
          await provider.finalizeInProgressConversation();
          // Also clear in-progress state on error
          provider.clearInProgressConversation();
          // Clear transcripts on error too for clean next session
          provider.clearTranscripts();
        } catch (cleanupError) {
          // Cleanup error handling
        }
        
        // Reset flag on error so user can try again
        provider.setConversationCreating(false);
      }
      // NOTE: WebSocket remains open for continuous recording sessions
      // User can immediately start recording again without reconnecting
      // All in-progress state is now completely clean for next session
    });
  }
}
