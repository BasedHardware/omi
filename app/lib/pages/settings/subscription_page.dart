import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/pages/settings/webview.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class SubscriptionPage extends StatefulWidget {
  const SubscriptionPage({super.key});

  @override
  State<SubscriptionPage> createState() => _SubscriptionPageState();
}

class _SubscriptionPageState extends State<SubscriptionPage> {
  bool isYearlySelected = true; // Default to yearly for better value

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Upgrade Subscription'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header section
            const Center(
              child: Column(
                children: [
                  FaIcon(
                    FontAwesomeIcons.crown,
                    color: Color(0xFFFFD700),
                    size: 48,
                  ),
                  SizedBox(height: 16),
                  Text(
                    'Unlock Unlimited Access',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: 8),
                  Text(
                    'Get unlimited access to all Omi features',
                    style: TextStyle(
                      color: Color(0xFF8E8E93),
                      fontSize: 16,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 40),

            // Plan toggle
            Container(
              padding: const EdgeInsets.all(4),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: GestureDetector(
                      onTap: () => setState(() => isYearlySelected = false),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        decoration: BoxDecoration(
                          color: !isYearlySelected ? const Color(0xFF007AFF) : Colors.transparent,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          'Monthly',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: !isYearlySelected ? Colors.white : const Color(0xFF8E8E93),
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Expanded(
                    child: GestureDetector(
                      onTap: () => setState(() => isYearlySelected = true),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        decoration: BoxDecoration(
                          color: isYearlySelected ? const Color(0xFF007AFF) : Colors.transparent,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              'Yearly',
                              style: TextStyle(
                                color: isYearlySelected ? Colors.white : const Color(0xFF8E8E93),
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: const Color(0xFF34C759),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: const Text(
                                'SAVE 17%',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),

            // Selected plan card
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: const Color(0xFF007AFF),
                  width: 2,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        isYearlySelected ? '\$199' : '\$19',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 48,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Text(
                          isYearlySelected ? '/year' : '/month',
                          style: const TextStyle(
                            color: Color(0xFF8E8E93),
                            fontSize: 18,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (isYearlySelected) ...[
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFF34C759),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: const Text(
                            '2 MONTHS FREE',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Text(
                          '\$228/year',
                          style: TextStyle(
                            color: Color(0xFF8E8E93),
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            decoration: TextDecoration.lineThrough,
                          ),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 24),

                  // Features list
                  _buildFeatureItem('Unlimited conversation minutes'),
                  _buildFeatureItem('Unlimited AI insights'),
                  _buildFeatureItem('Priority customer support'),
                  _buildFeatureItem('Early access to new features'),
                ],
              ),
            ),
            const SizedBox(height: 32),

            // Subscribe button
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton(
                onPressed: () => _handleSubscribe(),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF007AFF),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                child: Text(
                  isYearlySelected ? 'Subscribe Yearly' : 'Subscribe Monthly',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Terms and conditions
            const Text(
              'By subscribing, you agree to our Terms of Service and Privacy Policy. '
              'Subscription will auto-renew unless cancelled.',
              style: TextStyle(
                color: Color(0xFF8E8E93),
                fontSize: 13,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFeatureItem(String feature) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          const FaIcon(
            FontAwesomeIcons.check,
            color: Color(0xFF34C759),
            size: 16,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              feature,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w400,
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _handleSubscribe() {
    final String url = isYearlySelected
        ? 'https://buy.stripe.com/28EbIT9xW0KybwigG66wE1z' // Annual plan
        : 'https://buy.stripe.com/aFaeV5cK8dxk8k6cpQ6wE1y'; // Monthly plan

    MixpanelManager().track('Subscription Selected', properties: {
      'plan_type': isYearlySelected ? 'yearly' : 'monthly',
      'price': isYearlySelected ? 199 : 19,
    });

    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => PageWebView(
          url: url,
          title: 'Complete Subscription',
        ),
      ),
    );
  }
}
