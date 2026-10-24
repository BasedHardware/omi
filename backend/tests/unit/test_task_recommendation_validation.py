import unittest
from datetime import datetime, timezone
from pydantic import ValidationError

from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.task_recommendation import (
    NormalizedContextSnapshot,
    OpenLoopSnapshot,
    Recommendation,
    RecommendationSubjectKind,
    FeedbackSubjectKind,
    WhatMattersNowProjection,
)


class TestTaskRecommendationValidation(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.later = datetime(2026, 10, 14, 13, 0, 0, tzinfo=timezone.utc)
        self.earlier = datetime(2026, 10, 14, 11, 0, 0, tzinfo=timezone.utc)
        self.evidence_ref = EvidenceRef(
            kind=EvidenceKind.conversation,
            id="conv_123",
            scope=EvidenceScope.canonical,
        )

    def test_recommendation_valid(self):
        rec = Recommendation(
            intervention_id="int_1",
            output_version="out_1",
            subject_kind=RecommendationSubjectKind.task,
            subject_id="task_1",
            feedback_subject_kind=FeedbackSubjectKind.task,
            feedback_subject_id="task_1",
            headline=" Review proposal ",
            why_now=" Deadline approaching ",
            recommended_action=" Approve PR ",
            evidence_preview="Evidence snippet",
            evidence_refs=[self.evidence_ref],
            dedupe_key="dedupe_1",
            expires_at=self.later,
        )
        self.assertEqual(rec.headline, "Review proposal")
        self.assertEqual(rec.why_now, "Deadline approaching")
        self.assertEqual(rec.recommended_action, "Approve PR")

    def test_recommendation_blank_headline_rejected(self):
        with self.assertRaises(ValidationError):
            Recommendation(
                intervention_id="int_1",
                output_version="out_1",
                subject_kind=RecommendationSubjectKind.task,
                subject_id="task_1",
                feedback_subject_kind=FeedbackSubjectKind.task,
                feedback_subject_id="task_1",
                headline="   ",
                why_now="Deadline approaching",
                recommended_action="Approve PR",
                evidence_preview="Evidence snippet",
                evidence_refs=[self.evidence_ref],
                dedupe_key="dedupe_1",
                expires_at=self.later,
            )

    def test_recommendation_blank_why_now_rejected(self):
        with self.assertRaises(ValidationError):
            Recommendation(
                intervention_id="int_1",
                output_version="out_1",
                subject_kind=RecommendationSubjectKind.task,
                subject_id="task_1",
                feedback_subject_kind=FeedbackSubjectKind.task,
                feedback_subject_id="task_1",
                headline="Review proposal",
                why_now="   ",
                recommended_action="Approve PR",
                evidence_preview="Evidence snippet",
                evidence_refs=[self.evidence_ref],
                dedupe_key="dedupe_1",
                expires_at=self.later,
            )

    def test_recommendation_blank_recommended_action_rejected(self):
        with self.assertRaises(ValidationError):
            Recommendation(
                intervention_id="int_1",
                output_version="out_1",
                subject_kind=RecommendationSubjectKind.task,
                subject_id="task_1",
                feedback_subject_kind=FeedbackSubjectKind.task,
                feedback_subject_id="task_1",
                headline="Review proposal",
                why_now="Deadline approaching",
                recommended_action="   ",
                evidence_preview="Evidence snippet",
                evidence_refs=[self.evidence_ref],
                dedupe_key="dedupe_1",
                expires_at=self.later,
            )

    def test_what_matters_now_projection_valid_expiry(self):
        proj = WhatMattersNowProjection(
            evaluation_id="eval_1",
            output_version="out_1",
            material_version="mat_1",
            generated_at=self.now,
            expires_at=self.later,
            recommendations=[],
        )
        self.assertEqual(proj.expires_at, self.later)

    def test_what_matters_now_projection_invalid_expiry_rejected(self):
        with self.assertRaises(ValidationError):
            WhatMattersNowProjection(
                evaluation_id="eval_1",
                output_version="out_1",
                material_version="mat_1",
                generated_at=self.now,
                expires_at=self.earlier,
                recommendations=[],
            )

    def test_normalized_context_snapshot_valid_expiry(self):
        snapshot = NormalizedContextSnapshot(
            device_id="dev_1",
            snapshot_id="snap_1",
            generated_at=self.now,
            expires_at=self.later,
        )
        self.assertEqual(snapshot.expires_at, self.later)

    def test_normalized_context_snapshot_invalid_expiry_rejected(self):
        with self.assertRaises(ValidationError):
            NormalizedContextSnapshot(
                device_id="dev_1",
                snapshot_id="snap_1",
                generated_at=self.now,
                expires_at=self.earlier,
            )

    def test_open_loop_snapshot_valid_expiry(self):
        snapshot = OpenLoopSnapshot(
            device_id="dev_1",
            owner="owner_1",
            runtime_id="rt_1",
            workstream_id="ws_1",
            conversation_id="conv_1",
            context_packet_version="pkt_1",
            generated_at=self.now,
            expires_at=self.later,
        )
        self.assertEqual(snapshot.expires_at, self.later)

    def test_open_loop_snapshot_invalid_expiry_rejected(self):
        with self.assertRaises(ValidationError):
            OpenLoopSnapshot(
                device_id="dev_1",
                owner="owner_1",
                runtime_id="rt_1",
                workstream_id="ws_1",
                conversation_id="conv_1",
                context_packet_version="pkt_1",
                generated_at=self.now,
                expires_at=self.earlier,
            )


if __name__ == "__main__":
    unittest.main()
