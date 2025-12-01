import 'package:flutter/material.dart';

class IntegrationsHelpPage extends StatelessWidget {
  const IntegrationsHelpPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        backgroundColor: const Color(0xFF000000),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'How Integrations Work',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              const Text(
                'Connect your tools and chat with them',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              const Text(
                'Two simple steps to get started',
                style: TextStyle(
                  color: Color(0xFF8E8E93),
                  fontSize: 16,
                  fontWeight: FontWeight.w400,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),

              // Step 1
              _buildStepCard(
                stepNumber: 1,
                title: 'Connect to Your Tools',
                description: 'Link your favorite apps and services',
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0xFF4285F4),
                    Color(0xFF34A853),
                  ],
                ),
                apps: [
                  _AppLogo(
                    imagePath: 'assets/integration_app_logos/google-calendar.png',
                    name: 'Calendar',
                    fallbackIcon: Icons.calendar_today,
                    fallbackColor: const Color(0xFF4285F4),
                  ),
                  _AppLogo(
                    imagePath: 'assets/integration_app_logos/notion-logo.png',
                    name: 'Notion',
                    fallbackIcon: Icons.note,
                    fallbackColor: Colors.black,
                  ),
                  _AppLogo(
                    imagePath: null,
                    name: 'Gmail',
                    fallbackIcon: Icons.email,
                    fallbackColor: const Color(0xFFEA4335),
                  ),
                ],
              ),

              const SizedBox(height: 32),

              // Arrow connector with animation hint
              Center(
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            Colors.purple.withOpacity(0.3),
                            Colors.blue.withOpacity(0.3),
                          ],
                        ),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.purple.withOpacity(0.3),
                            blurRadius: 20,
                            spreadRadius: 2,
                          ),
                        ],
                      ),
                      child: const Icon(
                        Icons.arrow_downward_rounded,
                        color: Colors.purple,
                        size: 28,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Then',
                      style: TextStyle(
                        color: Color(0xFF8E8E93),
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 32),

              // Step 2
              _buildStepCard(
                stepNumber: 2,
                title: 'Ask Questions in Chat',
                description: 'Get information or perform actions naturally',
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0xFF9333EA),
                    Color(0xFF7C3AED),
                  ],
                ),
                chatExamples: [
                  _ChatExample(
                    message: 'What meetings do I have today?',
                    type: ChatExampleType.info,
                  ),
                  _ChatExample(
                    message: 'Create a task in Notion',
                    type: ChatExampleType.action,
                  ),
                  _ChatExample(
                    message: 'Show me my emails from yesterday',
                    type: ChatExampleType.info,
                  ),
                ],
              ),

              const SizedBox(height: 40),

              // Footer tip
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      Colors.purple.withOpacity(0.1),
                      Colors.blue.withOpacity(0.1),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: Colors.purple.withOpacity(0.3),
                    width: 1,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.purple.withOpacity(0.2),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(
                        Icons.lightbulb_outline,
                        color: Colors.purple,
                        size: 24,
                      ),
                    ),
                    const SizedBox(width: 16),
                    const Expanded(
                      child: Text(
                        'You can connect multiple tools and ask about any of them in a single conversation.',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStepCard({
    required int stepNumber,
    required String title,
    required String description,
    required LinearGradient gradient,
    List<_AppLogo>? apps,
    List<_ChatExample>? chatExamples,
  }) {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF1F1F25),
            const Color(0xFF2A2A2E),
          ],
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 30,
            offset: const Offset(0, 10),
          ),
          BoxShadow(
            color: gradient.colors.first.withOpacity(0.1),
            blurRadius: 20,
            spreadRadius: -5,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Step header
          Row(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  gradient: gradient,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: gradient.colors.first.withOpacity(0.4),
                      blurRadius: 12,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: Center(
                  child: Text(
                    '$stepNumber',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      description,
                      style: const TextStyle(
                        color: Color(0xFF8E8E93),
                        fontSize: 15,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 28),

          // Content
          if (apps != null) ...[
            // App logos grid
            Wrap(
              spacing: 16,
              runSpacing: 16,
              alignment: WrapAlignment.start,
              children: apps.map((app) => _buildAppLogoCard(app)).toList(),
            ),
          ],

          if (chatExamples != null) ...[
            // Chat examples
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: chatExamples.map((example) => _buildChatBubble(example)).toList(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAppLogoCard(_AppLogo app) {
    return Container(
      width: 100,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF2C2C2E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // App icon
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25),
              borderRadius: BorderRadius.circular(12),
            ),
            child: app.imagePath != null
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Image.asset(
                      app.imagePath!,
                      width: 56,
                      height: 56,
                      fit: BoxFit.contain,
                      errorBuilder: (context, error, stackTrace) {
                        return Container(
                          decoration: BoxDecoration(
                            color: app.fallbackColor.withOpacity(0.2),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(
                            app.fallbackIcon,
                            color: app.fallbackColor,
                            size: 28,
                          ),
                        );
                      },
                    ),
                  )
                : Container(
                    decoration: BoxDecoration(
                      color: app.fallbackColor.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      app.fallbackIcon,
                      color: app.fallbackColor,
                      size: 28,
                    ),
                  ),
          ),
          const SizedBox(height: 12),
          // App name
          Text(
            app.name,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  Widget _buildChatBubble(_ChatExample example) {
    final isInfo = example.type == ChatExampleType.info;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isInfo ? const Color(0xFF2C2C2E) : const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isInfo ? Colors.blue.withOpacity(0.3) : Colors.purple.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: (isInfo ? Colors.blue : Colors.purple).withOpacity(0.2),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(
              isInfo ? Icons.info_outline : Icons.auto_awesome,
              color: isInfo ? Colors.blue : Colors.purple,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isInfo ? 'Get info' : 'Do stuff',
                  style: TextStyle(
                    color: isInfo ? Colors.blue : Colors.purple,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  example.message,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AppLogo {
  final String? imagePath;
  final String name;
  final IconData fallbackIcon;
  final Color fallbackColor;

  _AppLogo({
    this.imagePath,
    required this.name,
    required this.fallbackIcon,
    required this.fallbackColor,
  });
}

class _ChatExample {
  final String message;
  final ChatExampleType type;

  _ChatExample({
    required this.message,
    required this.type,
  });
}

enum ChatExampleType {
  info,
  action,
}
