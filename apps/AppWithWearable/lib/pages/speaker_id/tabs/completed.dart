import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';

class CompletionTab extends StatefulWidget {
  const CompletionTab({super.key});

  @override
  State<CompletionTab> createState() => _CompletionTabState();
}

class _CompletionTabState extends State<CompletionTab> {
  @override
  void initState() {
    SharedPreferencesUtil().hasSpeakerProfile = true;
    super.initState();
  }
  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        SizedBox(height: 48),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: 16.0),
          child: Center(
            child: Text(
              'Your speech profile\nis ready 🎉',
              style: TextStyle(
                color: Colors.white,
                fontSize: 32,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ),
      ],
    );
  }
}
