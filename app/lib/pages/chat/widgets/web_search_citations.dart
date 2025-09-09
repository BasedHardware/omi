import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/gen/fonts.gen.dart';
import 'package:url_launcher/url_launcher.dart';

class WebSearchCitations extends StatelessWidget {
  final List<WebSearchCitation> citations;
  final bool isDesktop;

  const WebSearchCitations({
    super.key,
    required this.citations,
    this.isDesktop = false,
  });

  @override
  Widget build(BuildContext context) {
    if (citations.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: EdgeInsets.only(
        top: isDesktop ? 12 : 8,
        left: isDesktop ? 16 : 12,
        right: isDesktop ? 16 : 12,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25), // Match message background color
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.1),
          width: 1,
        ),
      ),
      child: ExpansionTile(
        leading: null,
        title: Text(
          'Sources (${citations.length})',
          style: TextStyle(
            fontFamily: FontFamily.sFProDisplay,
            fontSize: isDesktop ? 14 : 13,
            fontWeight: FontWeight.w600,
            color: Colors.deepPurple.shade400, // Deep purple accent
          ),
        ),
        iconColor: Colors.deepPurple.shade400, // Deep purple accent
        collapsedIconColor: Colors.deepPurple.shade400, // Deep purple accent
        shape: const Border(),
        childrenPadding: EdgeInsets.fromLTRB(
          isDesktop ? 16 : 12,
          0,
          isDesktop ? 16 : 12,
          isDesktop ? 16 : 12,
        ),
        children: citations.map((citation) => _buildCitationTile(citation)).toList(),
      ),
    );
  }

  Widget _buildCitationTile(WebSearchCitation citation) {
    return Padding(
      padding: EdgeInsets.only(bottom: isDesktop ? 12 : 8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _launchUrl(citation.url),
        child: Container(
          padding: EdgeInsets.all(isDesktop ? 12 : 10),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.1),
              width: 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.deepPurple.shade400,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      '[${citation.index}]',
                      style: TextStyle(
                        fontFamily: FontFamily.sFProDisplay,
                        fontSize: isDesktop ? 11 : 10,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      citation.title,
                      style: TextStyle(
                        fontFamily: FontFamily.sFProDisplay,
                        fontSize: isDesktop ? 14 : 13,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Icon(
                    FontAwesomeIcons.arrowUpRightFromSquare,
                    size: isDesktop ? 12 : 10,
                    color: Colors.deepPurple.shade400,
                  ),
                ],
              ),
              if (citation.snippet.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  citation.snippet,
                  style: TextStyle(
                    fontFamily: FontFamily.sFProDisplay,
                    fontSize: isDesktop ? 12 : 11,
                    color: Colors.white70,
                    height: 1.4,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              const SizedBox(height: 4),
              Text(
                citation.url,
                style: TextStyle(
                  fontFamily: FontFamily.sFProDisplay,
                  fontSize: isDesktop ? 11 : 10,
                  color: Colors.blue.shade400,
                  decoration: TextDecoration.underline,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _launchUrl(String url) async {
    try {
      final uri = Uri.parse(url);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    } catch (e) {
      debugPrint('Error launching URL: $e');
    }
  }
}
