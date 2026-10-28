import 'dart:io';

import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/ui/ui.dart';

class FilesHandlerWidget extends StatelessWidget {
  final ServerMessage message;
  const FilesHandlerWidget({super.key, required this.message});

  bool _isLocalPath(String? path) {
    if (path == null || path.isEmpty) return false;
    return path.startsWith('/') || path.startsWith('file://');
  }

  @override
  Widget build(BuildContext context) {
    if (message.files.isEmpty || message.filesId.isEmpty) {
      return const SizedBox.shrink();
    } else {
      return SizedBox(
        width: MediaQuery.sizeOf(context).width * 0.9,
        height: MediaQuery.sizeOf(context).height * 0.12,
        child: ListView.separated(
          itemCount: message.files.length,
          shrinkWrap: true,
          reverse: true,
          scrollDirection: Axis.horizontal,
          separatorBuilder: (context, index) {
            return const SizedBox(width: 6);
          },
          itemBuilder: (context, index) {
            final type = message.files[index].mimeTypeToFileType();
            if (type == 'video') {
              return _buildVideoThumbnail(context, message.files[index]);
            } else if (type == 'image') {
              return _buildImageThumbnail(context, index);
            } else {
              return Container(
                decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                margin: const EdgeInsets.only(bottom: 6, top: 2),
                width: MediaQuery.sizeOf(context).width * 0.32,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.insert_drive_file, color: OmiColors.textPrimary),
                    const SizedBox(height: 6),
                    Text(
                      message.files[index].name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: OmiType.footnote,
                    ),
                  ],
                ),
              );
            }
          },
        ),
      );
    }
  }

  /// A video shows its poster frame with a play badge and its length.
  Widget _buildVideoThumbnail(BuildContext context, MessageFile file) {
    final width = MediaQuery.sizeOf(context).width * 0.28;
    final height = MediaQuery.sizeOf(context).width * 0.22;
    final seconds = (file.videoDurationSeconds ?? 0).round();
    final length = '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
    return Semantics(
      label: '${file.name}, $length',
      image: true,
      child: Stack(
        children: [
          _thumbnailImage(file.localPreviewPath ?? file.thumbnail, width, height, Icons.videocam),
          Positioned.fill(
            bottom: 6,
            top: 2,
            child: Center(
              child: Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(color: OmiColors.surface0.withValues(alpha: 0.6), shape: BoxShape.circle),
                child: Icon(Icons.play_arrow, color: OmiColors.textPrimary, size: 18),
              ),
            ),
          ),
          Positioned(
            right: 8,
            bottom: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              decoration:
                  BoxDecoration(color: OmiColors.surface0.withValues(alpha: 0.6), borderRadius: OmiRadius.smAll),
              child: Text(length, style: OmiType.caption),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildImageThumbnail(BuildContext context, int index) {
    final width = MediaQuery.sizeOf(context).width * 0.28;
    final height = MediaQuery.sizeOf(context).width * 0.22;
    return _thumbnailImage(message.files[index].thumbnail, width, height, Icons.image);
  }

  Widget _thumbnailImage(String? thumbnail, double width, double height, IconData fallbackIcon) {
    Widget fallback() => Container(
          margin: const EdgeInsets.only(bottom: 6, top: 2),
          decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
          width: width,
          height: height,
          child: Center(child: Icon(fallbackIcon, color: OmiColors.textTertiary)),
        );

    if (_isLocalPath(thumbnail)) {
      final filePath = thumbnail!.startsWith('file://') ? thumbnail.substring(7) : thumbnail;
      // A local preview can be purged by the OS; fall back instead of a blank tile.
      return Container(
        margin: const EdgeInsets.only(bottom: 6, top: 2),
        width: width,
        height: height,
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
        child: ClipRRect(
          borderRadius: OmiRadius.mdAll,
          child: Image.file(
            File(filePath),
            fit: BoxFit.cover,
            width: width,
            height: height,
            errorBuilder: (context, error, stackTrace) => fallback(),
          ),
        ),
      );
    }
    if (thumbnail == null || thumbnail.isEmpty) return fallback();

    return CachedNetworkImage(
      imageUrl: thumbnail,
      imageBuilder: (context, imageProvider) => Container(
        margin: const EdgeInsets.only(bottom: 6, top: 2),
        decoration: BoxDecoration(
          color: OmiColors.surface2,
          borderRadius: OmiRadius.mdAll,
          image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
        ),
        width: width,
        height: height,
      ),
      placeholder: (context, url) => SizedBox(
        width: width,
        height: height,
        child: const Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
      ),
      errorWidget: (context, url, error) => fallback(),
    );
  }
}
