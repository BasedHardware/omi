import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// One row in the apps list.
///
/// Borderless. Three pieces of information only: icon, name + one-line
/// description, rating. No author, no status pill, no inline action button —
/// those belong on the detail page. Tapping the row opens the detail page.
///
/// Visually leans on whitespace and a hairline separator (provided by the
/// parent [AppSection]) rather than card backgrounds, so the list reads as
/// "content first" rather than "row of products".
class AppRowCard extends StatelessWidget {
  final App app;
  final bool showPrivateIcon;

  const AppRowCard({super.key, required this.app, this.showPrivateIcon = true});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () async {
          MixpanelManager().pageOpened('App Detail');
          await routeToPage(context, AppDetailPage(app: app));
          if (context.mounted) {
            context.read<AppProvider>().filterApps();
          }
        },
        splashColor: Colors.white.withValues(alpha: 0.04),
        highlightColor: Colors.white.withValues(alpha: 0.02),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              _Icon(app: app),
              const SizedBox(width: 14),
              Expanded(child: _Body(app: app, showPrivateIcon: showPrivateIcon)),
              const SizedBox(width: 12),
              if (app.ratingAvg != null) _Rating(value: app.getRatingAvg()!),
            ],
          ),
        ),
      ),
    );
  }
}

class _Icon extends StatelessWidget {
  final App app;
  const _Icon({required this.app});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: Container(
        width: 56,
        height: 56,
        color: const Color(0xFF1A1A1F),
        child: CachedNetworkImage(
          imageUrl: app.getImageUrl(),
          httpHeaders: const {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
          },
          fit: BoxFit.cover,
          placeholder: (context, url) => ShimmerWithTimeout(
            baseColor: const Color(0xFF1A1A1F),
            highlightColor: const Color(0xFF2A2A30),
            child: Container(color: const Color(0xFF1A1A1F)),
          ),
          errorWidget: (context, url, error) => Icon(Icons.apps_rounded, size: 26, color: Colors.grey.shade600),
        ),
      ),
    );
  }
}

class _Body extends StatelessWidget {
  final App app;
  final bool showPrivateIcon;
  const _Body({required this.app, required this.showPrivateIcon});

  @override
  Widget build(BuildContext context) {
    final showLock = app.private && showPrivateIcon;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Flexible(
              child: Text(
                app.name.decodeString,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                  letterSpacing: -0.2,
                  height: 1.25,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (showLock) ...[
              const SizedBox(width: 6),
              Icon(Icons.lock_rounded, size: 12, color: Colors.grey.shade500),
            ],
          ],
        ),
        if (app.description.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(
            app.description,
            style: TextStyle(
              fontSize: 13.5,
              color: Colors.grey.shade400,
              height: 1.35,
              letterSpacing: -0.1,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ],
    );
  }
}

class _Rating extends StatelessWidget {
  final String value;
  const _Rating({required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.star_rounded, color: Color(0xFF8B5CF6), size: 15),
        const SizedBox(width: 3),
        Text(
          value,
          style: const TextStyle(
            fontSize: 13.5,
            color: Colors.white,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.1,
            height: 1.0,
          ),
        ),
      ],
    );
  }
}

/// Selector wrapper around [AppRowCard] for cases where the row should react
/// to provider state changes (currently a thin pass-through; reserved for
/// future per-app reactive bits).
class AppRowCardReactive extends StatelessWidget {
  final App app;
  const AppRowCardReactive({super.key, required this.app});

  @override
  Widget build(BuildContext context) {
    return Selector<AppProvider, App>(
      selector: (_, p) => p.apps.firstWhere((a) => a.id == app.id, orElse: () => app),
      builder: (context, current, _) => AppRowCard(app: current),
    );
  }
}
