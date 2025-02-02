import 'package:flutter/material.dart';
import 'package:flutter_svg/svg.dart';
import 'package:friend_private/gen/assets.gen.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/animated_loading_button.dart';
import 'package:url_launcher/url_launcher.dart';

class StripeConnectIntroPage extends StatelessWidget {
  const StripeConnectIntroPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          children: [
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const SizedBox(
                  width: 18,
                ),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                  child: Image.asset(
                    Assets.images.herologo.path,
                    width: 26,
                    color: Colors.black,
                  ),
                ),
                Transform.translate(
                  offset: const Offset(-18, 0),
                  child: Container(
                    padding: const EdgeInsets.all(14),
                    decoration: const BoxDecoration(
                      color: Color(0xFF635BFF),
                      shape: BoxShape.circle,
                    ),
                    child: SvgPicture.asset(
                      Assets.images.stripeLogo,
                      width: 40,
                      color: Colors.white,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 32),
            const Text(
              'Get paid for your app sales through Stripe',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 48),
            _buildFeatureRow(
              icon: Icons.payments_rounded,
              title: 'Monthly payouts',
              description: 'Receive monthly payments directly to your account when you reach \$10 in earnings',
            ),
            const SizedBox(height: 24),
            _buildFeatureRow(
              icon: Icons.shield_outlined,
              title: 'Secure and reliable',
              description: 'Stripe ensures safe and timely transfers of your app revenue',
            ),
            const Spacer(),
            Text(
              'By clicking on "Connect Now" you agree to the',
              style: TextStyle(
                color: Colors.grey[400],
                fontSize: 14,
              ),
            ),
            const SizedBox(
              height: 4,
            ),
            GestureDetector(
              onTap: () {
                launchUrl(Uri.parse('https://stripe.com/connect-account/legal'));
              },
              child: const Text(
                'Stripe Connected Account Agreement',
                style: TextStyle(
                  color: Color(0xFF635BFF),
                  fontSize: 14,
                ),
              ),
            ),
            const SizedBox(height: 18),
            AnimatedLoadingButton(
              text: "Connect Now",
              onPressed: () async {},
              color: Colors.white,
              textStyle: const TextStyle(
                fontSize: 16,
                color: Colors.black,
              ),
              width: MediaQuery.of(context).size.width * 0.8,
            ),
            const SizedBox(height: 36),
          ],
        ),
      ),
    );
  }

  Widget _buildFeatureRow({
    required IconData icon,
    required String title,
    required String description,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: const Color(0xFF635BFF).withOpacity(0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            icon,
            color: const Color(0xFF635BFF),
            size: 24,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                description,
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey[400],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
