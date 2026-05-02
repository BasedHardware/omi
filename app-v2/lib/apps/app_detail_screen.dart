import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Marketplace detail page for a single app. Hero thumbnail + name + author,
/// full description, install/uninstall button. Pushed via Navigator from the
/// Apps tab row tap.
class AppDetailScreen extends StatelessWidget {
  const AppDetailScreen({super.key, required this.app});

  final NooApp app;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        flexibleSpace: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
            child: Container(
              color: AppColors.backgroundPrimary.withValues(alpha: 0.55),
            ),
          ),
        ),
        elevation: 0,
        iconTheme: const IconThemeData(color: AppColors.textPrimary),
        title: Text(
          app.name,
          style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
      ),
      body: _Body(app: app),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.app});
  final NooApp app;

  @override
  Widget build(BuildContext context) {
    final topInset = MediaQuery.of(context).padding.top + kToolbarHeight + AppStyles.spacingL;
    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppStyles.spacingL,
        topInset,
        AppStyles.spacingL,
        AppStyles.spacingXL + MediaQuery.of(context).padding.bottom,
      ),
      children: [
        _Header(app: app),
        const SizedBox(height: AppStyles.spacingL),
        _InstallButton(app: app),
        if (app.description.isNotEmpty) ...[
          const SizedBox(height: AppStyles.spacingXL),
          const _SectionLabel('ABOUT'),
          const SizedBox(height: AppStyles.spacingM),
          Text(
            app.description,
            style: const TextStyle(
              fontSize: 15,
              color: AppColors.textSecondary,
              height: 1.5,
            ),
          ),
        ],
        if (app.capabilities.isNotEmpty) ...[
          const SizedBox(height: AppStyles.spacingXL),
          const _SectionLabel('CAPABILITIES'),
          const SizedBox(height: AppStyles.spacingM),
          Wrap(
            spacing: AppStyles.spacingS,
            runSpacing: AppStyles.spacingS,
            children: [
              for (final cap in app.capabilities) _CapabilityChip(label: cap),
            ],
          ),
        ],
        // Two-way sync toggle: only meaningful for external_integration apps
        // that are currently installed. Defaults OFF — surprise writes to
        // third-party trackers are a trust hazard.
        if (app.externalIntegration != null) ...[
          const SizedBox(height: AppStyles.spacingXL),
          const _SectionLabel('PERMISSIONS'),
          const SizedBox(height: AppStyles.spacingM),
          _TwoWaySyncToggle(app: app),
        ],
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.app});
  final NooApp app;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _HeroThumbnail(url: app.imageUrl, name: app.name),
        const SizedBox(width: AppStyles.spacingL),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                app.name,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                  height: 1.2,
                ),
              ),
              if (app.author != null && app.author!.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  app.author!,
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textTertiary,
                  ),
                ),
              ],
              const SizedBox(height: AppStyles.spacingS),
              _MetaRow(app: app),
            ],
          ),
        ),
      ],
    );
  }
}

class _HeroThumbnail extends StatelessWidget {
  const _HeroThumbnail({required this.url, required this.name});
  final String url;
  final String name;

  @override
  Widget build(BuildContext context) {
    final initials = name.trim().isEmpty
        ? '?'
        : name.trim().split(RegExp(r'\s+')).take(2).map((p) => p.substring(0, 1).toUpperCase()).join();
    return Container(
      width: 80,
      height: 80,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      clipBehavior: Clip.antiAlias,
      child: url.isEmpty
          ? Container(
              color: AppColors.backgroundTertiary,
              alignment: Alignment.center,
              child: Text(
                initials,
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textTertiary,
                ),
              ),
            )
          : Image.network(url, fit: BoxFit.cover),
    );
  }
}

class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.app});
  final NooApp app;

  @override
  Widget build(BuildContext context) {
    final parts = <String>[];
    if (app.installs > 0) parts.add('${_compactCount(app.installs)} installs');
    if ((app.ratingCount ?? 0) > 0 && app.ratingAvg != null) {
      parts.add('★ ${app.ratingAvg!.toStringAsFixed(1)}');
    }
    if (parts.isEmpty) return const SizedBox.shrink();
    return Text(
      parts.join('  ·  '),
      style: const TextStyle(
        fontSize: 13,
        color: AppColors.textTertiary,
        fontWeight: FontWeight.w500,
      ),
    );
  }

  static String _compactCount(int n) {
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}k';
    return n.toString();
  }
}

class _InstallButton extends StatelessWidget {
  const _InstallButton({required this.app});
  final NooApp app;

  @override
  Widget build(BuildContext context) {
    final apps = context.watch<AppsProvider>();
    final installed = apps.isEnabled(app.id);
    final pending = apps.isPending(app.id);
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: FilledButton(
        onPressed: pending
            ? null
            : () async {
                HapticFeedback.lightImpact();
                final success = installed
                    ? await apps.uninstall(app.id)
                    : await apps.install(app.id);
                if (!context.mounted) return;
                if (!success && apps.error != null) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(installed
                          ? "Couldn't uninstall. Try again."
                          : "Couldn't install. Try again."),
                      backgroundColor: AppColors.backgroundSecondary,
                    ),
                  );
                }
              },
        style: FilledButton.styleFrom(
          backgroundColor: installed
              ? AppColors.backgroundSecondary
              : AppColors.brandPrimary,
          foregroundColor: AppColors.textPrimary,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
            side: installed
                ? BorderSide(color: Colors.white.withValues(alpha: 0.06))
                : BorderSide.none,
          ),
        ),
        child: pending
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.textPrimary,
                ),
              )
            : Text(
                installed ? 'Installed' : 'Install',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.label);
  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: const TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        color: AppColors.textTertiary,
        letterSpacing: 0.8,
      ),
    );
  }
}

class _CapabilityChip extends StatelessWidget {
  const _CapabilityChip({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppStyles.spacingM,
        vertical: AppStyles.spacingXS,
      ),
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Text(
        _humanize(label),
        style: const TextStyle(
          fontSize: 12,
          color: AppColors.textSecondary,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  /// "external_integration" → "External integration"
  static String _humanize(String raw) {
    if (raw.isEmpty) return raw;
    final cleaned = raw.replaceAll('_', ' ').replaceAll('-', ' ');
    return cleaned[0].toUpperCase() + cleaned.substring(1);
  }
}

/// Per-app writeback opt-in. Defaults OFF for any app — surprise writes to
/// third-party trackers (Jira tickets, Linear issues) are a trust hazard.
/// User flips this on after they've decided they trust Nooto to act on their
/// behalf in the source tracker.
class _TwoWaySyncToggle extends StatelessWidget {
  const _TwoWaySyncToggle({required this.app});
  final NooApp app;

  @override
  Widget build(BuildContext context) {
    final apps = context.watch<AppsProvider>();
    final enabled = apps.isTwoWaySyncEnabled(app.id);
    final installed = apps.isEnabled(app.id);
    return Container(
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      padding: const EdgeInsets.symmetric(
        horizontal: AppStyles.spacingL,
        vertical: AppStyles.spacingM,
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Allow ${app.name} writes',
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  installed
                      ? 'Let Nooto create or update ${app.name} items on your behalf.'
                      : 'Install ${app.name} first to enable writebacks.',
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textTertiary,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: AppStyles.spacingM),
          Switch.adaptive(
            value: enabled,
            onChanged: installed
                ? (v) {
                    HapticFeedback.lightImpact();
                    apps.setTwoWaySync(app.id, v);
                  }
                : null,
            activeTrackColor: AppColors.brandPrimary,
          ),
        ],
      ),
    );
  }
}
