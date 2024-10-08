import 'package:flutter/material.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:provider/provider.dart';

class SyncedMemoriesPage extends StatelessWidget {
  final Map<String, dynamic>? res;
  const SyncedMemoriesPage({super.key, this.res});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synced Memories'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Consumer<MemoryProvider>(
        builder: (context, memoryProvider, child) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                "Updated Memories",
                style: TextStyle(color: Colors.white),
              ),
              ListView.separated(
                shrinkWrap: true,
                itemBuilder: (ctx, i) {
                  return Container();
                },
                separatorBuilder: (ctx, i) {
                  return const SizedBox(
                    height: 10,
                  );
                },
                itemCount: memoryProvider.syncResult!['updated_memories'].length,
              ),
              const Text(
                "New Memories",
                style: TextStyle(color: Colors.white),
              ),
              ListView.separated(
                shrinkWrap: true,
                itemBuilder: (ctx, i) {
                  return Container();
                },
                separatorBuilder: (ctx, i) {
                  return const SizedBox(
                    height: 10,
                  );
                },
                itemCount: memoryProvider.syncResult!['new_memories'].length,
              ),
            ],
          );
        },
      ),
    );
  }
}
