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

        final results = await Future.wait(
          searchPrompts.map((prompt) => performExaSearch(prompt))
        );

        setState(() {
          searchResults = results.expand((result) => result.results).toList()
            ..shuffle();
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
        // 'category': 'tweet',
        'startPublishedDate': '2023-01-01',
        'contents': {
          'text': true,
          'summary': {
            'query': "Summarize the following website into a tweet-like format, making it easy to read for a user scrolling through a discovery feed. DO NOT USE EMOJIS. MAKE IT FEEL PROFESSIONAL, YET AUTHENTIC."
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
        title: Text('Discovery Feed', style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        elevation: 0,
        iconTheme: IconThemeData(color: Colors.black),
      ),
      body: Container(
        color: Colors.white,
        child: isLoading
            ? _buildLoadingView()
            : RefreshIndicator(
                onRefresh: generateSearchResults,
                child: searchResults.isEmpty
                    ? Center(child: Text('No results found. Pull to refresh.', style: TextStyle(color: Colors.black)))
                    : ListView.builder(
                        itemCount: searchResults.length,
                        itemBuilder: (context, index) {
                          final result = searchResults[index];
                          return DiscoveryCard(result: result);
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
            'Crafting Your Personal Discovery Feed',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black),
          ),
          SizedBox(height: 10),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 40),
            child: Text(
              'We\'re searching the entire internet to build a custom feed based on your recent memories and interests.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: Colors.grey[600]),
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
    return Container(
      margin: EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: Colors.grey[200]!, width: 1)),
      ),
      child: InkWell(
        onTap: () => _launchURL(result.url),
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (result.imageUrl != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: CachedNetworkImage(
                    imageUrl: result.imageUrl!,
                    height: 200,
                    width: double.infinity,
                    fit: BoxFit.cover,
                    placeholder: (context, url) => Container(
                      height: 200,
                      color: Colors.grey[200],
                      child: Center(child: CircularProgressIndicator()),
                    ),
                    errorWidget: (context, url, error) => Container(
                      height: 200,
                      color: Colors.grey[200],
                      child: Icon(Icons.error, color: Colors.grey[400]),
                    ),
                  ),
                ),
              SizedBox(height: 12),
              Text(
                result.title,
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.black),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              SizedBox(height: 8),
              Text(
                result.summary,
                style: TextStyle(fontSize: 14, color: Colors.black87),
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
