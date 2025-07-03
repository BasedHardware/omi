import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:photo_view/photo_view.dart';
import 'package:photo_view/photo_view_gallery.dart';

class PhotoViewerPage extends StatefulWidget {
  final List<ConversationPhoto> photos;
  final int initialIndex;

  const PhotoViewerPage({
    super.key,
    required this.photos,
    required this.initialIndex,
  });

  @override
  State<PhotoViewerPage> createState() => _PhotoViewerPageState();
}

class _PhotoViewerPageState extends State<PhotoViewerPage> {
  late int currentIndex;
  late PageController pageController;

  @override
  void initState() {
    super.initState();
    currentIndex = widget.initialIndex;
    pageController = PageController(initialPage: widget.initialIndex);
  }

  void onPageChanged(int index) {
    setState(() {
      currentIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    final currentPhoto = widget.photos[currentIndex];
    final hasDescription = currentPhoto.description != null && currentPhoto.description!.isNotEmpty;
    final isProcessing = currentPhoto.description == null;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: PhotoViewGallery.builder(
                itemCount: widget.photos.length,
                pageController: pageController,
                onPageChanged: onPageChanged,
                builder: (context, index) {
                  final photo = widget.photos[index];
                  final imageBytes = base64Decode(photo.base64);
                  return PhotoViewGalleryPageOptions(
                    imageProvider: MemoryImage(imageBytes),
                    minScale: PhotoViewComputedScale.contained,
                    maxScale: PhotoViewComputedScale.covered * 4,
                    heroAttributes: PhotoViewHeroAttributes(tag: photo.id ?? index.toString()),
                  );
                },
                scrollPhysics: const BouncingScrollPhysics(),
                backgroundDecoration: const BoxDecoration(
                  color: Colors.black,
                ),
              ),
            ),
            if (currentPhoto.discarded)
              const Padding(
                padding: EdgeInsets.fromLTRB(24, 24, 24, 48),
                child: Text(
                  "This photo was discarded as it was not significant.",
                  style: TextStyle(color: Colors.white70, fontSize: 16),
                  textAlign: TextAlign.center,
                ),
              )
            else if (isProcessing)
              const Padding(
                padding: EdgeInsets.fromLTRB(24, 24, 24, 48),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70),
                    ),
                    SizedBox(width: 12),
                    Text(
                      "Analyzing...",
                      style: TextStyle(color: Colors.white70, fontSize: 16),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              )
            else if (hasDescription)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
                child: Text(
                  currentPhoto.description!,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
