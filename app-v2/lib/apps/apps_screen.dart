import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/app_detail_screen.dart';
import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/apps/widgets/app_row.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Tab 4: Apps — capability-grouped browser of available integrations.
/// Reads `/v2/apps`. v0 is read-only; install/configure flows land in v1.
class AppsScreen extends StatefulWidget {
  const AppsScreen({super.key});

  @override
  State<AppsScreen> createState() => _AppsScreenState();
}

class _AppsScreenState extends State<AppsScreen> {
  @override
  void initState() {
    super.initState();
    // Kick off the fetch on first arrival; idempotent so subsequent rebuilds
    // don't re-hit the network.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<AppsProvider>().load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final apps = context.watch<AppsProvider>();
    if (apps.loading && !apps.hasFetched) return const _Loading();
    if (apps.error != null && apps.isEmpty) {
      return _ErrorState(error: apps.error!, onRetry: () => apps.load(force: true));
    }
    if (apps.isEmpty) return const _EmptyState();
    // Scaffold sets MediaQuery.padding.top = AppBar.preferredSize.height
    // when extendBodyBehindAppBar is true; already covers status bar +
    // toolbar. Just add a breathing gap.
    final topInset = MediaQuery.of(context).padding.top + AppStyles.spacingM;
    return RefreshIndicator(
      onRefresh: () => apps.load(force: true),
      color: AppColors.brandPrimary,
      backgroundColor: AppColors.backgroundSecondary,
      child: ListView.builder(
        padding: EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          topInset,
          AppStyles.spacingL,
          AppStyles.spacingXL,
        ),
        itemCount: apps.groups.length,
        itemBuilder: (_, i) => _GroupSection(group: apps.groups[i]),
      ),
    );
  }
}

class _GroupSection extends StatelessWidget {
  const _GroupSection({required this.group});
  final AppGroup group;

  @override
  Widget build(BuildContext context) {
    final apps = context.watch<AppsProvider>();
    return Padding(
      padding: const EdgeInsets.only(bottom: AppStyles.spacingXL),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS),
            child: Text(
              group.title.toUpperCase(),
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textTertiary,
                letterSpacing: 0.8,
              ),
            ),
          ),
          const SizedBox(height: AppStyles.spacingS),
          for (final app in group.apps)
            AppRow(
              app: app,
              installed: apps.isEnabled(app.id),
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => AppDetailScreen(app: app)),
                );
              },
            ),
        ],
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: SizedBox(
        width: 28,
        height: 28,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: AppColors.brandPrimary,
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
        child: Text(
          'No apps available yet.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 16,
            color: AppColors.textTertiary,
            height: 1.5,
          ),
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.error, required this.onRetry});
  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              "Couldn't load apps.",
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                color: AppColors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: AppStyles.spacingS),
            Text(
              'Pull to retry, or tap below.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 14,
                color: AppColors.textTertiary,
                height: 1.4,
              ),
            ),
            const SizedBox(height: AppStyles.spacingL),
            TextButton(
              onPressed: onRetry,
              child: const Text(
                'Retry',
                style: TextStyle(color: AppColors.brandPrimary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
