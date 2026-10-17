import unittest
from pydantic import ValidationError

from models.action_item import TaskCreatePayload
from models.candidate import SummaryTaskReference, WorkstreamProposal


class TestCandidateProposalValidation(unittest.TestCase):
    def test_summary_task_reference_valid(self):
        ref = SummaryTaskReference(
            conversation_id="conv-123",
            action_item_index=0,
            expected_description="Review pull request",
        )
        self.assertEqual(ref.expected_description, "Review pull request")

    def test_summary_task_reference_strips_whitespace(self):
        ref = SummaryTaskReference(
            conversation_id="conv-123",
            action_item_index=0,
            expected_description="  Review pull request  ",
        )
        self.assertEqual(ref.expected_description, "Review pull request")

    def test_summary_task_reference_rejects_empty(self):
        with self.assertRaises(ValidationError):
            SummaryTaskReference(
                conversation_id="conv-123",
                action_item_index=0,
                expected_description="",
            )

    def test_summary_task_reference_rejects_whitespace_only(self):
        for invalid in ["   ", "\t", "\n\r  \t"]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    SummaryTaskReference(
                        conversation_id="conv-123",
                        action_item_index=0,
                        expected_description=invalid,
                    )

    def test_workstream_proposal_valid(self):
        proposal = WorkstreamProposal(
            title="Q4 Architecture",
            objective="Migrate microservices to clean architecture",
            anchor_task=TaskCreatePayload(description="Initial audit"),
        )
        self.assertEqual(proposal.title, "Q4 Architecture")
        self.assertEqual(proposal.objective, "Migrate microservices to clean architecture")

    def test_workstream_proposal_strips_whitespace(self):
        proposal = WorkstreamProposal(
            title="  Q4 Architecture  ",
            objective="  Migrate microservices to clean architecture  ",
            anchor_task=TaskCreatePayload(description="Initial audit"),
        )
        self.assertEqual(proposal.title, "Q4 Architecture")
        self.assertEqual(proposal.objective, "Migrate microservices to clean architecture")

    def test_workstream_proposal_rejects_empty_or_whitespace_title(self):
        for invalid in ["", "   ", "\t\n "]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    WorkstreamProposal(
                        title=invalid,
                        objective="Valid objective",
                        anchor_task=TaskCreatePayload(description="Initial audit"),
                    )

    def test_workstream_proposal_rejects_empty_or_whitespace_objective(self):
        for invalid in ["", "   ", "\t\n "]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    WorkstreamProposal(
                        title="Valid title",
                        objective=invalid,
                        anchor_task=TaskCreatePayload(description="Initial audit"),
                    )


if __name__ == "__main__":
    unittest.main()
