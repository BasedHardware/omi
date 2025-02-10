import 'package:flutter/material.dart';

class CustomSignInButton extends StatelessWidget {
  final String title;
  final String? assetPath;
  final VoidCallback onTap;
  const CustomSignInButton(
      {super.key, required this.title, this.assetPath, required this.onTap});

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
