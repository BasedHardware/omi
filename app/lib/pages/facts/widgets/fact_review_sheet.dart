import 'package:flutter/material.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/providers/facts_provider.dart';

import '../facts_review_page.dart';

class FactReviewSheet extends StatelessWidget {
  final List<Fact> facts;
  final FactsProvider provider;

  const FactReviewSheet({
    super.key,
    required this.facts,
    required this.provider,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            margin: const EdgeInsets.only(bottom: 16),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: MediaQuery.of(context).size.width * 0.74,
                          child: Text(
                            'Review and save ${facts.length} facts generated from today\'s conversation with Omi',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w400,
                            ),
                          ),
                        ),
                        const SizedBox(height: 4),
                      ],
                    ),
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white70),
                      onPressed: () => Navigator.pop(context),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: TextButton(
                        style: TextButton.styleFrom(
                          backgroundColor: Colors.white.withOpacity(0.1),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () => Navigator.pop(context),
                        child: Text(
                          'Review later',
                          style: TextStyle(
                            color: Colors.grey.shade300,
                            fontSize: 15,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextButton(
                        style: TextButton.styleFrom(
                          backgroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () {
                          Navigator.pop(context);
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (context) => FactReviewPage(facts: facts),
                            ),
                          );
                        },
                        child: const Text(
                          'Review now',
                          style: TextStyle(
                            color: Colors.black,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
