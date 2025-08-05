import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class ActionItemFilterSheet extends StatelessWidget {
  const ActionItemFilterSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        return Container(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.85,
          ),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                const Color(0xFF1A1A1A),
                const Color(0xFF0F0F0F).withOpacity(0.95),
              ],
            ),
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(24),
              topRight: Radius.circular(24),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.3),
                blurRadius: 20,
                offset: const Offset(0, -8),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                margin: const EdgeInsets.only(top: 16),
                width: 48,
                height: 4,
                decoration: BoxDecoration(
                  color: const Color(0xFF888888),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Filter by Date',
                          style: TextStyle(
                            color: Color(0xFFFFFFFF),
                            fontSize: 24,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.5,
                          ),
                        ),
                        SizedBox(height: 4),
                        Text(
                          'Choose a time period to filter your action items',
                          style: TextStyle(
                            color: Color(0xFFB0B0B0),
                            fontSize: 12,
                            fontWeight: FontWeight.w400,
                          ),
                        ),
                      ],
                    ),
                    if (provider.selectedStartDate != null || provider.selectedEndDate != null)
                      Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () {
                            HapticFeedback.lightImpact();
                            provider.clearDateFilter();
                            MixpanelManager().actionItemsDateFilterCleared();
                            Navigator.pop(context);
                          },
                          borderRadius: BorderRadius.circular(20),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            decoration: BoxDecoration(
                              color: const Color(0xFF8B5CF6).withOpacity(0.1),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: const Color(0xFF8B5CF6).withOpacity(0.3),
                                width: 1,
                              ),
                            ),
                            child: const Text(
                              'Clear All',
                              style: TextStyle(
                                color: Color(0xFF8B5CF6),
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              
              // Quick Filters
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 3,
                          height: 16,
                          decoration: BoxDecoration(
                            color: const Color(0xFF8B5CF6),
                            borderRadius: BorderRadius.circular(2),
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Text(
                          'Quick Filters',
                          style: TextStyle(
                            color: Color(0xFFE5E5E5),
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            letterSpacing: -0.2,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    _buildQuickFilters(provider, context),
                  ],
                ),
              ),
              
              const SizedBox(height: 32),
              
              // Custom Date Range
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 3,
                          height: 16,
                          decoration: BoxDecoration(
                            color: const Color(0xFF8B5CF6),
                            borderRadius: BorderRadius.circular(2),
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Text(
                          'Custom Range',
                          style: TextStyle(
                            color: Color(0xFFE5E5E5),
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            letterSpacing: -0.2,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    _buildDateRange(provider, context),
                  ],
                ),
              ),
              
              const SizedBox(height: 40),
            ],
          ),
        );
      },
    );
  }

  Widget _buildQuickFilters(ActionItemsProvider provider, BuildContext context) {
    final quickFilters = [
      {'label': 'Today', 'icon': Icons.today_rounded, 'action': () => _applyQuickFilter(provider, context, 'Today')},
      {'label': 'Yesterday', 'icon': Icons.history_rounded, 'action': () => _applyQuickFilter(provider, context, 'Yesterday')},
      {'label': 'This Week', 'icon': Icons.date_range_rounded, 'action': () => _applyQuickFilter(provider, context, 'This Week')},
      {'label': 'Last Week', 'icon': Icons.skip_previous_rounded, 'action': () => _applyQuickFilter(provider, context, 'Last Week')},
      {'label': 'This Month', 'icon': Icons.calendar_month_rounded, 'action': () => _applyQuickFilter(provider, context, 'This Month')},
      {'label': 'Last Month', 'icon': Icons.arrow_back_rounded, 'action': () => _applyQuickFilter(provider, context, 'Last Month')},
    ];

    return Column(
      children: [
        // First row
        Row(
          children: quickFilters.take(3).map((filter) => Expanded(
            child: Padding(
              padding: EdgeInsets.only(right: filter == quickFilters[2] ? 0 : 8),
              child: _buildQuickFilterCard(
                filter['label'] as String,
                filter['icon'] as IconData,
                filter['action'] as VoidCallback,
                _isFilterSelected(provider, filter['label'] as String),
              ),
            ),
          )).toList(),
        ),
        const SizedBox(height: 8),
        // Second row
        Row(
          children: quickFilters.skip(3).map((filter) => Expanded(
            child: Padding(
              padding: EdgeInsets.only(right: filter == quickFilters[5] ? 0 : 8),
              child: _buildQuickFilterCard(
                filter['label'] as String,
                filter['icon'] as IconData,
                filter['action'] as VoidCallback,
                _isFilterSelected(provider, filter['label'] as String),
              ),
            ),
          )).toList(),
        ),
      ],
    );
  }

  Widget _buildQuickFilterCard(String label, IconData icon, VoidCallback onTap, bool isSelected) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        borderRadius: BorderRadius.circular(16),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeInOut,
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
          decoration: BoxDecoration(
            gradient: isSelected ? const LinearGradient(
              colors: [Color(0xFF8B5CF6), Color(0xFFA855F7)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ) : null,
            color: isSelected ? null : const Color(0xFF252525),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isSelected 
                ? const Color(0xFF8B5CF6).withOpacity(0.5)
                : const Color(0xFF2A2A2A),
              width: 1,
            ),
            boxShadow: isSelected ? [
              BoxShadow(
                color: const Color(0xFF8B5CF6).withOpacity(0.3),
                blurRadius: 8,
                offset: const Offset(0, 4),
              ),
            ] : [
              BoxShadow(
                color: Colors.black.withOpacity(0.1),
                blurRadius: 4,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                color: isSelected ? Colors.white : const Color(0xFFB0B0B0),
                size: 20,
              ),
              const SizedBox(height: 8),
              Text(
                label,
                style: TextStyle(
                  color: isSelected ? Colors.white : const Color(0xFFE5E5E5),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -0.1,
                ),
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _applyQuickFilter(ActionItemsProvider provider, BuildContext context, String filterType) {
    final now = DateTime.now();
    DateTime startDate, endDate;
    
    switch (filterType) {
      case 'Today':
        startDate = DateTime(now.year, now.month, now.day);
        endDate = DateTime(now.year, now.month, now.day, 23, 59, 59);
        break;
      case 'Yesterday':
        final yesterday = now.subtract(const Duration(days: 1));
        startDate = DateTime(yesterday.year, yesterday.month, yesterday.day);
        endDate = DateTime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59);
        break;
      case 'This Week':
        final startOfWeek = now.subtract(Duration(days: now.weekday - 1));
        startDate = DateTime(startOfWeek.year, startOfWeek.month, startOfWeek.day);
        endDate = now;
        break;
      case 'Last Week':
        final startOfThisWeek = now.subtract(Duration(days: now.weekday - 1));
        final startOfLastWeek = startOfThisWeek.subtract(const Duration(days: 7));
        final endOfLastWeek = startOfThisWeek.subtract(const Duration(days: 1));
        startDate = DateTime(startOfLastWeek.year, startOfLastWeek.month, startOfLastWeek.day);
        endDate = DateTime(endOfLastWeek.year, endOfLastWeek.month, endOfLastWeek.day, 23, 59, 59);
        break;
      case 'This Month':
        startDate = DateTime(now.year, now.month, 1);
        endDate = now;
        break;
      case 'Last Month':
        startDate = DateTime(now.year, now.month - 1, 1);
        endDate = DateTime(now.year, now.month, 0, 23, 59, 59);
        break;
      default:
        return;
    }
    
    provider.setDateFilter(startDate, endDate);
    MixpanelManager().actionItemsDateFilterApplied(filterType);
    Navigator.pop(context);
  }

  bool _isFilterSelected(ActionItemsProvider provider, String filterType) {
    final startDate = provider.selectedStartDate;
    final endDate = provider.selectedEndDate;
    
    if (startDate == null || endDate == null) return false;
    
    final now = DateTime.now();
    
    switch (filterType) {
      case 'Today':
        final todayStart = DateTime(now.year, now.month, now.day);
        final todayEnd = DateTime(now.year, now.month, now.day, 23, 59, 59);
        return _isSameDay(startDate, todayStart) && _isSameDay(endDate, todayEnd);
      case 'Yesterday':
        final yesterday = now.subtract(const Duration(days: 1));
        final yesterdayStart = DateTime(yesterday.year, yesterday.month, yesterday.day);
        final yesterdayEnd = DateTime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59);
        return _isSameDay(startDate, yesterdayStart) && _isSameDay(endDate, yesterdayEnd);
      case 'This Week':
        final startOfWeek = now.subtract(Duration(days: now.weekday - 1));
        final startOfWeekFormatted = DateTime(startOfWeek.year, startOfWeek.month, startOfWeek.day);
        return _isSameDay(startDate, startOfWeekFormatted) && _isSameMinute(endDate, now);
      case 'This Month':
        final startOfMonth = DateTime(now.year, now.month, 1);
        return _isSameDay(startDate, startOfMonth) && _isSameMinute(endDate, now);
      default:
        return false;
    }
  }

  bool _isSameMinute(DateTime date1, DateTime date2) {
    return date1.year == date2.year && 
           date1.month == date2.month && 
           date1.day == date2.day &&
           date1.hour == date2.hour &&
           date1.minute == date2.minute;
  }

  Widget _buildDateRange(ActionItemsProvider provider, BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _buildDateSelector(
                'Start Date',
                provider.selectedStartDate,
                Icons.event_rounded,
                (date) async {
                  await provider.setDateFilter(date, provider.selectedEndDate);
                  MixpanelManager().actionItemsDateFilterApplied('Custom Date Range');
                },
                context,
              ),
            ),
            const SizedBox(width: 12),
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: const Color(0xFF8B5CF6).withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(
                Icons.arrow_forward_rounded,
                size: 14,
                color: Color(0xFF8B5CF6),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildDateSelector(
                'End Date',
                provider.selectedEndDate,
                Icons.event_available_rounded,
                (date) async {
                  await provider.setDateFilter(provider.selectedStartDate, date);
                  MixpanelManager().actionItemsDateFilterApplied('Custom Date Range');
                },
                context,
              ),
            ),
          ],
        ),
        if (provider.selectedStartDate != null || provider.selectedEndDate != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0xFF8B5CF6).withOpacity(0.05),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: const Color(0xFF8B5CF6).withOpacity(0.2),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.info_outline_rounded,
                  size: 16,
                  color: const Color(0xFF8B5CF6).withOpacity(0.8),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _getCustomRangeDescription(provider.selectedStartDate, provider.selectedEndDate),
                    style: TextStyle(
                      color: const Color(0xFF8B5CF6).withOpacity(0.9),
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildDateSelector(String label, DateTime? selectedDate, IconData icon, Function(DateTime?) onDateSelected, BuildContext context) {
    final hasDate = selectedDate != null;
    
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () async {
          HapticFeedback.mediumImpact();
          await _showCupertinoDatePicker(
            context: context,
            initialDate: selectedDate ?? DateTime.now(),
            onDateSelected: onDateSelected,
          );
        },
        borderRadius: BorderRadius.circular(16),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: hasDate 
              ? const Color(0xFF8B5CF6).withOpacity(0.05)
              : const Color(0xFF252525),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: hasDate 
                ? const Color(0xFF8B5CF6).withOpacity(0.3)
                : const Color(0xFF2A2A2A),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.1),
                blurRadius: 4,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    icon,
                    size: 16,
                    color: hasDate 
                      ? const Color(0xFF8B5CF6)
                      : const Color(0xFFB0B0B0),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    label,
                    style: TextStyle(
                      color: hasDate 
                        ? const Color(0xFF8B5CF6)
                        : const Color(0xFFB0B0B0),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      letterSpacing: -0.1,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                selectedDate != null
                    ? _formatDateForDisplay(selectedDate)
                    : 'Select Date',
                style: TextStyle(
                  color: selectedDate != null 
                    ? const Color(0xFFFFFFFF)
                    : const Color(0xFF888888),
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -0.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _getCustomRangeDescription(DateTime? startDate, DateTime? endDate) {
    if (startDate != null && endDate != null) {
      final daysDiff = endDate.difference(startDate).inDays;
      if (daysDiff == 0) {
        return 'Filtering for ${_formatDateForDisplay(startDate)}';
      }
      return 'Filtering ${daysDiff + 1} days from ${_formatDateForDisplay(startDate)} to ${_formatDateForDisplay(endDate)}';
    } else if (startDate != null) {
      return 'Filtering from ${_formatDateForDisplay(startDate)} onwards';
    } else if (endDate != null) {
      return 'Filtering until ${_formatDateForDisplay(endDate)}';
    }
    return 'Custom date range selected';
  }

  String _formatDateForDisplay(DateTime date) {
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${months[date.month - 1]} ${date.day}, ${date.year}';
  }

  bool _isSameDay(DateTime date1, DateTime date2) {
    return date1.year == date2.year && 
           date1.month == date2.month && 
           date1.day == date2.day;
  }

  Future<void> _showCupertinoDatePicker({
    required BuildContext context,
    required DateTime initialDate,
    required Function(DateTime?) onDateSelected,
  }) async {
    DateTime selectedDate = initialDate;

    await showCupertinoModalPopup<void>(
      context: context,
      builder: (BuildContext context) {
        return Material(
          child: Container(
          height: 300,
          padding: const EdgeInsets.only(top: 6.0),
          margin: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom,
          ),
          decoration: const BoxDecoration(
            color: Color(0xFF1A1A1A),
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(20),
            ),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              children: [
                // Modern header with Cancel and Done buttons
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
                  decoration: const BoxDecoration(
                    color: Color(0xFF1A1A1A),
                    borderRadius: BorderRadius.only(
                      topLeft: Radius.circular(20),
                      topRight: Radius.circular(20),
                    ),
                    border: Border(
                      bottom: BorderSide(
                        color: Color(0xFF2A2A2A),
                        width: 1,
                      ),
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          HapticFeedback.lightImpact();
                          Navigator.of(context).pop();
                        },
                        child: const Text(
                          'Cancel',
                          style: TextStyle(
                            color: Color(0xFFE5E5E5),
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                      const Text(
                        'Select Date',
                        style: TextStyle(
                          color: Color(0xFFFFFFFF),
                          fontSize: 17,
                          fontWeight: FontWeight.w600,
                          letterSpacing: -0.2,
                        ),
                      ),
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          HapticFeedback.mediumImpact();
                          Navigator.of(context).pop();
                          onDateSelected(selectedDate);
                          MixpanelManager().actionItemsDateFilterApplied('iOS Date Picker');
                        },
                        child: const Text(
                          'Done',
                          style: TextStyle(
                            color: Color(0xFF8B5CF6),
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                // iOS-style date picker
                Expanded(
                  child: Container(
                    color: const Color(0xFF1A1A1A),
                    child: CupertinoDatePicker(
                      mode: CupertinoDatePickerMode.date,
                      initialDateTime: initialDate,
                      minimumDate: DateTime(2020),
                      maximumDate: DateTime.now().add(const Duration(days: 365)),
                      onDateTimeChanged: (DateTime newDate) {
                        selectedDate = newDate;
                      },
                      // Modern styling for dark theme
                      backgroundColor: const Color(0xFF1A1A1A),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        );
      
      },
    );
  }

  static void show(BuildContext context) {
    HapticFeedback.mediumImpact();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => const ActionItemFilterSheet(),
    );
  }
}