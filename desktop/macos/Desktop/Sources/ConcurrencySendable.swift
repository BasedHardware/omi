import Foundation

// KeyPath is an immutable reference type that is safe to share across concurrency
// domains. The standard library does not declare it Sendable, which blocks
// AttributedString attribute-scope key paths under strict concurrency.
extension KeyPath: @retroactive @unchecked Sendable {}

// Strict-concurrency bridge: the types below are wire DTOs (OpenAPI-generated) or
// immutable domain value records that are decoded once and then passed across actor
// boundaries as values. They are marked `@unchecked Sendable` because the compiler
// cannot always prove Sendability through their nested/`Any` fields, even though they
// are effectively immutable after decoding.

extension TaskActionItem: @unchecked Sendable {}
extension ToolChatResult: @unchecked Sendable {}
extension ServerConversation: @unchecked Sendable {}

extension OmiAPI.EvidenceRef: @unchecked Sendable {}
extension OmiAPI.TaskWorkflowControl: @unchecked Sendable {}
extension OmiAPI.CandidateResolutionReceipt: @unchecked Sendable {}
extension OmiAPI.CandidateRecord: @unchecked Sendable {}
extension OmiAPI.InterventionCreate: @unchecked Sendable {}
extension OmiAPI.InterventionRecord: @unchecked Sendable {}
extension OmiAPI.FeedbackCreate: @unchecked Sendable {}
extension OmiAPI.FeedbackRecord: @unchecked Sendable {}
extension OmiAPI.OutcomeCreate: @unchecked Sendable {}
extension OmiAPI.OutcomeRecord: @unchecked Sendable {}
extension OmiAPI.WhatMattersNowProjection: @unchecked Sendable {}
extension OmiAPI.NormalizedContextSnapshot: @unchecked Sendable {}
extension OmiAPI.SnapshotReceipt: @unchecked Sendable {}
extension OmiAPI.EvaluationRequest: @unchecked Sendable {}
extension OmiAPI.GoalResponse: @unchecked Sendable {}
extension OmiAPI.GoalDetailProjection: @unchecked Sendable {}
extension OmiAPI.WorkIntentReceipt: @unchecked Sendable {}
extension OmiAPI.ArtifactDescriptor: @unchecked Sendable {}
extension OmiAPI.ContinuationCheckpoint: @unchecked Sendable {}
extension OmiAPI.WorkstreamDetailProjection: @unchecked Sendable {}
extension AssistantSettingsResponse: @unchecked Sendable {}
extension OmiAPI.RecommendationSubjectKind: @unchecked Sendable {}
extension OmiAPI.GoalStatus: @unchecked Sendable {}
extension DashboardRecommendation: @unchecked Sendable {}
extension DashboardRecommendationDestination: @unchecked Sendable {}
extension OmiAPI.FeedbackSubjectKind: @unchecked Sendable {}
extension OmiAPI.ArtifactDescriptorCreate: @unchecked Sendable {}
extension OmiAPI.ContinuationCheckpointUpsert: @unchecked Sendable {}
extension GeminiRequest.GenerationConfig.ResponseSchema: @unchecked Sendable {}
extension GeminiRequest.GenerationConfig.ResponseSchema.Property: @unchecked Sendable {}
extension OmiAPI.TaskIntelligenceFeedbackReason: @unchecked Sendable {}
