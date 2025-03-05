import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/facts_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/extensions/string.dart';

class FactItem extends StatelessWidget {
  final Fact fact;
  final FactsProvider provider;
  final Function(BuildContext, Fact, FactsProvider) onTap;
  final bool showDismissible;

  const FactItem({
    super.key,
    required this.fact,
    required this.provider,
    required this.onTap,
    this.showDismissible = true,
  });

  @override
  Widget build(BuildContext context) {
    final Widget factWidget = GestureDetector(
      onTap: () => onTap(context, fact, provider),
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(12),
        ),
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          title: Text(
            fact.content.decodeString,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
            ),
          ),
        ),
      ),
    );

    if (!showDismissible) {
      return factWidget;
    }

    return Dismissible(
      key: Key(fact.id),
      direction: DismissDirection.endToStart,
      onDismissed: (direction) {
        provider.deleteFact(fact);
        MixpanelManager().factsPageDeletedFact(fact);
      },
      background: Container(
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(
          color: Colors.red.shade900,
          borderRadius: BorderRadius.circular(12),
        ),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      child: factWidget,
    );
  }
}
