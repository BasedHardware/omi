import 'package:flutter/material.dart';
import 'package:friend_private/gen/assets.gen.dart';

class SignInButton extends StatelessWidget {
  final String title;
  final String? assetPath;
  final VoidCallback onTap;
  const SignInButton(
      {super.key, required this.title, this.assetPath, required this.onTap});

  factory SignInButton.withGoogle({required VoidCallback onTap}) {
    return SignInButton(
      assetPath: Assets.images.googleLogo.path,
      title: "Sign in with Google",
      onTap: onTap,
    );
  }

  factory SignInButton.withApple({required VoidCallback onTap}) {
    return SignInButton(
      assetPath: Assets.images.appleLogo.path,
      title: "Sign in with Apple",
      onTap: onTap,
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
            const SizedBox(width: 6),
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
