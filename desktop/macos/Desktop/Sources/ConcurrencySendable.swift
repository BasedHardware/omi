import Foundation

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
extension OmiAPI.GoalStatus: @unchecked Sendable {}
