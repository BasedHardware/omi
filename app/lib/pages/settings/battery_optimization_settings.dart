import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/battery_optimization_provider.dart';

class BatteryOptimizationSettings extends StatefulWidget {
  const BatteryOptimizationSettings({Key? key}) : super(key: key);

  @override
  State<BatteryOptimizationSettings> createState() => _BatteryOptimizationSettingsState();
}

class _BatteryOptimizationSettingsState extends State<BatteryOptimizationSettings> {
  @override
  void initState() {
    super.initState();
    // Initialize battery optimization provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<BatteryOptimizationProvider>().initialize();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Battery Optimization'),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      body: Consumer<BatteryOptimizationProvider>(
        builder: (context, batteryProvider, child) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildHeader(),
                const SizedBox(height: 24),
                _buildOptimizationLevelCard(batteryProvider),
                const SizedBox(height: 16),
                _buildBatteryStatsCard(batteryProvider),
                const SizedBox(height: 16),
                _buildRecommendationsCard(batteryProvider),
                const SizedBox(height: 16),
                _buildMonitoringCard(batteryProvider),
                const SizedBox(height: 24),
                _buildInfoSection(),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.blue.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.blue.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Icon(
            Icons.battery_saver,
            color: Colors.blue[700],
            size: 32,
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Battery Optimization',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: Colors.blue[700],
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Optimize battery usage for longer device life',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Colors.grey[600],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOptimizationLevelCard(BatteryOptimizationProvider provider) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.tune, color: Colors.orange[600]),
                const SizedBox(width: 8),
                Text(
                  'Optimization Level',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            _buildOptimizationOption(
              provider,
              BatteryOptimizationLevel.none,
              'No Optimization',
              'Best performance, higher battery usage',
              Icons.speed,
              Colors.green,
            ),
            const SizedBox(height: 12),
            _buildOptimizationOption(
              provider,
              BatteryOptimizationLevel.moderate,
              'Moderate',
              'Balanced performance and battery life',
              Icons.balance,
              Colors.orange,
            ),
            const SizedBox(height: 12),
            _buildOptimizationOption(
              provider,
              BatteryOptimizationLevel.aggressive,
              'Aggressive',
              'Maximum battery savings, reduced performance',
              Icons.battery_saver,
              Colors.red,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOptimizationOption(
    BatteryOptimizationProvider provider,
    BatteryOptimizationLevel level,
    String title,
    String description,
    IconData icon,
    Color color,
  ) {
    bool isSelected = provider.optimizationLevel == level;
    
    return InkWell(
      onTap: () {
        switch (level) {
          case BatteryOptimizationLevel.none:
            provider.disableOptimization();
            break;
          case BatteryOptimizationLevel.moderate:
            provider.enableModerateOptimization();
            break;
          case BatteryOptimizationLevel.aggressive:
            provider.enableAggressiveOptimization();
            break;
        }
      },
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isSelected ? color.withOpacity(0.1) : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isSelected ? color : Colors.grey.withOpacity(0.3),
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Row(
          children: [
            Icon(
              icon,
              color: isSelected ? color : Colors.grey[600],
              size: 24,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: isSelected ? color : Colors.black87,
                    ),
                  ),
                  Text(
                    description,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Colors.grey[600],
                    ),
                  ),
                ],
              ),
            ),
            if (isSelected)
              Icon(
                Icons.check_circle,
                color: color,
                size: 20,
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildBatteryStatsCard(BatteryOptimizationProvider provider) {
    final stats = provider.getBatteryUsageStats();
    final drainRate = stats['drainRate'] as double? ?? 0.0;
    final batteryLevel = stats['batteryLevel'] as int? ?? -1;
    
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.analytics, color: Colors.purple[600]),
                const SizedBox(width: 8),
                Text(
                  'Battery Statistics',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: _buildStatItem(
                    'Battery Level',
                    batteryLevel >= 0 ? '$batteryLevel%' : 'Unknown',
                    Icons.battery_full,
                    _getBatteryColor(batteryLevel),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _buildStatItem(
                    'Drain Rate',
                    '${drainRate.toStringAsFixed(1)}%/hour',
                    Icons.trending_down,
                    _getDrainRateColor(drainRate),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey[100],
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Icon(Icons.info_outline, color: Colors.blue[600], size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      stats['statusSummary'] as String? ?? 'Unknown status',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Colors.grey[700],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatItem(String label, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 24),
          const SizedBox(height: 8),
          Text(
            value,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          Text(
            label,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Colors.grey[600],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecommendationsCard(BatteryOptimizationProvider provider) {
    final recommendations = provider.getOptimizationRecommendations();
    
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.lightbulb_outline, color: Colors.amber[600]),
                const SizedBox(width: 8),
                Text(
                  'Recommendations',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            ...recommendations.map((recommendation) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.check_circle_outline,
                    color: Colors.green[600],
                    size: 16,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      recommendation,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Colors.grey[700],
                      ),
                    ),
                  ),
                ],
              ),
            )),
          ],
        ),
      ),
    );
  }

  Widget _buildMonitoringCard(BatteryOptimizationProvider provider) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.monitor, color: Colors.teal[600]),
                const SizedBox(width: 8),
                Text(
                  'Monitoring',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Battery monitoring is ${provider.isMonitoringEnabled ? "enabled" : "disabled"}',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
                Switch(
                  value: provider.isMonitoringEnabled,
                  onChanged: (value) {
                    provider.toggleMonitoring();
                  },
                  activeColor: Colors.teal[600],
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Monitoring helps track battery usage and provides optimization recommendations',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Colors.grey[600],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoSection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.grey[50],
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey[300]!),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.help_outline, color: Colors.grey[600]),
              const SizedBox(width: 8),
              Text(
                'How it works',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _buildInfoItem(
            'Reduces Bluetooth scanning frequency',
            'Scans for devices less frequently to save battery',
          ),
          _buildInfoItem(
            'Optimizes background services',
            'Reduces background processing when not needed',
          ),
          _buildInfoItem(
            'Smart reconnection logic',
            'Limits reconnection attempts to prevent battery drain',
          ),
          _buildInfoItem(
            'Adaptive optimization',
            'Automatically adjusts based on battery level and usage patterns',
          ),
        ],
      ),
    );
  }

  Widget _buildInfoItem(String title, String description) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.arrow_right,
            color: Colors.grey[600],
            size: 16,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: Colors.grey[800],
                  ),
                ),
                Text(
                  description,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.grey[600],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Color _getBatteryColor(int level) {
    if (level < 0) return Colors.grey;
    if (level < 20) return Colors.red;
    if (level < 50) return Colors.orange;
    return Colors.green;
  }

  Color _getDrainRateColor(double rate) {
    if (rate > 15) return Colors.red;
    if (rate > 8) return Colors.orange;
    return Colors.green;
  }
} 