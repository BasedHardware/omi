import 'dart:convert';
import 'dart:math';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';

class ImageSegment {
  final String id;
  final String thumbnailUrl;
  final String mimeType;
  final DateTime createdAt;

  ImageSegment({
    required this.id,
    required this.thumbnailUrl,
    required this.mimeType,
    required this.createdAt,
  });

  factory ImageSegment.fromJson(Map<String, dynamic> json) {
    return ImageSegment(
      id: json['id'] as String,
      thumbnailUrl: json['thumbnail_url'] as String,
      mimeType: json['mime_type'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class TranscriptWidget extends StatefulWidget {
  final List<TranscriptSegment> segments;
  final List<ImageSegment> images;
  final bool horizontalMargin;
  final bool topMargin;
  final bool separator;
  final bool canDisplaySeconds;
  final bool isConversationDetail;
  final double bottomMargin;
  final Function(int, int)? editSegment;

  const TranscriptWidget({
    super.key,
    required this.segments,
    this.images = const [],
    this.horizontalMargin = true,
    this.topMargin = true,
    this.separator = true,
    this.canDisplaySeconds = true,
    this.isConversationDetail = false,
    this.bottomMargin = 200,
    this.editSegment,
  });

  @override
  State<TranscriptWidget> createState() => _TranscriptWidgetState();
}

class _TranscriptWidgetState extends State<TranscriptWidget> {
  // Cache for person data to avoid repeated lookups
  final Map<String?, Person?> _personCache = {};
  // Cache for decoded text to avoid repeated decoding
  final Map<String, String> _decodedTextCache = {};

  // ScrollController to enable proper scrolling
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  String _getDecodedText(String text) {
    if (!_decodedTextCache.containsKey(text)) {
      _decodedTextCache[text] = tryDecodingText(text);
    }
    return _decodedTextCache[text]!;
  }

  Person? _getPersonById(String? personId) {
    if (personId == null) return null;
    if (!_personCache.containsKey(personId)) {
      _personCache[personId] = SharedPreferencesUtil().getPersonById(personId);
    }
    return _personCache[personId];
  }

  @override
  Widget build(BuildContext context) {
    // **FIXED: Less aggressive filtering for existing conversations**
    // For existing conversations with photos, show all images and let descriptions load in background
    // Only filter out images without descriptions for live conversations to prevent loaders
    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    final isExistingConversation = provider.photos.isNotEmpty;
    
    List<ImageSegment> imagesToShow;
    if (isExistingConversation) {
      // For existing conversations, show all images and let descriptions load
      imagesToShow = widget.images;
    } else {
      // For live conversations, only show images with descriptions to avoid loaders
      imagesToShow = widget.images.where((image) {
        return provider.photos.any((photo) {
          String photoIdentifier = photo.photoId?.isNotEmpty == true 
              ? photo.photoId! 
              : photo.id.toString();
          bool matches = photoIdentifier == image.id;
          bool hasDescription = photo.description.isNotEmpty;
          return matches && hasDescription;
        });
      }).toList();
    }
    
    // Combine segments and images into a single timeline
    final allItems = <dynamic>[];
    allItems.addAll(widget.segments);
    allItems.addAll(imagesToShow);
    
    // Sort by creation time - FIX: Proper comparison logic
    allItems.sort((a, b) {
      double aTime, bTime;
      
      if (a is TranscriptSegment) {
        aTime = a.start;
      } else if (a is ImageSegment) {
        aTime = a.createdAt.millisecondsSinceEpoch / 1000;
      } else {
        aTime = 0;
      }
      
      if (b is TranscriptSegment) {
        bTime = b.start;
      } else if (b is ImageSegment) {
        bTime = b.createdAt.millisecondsSinceEpoch / 1000;
      } else {
        bTime = 0;
      }
      
      return aTime.compareTo(bTime);
    });

    return ListView.builder(
      controller: _scrollController,
      padding: EdgeInsets.zero,
      itemCount: allItems.length + 2,
      itemBuilder: (context, idx) {
        if (idx == 0) return SizedBox(height: widget.topMargin ? 32 : 0);
        if (idx == allItems.length + 1) return SizedBox(height: widget.bottomMargin);

        final item = allItems[idx - 1];
        
        if (item is ImageSegment) {
          return _buildImageItem(item);
        } else {
          return _buildSegmentItem(idx - 1);
        }
      },
    );
  }

  Widget _buildImageItem(ImageSegment image) {
    // Check if this is a base64 data URL
    final isDataUrl = image.thumbnailUrl.startsWith('data:image/');
    
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        widget.horizontalMargin ? 16 : 0,
        16,
        widget.horizontalMargin ? 16 : 0,
        0,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GestureDetector(
            onTap: () => _showImageDialog(context, image),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: isDataUrl 
                ? _buildBase64Image(image.thumbnailUrl)
                : Image.network(
                    image.thumbnailUrl,
                    fit: BoxFit.cover,
                    loadingBuilder: (context, child, loadingProgress) {
                      if (loadingProgress == null) {
                        return child;
                      }
                      return Container(
                        height: 200,
                        color: Colors.grey[900],
                        child: const Center(
                          child: CircularProgressIndicator(),
                        ),
                      );
                    },
                    errorBuilder: (context, error, stackTrace) {
                      return Container(
                        height: 200,
                        color: Colors.grey[900],
                        child: const Center(
                          child: Icon(Icons.error_outline, color: Colors.red),
                        ),
                      );
                    },
                  ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Image captured at ${DateFormat('HH:mm:ss').format(image.createdAt)}',
            style: const TextStyle(
              color: Colors.grey,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 8),
          // AI description section - Handle both existing and live conversations
          Consumer<ConversationDetailProvider>(
            builder: (context, provider, child) {
              final matchingPhoto = provider.photos.where((photo) {
                String photoIdentifier = photo.photoId?.isNotEmpty == true 
                    ? photo.photoId! 
                    : photo.id.toString();
                bool matches = photoIdentifier == image.id;
                return matches;
              }).firstOrNull;
              
              // Handle different states: no photo found, photo without description, photo with description
              if (matchingPhoto == null) {
                // No matching photo found - this might be a timing issue, show loading
                return Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation(Colors.orange),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Loading description...',
                        style: TextStyle(
                          color: Colors.orange,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                );
              }
              
              final description = matchingPhoto.description;
              final hasDescription = description.isNotEmpty;
              
              if (!hasDescription) {
                // Photo found but no description yet - show loading state
                return Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation(Colors.orange),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'AI analyzing...',
                        style: TextStyle(
                          color: Colors.orange,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                );
              }
              
              // Photo with description - show it
              return Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.grey.shade900,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.smart_toy, 
                          color: Colors.green, 
                          size: 14
                        ),
                        const SizedBox(width: 6),
                        Text(
                          'AI Summary',
                          style: TextStyle(
                            color: Colors.green,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      description,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        height: 1.3,
                      ),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildBase64Image(String dataUrl) {
    return _buildBase64ImageWithFit(dataUrl, BoxFit.cover);
  }

  Widget _buildBase64ImageFullSize(String dataUrl) {
    return _buildBase64ImageWithFit(dataUrl, BoxFit.contain);
  }

  Widget _buildBase64ImageWithFit(String dataUrl, BoxFit fit) {
    try {
      // Extract base64 data from data URL
      final base64Data = dataUrl.split(',')[1];
      final bytes = base64Decode(base64Data);
      return Image.memory(
        bytes,
        fit: fit,
        width: fit == BoxFit.contain ? double.infinity : null,
        errorBuilder: (context, error, stackTrace) {
          return Container(
            height: 200,
            color: Colors.grey[900],
            child: const Center(
              child: Icon(Icons.error_outline, color: Colors.red),
            ),
          );
        },
      );
    } catch (e) {
      return Container(
        height: 200,
        color: Colors.grey[900],
        child: const Center(
          child: Icon(Icons.error_outline, color: Colors.red),
        ),
      );
    }
  }

  void _showImageDialog(BuildContext context, ImageSegment image) {
    // Check if this is a base64 data URL
    final isDataUrl = image.thumbnailUrl.startsWith('data:image/');
    
    showDialog(
      context: context,
      builder: (context) => Dialog(
        backgroundColor: Colors.transparent,
        child: Container(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.8,
            maxWidth: MediaQuery.of(context).size.width * 0.9,
          ),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(12.0),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Image section
              Expanded(
                flex: 7,
                child: ClipRRect(
                  borderRadius: const BorderRadius.vertical(top: Radius.circular(12.0)),
                  child: isDataUrl 
                    ? _buildBase64ImageFullSize(image.thumbnailUrl)
                    : Image.network(
                        image.thumbnailUrl,
                        fit: BoxFit.contain,
                        width: double.infinity,
                        errorBuilder: (context, error, stackTrace) {
                          return Container(
                            color: Colors.grey.shade700,
                            child: const Center(
                              child: Icon(Icons.error, color: Colors.white, size: 48),
                            ),
                          );
                        },
                      ),
                ),
              ),
              
              // AI Summary section - No loading state needed since we only show images with descriptions
              Expanded(
                flex: 3,
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Consumer<ConversationDetailProvider>(
                            builder: (context, provider, child) {
                              return Row(
                                children: [
                                  Icon(
                                    Icons.smart_toy, 
                                    color: Colors.green, 
                                    size: 16
                                  ),
                                  const SizedBox(width: 8),
                                  Text(
                                    'AI Summary',
                                    style: TextStyle(
                                      color: Colors.green,
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              );
                            },
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Expanded(
                        child: SingleChildScrollView(
                          child: Consumer<ConversationDetailProvider>(
                            builder: (context, provider, child) {
                              // Find the photo with matching ID to get description
                              final matchingPhoto = provider.photos.where((photo) {
                                String photoIdentifier = photo.photoId?.isNotEmpty == true 
                                    ? photo.photoId! 
                                    : photo.id.toString();
                                return photoIdentifier == image.id;
                              }).firstOrNull;
                              
                              // Handle different states
                              if (matchingPhoto == null) {
                                return Row(
                                  children: [
                                    SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        valueColor: AlwaysStoppedAnimation(Colors.orange),
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      'Loading description...',
                                      style: TextStyle(
                                        color: Colors.orange,
                                        fontSize: 14,
                                        height: 1.4,
                                      ),
                                    ),
                                  ],
                                );
                              }
                              
                              final description = matchingPhoto.description;
                              final hasDescription = description.isNotEmpty;
                              
                              if (!hasDescription) {
                                return Row(
                                  children: [
                                    SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        valueColor: AlwaysStoppedAnimation(Colors.orange),
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      'AI analyzing...',
                                      style: TextStyle(
                                        color: Colors.orange,
                                        fontSize: 14,
                                        height: 1.4,
                                      ),
                                    ),
                                  ],
                                );
                              }
                              
                              // Show the description
                              return Text(
                                description,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  height: 1.4,
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              
              // Close button
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8.0),
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Close', style: TextStyle(color: Colors.white)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSegmentItem(int segmentIdx) {
    final data = widget.segments[segmentIdx];
    final Person? person = data.personId != null ? _getPersonById(data.personId) : null;

    return Padding(
      padding:
          EdgeInsetsDirectional.fromSTEB(widget.horizontalMargin ? 16 : 0, 0.0, widget.horizontalMargin ? 16 : 0, 0.0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () {
              widget.editSegment?.call(segmentIdx, data.speakerId);
              MixpanelManager().assignSheetOpened();
            },
            child: Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Image.asset(
                  data.isUser
                      ? Assets.images.speaker0Icon.path
                      : person != null
                          ? speakerImagePath[person.colorIdx!]
                          : Assets.images.speaker1Icon.path,
                  width: 26,
                  height: 26,
                ),
                const SizedBox(width: 12),
                Text(
                  data.isUser
                      ? SharedPreferencesUtil().givenName.isNotEmpty
                          ? SharedPreferencesUtil().givenName
                          : 'You'
                      : data.personId != null
                          ? person?.name ?? 'Deleted Person'
                          : 'Speaker ${data.speakerId}',
                  style: const TextStyle(color: Colors.white, fontSize: 18),
                ),
                if (widget.canDisplaySeconds) ...[
                  const SizedBox(width: 12),
                  Text(
                    data.getTimestampString(),
                    style: const TextStyle(color: Colors.grey, fontSize: 14),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: SelectionArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _getDecodedText(data.text),
                    style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
                    textAlign: TextAlign.left,
                  ),
                  if (data.translations.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    ...data.translations.map((translation) => Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            _getDecodedText(translation.text),
                            style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
                            textAlign: TextAlign.left,
                          ),
                        )),
                    const SizedBox(height: 4),
                    _buildTranslationNotice(),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
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
}

class LiteTranscriptWidget extends StatelessWidget {
  final List<TranscriptSegment> segments;
  // Cache the processed text to avoid recalculating on every rebuild
  final String? _cachedText;

  LiteTranscriptWidget({
    super.key,
    required this.segments,
  }) : _cachedText = _processText(segments);

  static String? _processText(List<TranscriptSegment> segments) {
    if (segments.isEmpty) return null;

    var text = getLastTranscript(segments, maxCount: 70, includeTimestamps: false);
    return text.replaceAll(RegExp(r"\s+|\n+"), " ");
  }

  @override
  Widget build(BuildContext context) {
    if (_cachedText == null) {
      return const SizedBox.shrink();
    }

    return Text(
      _cachedText!,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
      textAlign: TextAlign.right,
    );
  }
}

String getLastTranscript(List<TranscriptSegment> transcriptSegments,
    {int? maxCount, bool generate = false, bool includeTimestamps = true}) {
  var transcript = TranscriptSegment.segmentsAsString(
      transcriptSegments.sublist(transcriptSegments.length >= 50 ? transcriptSegments.length - 50 : 0),
      includeTimestamps: includeTimestamps);
  if (maxCount != null) transcript = transcript.substring(max(transcript.length - maxCount, 0));
  return tryDecodingText(transcript);
}

// Cache for decoded text
final Map<String, String> _decodedTextCache = {};

String tryDecodingText(String text) {
  if (!_decodedTextCache.containsKey(text)) {
    try {
      _decodedTextCache[text] = utf8.decode(text.toString().codeUnits);
    } catch (e) {
      _decodedTextCache[text] = text;
    }
  }
  return _decodedTextCache[text]!;
}

String formatChatTimestamp(DateTime dateTime) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final messageDate = DateTime(dateTime.year, dateTime.month, dateTime.day);

  if (messageDate == today) {
    // Today, show time only
    return dateTimeFormat('h:mm a', dateTime);
  } else if (messageDate == today.subtract(const Duration(days: 1))) {
    // Yesterday
    return 'Yesterday ${dateTimeFormat('h:mm a', dateTime)}';
  } else {
    // Other days
    return dateTimeFormat('MMM d, h:mm a', dateTime);
  }
}
