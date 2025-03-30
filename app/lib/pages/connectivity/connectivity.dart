import 'package:flutter/material.dart';
import 'package:omi/providers/connectivity_provider.dart';

void showNoConnectionDialog(
    ConnectivityProvider connectivityProvider, BuildContext ctx, bool mounted) {
  if (!connectivityProvider.isConnected && mounted) {
    ScaffoldMessenger.of(ctx).showMaterialBanner(
      MaterialBanner(
        content: const Text(
          'No internet connection. Please check your connection.',
          style: TextStyle(color: Colors.white70),
        ),
        backgroundColor: const Color(0xFF424242), // Dark gray instead of red
        leading: const Icon(Icons.wifi_off, color: Colors.white70),
        actions: [
          TextButton(
            onPressed: () {
              ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
            },
            child:
                const Text('Dismiss', style: TextStyle(color: Colors.white70)),
          ),
        ],
      ),
    );
  }
}

void showConnectionRestoredDialoag(BuildContext ctx, bool mounted) {
  if (mounted) {
    ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
    ScaffoldMessenger.of(ctx).showMaterialBanner(
      MaterialBanner(
        content: const Text(
          'Internet connection is restored.',
          style: TextStyle(color: Colors.white),
        ),
        backgroundColor:
            const Color(0xFF2E7D32), // Dark green instead of bright green
        leading: const Icon(Icons.wifi, color: Colors.white),
        actions: [
          TextButton(
            onPressed: () {
              if (mounted) {
                ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
              }
            },
            child: const Text('Dismiss', style: TextStyle(color: Colors.white)),
          ),
        ],
        onVisible: () => Future.delayed(const Duration(seconds: 3), () {
          if (mounted) {
            ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
          }
        }),
      ),
    );
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted) {
        ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
      }
    });
  }
}
