import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';

class CompletionTab extends StatefulWidget {
  final VoidCallback goNext;

  const CompletionTab({super.key, required this.goNext});

  @override
  State<CompletionTab> createState() => _CompletionTabState();
}

class _CompletionTabState extends State<CompletionTab> {
  @override
  void initState() {
    SharedPreferencesUtil().hasSpeakerProfile = true;
    MixpanelManager().speechProfileCompleted();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          height: 48,
          width: 48,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(24),
          ),
          child: const Icon(
            Icons.check,
            color: Colors.black,
            weight: 5,
          ),
        ),
        const SizedBox(height: 16),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16.0),
          child: Center(
            child: Text(
              'Your speech profile is now\nfully set up!',
              style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w500, height: 1.5),
              textAlign: TextAlign.center,
            ),
          ),
        ),
        const SizedBox(height: 16),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Center(
            child: Text(
              'You can always do it later and improve it\'s accuracy!',
              style: TextStyle(color: Colors.grey.shade300, fontSize: 16, height: 1.5),
              textAlign: TextAlign.center,
            ),
          ),
        ),
        const SizedBox(height: 32),
        Row(
          children: [
            Expanded(
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                child: MaterialButton(
                  onPressed: () {
                    widget.goNext();
                  },
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                    side: const BorderSide(color: Colors.white, width: 1),
                  ),
                  color: Theme.of(context).colorScheme.primary,
                  child: const Padding(
                    padding: EdgeInsets.all(16.0),
                    child: Text(
                      'Finalize',
                      style: TextStyle(color: Colors.white, fontSize: 20),
                    ),
                  ),
                ),
              ),
            )
          ],
        )
      ],
    );
  }
}
