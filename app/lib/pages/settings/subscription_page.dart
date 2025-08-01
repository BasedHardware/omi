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
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            FaIcon(
              FontAwesomeIcons.crown,
              color: Color(0xFFFFD700),
              size: 20,
            ),
            SizedBox(width: 8),
            Text('Upgrade Subscription'),
          ],
        ),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Benefits Section
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'What you get:',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 16),
                  _buildFeatureItem('Unlimited conversation minutes'),
                  _buildFeatureItem('Unlimited AI insights'),
                  _buildFeatureItem('Priority customer support'),
                  _buildFeatureItem('Early access to new features'),
                ],
              ),
            ),
            const SizedBox(height: 32),

            // Yearly Plan Card (Recommended)
            _buildPlanCard(
              title: 'Yearly Plan',
              price: '\$199',
              period: '/year',
              isRecommended: true,
              badge: 'SAVE 17%',
              originalPrice: '\$228/year',
              onTap: () => _handleSubscribe(isYearly: true),
            ),
            const SizedBox(height: 16),

            // Monthly Plan Card
            _buildPlanCard(
              title: 'Monthly Plan',
              price: '\$19',
              period: '/month',
              isRecommended: false,
              onTap: () => _handleSubscribe(isYearly: false),
            ),
            const SizedBox(height: 32),

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

  Widget _buildPlanCard({
    required String title,
    required String price,
    required String period,
    required bool isRecommended,
    required VoidCallback onTap,
    String? badge,
    String? originalPrice,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isRecommended ? Colors.white : const Color(0xFF3C3C43),
            width: isRecommended ? 2 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header with title and badge
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (isRecommended)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Text(
                      'RECOMMENDED',
                      style: TextStyle(
                        color: Colors.black,
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 16),

            // Price
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Dollar sign
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    '\$',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                // Price number
                Text(
                  price.substring(1), // Remove the $ from the price string
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 48,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(width: 8),
                Padding(
                  padding: const EdgeInsets.only(top: 28),
                  child: Text(
                    period,
                    style: const TextStyle(
                      color: Color(0xFF8E8E93),
                      fontSize: 18,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),

            // Savings information for yearly plan
            if (isRecommended && badge != null && originalPrice != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFF34C759),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      badge,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '\$',
                        style: const TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          decoration: TextDecoration.lineThrough,
                        ),
                      ),
                      Text(
                        originalPrice!.substring(1), // Remove $ from originalPrice
                        style: const TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          decoration: TextDecoration.lineThrough,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
            const SizedBox(height: 24),

            // Subscribe button
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton(
                onPressed: onTap,
                style: ElevatedButton.styleFrom(
                  backgroundColor: isRecommended ? Colors.white : const Color(0xFF3C3C43),
                  foregroundColor: isRecommended ? Colors.black : Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: Text(
                  isRecommended ? 'Subscribe Yearly' : 'Subscribe Monthly',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
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

  void _handleSubscribe({required bool isYearly}) {
    final String url = isYearly
        ? 'https://buy.stripe.com/28EbIT9xW0KybwigG66wE1z' // Annual plan
        : 'https://buy.stripe.com/aFaeV5cK8dxk8k6cpQ6wE1y'; // Monthly plan

    MixpanelManager().track('Subscription Selected', properties: {
      'plan_type': isYearly ? 'yearly' : 'monthly',
      'price': isYearly ? 199 : 19,
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
