import 'package:flutter/material.dart';

class SubscriptionPage extends StatelessWidget {
  const SubscriptionPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        centerTitle: true,
        title: const Text('Subscriptions'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 25),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            /*subscriptionCard(
              heading: 'General Subscriptions',
              title: 'PREMIUM',
              subtitle: '10M tokens',
              description:
                  'Lorem ipsum dolor sit amet, Eum nostrum voluptas est saepe quod et tempore harum est magnam eaque eos enim saepe est voluptatem quasi.',
              price: '\$19.9',
              iconColor: Colors.orange,
            ),*/
            subscriptionCard(
              heading: 'Plugin Subscriptions',
              title: 'PLUGIN',
              subtitle: 'Fixed',
              description:
                  'Lorem ipsum dolor sit amet, Eum nostrum voluptas est saepe quod et tempore harum est magnam eaque eos enim saepe est voluptatem quasi.',
              price: '\$4.9',
              iconColor: Colors.red,
            ),
          ],
        ),
      ),
    );
  }

  Widget subscriptionCard({
    required String heading,
    required String title,
    required String subtitle,
    required String description,
    required String price,
    required Color iconColor,
  }) {
    return Container(
      margin: const EdgeInsets.only(top: 30),
      child: Stack(
        alignment: Alignment.topCenter,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 40),
            margin: EdgeInsets.only(top: 15),
            decoration: BoxDecoration(
              color: Colors.grey[900],
              borderRadius: BorderRadius.circular(20),
            ),
            child: Column(
              children: [
                Text(
                  title,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: const TextStyle(color: Colors.white),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Image.asset(
                    'assets/images/ic_subscription.png',
                    height: 55,
                  ),
                ),
                Text(
                  description,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70),
                ),
                Container(
                  width: 100,
                  margin: const EdgeInsets.symmetric(vertical: 10),
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  decoration: BoxDecoration(
                      color: Colors.deepPurple,
                      borderRadius: BorderRadius.circular(40)),
                  alignment: Alignment.center,
                  child: Text(
                    price,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.deepPurple,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              heading,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }
}
