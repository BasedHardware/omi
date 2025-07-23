import 'package:flutter/material.dart';
import 'package:flutter_svg/svg.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:skeletonizer/skeletonizer.dart';

class AppAnalyticsWidget extends StatelessWidget {
  final int installs;
  final double moneyMade;
  const AppAnalyticsWidget({super.key, required this.installs, required this.moneyMade});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16.0),
      margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('App Analytics', style: TextStyle(color: Colors.white, fontSize: 16)),
              const Spacer(),
              GestureDetector(
                onTap: () async {
                  await IntercomManager().displayEarnMoneyArticle();
                },
                child: Row(
                  children: [
                    Text("learn more", style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
                    Icon(
                      Icons.arrow_outward_rounded,
                      size: 12,
                      color: Colors.grey.shade400,
                    )
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Skeleton.shade(child: SvgPicture.asset(Assets.images.icChart, width: 20)),
                      const SizedBox(width: 8),
                      Text(
                        installs.toString(),
                        style: const TextStyle(color: Colors.white, fontSize: 30),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text('Installs', style: TextStyle(color: Colors.grey.shade300, fontSize: 14)),
                ],
              ),
              const Spacer(flex: 2),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Skeleton.shade(child: SvgPicture.asset(Assets.images.icDollar, width: 20)),
                      const SizedBox(width: 8),
                      Text(
                        "\$$moneyMade",
                        style: const TextStyle(color: Colors.white, fontSize: 28),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text('Money Earned', style: TextStyle(color: Colors.grey.shade300, fontSize: 14)),
                ],
              ),
              const Spacer(flex: 2),
            ],
          ),
        ],
      ),
    );
  }
}
