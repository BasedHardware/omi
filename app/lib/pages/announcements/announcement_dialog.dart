import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/models/announcement.dart';

class AnnouncementDialog extends StatelessWidget {
  final Announcement announcement;
  final VoidCallback? onDismiss;
  final VoidCallback? onCTAPressed;

  const AnnouncementDialog({
    super.key,
    required this.announcement,
    this.onDismiss,
    this.onCTAPressed,
  });

  /// Show the announcement dialog.
  /// Returns true if the CTA button was clicked, false otherwise.
  static Future<bool> show(
    BuildContext context,
    Announcement announcement, {
    VoidCallback? onDismiss,
    VoidCallback? onCTAPressed,
  }) async {
    bool ctaClicked = false;

    await showDialog(
      context: context,
      barrierDismissible: true,
      barrierColor: Colors.black87,
      builder: (context) => AnnouncementDialog(
        announcement: announcement,
        onDismiss: onDismiss,
        onCTAPressed: () {
          ctaClicked = true;
          onCTAPressed?.call();
        },
      ),
    );

    return ctaClicked;
  }

  @override
  Widget build(BuildContext context) {
    final content = announcement.announcementContent;
    final hasImage = content.imageUrl != null;

    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 360),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(24),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.4),
              blurRadius: 30,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Image at top (if available)
              if (hasImage) _buildImage(content.imageUrl!),

              // Close button (if no image)
              if (!hasImage) _buildCloseButton(context),

              // Content
              Padding(
                padding: EdgeInsets.fromLTRB(24, hasImage ? 24 : 8, 24, 24),
                child: Column(
                  children: [
                    // Title
                    Text(
                      content.title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                        height: 1.2,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),
                    // Body
                    Text(
                      content.body,
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 15,
                        height: 1.5,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    if (content.cta != null) ...[
                      const SizedBox(height: 28),
                      _buildCTAButton(context, content.cta!),
                    ],
                    const SizedBox(height: 8),
                    // Dismiss text button
                    TextButton(
                      onPressed: () {
                        onDismiss?.call();
                        Navigator.pop(context);
                      },
                      child: Text(
                        'Maybe Later',
                        style: TextStyle(
                          color: Colors.grey.shade500,
                          fontSize: 14,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCloseButton(BuildContext context) {
    return Align(
      alignment: Alignment.topRight,
      child: Padding(
        padding: const EdgeInsets.only(top: 8, right: 8),
        child: IconButton(
          onPressed: () {
            onDismiss?.call();
            Navigator.pop(context);
          },
          icon: Icon(
            Icons.close,
            color: Colors.grey.shade500,
            size: 24,
          ),
        ),
      ),
    );
  }

  Widget _buildImage(String imageUrl) {
    return Stack(
      children: [
        CachedNetworkImage(
          imageUrl: imageUrl,
          width: double.infinity,
          height: 180,
          fit: BoxFit.cover,
          placeholder: (context, url) => Container(
            height: 180,
            color: const Color(0xFF2A2A2E),
            child: const Center(
              child: CircularProgressIndicator(
                color: Colors.white54,
                strokeWidth: 2,
              ),
            ),
          ),
          errorWidget: (context, url, error) => Container(
            height: 180,
            color: const Color(0xFF2A2A2E),
            child: const Icon(
              Icons.campaign_outlined,
              color: Colors.white54,
              size: 48,
            ),
          ),
        ),
        // Close button overlaid on image
        Positioned(
          top: 8,
          right: 8,
          child: Builder(
            builder: (ctx) => Container(
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.5),
                shape: BoxShape.circle,
              ),
              child: IconButton(
                onPressed: () {
                  onDismiss?.call();
                  Navigator.pop(ctx);
                },
                icon: const Icon(
                  Icons.close,
                  color: Colors.white70,
                  size: 20,
                ),
                padding: const EdgeInsets.all(8),
                constraints: const BoxConstraints(),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCTAButton(BuildContext context, AnnouncementCTA cta) {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: ElevatedButton(
        onPressed: () {
          onCTAPressed?.call();
          Navigator.pop(context);
          _handleCTAAction(context, cta.action);
        },
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(26),
          ),
          elevation: 0,
        ),
        child: Text(
          cta.text,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  void _handleCTAAction(BuildContext context, String action) async {
    final uri = Uri.tryParse(action);
    if (uri == null) {
      debugPrint('Invalid URL: $action');
      return;
    }

    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e) {
      debugPrint('Failed to open URL: $e');
    }
  }
}
