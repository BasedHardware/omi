import 'package:flutter/material.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

import 'creator_profile_provider.dart';

class PayoutHistory extends StatefulWidget {
  const PayoutHistory({super.key});

  @override
  State<PayoutHistory> createState() => _PayoutHistoryState();
}

class _PayoutHistoryState extends State<PayoutHistory> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await Provider.of<CreatorProfileProvider>(context, listen: false).getPayoutHistory();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        title: const Text('Payout History'),
        centerTitle: false,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new),
          onPressed: () {
            Navigator.pop(context);
          },
        ),
      ),
      body: Consumer<CreatorProfileProvider>(builder: (context, provider, child) {
        return Skeletonizer(
          enabled: provider.isLoading,
          child: ListView.builder(
            itemBuilder: (ctx, idx) {
              return Container(
                padding: const EdgeInsets.all(16.0),
                margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
                width: double.infinity,
                decoration: BoxDecoration(
                  color: Colors.grey.shade900,
                  borderRadius: BorderRadius.circular(16.0),
                ),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text("${provider.payoutHistory[idx].amount} ${provider.payoutHistory[idx].currency}",
                                style: const TextStyle(color: Colors.white, fontSize: 20)),
                            const SizedBox(
                              height: 4,
                            ),
                            Text(dateTimeFormat('MMM d, h:mm a', provider.payoutHistory[idx].date),
                                style: const TextStyle(color: Colors.white, fontSize: 12)),
                          ],
                        ),
                        const Spacer(),
                        getStatusChip(provider.payoutHistory[idx].paymentStatus),
                      ],
                    ),
                    const SizedBox(
                      height: 6,
                    ),
                    Divider(
                      color: Colors.grey.shade700,
                      thickness: 1,
                    ),
                    const SizedBox(
                      height: 6,
                    ),
                    Row(
                      children: [
                        const Text('Payment Method', style: TextStyle(color: Colors.white)),
                        const Spacer(),
                        Text(provider.payoutHistory[idx].payoutMethodText(),
                            style: const TextStyle(color: Colors.white)),
                      ],
                    ),
                  ],
                ),
              );
            },
            itemCount: provider.payoutHistory.length,
          ),
        );
      }),
    );
  }

  Widget getStatusChip(String status) {
    if (status == 'pending') {
      return const Chip(
        label: Text("Pending", style: TextStyle(color: Colors.white)),
      );
    } else if (status == 'failed') {
      return Chip(
        backgroundColor: Colors.red.withOpacity(0.4),
        label: const Text("Failed", style: TextStyle(color: Colors.red)),
      );
    } else {
      return Chip(
        backgroundColor: const Color(0xFF4CAF50).withOpacity(0.4),
        label: const Text("Successful", style: TextStyle(color: Color.fromARGB(255, 40, 231, 46))),
      );
    }
  }
}
