import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/facts_provider.dart';
import 'package:friend_private/widgets/extensions/functions.dart';
import 'package:provider/provider.dart';

class FactsPage extends StatelessWidget {
  const FactsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => FactsProvider(),
      child: const _FactsPage(),
    );
  }
}

class _FactsPage extends StatefulWidget {
  const _FactsPage();

  @override
  State<_FactsPage> createState() => _FactsPageState();
}

class _FactsPageState extends State<_FactsPage> with AutomaticKeepAliveClientMixin {
  @override
  void initState() {
    () {
      context.read<FactsProvider>().init();
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<FactsProvider>(
      builder: (context, provider, _) {
        return ListView.builder(
          itemCount: provider.facts.length,
          itemBuilder: (context, index) {
            Fact fact = provider.facts[index];
            if (fact.id.isEmpty) {
              // TextField to create a new fact + dropdown selector + save or discard button
              return Card(
                color: Colors.black12,
                elevation: 0,
                child: Padding(
                  padding: const EdgeInsets.only(top: 16.0),
                  child: ListTile(
                    title: TextField(
                      onChanged: (value) {
                        fact.content = value;
                      },
                      decoration: const InputDecoration(hintText: 'Fact'),
                    ),
                    subtitle: Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        DropdownButton<FactCategory>(
                          value: fact.category,
                          onChanged: (value) {
                            fact.category = value!;
                          },
                          items: FactCategory.values
                              .map((category) => DropdownMenuItem(
                                    value: category,
                                    child: Text(category.toString().split('.').last),
                                  ))
                              .toList(),
                        ),
                        IconButton(
                          onPressed: () {
                            provider.createFactProvider(fact.content, fact.category);
                          },
                          icon: const Icon(Icons.save),
                        ),
                        IconButton(
                          onPressed: () {},
                          icon: const Icon(Icons.cancel),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            }
            return Dismissible(
                key: Key(fact.id),
                direction: DismissDirection.endToStart,
                onDismissed: (direction) {
                  provider.deleteFactProvider(index);
                },
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 20.0),
                  color: Colors.red,
                  child: const Icon(Icons.delete, color: Colors.white),
                ),
                child: Card(
                  color: Colors.black12,
                  elevation: 0,
                  child: Padding(
                    padding: const EdgeInsets.only(top: 16.0),
                    child: ListTile(
                      title: Text(provider.facts[index].content),
                      subtitle: fact.reviewed
                          ? const SizedBox()
                          : Row(
                              mainAxisAlignment: MainAxisAlignment.end,
                              children: [
                                IconButton(
                                  onPressed: () => provider.reviewFactProvider(index, false),
                                  icon: const Icon(Icons.cancel_outlined),
                                ),
                                IconButton(
                                  onPressed: () => provider.reviewFactProvider(index, true),
                                  icon: const Icon(Icons.check),
                                ),
                              ],
                            ),
                    ),
                  ),
                ));
          },
        );
      },
    );
  }
}
