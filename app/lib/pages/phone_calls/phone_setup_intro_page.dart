import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/pages/phone_calls/phone_setup_number_page.dart';

class PhoneSetupIntroPage extends StatelessWidget {
  const PhoneSetupIntroPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              const SizedBox(height: 40),
              // Hero icon
              Container(
                width: 80,
                height: 80,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Color(0xFF1F1F25),
                ),
                child: const Icon(Icons.phone, color: Colors.white, size: 36),
              ),
              const SizedBox(height: 24),
              const Text(
                'Phone Calls with Omi',
                style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: Colors.white),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Make calls with real-time transcription',
                style: TextStyle(fontSize: 15, color: Colors.grey[500]),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              // Step rows
              const _StepRow(
                icon: Icons.phone_outlined,
                title: 'Verify your phone number',
                subtitle: "We'll call you to confirm it's yours",
              ),
              const SizedBox(height: 16),
              const _StepRow(
                icon: Icons.dialpad,
                title: 'Enter a verification code',
                subtitle: "A short code you'll type on the call",
              ),
              const SizedBox(height: 16),
              const _StepRow(
                icon: Icons.people_outline,
                title: 'Start calling your contacts',
                subtitle: 'With live transcription built in',
              ),
              const Spacer(),
              // Get Started button
              GestureDetector(
                onTap: () {
                  HapticFeedback.mediumImpact();
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const PhoneSetupNumberPage()),
                  );
                },
                child: Container(
                  width: double.infinity,
                  height: 56,
                  decoration: BoxDecoration(
                    color: Colors.deepPurple,
                    borderRadius: BorderRadius.circular(28),
                  ),
                  alignment: Alignment.center,
                  child: const Text(
                    'Get Started',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Call recording may require consent in your jurisdiction',
                style: TextStyle(fontSize: 12, color: Colors.grey[700]),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  const _StepRow({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: Colors.white, size: 20),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500, color: Colors.white),
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                style: TextStyle(fontSize: 13, color: Colors.grey[500]),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
