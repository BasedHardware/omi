import 'package:flutter/material.dart';
import 'package:friend_private/providers/no_device_onboarding_provider.dart';
import 'package:provider/provider.dart';
import 'package:collection/collection.dart';

class CloneAudienceScreen extends StatefulWidget {
  final VoidCallback onNext;
  final VoidCallback onBack;

  const CloneAudienceScreen({
    super.key,
    required this.onNext,
    required this.onBack,
  });

  @override
  State<CloneAudienceScreen> createState() => _CloneAudienceScreenState();
}

class _CloneAudienceScreenState extends State<CloneAudienceScreen> {
  final List<String> _selectedAudiences = [];

  final List<String> _audiences = [
    'Colleagues',
    'Community',
    'Family',
    'Followers',
    'Just Myself',
  ];

  @override
  void initState() {
    super.initState();
    final providerAudiences = context.read<NoDeviceOnboardingProvider>().audiences;
    if (providerAudiences.isNotEmpty) {
      _selectedAudiences.addAll(providerAudiences);
    }
  }

  void _toggleAudience(String audience) {
    setState(() {
      if (_selectedAudiences.contains(audience)) {
        _selectedAudiences.remove(audience);
      } else {
        _selectedAudiences.add(audience);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // Background image
        Positioned.fill(
          child: Image.asset(
            'assets/images/new_background.png',
            fit: BoxFit.cover,
          ),
        ),
        Scaffold(
          backgroundColor: Colors.transparent,
          appBar: AppBar(
            backgroundColor: Colors.transparent,
            elevation: 0,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back, color: Colors.white),
              onPressed: widget.onBack,
            ),
          ),
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const SizedBox(height: 0),
                  Column(
                    children: [
                      const Center(
                        child: Text(
                          '🤖',
                          style: TextStyle(
                            fontSize: 42,
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        'Who will interact with\nyour Omi Clone?',
                        style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                              shadows: [
                                Shadow(
                                  offset: const Offset(0, 1),
                                  blurRadius: 15,
                                  color: Colors.white.withOpacity(1),
                                ),
                                Shadow(
                                  offset: const Offset(0, 0),
                                  blurRadius: 15,
                                  color: Colors.white.withOpacity(0.3),
                                ),
                              ],
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Select all that apply\nYou can make more clones later',
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              color: Colors.white.withOpacity(0.8),
                              shadows: [
                                Shadow(
                                  offset: const Offset(0, 1),
                                  blurRadius: 3,
                                  color: Colors.white.withOpacity(0.25),
                                ),
                              ],
                            ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 32),
                      ..._audiences.map((audience) => Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: GestureDetector(
                              onTap: () => _toggleAudience(audience),
                              child: Container(
                                width: double.infinity,
                                padding: const EdgeInsets.symmetric(vertical: 16),
                                decoration: BoxDecoration(
                                  color: _selectedAudiences.contains(audience)
                                      ? Colors.white.withOpacity(0.3)
                                      : Colors.white.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(28),
                                  border: Border.all(
                                    color: _selectedAudiences.contains(audience)
                                        ? Colors.white.withOpacity(0.4)
                                        : Colors.white.withOpacity(0.2),
                                  ),
                                ),
                                child: Text(
                                  audience,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                          )),
                    ],
                  ),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 40),
                    child: ElevatedButton(
                      onPressed: _selectedAudiences.isNotEmpty
                          ? () {
                              context.read<NoDeviceOnboardingProvider>().setAudiences(_selectedAudiences);
                              widget.onNext();
                            }
                          : null,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.grey[900],
                        foregroundColor: Colors.white,
                        minimumSize: const Size(double.infinity, 56),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(28),
                        ),
                      ),
                      child: const Text(
                        'Next',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
} 