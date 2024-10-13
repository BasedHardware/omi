import 'package:flutter/material.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:url_launcher/url_launcher.dart';
import 'package:lottie/lottie.dart';
import 'dart:math';
import 'package:cached_network_image/cached_network_image.dart';

class DiscoveryPage extends StatefulWidget {
  const DiscoveryPage({Key? key}) : super(key: key);

  @override
  _DiscoveryPageState createState() => _DiscoveryPageState();
}

class _DiscoveryPageState extends State<DiscoveryPage> {
  List<ExaResult> searchResults = [];
  bool isLoading = false;
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    generateSearchResults();
  }

  Future<void> generateSearchResults() async {
    setState(() {
      isLoading = true;
    });

    try {
      final homeProvider = Provider.of<HomeProvider>(context, listen: false);
      final messageProvider = Provider.of<MessageProvider>(context, listen: false);
      final memories = await homeProvider.fetchLatestMemories();

      if (memories.isNotEmpty) {
        final recentMemories = memories.join('\n');
        // final prompt = "Based on these recent memories: $recentMemories, generate 5 different search queries that would be interesting for the user.";
        final prompt = """
Based on the following recent memories of the user:
$recentMemories

Generate 5 different search queries that would be interesting for the user to search for.

Return the search queries as a list of strings, without any preamble or additional text:

SEARCH QUERY A
SEARCH QUERY B
SEARCH QUERY C
SEARCH QUERY D
SEARCH QUERY E
...
""";
        
        print("@@@@@@@");
        print(prompt);
        print("@@@@@@@");

        final newMessage = ServerMessage(
          const Uuid().v4(),
          DateTime.now(),
          prompt,
          MessageSender.human,
          MessageType.text,
          null,
          false,
          [],
        );

        await messageProvider.sendMessageToServer(prompt, null);

        final aiResponse = messageProvider.messages.firstWhere(
          (msg) => msg.sender == MessageSender.ai,
          orElse: () => ServerMessage(
            '',
            DateTime.now(),
            'No response from AI',
            MessageSender.ai,
            MessageType.text,
            null,
            false,
            [],
          ),
        );
        final searchPrompts = aiResponse.text.split('\n')
            .where((line) => line.trim().isNotEmpty)
            .map((line) => line.replaceFirst(RegExp(r'^\d+\.\s*'), ''))
            .toList();

        print("***************");
        print(searchPrompts);
        print("***************");

        // Perform Exa.AI search for each prompt
        final results = await Future.wait(
          searchPrompts.map((prompt) => performExaSearch(prompt))
        );

        setState(() {
          searchResults = results.expand((result) => result.results).toList()
            ..shuffle(); // Shuffle results for variety
        });
      } else {
        setState(() {
          searchResults = [];
        });
      }
    } catch (error) {
      Logger.instance.talker.error('Error generating search results: $error');
      setState(() {
        searchResults = [];
      });
    } finally {
      setState(() {
        isLoading = false;
      });
    }
  }

  Future<ExaSearchResult> performExaSearch(String query) async {
    final url = Uri.parse('https://api.exa.ai/search');
    final response = await http.post(
      url,
      headers: {
        'accept': 'application/json',
        'content-type': 'application/json',
        'x-api-key': '33fecc92-af74-4804-81de-f71e88e39b23',
      },
      body: jsonEncode({
        'query': query,
        'type': 'neural',
        'useAutoprompt': true,
        'numResults': 10,
        // 'excludeDomains': ['en.wikipedia.org'],
        'category': 'tweet',
        'startPublishedDate': '2023-01-01',
        'contents': {
          'text': true,
          'summary': {
            'query': "Summarize the following website text so it will be presented to a user in a discovery feed. Make it feel like a tweet"
          }
        }
      }),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      return ExaSearchResult(
        query: query,
        results: (data['results'] as List).map((result) => ExaResult.fromJson(result)).toList(),
      );
    } else {
      throw Exception('Failed to perform Exa.AI search');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Discover'),
        backgroundColor: Colors.blue,
      ),
      body: isLoading
          ? _buildLoadingView()
          : RefreshIndicator(
              onRefresh: generateSearchResults,
              child: searchResults.isEmpty
                  ? Center(child: Text('No results found. Pull to refresh.'))
                  : ListView.builder(
                      itemCount: searchResults.length,
                      itemBuilder: (context, index) {
                        final result = searchResults[index];
                        return DiscoveryCard(result: result);
                      },
                    ),
            ),
    );
  }

  Widget _buildLoadingView() {
    final int randomIndex = _random.nextInt(6) + 1; // Generates a random number between 1 and 6
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
          const SizedBox(height: 20),
          const Text(
            'Crafting Your Personal Discovery Feed',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 10),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 40),
            child: Text(
              'We\'re searching the entire internet to build a custom feed based on your recent memories and interests.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: Colors.grey),
            ),
          ),
        ],
      ),
    );
  }
}

class DiscoveryCard extends StatelessWidget {
  final ExaResult result;

  const DiscoveryCard({Key? key, required this.result}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        onTap: () => _launchURL(result.url),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
              child: CachedNetworkImage(
                imageUrl: result.imageUrl ?? 'https://via.placeholder.com/300x200',
                height: 200,
                width: double.infinity,
                fit: BoxFit.cover,
                placeholder: (context, url) => Container(
                  height: 200,
                  color: Colors.grey[300],
                  child: Center(child: CircularProgressIndicator()),
                ),
                errorWidget: (context, url, error) => Container(
                  height: 200,
                  color: Colors.grey[300],
                  child: Icon(Icons.error),
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    result.title,
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: 8),
                  Text(
                    result.summary,
                    style: TextStyle(fontSize: 14, color: Colors.grey[600]),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: 8),
                  Row(
                    children: [
                      Icon(Icons.link, size: 16, color: Colors.blue),
                      SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          Uri.parse(result.url).host,
                          style: TextStyle(fontSize: 12, color: Colors.blue),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _launchURL(String url) async {
    if (await canLaunch(url)) {
      await launch(url);
    } else {
      print('Could not launch $url');
    }
  }
}

class ExaSearchResult {
  final String query;
  final List<ExaResult> results;

  ExaSearchResult({required this.query, required this.results});
}

class ExaResult {
  final String title;
  final String url;
  final String text;
  final String summary;
  final String? imageUrl;

  ExaResult({
    required this.title,
    required this.url,
    required this.text,
    required this.summary,
    this.imageUrl,
  });

  factory ExaResult.fromJson(Map<String, dynamic> json) {
    return ExaResult(
      title: json['title'],
      url: json['url'],
      text: json['text'],
      summary: json['summary'] ?? 'No summary available.',
      imageUrl: json['image'],
    );
  }
}
