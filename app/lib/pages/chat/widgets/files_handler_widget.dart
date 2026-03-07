import 'dart:io';

import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';

import 'package:omi/backend/schema/message.dart';

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
            if (message.files[index].mimeTypeToFileType() == 'image') {
              return _buildImageThumbnail(context, index);
            } else {
              return Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).primaryColor,
                  borderRadius: const BorderRadius.all(Radius.circular(10.0)),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                margin: const EdgeInsets.only(bottom: 6, top: 2),
                width: MediaQuery.sizeOf(context).width * 0.32,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.insert_drive_file, color: Colors.white),
                    const SizedBox(height: 6),
                    Text(
                      message.files[index].name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                      ),
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

  Widget _buildImageThumbnail(BuildContext context, int index) {
    final thumbnail = message.files[index].thumbnail;
    final width = MediaQuery.sizeOf(context).width * 0.28;
    final height = MediaQuery.sizeOf(context).width * 0.22;

    if (_isLocalPath(thumbnail)) {
      final filePath = thumbnail!.startsWith('file://') ? thumbnail.substring(7) : thumbnail;
      return Container(
        margin: const EdgeInsets.only(bottom: 6, top: 2),
        decoration: BoxDecoration(
          color: Theme.of(context).primaryColor,
          borderRadius: const BorderRadius.all(Radius.circular(10.0)),
          image: DecorationImage(image: FileImage(File(filePath)), fit: BoxFit.cover),
        ),
        width: width,
        height: height,
      );
    }

    return CachedNetworkImage(
      imageUrl: thumbnail ?? '',
      imageBuilder: (context, imageProvider) => Container(
        margin: const EdgeInsets.only(bottom: 6, top: 2),
        decoration: BoxDecoration(
          color: Theme.of(context).primaryColor,
          borderRadius: const BorderRadius.all(Radius.circular(10.0)),
          image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
        ),
        width: width,
        height: height,
      ),
      placeholder: (context, url) => SizedBox(
        width: width,
        height: height,
        child: const Center(
          child: CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
          ),
        ),
      ),
      errorWidget: (context, url, error) => Container(
        margin: const EdgeInsets.only(bottom: 6, top: 2),
        decoration: BoxDecoration(
          color: Theme.of(context).primaryColor,
          borderRadius: const BorderRadius.all(Radius.circular(10.0)),
        ),
        width: width,
        height: height,
        child: const Center(child: Icon(Icons.image, color: Colors.white54)),
      ),
    );
  }
}
