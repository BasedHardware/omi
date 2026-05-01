import 'package:flutter/material.dart';

import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Single app row in the Apps screen — square thumbnail, name, one-line
/// description. No card chrome around it; the row IS the surface.
class AppRow extends StatelessWidget {
  const AppRow({super.key, required this.app, this.onTap});

  final NooApp app;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppStyles.spacingS,
          vertical: AppStyles.spacingM,
        ),
        child: Row(
          children: [
            _Thumbnail(url: app.imageUrl, name: app.name),
            const SizedBox(width: AppStyles.spacingM),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    app.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  if (app.description.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      app.description,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppColors.textTertiary,
                        height: 1.35,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (app.enabled)
              const Padding(
                padding: EdgeInsets.only(left: AppStyles.spacingS),
                child: Icon(
                  Icons.check_circle_rounded,
                  size: 18,
                  color: AppColors.brandPrimary,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.url, required this.name});
  final String url;
  final String name;

  @override
  Widget build(BuildContext context) {
    final placeholder = _initials(name);
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
      child: SizedBox(
        width: 48,
        height: 48,
        child: url.isEmpty
            ? _Placeholder(initials: placeholder)
            : Image.network(
                url,
                fit: BoxFit.cover,
                errorBuilder: (ctx, err, stack) => _Placeholder(initials: placeholder),
                loadingBuilder: (ctx, child, progress) =>
                    progress == null ? child : _Placeholder(initials: placeholder),
              ),
      ),
    );
  }

  static String _initials(String name) {
    final trimmed = name.trim();
    if (trimmed.isEmpty) return '?';
    final parts = trimmed.split(RegExp(r'\s+'));
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts[0].substring(0, 1) + parts[1].substring(0, 1)).toUpperCase();
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder({required this.initials});
  final String initials;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.backgroundTertiary,
      alignment: Alignment.center,
      child: Text(
        initials,
        style: const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: AppColors.textTertiary,
        ),
      ),
    );
  }
}
