import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';

class InstructionsTab extends StatefulWidget {
  const InstructionsTab({super.key});

  @override
  State<InstructionsTab> createState() => _InstructionsTabState();
}

class _InstructionsTabState extends State<InstructionsTab> {
  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 48),
        const Center(
          child: Text(
            'Setup Your Speech Profile',
            style: TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        const SizedBox(height: 24),
        Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24.0),
            child: Text(
              'You will record samples of your voice to create a speech profile. This will help the device recognize your voice.',
              style: TextStyle(color: Colors.grey.shade300, fontSize: 15),
              textAlign: TextAlign.center,
            ),
          ),
        ),
        const SizedBox(height: 48),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 24.0),
          child: Text(
            'Instructions:',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        const SizedBox(height: 20),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 24.0, vertical: 8.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '1. Wear the device and make sure it is connected to the app 🛜',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
              SizedBox(height: 16),
              Text(
                '2. Make sure you are in a very quiet environment 🤫',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
              SizedBox(height: 16),
              Text(
                '3. Repeat the phrases that will be shown on the screen 🗣️',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
            ],
          ),
        ),
        const SizedBox(height: 48),
        SharedPreferencesUtil().hasSpeakerProfile
            ? const Padding(
                padding: EdgeInsets.symmetric(horizontal: 24.0),
                child: Text(
                  '✅ You already have a speaker profile. Feel free to record new samples to improve your profile quality.',
                  style: TextStyle(color: Colors.white),
                ),
              )
            : const SizedBox.shrink(),
      ],
    );
  }
}
