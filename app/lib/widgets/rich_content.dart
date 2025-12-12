import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/widgets/extensions/string.dart';

class RichContent extends StatelessWidget {
  final String content;
  final TextStyle? baseStyle;

  const RichContent({
    super.key,
    required this.content,
    this.baseStyle,
  });

  static const _cardColors = {
    'highlight': Color(0xFF3B82F6),
    'success': Color(0xFF10B981),
    'warning': Color(0xFFF59E0B),
    'error': Color(0xFFEF4444),
    'info': Color(0xFF8B5CF6),
  };

  @override
  Widget build(BuildContext context) {
    final decodedContent = content;
    final style = baseStyle ??
        const TextStyle(
          color: Colors.white,
          fontSize: 15,
          height: 1.4,
        );

    final components = _parseContent(decodedContent);

    if (components.length == 1 && components.first is _TextComponent) {
      return _buildMarkdown(decodedContent, style);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: components.map((c) => _buildComponent(c, style)).toList(),
    );
  }

  List<_Component> _parseContent(String content) {
    final components = <_Component>[];
    final lines = content.split('\n');
    final buffer = StringBuffer();
    _Component? currentComponent;
    String? currentCardType;

    for (final line in lines) {
      // Bar chart
      if (line.startsWith(':::chart')) {
        if (buffer.isNotEmpty) {
          components.add(_TextComponent(buffer.toString().trim()));
          buffer.clear();
        }
        currentComponent = _BarChartComponent();
      }
      // Pie/donut chart
      else if (line.startsWith(':::pie') || line.startsWith(':::donut')) {
        if (buffer.isNotEmpty) {
          components.add(_TextComponent(buffer.toString().trim()));
          buffer.clear();
        }
        final isDonut = line.startsWith(':::donut');
        final titleMatch = RegExp(r':::(pie|donut)\s*"([^"]*)"').firstMatch(line);
        final title = titleMatch?.group(2) ?? '';
        currentComponent = _PieChartComponent(isDonut: isDonut, title: title);
      }
      // Card container
      else if (line.startsWith(':::card')) {
        if (buffer.isNotEmpty) {
          components.add(_TextComponent(buffer.toString().trim()));
          buffer.clear();
        }
        final typeMatch = RegExp(r':::card\s+(\w+)').firstMatch(line);
        currentCardType = typeMatch?.group(1) ?? 'highlight';
        currentComponent = _CardComponent(type: currentCardType);
      }
      // Progress bar
      else if (line.startsWith(':::progress')) {
        if (buffer.isNotEmpty) {
          components.add(_TextComponent(buffer.toString().trim()));
          buffer.clear();
        }
        final match = RegExp(r':::progress\s+(\d+)%?\s*(.*)').firstMatch(line);
        if (match != null) {
          final value = int.tryParse(match.group(1) ?? '0') ?? 0;
          final label = match.group(2)?.trim() ?? '';
          components.add(_ProgressComponent(value, label));
        }
      }
      // Metric
      else if (line.startsWith(':::metric')) {
        if (buffer.isNotEmpty) {
          components.add(_TextComponent(buffer.toString().trim()));
          buffer.clear();
        }
        final match = RegExp(r':::metric\s+"([^"]+)"\s+"([^"]+)"').firstMatch(line);
        if (match != null) {
          components.add(_MetricComponent(match.group(1) ?? '', match.group(2) ?? ''));
        }
      }
      // Tags
      else if (line.startsWith(':::tags')) {
        if (buffer.isNotEmpty) {
          components.add(_TextComponent(buffer.toString().trim()));
          buffer.clear();
        }
        final tagsStr = line.replaceFirst(':::tags', '').trim();
        final tags = tagsStr.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();
        if (tags.isNotEmpty) {
          components.add(_TagsComponent(tags));
        }
      }
      // End of block
      else if (line == ':::' && currentComponent != null) {
        if (currentComponent is _BarChartComponent) {
          currentComponent.data = buffer.toString().trim();
          components.add(currentComponent);
        } else if (currentComponent is _PieChartComponent) {
          currentComponent.data = buffer.toString().trim();
          components.add(currentComponent);
        } else if (currentComponent is _CardComponent) {
          currentComponent.content = buffer.toString().trim();
          components.add(currentComponent);
        }
        buffer.clear();
        currentComponent = null;
        currentCardType = null;
      }
      // Inside a block
      else if (currentComponent != null) {
        buffer.writeln(line);
      }
      // Regular text
      else {
        buffer.writeln(line);
      }
    }

    if (buffer.isNotEmpty) {
      components.add(_TextComponent(buffer.toString().trim()));
    }

    return components.isEmpty ? [_TextComponent(content)] : components;
  }

  Widget _buildComponent(_Component component, TextStyle style) {
    if (component is _TextComponent) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: _buildMarkdown(component.text, style),
      );
    } else if (component is _BarChartComponent) {
      return _buildBarChart(component, style);
    } else if (component is _PieChartComponent) {
      return _buildPieChart(component, style);
    } else if (component is _CardComponent) {
      return _buildCard(component, style);
    } else if (component is _ProgressComponent) {
      return _buildProgress(component, style);
    } else if (component is _MetricComponent) {
      return _buildMetric(component, style);
    } else if (component is _TagsComponent) {
      return _buildTags(component, style);
    }
    return const SizedBox.shrink();
  }

  Widget _buildMarkdown(String text, TextStyle style) {
    return MarkdownBody(
      data: text,
      selectable: false,
      shrinkWrap: true,
      softLineBreak: true,
      onTapLink: (text, href, title) async {
        if (href != null) {
          final uri = Uri.parse(href);
          await launchUrl(uri, mode: LaunchMode.externalApplication);
        }
      },
      styleSheet: MarkdownStyleSheet(
        p: style,
        strong: style.copyWith(fontWeight: FontWeight.w600),
        em: style.copyWith(fontStyle: FontStyle.italic),
        listBullet: style.copyWith(color: Colors.white70),
        tableHead: style.copyWith(fontWeight: FontWeight.w600),
        tableBody: style,
        tableBorder: TableBorder.all(color: Colors.white24, width: 0.5),
        tableColumnWidth: const IntrinsicColumnWidth(),
        tableCellsPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        tableHeadAlign: TextAlign.left,
        blockSpacing: 8,
        listIndent: 16,
        listBulletPadding: const EdgeInsets.only(right: 4),
        a: style.copyWith(color: Colors.blueAccent, decoration: TextDecoration.underline),
      ),
    );
  }

  Widget _buildCard(_CardComponent component, TextStyle style) {
    final color = _cardColors[component.type] ?? _cardColors['highlight']!;

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.3), width: 1),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 4,
            height: 40,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildMarkdown(component.content, style),
          ),
        ],
      ),
    );
  }

  Widget _buildPieChart(_PieChartComponent component, TextStyle style) {
    final segments = _parsePieData(component.data);
    if (segments.isEmpty) return const SizedBox.shrink();

    final total = segments.fold<double>(0, (sum, s) => sum + s.value);

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (component.title.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                component.title,
                style: style.copyWith(fontWeight: FontWeight.w600),
              ),
            ),
          Row(
            children: [
              SizedBox(
                width: 100,
                height: 100,
                child: CustomPaint(
                  painter: _PieChartPainter(
                    segments: segments,
                    total: total,
                    isDonut: component.isDonut,
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: segments.map((segment) {
                    final percent = total > 0 ? (segment.value / total * 100).round() : 0;
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(
                        children: [
                          Container(
                            width: 10,
                            height: 10,
                            decoration: BoxDecoration(
                              color: segment.color,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              segment.label,
                              style: style.copyWith(fontSize: 12),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Text(
                            '$percent%',
                            style: style.copyWith(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: Colors.white70,
                            ),
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  List<_PieSegment> _parsePieData(String data) {
    final segments = <_PieSegment>[];
    final defaultColors = [
      const Color(0xFF8B5CF6),
      const Color(0xFF10B981),
      const Color(0xFFF59E0B),
      const Color(0xFF3B82F6),
      const Color(0xFFEF4444),
      const Color(0xFFEC4899),
    ];

    int colorIndex = 0;
    for (final line in data.split('\n')) {
      final parts = line.split(':');
      if (parts.length >= 2) {
        final label = parts[0].trim();
        final rest = parts.sublist(1).join(':').trim();
        final valuePart = rest.split(' ').first;
        final value = double.tryParse(valuePart.replaceAll(RegExp(r'[^0-9.]'), '')) ?? 0;

        Color color = defaultColors[colorIndex % defaultColors.length];
        final colorMatch = RegExp(r'#([A-Fa-f0-9]{6})').firstMatch(rest);
        if (colorMatch != null) {
          color = Color(int.parse('FF${colorMatch.group(1)}', radix: 16));
        }

        if (label.isNotEmpty && value > 0) {
          segments.add(_PieSegment(label, value, color));
          colorIndex++;
        }
      }
    }
    return segments;
  }

  Widget _buildBarChart(_BarChartComponent component, TextStyle style) {
    final entries = _parseBarChartData(component.data);
    if (entries.isEmpty) return const SizedBox.shrink();

    final maxValue = entries.map((e) => e.value).reduce((a, b) => a > b ? a : b);

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: entries.map((entry) {
          final percent = maxValue > 0 ? entry.value / maxValue : 0.0;
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                SizedBox(
                  width: 80,
                  child: Text(
                    entry.label,
                    style: style.copyWith(fontSize: 12),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Stack(
                    children: [
                      Container(
                        height: 20,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      FractionallySizedBox(
                        widthFactor: percent,
                        child: Container(
                          height: 20,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: entry.color != null
                                  ? [entry.color!, entry.color!.withValues(alpha: 0.7)]
                                  : [Colors.blueAccent, Colors.purpleAccent],
                            ),
                            borderRadius: BorderRadius.circular(4),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  entry.value.toStringAsFixed(entry.value == entry.value.roundToDouble() ? 0 : 1),
                  style: style.copyWith(fontSize: 12, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  List<_BarChartEntry> _parseBarChartData(String data) {
    final entries = <_BarChartEntry>[];
    for (final line in data.split('\n')) {
      final parts = line.split(':');
      if (parts.length >= 2) {
        final label = parts[0].trim();
        final rest = parts.sublist(1).join(':').trim();
        final value = double.tryParse(rest.split(' ').first.replaceAll(RegExp(r'[^0-9.]'), '')) ?? 0;

        Color? color;
        final colorMatch = RegExp(r'#([A-Fa-f0-9]{6})').firstMatch(rest);
        if (colorMatch != null) {
          color = Color(int.parse('FF${colorMatch.group(1)}', radix: 16));
        }

        if (label.isNotEmpty) {
          entries.add(_BarChartEntry(label, value, color));
        }
      }
    }
    return entries;
  }

  Widget _buildProgress(_ProgressComponent component, TextStyle style) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (component.label.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(component.label, style: style.copyWith(fontSize: 12)),
            ),
          Stack(
            children: [
              Container(
                height: 8,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              FractionallySizedBox(
                widthFactor: component.value / 100,
                child: Container(
                  height: 8,
                  decoration: BoxDecoration(
                    color: _getProgressColor(component.value),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              '${component.value}%',
              style: style.copyWith(fontSize: 11, color: Colors.white70),
            ),
          ),
        ],
      ),
    );
  }

  Color _getProgressColor(int value) {
    if (value >= 80) return Colors.green;
    if (value >= 50) return Colors.orange;
    return Colors.redAccent;
  }

  Widget _buildMetric(_MetricComponent component, TextStyle style) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            component.value,
            style: style.copyWith(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.blueAccent),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(component.label, style: style.copyWith(fontSize: 13, color: Colors.white70)),
          ),
        ],
      ),
    );
  }

  Widget _buildTags(_TagsComponent component, TextStyle style) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: component.tags.map((tag) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.blueAccent.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.blueAccent.withValues(alpha: 0.4)),
            ),
            child: Text(
              tag,
              style: style.copyWith(fontSize: 12, color: Colors.blueAccent),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _PieChartPainter extends CustomPainter {
  final List<_PieSegment> segments;
  final double total;
  final bool isDonut;

  _PieChartPainter({
    required this.segments,
    required this.total,
    required this.isDonut,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;
    final donutWidth = radius * 0.35;

    double startAngle = -math.pi / 2;

    for (final segment in segments) {
      final sweepAngle = (segment.value / total) * 2 * math.pi;
      final paint = Paint()
        ..color = segment.color
        ..style = PaintingStyle.fill;

      if (isDonut) {
        final path = Path()
          ..moveTo(
            center.dx + (radius - donutWidth) * math.cos(startAngle),
            center.dy + (radius - donutWidth) * math.sin(startAngle),
          )
          ..arcTo(
            Rect.fromCircle(center: center, radius: radius),
            startAngle,
            sweepAngle,
            false,
          )
          ..arcTo(
            Rect.fromCircle(center: center, radius: radius - donutWidth),
            startAngle + sweepAngle,
            -sweepAngle,
            false,
          )
          ..close();
        canvas.drawPath(path, paint);
      } else {
        canvas.drawArc(
          Rect.fromCircle(center: center, radius: radius),
          startAngle,
          sweepAngle,
          true,
          paint,
        );
      }

      startAngle += sweepAngle;
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

abstract class _Component {}

class _TextComponent extends _Component {
  final String text;
  _TextComponent(this.text);
}

class _BarChartComponent extends _Component {
  String data = '';
}

class _PieChartComponent extends _Component {
  final bool isDonut;
  final String title;
  String data = '';
  _PieChartComponent({required this.isDonut, required this.title});
}

class _CardComponent extends _Component {
  final String type;
  String content = '';
  _CardComponent({required this.type});
}

class _ProgressComponent extends _Component {
  final int value;
  final String label;
  _ProgressComponent(this.value, this.label);
}

class _MetricComponent extends _Component {
  final String value;
  final String label;
  _MetricComponent(this.value, this.label);
}

class _TagsComponent extends _Component {
  final List<String> tags;
  _TagsComponent(this.tags);
}

class _BarChartEntry {
  final String label;
  final double value;
  final Color? color;
  _BarChartEntry(this.label, this.value, this.color);
}

class _PieSegment {
  final String label;
  final double value;
  final Color color;
  _PieSegment(this.label, this.value, this.color);
}
