import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import '../models/rich_list_item_data.dart';

/// Horizontal scrollable list widget for rendering rich items with images
class RichListWidget extends StatelessWidget {
  final List<RichListItemData> items;
  final Function(String url)? onUrlTap;

  const RichListWidget({
    super.key,
    required this.items,
    this.onUrlTap,
  });

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 12),
      height: 200,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        itemCount: items.length,
        padding: const EdgeInsets.symmetric(horizontal: 4),
        itemBuilder: (context, index) {
          return _RichListCard(
            data: items[index],
            onTap: items[index].hasUrl && onUrlTap != null
                ? () => onUrlTap!(items[index].url!)
                : null,
          );
        },
      ),
    );
  }
}

class _RichListCard extends StatelessWidget {
  final RichListItemData data;
  final VoidCallback? onTap;

  const _RichListCard({
    required this.data,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 160,
      margin: const EdgeInsets.symmetric(horizontal: 6),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: Colors.white.withOpacity(0.08),
                width: 1,
              ),
            ),
            clipBehavior: Clip.antiAlias,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Image
                Expanded(
                  flex: 3,
                  child: _buildImage(),
                ),
                // Content
                Expanded(
                  flex: 2,
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          data.title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            height: 1.2,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (data.description != null && data.description!.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Expanded(
                            child: Text(
                              data.description!,
                              style: TextStyle(
                                color: Colors.white.withOpacity(0.5),
                                fontSize: 11,
                                height: 1.3,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildImage() {
    if (!data.hasThumbnail) {
      return Container(
        color: const Color(0xFF2A2A30),
        child: Center(
          child: Icon(
            Icons.image_outlined,
            color: Colors.white.withOpacity(0.3),
            size: 32,
          ),
        ),
      );
    }

    return CachedNetworkImage(
      imageUrl: data.thumbnailUrl!,
      fit: BoxFit.cover,
      width: double.infinity,
      placeholder: (context, url) => Container(
        color: const Color(0xFF2A2A30),
        child: Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(
                Colors.white.withOpacity(0.3),
              ),
            ),
          ),
        ),
      ),
      errorWidget: (context, url, error) => Container(
        color: const Color(0xFF2A2A30),
        child: Center(
          child: Icon(
            Icons.broken_image_outlined,
            color: Colors.white.withOpacity(0.3),
            size: 32,
          ),
        ),
      ),
    );
  }
}
