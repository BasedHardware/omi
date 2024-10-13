import 'package:flutter/material.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:lottie/lottie.dart';
import 'dart:math';

class MyHistorianPage extends StatefulWidget {
  const MyHistorianPage({Key? key}) : super(key: key);

  @override
  _MyHistorianPageState createState() => _MyHistorianPageState();
}

class _MyHistorianPageState extends State<MyHistorianPage> {
  List<String> memories = [];
  bool isLoading = false;
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    fetchMemories();
  }

  Future<void> fetchMemories() async {
    setState(() {
      isLoading = true;
    });

    try {
      final homeProvider = Provider.of<HomeProvider>(context, listen: false);
      final fetchedMemories = await homeProvider.fetchLatestMemories();

      setState(() {
        memories = fetchedMemories;
      });
    } catch (error) {
      Logger.instance.talker.error('Error fetching memories: $error');
      setState(() {
        memories = [];
      });
    } finally {
      setState(() {
        isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('My Personal Historian', style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        elevation: 0,
        iconTheme: IconThemeData(color: Colors.black),
      ),
      body: Container(
        color: Colors.white,
        child: isLoading
            ? _buildLoadingView()
            : RefreshIndicator(
                onRefresh: fetchMemories,
                child: memories.isEmpty
                    ? Center(child: Text('No memories found. Pull to refresh.', style: TextStyle(color: Colors.black)))
                    : ListView.builder(
                        itemCount: memories.length,
                        itemBuilder: (context, index) {
                          return MemoryCard(memory: memories[index]);
                        },
                      ),
              ),
      ),
    );
  }

  Widget _buildLoadingView() {
    final int randomIndex = _random.nextInt(6) + 1;
    final String animationPath = 'assets/lottie_animations/loading/loading$randomIndex.json';

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Lottie.asset(
            animationPath,
            width: 200,
            height: 200,
          ),
          SizedBox(height: 20),
          Text(
            'Retrieving Your Memories',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black),
          ),
          SizedBox(height: 10),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 40),
            child: Text(
              'We\'re compiling your recent memories to create your personal history.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: Colors.grey[600]),
            ),
          ),
        ],
      ),
    );
  }
}

class MemoryCard extends StatelessWidget {
  final String memory;

  const MemoryCard({Key? key, required this.memory}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Memory',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.blue),
            ),
            SizedBox(height: 8),
            Text(
              memory,
              style: TextStyle(fontSize: 16, color: Colors.black87),
            ),
          ],
        ),
      ),
    );
  }
}
