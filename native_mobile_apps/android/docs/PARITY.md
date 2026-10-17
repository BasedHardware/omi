# Parity: omi-native iOS -> Android

One row per Swift file with views (features + app shell), rebuilt from the code by
`Tools/parity/parity_table.py`: ✅ every view has its Kotlin composable, every text key the file uses
is used on Android and those Kotlin files carry no `TODO(visual-stub)`; 🟡 says what is missing;
➖ is iOS only by nature; ❌ has no Kotlin view.
Built from omi-native `e24f187` and omi-android `dfd5879`: 142 rows, 140 ✅, 0 🟡, 2 ➖, 0 ❌.

| Swift file | LOC | Views | Kotlin | Status |
|---|---|---|---|---|
| `App/HomeChrome.swift` | 148 | DevicePill, OmiBottomBar | `app/.../shell/HomeChrome.kt` | ✅ |
| `App/MainTabView.swift` | 325 | MainTabView | `app/.../shell/MainTabView.kt` | ✅ |
| `App/RecordWithSheet.swift` | 72 | RecordWithSheet | `app/.../shell/RecordWithSheet.kt` | ✅ |
| `App/RootView.swift` | 49 | RootView | `app/.../RootView.kt` | ✅ |
| `App/System/SiriTipSheet.swift` | 57 | SiriTipSheet | none | ➖ iOS only: the Siri tip; Android has no Siri |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatAppPicker.swift` | 51 | ChatAppPicker | `features/.../features/agent/ChatAppPicker.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatAttachments.swift` | 194 | AttachmentButton, AttachmentStrip | `features/.../features/agent/ChatAttachments.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatBlockCards.swift` | 55 | ChatBlocks | `features/.../features/agent/ChatBlockCards.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatBlockChrome.swift` | 162 | ChatBlockFallbacks, ChatBlockCard, ChatBlockEyebrow, ChatBlockNotice, ChatBlockLinkCard, ChatBlockAction | `features/.../features/agent/ChatBlockChrome.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatBlockKinds.swift` | 296 | DiscoveryBlockCard, QuestionBlockCard, AgentRunBlockCard, MemoryReviewBlockCard | `features/.../features/agent/ChatBlockKinds.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatBlockLinkCards.swift` | 87 | MemoryBlockCard, ConversationBlockCard | `features/.../features/agent/ChatBlockLinkCards.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatBlockTaskCards.swift` | 127 | TaskBlockCard, GoalBlockCard | `features/.../features/agent/ChatBlockTaskCards.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatBubbles.swift` | 101 | OmiAvatar, ChatCardStack | `features/.../features/agent/ChatBubbles.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatCards.swift` | 205 | AnswerCards, ConnectCard, TaskChangeCard, CitationChips | `features/.../features/agent/ChatCards.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatChrome.swift` | 184 | ChatMenu, OfflineHint | `features/.../features/agent/ChatChrome.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatComposer.swift` | 216 | ChatComposer, ComposerBackdrop, ComposerMic | `features/.../features/agent/ChatComposer.kt`, `features/.../features/agent/ChatScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatDaySummaryCard.swift` | 49 | DaySummaryCard | `features/.../features/agent/ChatDaySummaryCard.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatMedia.swift` | 171 | ChartCard, MessageFiles, FilePreviewSheet, AttachmentThumbnail, DocumentChip | `features/.../features/agent/ChatMedia.kt`, `features/.../features/agent/FilePreviewSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatParts.swift` | 400 | MessageBubble, QuoteLine, TypingBubble, DayDivider, StepList | `features/.../features/agent/ChatParts.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatRunning.swift` | 158 | RunningStrip, RunningRow, RunOutcomeRow | `features/.../features/agent/ChatRunning.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatScreen+Tab.swift` | 331 | SearchMatchRow | `features/.../features/agent/ChatScreenTab.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/ChatScreen.swift` | 383 | ChatScreen | `features/.../features/agent/ChatScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/HandOverSheet.swift` | 259 | HandOverSheet, WorkingCard, HandOverKicker | `features/.../features/agent/HandOverSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AgentFeature/MessageActions.swift` | 76 | AnswerMenu | `features/.../features/agent/MessageActions.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AuthFeature/ConsentScreen.swift` | 46 | ConsentScreen | `features/.../features/auth/ConsentScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/AuthFeature/SignInScreen.swift` | 175 | SignInScreen, PhotoReel | `features/.../features/auth/SignInScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/AudioPlayerBar.swift` | 173 | AudioPlayerBar | `features/.../features/conversations/AudioPlayerBar.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/CaptureRecordingsSheet.swift` | 172 | CaptureRecordingsSheet, TestPromptSheet | `features/.../features/conversations/CaptureRecordingsSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/ConversationCalendar.swift` | 221 | LinkedEventCard, CalendarEventSheet, LinkEventSheet, AddToCalendarView | `features/.../features/conversations/ConversationCalendar.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/ConversationDetailScreen.swift` | 338 | ConversationDetailScreen | `features/.../features/conversations/ConversationDetailScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/ConversationMedia.swift` | 285 | SummaryExtrasSection, ParticipantsRow, ProcessingStrip, ConversationPhotosGrid, ScreenshotsStrip, RemoteImage, ImageViewer | `features/.../features/conversations/ConversationMedia.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/ConversationSummaryView.swift` | 377 | ConversationSummaryView, DetailActions, MoreDetailsSection, DetailGroup, ConversationInsightsView | `features/.../features/conversations/ConversationSummaryView.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/EdgeSwipeBack.swift` | 56 | EdgeSwipeBackFirst | none | ➖ iOS only: lets the edge swipe win over the pager; Android's system back gesture never competes |
| `Packages/OmiFeatures/Sources/ConversationsFeature/NameSpeakerSheet.swift` | 101 | NameSpeakerSheet, VoiceMatchesSheet | `features/.../features/conversations/NameSpeakerSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/SearchFilters.swift` | 129 | SearchFilterMenu, FilterChip, DateRangeSheet | `features/.../features/conversations/SearchFilters.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/SearchScreen.swift` | 248 | SearchScreen, MemoryResult | `features/.../features/conversations/SearchScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/SummaryFeedbackRow.swift` | 165 | SummaryFeedbackRow, FeedbackReasonsSheet | `features/.../features/conversations/SummaryFeedbackRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/SummaryTemplateSheet.swift` | 239 | SummaryTemplateSheet, AppIcon, CreateTemplateForm | `features/.../features/conversations/SummaryTemplateSheet.kt`, `features/.../features/settings/AppsBrowserScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/ConversationsFeature/TranscriptView.swift` | 295 | TranscriptView, EditLineSheet | `features/.../features/conversations/TranscriptView.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/DeviceControlsSection.swift` | 97 | DeviceControlsSection | `features/.../features/device/DeviceControlsSection.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/DeviceDiagnosticsScreen.swift` | 283 | DeviceDiagnosticsScreen | `features/.../features/device/DeviceDiagnosticsScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/DeviceInfoScreen.swift` | 51 | DeviceInfoScreen | `features/.../features/device/DeviceInfoScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/DeviceQuickButtons.swift` | 174 | DeviceQuickButtons, QuickButton, LightSheet | `features/.../features/device/DeviceQuickButtons.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/DeviceRecordingsRow.swift` | 103 | DeviceRecordingsRow, DeviceRecordingsScreen | `features/.../features/device/DeviceRecordingsRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/DeviceScreen.swift` | 315 | DeviceScreen, BatteryBadge, DeviceRow | `features/.../features/device/DeviceScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/FirmwareUpdateRow.swift` | 142 | FirmwareUpdateRow | `features/.../features/device/FirmwareUpdateRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/DeviceFeature/OmiHelpScreen.swift` | 62 | OmiHelpScreen | `features/.../features/device/OmiHelpScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/MemoryFeature/MemoryCard.swift` | 79 | MemoryCard | `features/.../features/memory/MemoryCard.kt` | ✅ |
| `Packages/OmiFeatures/Sources/MemoryFeature/MemoryReview.swift` | 230 | MemoryReviewEntry, MemoryReviewSheet | `features/.../features/memory/MemoryReview.kt` | ✅ |
| `Packages/OmiFeatures/Sources/MemoryFeature/MemoryScreen.swift` | 229 | MemoryScreen | `features/.../features/memory/MemoryScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/MemoryFeature/MemorySheets.swift` | 175 | EditMemorySheet, NewMemorySheet, MemoryGraphScreen | `features/.../features/memory/MemorySheets.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/ConversationRow.swift` | 134 | ConversationRow, EmojiTile | `features/.../features/components/ConversationRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/ConversationToasts.swift` | 64 | UndoDeleteToast, OmiToast | `features/.../features/components/ConversationToasts.kt`, `features/.../features/components/OmiToast.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/DecisionCard.swift` | 137 | DecisionCard | `features/.../features/components/DecisionCard.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/DeviceLive.swift` | 47 | DeviceHero | `features/.../features/device/DeviceLive.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/EntityAvatar.swift` | 225 | EntityAvatar, BrandLogo, NameMonogram, CategoryEmojiTile | `design/.../design/EntityAvatar.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/FolderSheets.swift` | 162 | MoveToFolderSheet, FoldersSheet, FolderLabel | `features/.../features/components/FolderSheets.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/GoalViews.swift` | 193 | GoalRow, GoalFormSheet, GoalsScreen | `features/.../features/components/GoalViews.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/GroupedList.swift` | 86 | OmiGroupedList, OmiFlatList, OmiSectionLabel | `features/.../features/components/GroupedList.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/KnowledgeGraphView.swift` | 129 | KnowledgeGraphView | `features/.../features/components/KnowledgeGraphView.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/MarkdownBlocks.swift` | 230 | MarkdownBlocks, TableBlock, DraftCard | `features/.../features/components/MarkdownBlocks.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/OmiAsks.swift` | 189 | OmiAsksCard, OmiAsksEditSheet | `features/.../features/components/OmiAsks.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/OmiMeterBar.swift` | 25 | OmiMeterBar | `features/.../features/settings/SettingsHubViews.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/OmiStatus.swift` | 54 | OmiStatusDot | `features/.../features/settings/SettingsHubViews.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/PendingRecordingRow.swift` | 91 | PendingRecordingRow | `features/.../features/components/PendingRecordingRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/PlaceViews.swift` | 57 | ConversationPlaceCard | `features/.../features/components/PlaceViews.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/SpeakerNamePicker.swift` | 139 | SpeakerNamePicker | `features/.../features/components/SpeakerNamePicker.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/TaskRow.swift` | 180 | TaskRow, AgentStatusChip, HandOverButton | `app/.../system/widgets/OmiWidgets.kt`, `features/.../features/components/AgentWording.kt`, `features/.../features/components/TaskRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OmiComponents/TaskToasts.swift` | 85 | TaskToasts, GoalUndoToast | `features/.../features/components/TaskToasts.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/AboutYouSteps.swift` | 191 | NameStep, LanguageStep, LanguageRow, SourceStep | `features/.../features/onboarding/AboutYouSteps.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/IntroDemos.swift` | 331 | ListenDemo, TranscriptLine, MemoryDemo, VoicesDemo, ForYouDemo, HandOverDemo, LockScreenActivity | `features/.../features/onboarding/IntroDemos.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/IntroSteps.swift` | 303 | ReadyFlow, ReadyStep, ReadyMark, IntroTourScreen, IntroCard, PageDots | `features/.../features/onboarding/IntroSteps.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/OmiButtonSteps.swift` | 185 | AskOmiStep, QuestionCard, AnswerCard, DoublePressStep | `features/.../features/onboarding/OmiButtonSteps.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/OmiButtonTutorialScreen.swift` | 101 | OmiButtonAndWatchSteps, OmiButtonTutorialScreen | `features/.../features/onboarding/OmiButtonTutorialScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/OmiSteps.swift` | 296 | HasOmiStep, OmiChoiceCard, PairStep, LightsStep, PermissionsStep | `features/.../features/onboarding/OmiSteps.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/OnboardingComponents.swift` | 300 | OnboardingProgress, OnboardingHeader, OnboardingLayout, OnboardingButton, ChoiceRow, RowList, PendantImage | `features/.../features/onboarding/OnboardingComponents.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/OnboardingScreen.swift` | 160 | OnboardingScreen | `features/.../features/onboarding/OnboardingScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/SetupStep.swift` | 128 | SetupStep | `features/.../features/onboarding/SetupStep.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/VoiceReplyStep.swift` | 152 | VoiceReplyStep, SpeakingBars | `features/.../features/onboarding/VoiceReplyStep.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/VoiceSentenceViews.swift` | 128 | SentenceSteps, GapSentenceText, ListeningLine | `features/.../features/onboarding/VoiceSentenceViews.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/VoiceSteps.swift` | 304 | HelloStep, VoiceStep, VoiceProfileScreen, Prompting, VoiceSaved, VoiceLiveCard, LevelBars | `features/.../features/onboarding/VoiceSentenceViews.kt`, `features/.../features/onboarding/VoiceSteps.kt` | ✅ |
| `Packages/OmiFeatures/Sources/OnboardingFeature/WatchStep.swift` | 101 | WatchStep | `features/.../features/onboarding/WatchStep.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AccountScreen.swift` | 90 | AccountScreen | `features/.../features/settings/AccountScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/ActiveCallScreen.swift` | 258 | ActiveCallScreen, CallControl, CallTranscriptView, DTMFSheet | `features/.../features/settings/ActiveCallScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AdvancedTranscriptionScreen.swift` | 135 | AdvancedTranscriptionScreen | `features/.../features/settings/AdvancedTranscriptionScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AppDetailScreen.swift` | 208 | AppDetailScreen | `features/.../features/settings/AppDetailScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AppLinkScreen.swift` | 42 | AppLinkScreen | `features/.../features/settings/AppDetailScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AppReviewsSection.swift` | 105 | AppReviewsSection, Stars | `features/.../features/settings/AppDetailScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AppearanceScreen.swift` | 141 | AppearanceScreen, ModeChoice, MiniScreen | `features/.../features/settings/AppearanceScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AppleHealthScreen.swift` | 124 | AppleHealthScreen, AppleHealthIcon | `features/.../features/settings/AppleHealthScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AppsBrowserScreen.swift` | 209 | AppsBrowserScreen, KindChips, AppRow, AppIcon | `features/.../features/conversations/SummaryTemplateSheet.kt`, `features/.../features/settings/AppsBrowserScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/AssistantScreen.swift` | 169 | AssistantScreen, VoicePickerScreen | `features/.../features/settings/AssistantScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/CapabilitiesScreen.swift` | 203 | CapabilitiesScreen, IntegrationRow, RemindersRow, IntegrationLogo | `features/.../features/settings/CapabilitiesScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/CaptureSettingsScreen.swift` | 192 | CaptureSettingsScreen, ListeningAdvancedScreen, VocabularyScreen, PhoneRecordingsSection | `features/.../features/settings/CaptureSettingsScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/ConnectAIScreen.swift` | 197 | ConnectAIScreen | `features/.../features/settings/ConnectAIScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/DeveloperKeysSection.swift` | 150 | DeveloperKeysSection, CreatedKeySheet | `features/.../features/settings/DeveloperScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/DeveloperScreen.swift` | 253 | DeveloperScreen, WebhooksScreen, DeveloperKeysScreen, DeveloperLogsScreen, WebhookRow, DebugLogScreen | `features/.../features/settings/DeveloperScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/ImportScreen.swift` | 130 | ImportScreen, ImportJobRow | `features/.../features/settings/ImportScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/KnowledgeSummaryScreen.swift` | 126 | KnowledgeSummaryScreen | `features/.../features/settings/KnowledgeSummaryScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/NotificationsScreen.swift` | 78 | NotificationsScreen | `features/.../features/settings/NotificationsScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PeopleCleanUpScreen.swift` | 107 | PeopleCleanUpScreen, IgnoredVoicesScreen | `features/.../features/settings/PeopleCleanUpScreen.kt`, `features/.../features/settings/PeopleScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PeopleScreen.swift` | 177 | PeopleScreen, PersonRow | `features/.../features/settings/PeopleScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PersonDetailScreen.swift` | 195 | PersonDetailScreen | `features/.../features/settings/PersonDetailScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PhoneAndHelpScreens.swift` | 63 | HelpScreen | `features/.../features/settings/PhoneAndHelpScreens.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PhoneCallsScreen.swift` | 207 | PhoneScreen, PhoneIntroSections | `features/.../features/settings/PhoneCallsScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PhoneDialerScreen.swift` | 214 | PhoneDialerScreen, PhoneKeypad | `features/.../features/settings/PhoneDialerScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PhoneNumberSetupScreen.swift` | 179 | PhoneNumberSetupScreen, PhoneVerifyScreen, CountryPicker | `features/.../features/settings/PhoneNumberSetupScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PlanPicker.swift` | 265 | PlanPickerSection, PlanCard | `features/.../features/settings/PlanPicker.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PlanUsageScreen.swift` | 281 | PlanUsageScreen, PlanSummarySection, NoticeRow, MetersSection | `features/.../features/settings/PlanUsageScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/PrivacyScreen.swift` | 190 | PrivacyScreen, AppAccessScreen, ExportDataRow | `features/.../features/settings/PrivacyScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/SettingsComponents.swift` | 111 | SettingsIcon, SettingsRowLabel, Monogram, SettingsHero | `features/.../features/settings/SettingsComponents.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/SettingsHubViews.swift` | 229 | SettingsProfileHeader, SettingsHubTiles, HubTile, HubGlyph | `features/.../features/settings/SettingsHubViews.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/SettingsScreen.swift` | 378 | SettingsScreen, SettingsSearchField | `features/.../features/settings/SettingsScreen.kt`, `features/.../features/settings/SettingsSearch.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/SettingsSearch.swift` | 109 | SettingsSearchResults | `features/.../features/settings/SettingsSearch.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/SubscriptionAndReferral.swift` | 176 | CancelSubscriptionSheet, ReferralScreen | `features/.../features/settings/SubscriptionAndReferral.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/SupportChatRow.swift` | 34 | SupportChatRow | `features/.../features/settings/SupportChatRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/TaskAppSettingsScreen.swift` | 94 | TaskAppSettingsScreen | `features/.../features/settings/CapabilitiesScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/UsageScreens.swift` | 165 | ActivitySection, FairUseSection | `features/.../features/settings/UsageScreens.kt` | ✅ |
| `Packages/OmiFeatures/Sources/SettingsFeature/WhatsNew.swift` | 166 | AnnouncementSheet, ChangesSection, WhatsNewScreen | `features/.../features/settings/WhatsNew.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TasksFeature/DayTasksScreen.swift` | 87 | DayTasksScreen | `features/.../features/tasks/DayTasksScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TasksFeature/NewTaskSheet.swift` | 28 | NewTaskSheet, TaskDetailSheet | `features/.../features/tasks/NewTaskSheet.kt`, `features/.../features/tasks/TaskFormSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TasksFeature/SharedTasksSheet.swift` | 77 | SharedTasksSheet | `features/.../features/tasks/SharedTasksSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TasksFeature/TaskFormSheet.swift` | 206 | TaskFormSheet | `features/.../features/tasks/TaskFormSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TasksFeature/TaskMenus.swift` | 122 | ExportMenu, TaskContextMenu, TasksHeaderMenu | `features/.../features/tasks/TaskMenus.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TasksFeature/TaskSelectionBar.swift` | 70 | TaskSelectionBar | `features/.../features/tasks/TaskSelectionBar.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TasksFeature/TasksScreen.swift` | 225 | TasksScreen | `features/.../features/tasks/TasksScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/CaptureRecoveryBanner.swift` | 114 | CaptureRecoveryBanner | `features/.../features/today/CaptureRecoveryBanner.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/ConnectSuggestion.swift` | 96 | ConnectSuggestionCard | `features/.../features/today/ConnectSuggestion.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/ConversationList.swift` | 257 | ConversationList | `features/.../features/today/ConversationList.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/ConversationListExtras.swift` | 192 | LockedRowCover, DisplayOptionsMenu, DayPickerSheet, DayConversationsScreen | `features/.../features/today/ConversationListExtras.kt`, `features/.../features/today/DayConversationsScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/ConversationMapScreen.swift` | 106 | ConversationMapScreen | `features/.../features/today/ConversationMapScreen.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/DailyRecaps.swift` | 179 | RecapRow, RecapScreen | `features/.../features/today/DailyRecaps.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/ForYouRow.swift` | 152 | ForYouRow | `features/.../features/onboarding/IntroDemos.kt`, `features/.../features/today/ForYouRow.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/GoalsCard.swift` | 78 | GoalsCard | `features/.../features/today/GoalsCard.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/LiveTranscriptSheet.swift` | 162 | LiveTranscriptSheet | `features/.../features/today/LiveTranscriptSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/NeedsYouSection.swift` | 314 | NeedsYouSection | `features/.../features/today/NeedsYouSection.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/NeedsYouTaskCard.swift` | 203 | LaterUndoToast | `features/.../features/today/TaskLaterUndo.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/SelectionBar.swift` | 90 | SelectionBar | `features/.../features/today/SelectionBar.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/SpeakerPromptCard.swift` | 145 | SpeakerPromptSheet, SpeakerPromptCard | `features/.../features/today/SpeakerPromptCard.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/TaskCardView.swift` | 205 | TaskCardView, SpinningRing | `features/.../features/components/TaskCardModern.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/TidyUpSheet.swift` | 109 | TidyUpSheet | `features/.../features/today/TidyUpSheet.kt` | ✅ |
| `Packages/OmiFeatures/Sources/TodayFeature/TodayScreen.swift` | 231 | TodayScreen, LiveBar | `features/.../features/today/LiveBar.kt`, `features/.../features/today/TodayScreen.kt` | ✅ |

## Beyond the table

- Extensions: iOS Live Activities map to promoted ongoing notifications (phone, Omi and watch
  recordings; Omi's runs with the current step), the battery widget to a Glance widget. Not ported:
  the animated waveform (a notification cannot animate), the Siri tip and Apple Reminders.
- Check it again: `python3 Tools/parity/parity_table.py ../omi-native . <ios-sha> <android-sha> Tools/parity/parity_config.json > docs/PARITY.md`.
  Every alias and iOS-only entry in `parity_config.json` was checked by hand against both codes.
