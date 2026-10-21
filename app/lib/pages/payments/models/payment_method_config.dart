import 'package:flutter/material.dart';

import 'package:flutter_svg/svg.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/ui/ui.dart';

class PaymentMethodConfig {
  final String title;
  final String subtitle;
  final Widget icon;
  final Color backgroundColor;
  final VoidCallback onManageTap;
  final VoidCallback? onSetActiveTap;
  final bool isActive;
  final bool isConnected;

  const PaymentMethodConfig({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.backgroundColor,
    required this.onManageTap,
    this.onSetActiveTap,
    this.isActive = false,
    this.isConnected = false,
  });

  static PaymentMethodConfig stripe({
    required String title,
    required String subtitle,
    required VoidCallback onManageTap,
    VoidCallback? onSetActiveTap,
    bool isActive = false,
    bool isConnected = false,
  }) {
    return PaymentMethodConfig(
      title: title,
      subtitle: subtitle,
      icon: SvgPicture.asset(
        Assets.images.stripeLogo,
        width: 80,
        colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
      ),
      backgroundColor: isActive ? OmiColors.surface2 : OmiColors.surface1,
      onManageTap: onManageTap,
      onSetActiveTap: onSetActiveTap,
      isActive: isActive,
      isConnected: isConnected,
    );
  }

  static PaymentMethodConfig paypal({
    required String title,
    required String subtitle,
    required VoidCallback onManageTap,
    VoidCallback? onSetActiveTap,
    bool isActive = false,
    bool isConnected = false,
  }) {
    return PaymentMethodConfig(
      title: title,
      subtitle: subtitle,
      icon: const Icon(Icons.paypal, size: 32, color: Colors.white),
      backgroundColor: isActive ? OmiColors.surface2 : OmiColors.surface1,
      onManageTap: onManageTap,
      onSetActiveTap: onSetActiveTap,
      isActive: isActive,
      isConnected: isConnected,
    );
  }
}

class PayPalDetails {
  final String email;
  final String link;

  PayPalDetails({required this.email, required this.link});

  Map<String, dynamic> toJson() {
    return {'email': email, 'paypalme_url': link};
  }

  factory PayPalDetails.fromJson(Map<String, dynamic> json) {
    return PayPalDetails(email: json['email'], link: json['paypalme_url']);
  }
}
