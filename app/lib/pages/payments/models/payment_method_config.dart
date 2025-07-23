import 'package:flutter/material.dart';
import 'package:flutter_svg/svg.dart';
import 'package:omi/gen/assets.gen.dart';

class PaymentMethodConfig {
  final String title;
  final Widget icon;
  final Color backgroundColor;
  final VoidCallback onManageTap;
  final VoidCallback? onSetActiveTap;
  final bool isActive;
  final bool isConnected;

  const PaymentMethodConfig({
    required this.title,
    required this.icon,
    required this.backgroundColor,
    required this.onManageTap,
    this.onSetActiveTap,
    this.isActive = false,
    this.isConnected = false,
  });

  String get subtitle => isActive ? 'Active' : (isConnected ? 'Connected' : 'Not Connected');

  static PaymentMethodConfig stripe({
    required VoidCallback onManageTap,
    VoidCallback? onSetActiveTap,
    bool isActive = false,
    bool isConnected = false,
  }) {
    return PaymentMethodConfig(
      title: 'Stripe',
      icon: SvgPicture.asset(
        Assets.images.stripeLogo,
        width: 80,
        color: Colors.white,
      ),
      backgroundColor: isActive ? const Color(0xFF635BFF) : Color(0xFF35343B),
      onManageTap: onManageTap,
      onSetActiveTap: onSetActiveTap,
      isActive: isActive,
      isConnected: isConnected,
    );
  }

  static PaymentMethodConfig paypal({
    required VoidCallback onManageTap,
    VoidCallback? onSetActiveTap,
    bool isActive = false,
    bool isConnected = false,
  }) {
    return PaymentMethodConfig(
      title: 'PayPal',
      icon: const Icon(
        Icons.paypal,
        size: 32,
        color: Colors.white,
      ),
      backgroundColor: isActive ? const Color(0xFF003087) : Color(0xFF35343B),
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
    return {
      'email': email,
      'paypalme_url': link,
    };
  }

  factory PayPalDetails.fromJson(Map<String, dynamic> json) {
    return PayPalDetails(
      email: json['email'],
      link: json['paypalme_url'],
    );
  }
}
