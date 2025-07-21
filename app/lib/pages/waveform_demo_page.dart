import 'package:flutter/material.dart';
import 'package:omi/widgets/gradient_waveform.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class WaveformDemoPage extends StatelessWidget {
  const WaveformDemoPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      appBar: AppBar(
        title: const Text('Gradient Waveform Demo'),
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        foregroundColor: ResponsiveHelper.textPrimary,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Static Waveforms Section
            _buildSection(
              'Static Waveforms',
              [
                _buildDemoItem(
                  'Default (4 bars)',
                  const GradientWaveform(),
                ),
                _buildDemoItem(
                  'Custom Heights',
                  const GradientWaveform(
                    barHeights: [0.3, 0.8, 1.0, 0.5],
                    width: 100,
                    height: 50,
                  ),
                ),
                _buildDemoItem(
                  'More Bars',
                  const GradientWaveform(
                    barCount: 6,
                    barHeights: [0.4, 0.7, 1.0, 0.6, 0.8, 0.3],
                    width: 120,
                    height: 60,
                    barWidth: 10,
                    spacing: 6,
                  ),
                ),
                _buildDemoItem(
                  'Thin Bars',
                  const GradientWaveform(
                    barWidth: 4,
                    spacing: 2,
                    width: 60,
                    height: 30,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 40),

            // Animated Waveforms Section
            _buildSection(
              'Animated Waveforms',
              [
                _buildDemoItem(
                  'Default Animation',
                  const GradientWaveform(
                    animated: true,
                    width: 100,
                    height: 50,
                  ),
                ),
                _buildDemoItem(
                  'Fast Animation',
                  const GradientWaveform(
                    animated: true,
                    animationDuration: Duration(milliseconds: 600),
                    width: 100,
                    height: 50,
                  ),
                ),
                _buildDemoItem(
                  'Slow Animation',
                  const GradientWaveform(
                    animated: true,
                    animationDuration: Duration(milliseconds: 2000),
                    width: 100,
                    height: 50,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 40),

            // Custom Colors Section
            _buildSection(
              'Custom Colors',
              [
                _buildDemoItem(
                  'Blue Gradient',
                  const GradientWaveform(
                    gradientColors: [
                      Color(0xFF3B82F6),
                      Color(0xFF60A5FA),
                      Color(0xFF93C5FD),
                    ],
                  ),
                ),
                _buildDemoItem(
                  'Green Gradient',
                  const GradientWaveform(
                    gradientColors: [
                      Color(0xFF10B981),
                      Color(0xFF34D399),
                      Color(0xFF6EE7B7),
                    ],
                  ),
                ),
                _buildDemoItem(
                  'Red Gradient',
                  const GradientWaveform(
                    gradientColors: [
                      Color(0xFFEF4444),
                      Color(0xFFF87171),
                      Color(0xFFFCA5A5),
                    ],
                  ),
                ),
              ],
            ),

            const SizedBox(height: 40),

            // In Context Examples
            _buildSection(
              'In Context Examples',
              [
                _buildContextExample(
                  'Recording Indicator',
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: ResponsiveHelper.backgroundTertiary,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.mic,
                              color: ResponsiveHelper.purplePrimary,
                              size: 16,
                            ),
                            SizedBox(width: 8),
                            GradientWaveform(
                              animated: true,
                              width: 60,
                              height: 20,
                              barWidth: 3,
                              spacing: 2,
                            ),
                            SizedBox(width: 8),
                            Text(
                              '00:15',
                              style: TextStyle(
                                color: ResponsiveHelper.textSecondary,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                _buildContextExample(
                  'Audio Message',
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundSecondary,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.play_arrow,
                          color: ResponsiveHelper.purplePrimary,
                        ),
                        SizedBox(width: 12),
                        GradientWaveform(
                          barHeights: [0.3, 0.6, 0.9, 0.4, 0.7, 0.2],
                          barCount: 6,
                          width: 120,
                          height: 30,
                        ),
                        SizedBox(width: 12),
                        Text(
                          '0:24',
                          style: TextStyle(
                            color: ResponsiveHelper.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSection(String title, List<Widget> children) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.bold,
            color: ResponsiveHelper.textPrimary,
          ),
        ),
        const SizedBox(height: 20),
        ...children,
      ],
    );
  }

  Widget _buildDemoItem(String label, Widget waveform) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w500,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary,
                width: 1,
              ),
            ),
            child: Center(child: waveform),
          ),
        ],
      ),
    );
  }

  Widget _buildContextExample(String label, Widget example) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w500,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary,
                width: 1,
              ),
            ),
            child: example,
          ),
        ],
      ),
    );
  }
}
