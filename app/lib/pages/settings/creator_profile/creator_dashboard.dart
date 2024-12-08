import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:friend_private/gen/assets.gen.dart';
import 'package:friend_private/pages/settings/creator_profile/creator_profile_details.dart';
import 'package:friend_private/pages/settings/creator_profile/creator_profile_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

class CreatorDashboard extends StatefulWidget {
  const CreatorDashboard({super.key});

  @override
  State<CreatorDashboard> createState() => _CreatorDashboardState();
}

class _CreatorDashboardState extends State<CreatorDashboard> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await Provider.of<CreatorProfileProvider>(context, listen: false).getCreatorProfileDetails();
      await Provider.of<CreatorProfileProvider>(context, listen: false).getCreatorStats();
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
        title: const Text('Creator Dashboard'),
        centerTitle: false,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new),
          onPressed: () {
            Navigator.pop(context);
          },
        ),
      ),
      body: Consumer<CreatorProfileProvider>(builder: (context, provider, child) {
        return SingleChildScrollView(
          child: Skeletonizer(
            enabled: provider.isLoading,
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.all(16.0),
                  margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                  child: Row(
                    children: [
                      Skeleton.shade(child: SvgPicture.asset(Assets.images.icMoney, width: 38)),
                      const SizedBox(width: 10),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("\$${provider.totalEarnings}",
                              style: const TextStyle(color: Colors.white, fontSize: 20)),
                          const SizedBox(height: 4),
                          const Text("Money Earned", style: TextStyle(color: Colors.white, fontSize: 12)),
                        ],
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.all(16.0),
                  margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                  child: Row(
                    children: [
                      Skeleton.shade(child: SvgPicture.asset(Assets.images.icChart2, width: 38)),
                      const SizedBox(width: 10),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(provider.totalUsage.toString(),
                              style: const TextStyle(color: Colors.white, fontSize: 20)),
                          const SizedBox(height: 4),
                          const Text("Times Used", style: TextStyle(color: Colors.white, fontSize: 12)),
                        ],
                      ),
                    ],
                  ),
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(16.0),
                      margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
                      width: MediaQuery.sizeOf(context).width * 0.46,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade900,
                        borderRadius: BorderRadius.circular(16.0),
                      ),
                      child: Row(
                        children: [
                          Skeleton.shade(child: SvgPicture.asset(Assets.images.icApps, width: 36)),
                          const SizedBox(width: 8),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(provider.publishedApps.toString(),
                                  style: const TextStyle(color: Colors.white, fontSize: 18)),
                              const SizedBox(height: 4),
                              const Text("Published Apps", style: TextStyle(color: Colors.white, fontSize: 12)),
                            ],
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.all(16.0),
                      margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
                      width: MediaQuery.sizeOf(context).width * 0.46,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade900,
                        borderRadius: BorderRadius.circular(16.0),
                      ),
                      child: Row(
                        children: [
                          Skeleton.shade(child: SvgPicture.asset(Assets.images.icUsers, width: 36)),
                          const SizedBox(width: 8),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(provider.totalUsers.toString(),
                                  style: const TextStyle(color: Colors.white, fontSize: 18)),
                              const SizedBox(height: 4),
                              const Text("Active Users", style: TextStyle(color: Colors.white, fontSize: 12)),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                InkWell(
                  onTap: () {
                    routeToPage(context, const CreatorProfileDetails());
                  },
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16.0),
                    margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade900,
                      borderRadius: BorderRadius.circular(16.0),
                    ),
                    child: Row(
                      children: [
                        const Text("Creator Profile", style: TextStyle(color: Colors.white, fontSize: 16)),
                        const Spacer(),
                        Icon(Icons.arrow_forward_ios, color: Colors.grey.shade400),
                      ],
                    ),
                  ),
                ),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16.0),
                  margin: const EdgeInsets.only(left: 8.0, right: 8.0, top: 12, bottom: 6),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                  child: Row(
                    children: [
                      const Text("Payout History", style: TextStyle(color: Colors.white, fontSize: 16)),
                      const Spacer(),
                      Icon(Icons.arrow_forward_ios, color: Colors.grey.shade400),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      }),
    );
  }
}
