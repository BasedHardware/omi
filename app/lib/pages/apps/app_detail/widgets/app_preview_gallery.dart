import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/pages/apps/widgets/app_form_fields.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// An app's screenshots, scrolled horizontally. Tapping one opens the media viewer as a modal
/// (it floats over the page, so it leaves by its close X — docs/ux-contract.md §1). A screenshot
/// that does not load drops out rather than leaving a broken tile, and with none left the section
/// is gone.
class AppPreviewGallery extends StatefulWidget {
  const AppPreviewGallery({super.key, required this.imageUrls, this.onImageOpened});

  final List<String> imageUrls;

  /// Called with the index of the screenshot the reader opened (analytics).
  final ValueChanged<int>? onImageOpened;

  @override
  State<AppPreviewGallery> createState() => _AppPreviewGalleryState();
}

class _AppPreviewGalleryState extends State<AppPreviewGallery> {
  final Set<String> _failed = {};

  void _open(BuildContext context, List<String> shown, int index) {
    widget.onImageOpened?.call(widget.imageUrls.indexOf(shown[index]));
    openAppScreenshots(context, shown, index);
  }

  void _dropFailed(String url) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _failed.add(url)) setState(() {});
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final imageUrls = widget.imageUrls.where((url) => !_failed.contains(url)).toList();
    if (imageUrls.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Semantics(header: true, child: Text(l10n.preview, style: OmiType.headline)),
        ),
        SizedBox(
          height: 250,
          child: ListView.builder(
            padding: EdgeInsets.zero,
            scrollDirection: Axis.horizontal,
            itemCount: imageUrls.length,
            itemBuilder: (context, index) {
              return Semantics(
                button: true,
                label: l10n.previewImageLabel(index + 1, imageUrls.length),
                child: GestureDetector(
                  onTap: () => _open(context, imageUrls, index),
                  child: Container(
                    margin: EdgeInsets.only(
                      left: index == 0 ? OmiSpacing.md : OmiSpacing.xs,
                      right: index == imageUrls.length - 1 ? OmiSpacing.md : OmiSpacing.xs,
                    ),
                    decoration: BoxDecoration(
                      border: Border.all(color: OmiColors.border, width: 1),
                      borderRadius: OmiRadius.mdAll,
                    ),
                    child: ClipRRect(
                      borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.md - 1)),
                      child: CachedNetworkImage(
                        imageUrl: imageUrls[index],
                        fit: BoxFit.contain,
                        placeholder: (context, url) => SizedBox(
                          width: 150,
                          child: ShimmerWithTimeout(
                            baseColor: OmiColors.surface1,
                            highlightColor: OmiColors.surface2,
                            child: Container(color: OmiColors.surface0),
                          ),
                        ),
                        errorWidget: (context, url, error) {
                          _dropFailed(url);
                          return const SizedBox.shrink();
                        },
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
    );
  }
}

/// A one-line status note under the app header (beta, under review, rejected, disabled).
class AppDetailNotice extends StatelessWidget {
  const AppDetailNotice({super.key, required this.icon, required this.text});

  final FaIconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          ExcludeSemantics(child: FaIcon(icon, color: OmiColors.textTertiary, size: 18)),
          const SizedBox(width: 10),
          SizedBox(
            width: MediaQuery.sizeOf(context).width * 0.78,
            child: Text(text, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ),
        ],
      ),
    );
  }
}
