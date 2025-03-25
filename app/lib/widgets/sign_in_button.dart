import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/gen/assets.gen.dart';

class SignInButton extends StatelessWidget {
  final String title;
  final String? assetPath;
  final VoidCallback onTap;
  final EdgeInsets? padding;
  final double iconSpacing;
  const SignInButton(
      {super.key, required this.title, this.assetPath, required this.onTap, this.padding, required this.iconSpacing});

  factory SignInButton.withGoogle({required VoidCallback onTap, String? title}) {
    return SignInButton(
      assetPath: Assets.images.googleLogo.path,
      title: title ?? "Sign in with Google",
      onTap: onTap,
      padding: Platform.isIOS
          ? const EdgeInsets.symmetric(horizontal: 16, vertical: 12)
          : const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      iconSpacing: Platform.isIOS ? 12 : 10,
    );
  }

  factory SignInButton.withApple({required VoidCallback onTap, String? title}) {
    return SignInButton(
      assetPath: Assets.images.appleLogo.path,
      title: title ?? "Sign in with Apple",
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      iconSpacing: 12,
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: padding ?? const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(6),
          color: Colors.white,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (assetPath != null)
              Image.asset(
                assetPath!,
                height: 20,
                width: 20,
              ),
            SizedBox(width: iconSpacing),
            Text(
              title,
              style: const TextStyle(
                inherit: false,
                fontSize: 20,
                color: Colors.black,
                letterSpacing: -0.41,
              ),
            )
          ],
        ),
      ),
    );
  }
}
