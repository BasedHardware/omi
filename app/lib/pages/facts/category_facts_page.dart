import 'package:flutter/material.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/providers/facts_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

import 'widgets/fact_edit_sheet.dart';
import 'widgets/fact_item.dart';
import 'widgets/fact_dialog.dart';

class CategoryFactsPage extends StatelessWidget {
  final FactCategory category;

  const CategoryFactsPage({
    super.key,
    required this.category,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<FactsProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                category.toString().split('.').last[0].toUpperCase() + category.toString().split('.').last.substring(1),
              ),
              Text(
                '${provider.filteredFacts.length} facts',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey.shade400,
                  fontWeight: FontWeight.normal,
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.add),
              onPressed: () {
                showFactDialog(context, provider);
                MixpanelManager().factsPageCreateFactBtn();
              },
            ),
          ],
        ),
        body: provider.filteredFacts.isEmpty
            ? Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.note_add, size: 48, color: Colors.grey.shade600),
                    const SizedBox(height: 16),
                    Text(
                      'No facts in this category yet',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 18,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () => showFactDialog(context, provider),
                      child: const Text('Add your first fact'),
                    ),
                  ],
                ),
              )
            : ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: provider.filteredFacts.length,
                itemBuilder: (context, index) {
                  final fact = provider.filteredFacts[index];
                  return FactItem(
                    fact: fact,
                    provider: provider,
                    onTap: _showQuickEditSheet,
                  );
                },
              ),
      );
    });
  }

  void _showQuickEditSheet(BuildContext context, Fact fact, FactsProvider provider) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => FactEditSheet(
        fact: fact,
        provider: provider,
        onDelete: (_, __, ___) {},
      ),
    );
  }
}
