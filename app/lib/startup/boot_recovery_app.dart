import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/l10n/app_localizations_en.dart';
import 'package:omi/ui/omi_tokens.dart';

/// Provider-free recovery surface: it can render when a boot dependency fails.
class BootRecoveryApp extends StatelessWidget {
  const BootRecoveryApp({super.key, required this.onRetry});

  final Future<void> Function() onRetry;

  String get _retryLabel {
    try {
      return lookupAppLocalizations(ui.PlatformDispatcher.instance.locale).tryAgain;
    } catch (_) {
      return AppLocalizationsEn().tryAgain;
    }
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        home: Scaffold(
          body: SafeArea(
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.health_and_safety_outlined, size: 48),
                    const SizedBox(height: 16),
                    Text(
                      // omi-ux-allow: hardcoded-text -- mandated copy before localization boots.
                      'Recovery mode — some features paused; tap to retry full startup',
                      key: const Key('boot_recovery_banner'),
                      textAlign: TextAlign.center,
                      style: OmiType.title2,
                    ),
                    const SizedBox(height: 24),
                    ElevatedButton(
                      key: const Key('boot_recovery_retry'),
                      onPressed: onRetry,
                      child: Text(_retryLabel),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
}
