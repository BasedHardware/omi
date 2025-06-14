import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'dart:math' as math;

class ImageDialog extends StatefulWidget {
  final Map<String, dynamic> image;

  const ImageDialog({Key? key, required this.image}) : super(key: key);

  @override
  State<ImageDialog> createState() => _ImageDialogState();
}

class _ImageDialogState extends State<ImageDialog> {
  @override
  Widget build(BuildContext context) {
    return Consumer<CaptureProvider>(
      builder: (context, captureProvider, child) {
        // Find the most up-to-date version of this image across ALL sources
        final imageId = widget.image['id']?.toString();
        Map<String, dynamic>? currentImage = widget.image;
        
        if (imageId != null) {
          // **ENHANCED: Search across ALL image sources for the most up-to-date version**
          Map<String, dynamic>? updatedImage;
          
          // 1. Check cloud images (WebSocket updates)
          updatedImage = captureProvider.cloudImages
              .where((img) => img['id']?.toString() == imageId)
              .firstOrNull;
          
          // 2. Check in-progress images (shared conversation state)
          if (updatedImage == null) {
            updatedImage = captureProvider.inProgressImages
                .where((img) => img['id']?.toString() == imageId)
                .firstOrNull;
          }
          
          // 3. Check local images (immediate capture)
          if (updatedImage == null) {
            updatedImage = captureProvider.localImages
                .where((img) => img['id']?.toString() == imageId)
                .firstOrNull;
          }
          
          // 4. Also check by thumbnail URL for robustness
          if (updatedImage == null && widget.image['thumbnail_url'] != null) {
            final thumbnailUrl = widget.image['thumbnail_url'].toString();
            
            // Search all sources by thumbnail URL
            for (final imageList in [captureProvider.cloudImages, captureProvider.inProgressImages, captureProvider.localImages]) {
              updatedImage = imageList
                  .where((img) => img['thumbnail_url']?.toString() == thumbnailUrl)
                  .firstOrNull;
              if (updatedImage != null) break;
            }
          }
          
          if (updatedImage != null) {
            currentImage = updatedImage;
          } else {
            // No updated version found, use original image
          }
        }
        
        final isLocalImage = currentImage['data'] != null;
        final description = currentImage['description'] as String?;
        final isDescriptionLoading = description == null || description.isEmpty;
        
        return Dialog(
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
                    child: isLocalImage 
                      ? Image.memory(
                          currentImage['data'] as Uint8List,
                          fit: BoxFit.contain,
                          width: double.infinity,
                        )
                      : Image.network(
                          currentImage['url'] ?? '',
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
                
                // AI Summary section - Always show, with loading state when needed
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
                            Icon(
                              isDescriptionLoading ? Icons.auto_awesome : Icons.smart_toy, 
                              color: isDescriptionLoading ? Colors.orange : Colors.green, 
                              size: 16
                            ),
                            const SizedBox(width: 8),
                            Text(
                              isDescriptionLoading ? 'AI Analysis' : 'AI Summary',
                              style: TextStyle(
                                color: isDescriptionLoading ? Colors.orange : Colors.green,
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            if (isDescriptionLoading) ...[
                              const SizedBox(width: 8),
                              const SizedBox(
                                width: 12,
                                height: 12,
                                child: CircularProgressIndicator(
                                  strokeWidth: 1.5,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.orange),
                                ),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 8),
                        Expanded(
                          child: SingleChildScrollView(
                            child: Text(
                              isDescriptionLoading 
                                ? 'Analyzing image content...' // Show loading text
                                : description!,
                              style: TextStyle(
                                color: isDescriptionLoading ? Colors.grey.shade300 : Colors.white,
                                fontSize: 14,
                                height: 1.4,
                                fontStyle: isDescriptionLoading ? FontStyle.italic : FontStyle.normal,
                              ),
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
        );
      },
    );
  }
} 