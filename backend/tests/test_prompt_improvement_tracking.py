"""
Tests for the prompt improvement tracking module.
"""

import unittest
from datetime import datetime, timedelta
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
import uuid

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from utils.prompt_evaluation import EvaluationResult
from utils.prompt_improvement import PromptVersion
from utils.prompt_improvement_tracking import (
    get_prompt_version_history,
    get_evaluation_history,
    calculate_performance_metrics,
    generate_performance_report,
    plot_performance_over_time,
    plot_criteria_comparison,
    export_report_to_json,
)


class TestPromptImprovementTracking(unittest.TestCase):
    """Test cases for the prompt improvement tracking module."""

    def setUp(self):
        """Set up test fixtures."""
        # Create sample prompt versions
        self.prompt_type = "test_prompt"
        self.versions = []

        for i in range(3):
            version_id = str(uuid.uuid4())
            timestamp = datetime.now() - timedelta(days=10-i*3)

            version = PromptVersion(
                id=version_id,
                timestamp=timestamp,
                prompt_type=self.prompt_type,
                prompt=f"This is version {i+1} of the test prompt.",
                description=f"Version {i+1} with improvements",
                active=(i == 2),  # Only the latest version is active
                evaluation_results=[]
            )

            self.versions.append(version)

        # Create sample evaluation results
        self.evaluation_results = []

        for i, version in enumerate(self.versions):
            for j in range(2):
                result_id = str(uuid.uuid4())

                # Create scores that improve over time
                omi_score = 7.0 + i * 0.5 + j * 0.1
                competitor_score = 7.5 + j * 0.1

                # Create criteria scores
                criteria = ["relevance", "accuracy", "helpfulness", "naturalness",
                           "personalization", "conciseness", "creativity"]

                omi_criteria = {}
                competitor_criteria = {}

                for criterion in criteria:
                    omi_criteria[criterion] = 7.0 + i * 0.4 + j * 0.1
                    competitor_criteria[criterion] = 7.5 + j * 0.1

                # Create the evaluation result
                result = EvaluationResult(
                    id=result_id,
                    timestamp=version.timestamp + timedelta(hours=j),
                    prompt_version_id=version.id,
                    conversation=[],
                    omi_response="Sample Omi response",
                    competitor_responses={
                        "competitor1": "Sample competitor 1 response",
                        "competitor2": "Sample competitor 2 response"
                    },
                    scores={
                        "omi": omi_criteria,
                        "competitor1": competitor_criteria,
                        "competitor2": competitor_criteria
                    },
                    overall_scores={
                        "omi": omi_score,
                        "competitor1": competitor_score,
                        "competitor2": competitor_score
                    },
                    improvement_suggestions=[
                        f"Suggestion 1 for version {i+1}",
                        f"Suggestion 2 for version {i+1}"
                    ]
                )

                self.evaluation_results.append(result)
                version.evaluation_results.append(result_id)

    @patch('database.prompt_improvement.get_prompt_versions')
    def test_get_prompt_version_history(self, mock_get_prompt_versions):
        """Test getting prompt version history."""
        mock_get_prompt_versions.return_value = self.versions

        # Call the function
        versions = get_prompt_version_history(self.prompt_type)

        # Verify the results
        self.assertEqual(len(versions), 3)
        self.assertEqual(versions[0].description, "Version 1 with improvements")
        self.assertEqual(versions[2].description, "Version 3 with improvements")

        # Verify the mock was called correctly
        mock_get_prompt_versions.assert_called_once_with(
            prompt_type=self.prompt_type,
            include_inactive=True,
            sort_by="timestamp",
            sort_order="asc",
        )

    @patch('database.prompt_improvement.get_prompt_versions')
    @patch('database.prompt_improvement.get_evaluation_result')
    def test_get_evaluation_history(self, mock_get_evaluation_result, mock_get_prompt_versions):
        """Test getting evaluation history."""
        mock_get_prompt_versions.return_value = self.versions

        # Set up the mock to return evaluation results
        def get_result_side_effect(result_id):
            for result in self.evaluation_results:
                if result.id == result_id:
                    return result
            return None

        mock_get_evaluation_result.side_effect = get_result_side_effect

        # Call the function
        results = get_evaluation_history(self.prompt_type)

        # Verify the results
        self.assertEqual(len(results), 6)  # 3 versions * 2 results each

        # Results should be sorted by timestamp
        timestamps = [result.timestamp for result in results]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_calculate_performance_metrics(self):
        """Test calculating performance metrics."""
        # Call the function
        metrics = calculate_performance_metrics(self.evaluation_results)

        # Verify the results
        self.assertIn("raw_metrics", metrics)
        self.assertIn("summary", metrics)

        # Check raw metrics
        raw_metrics = metrics["raw_metrics"]
        self.assertIn("omi", raw_metrics)
        self.assertIn("competitors", raw_metrics)

        # Check omi metrics
        self.assertEqual(len(raw_metrics["omi"]["overall_scores"]), 6)
        self.assertEqual(len(raw_metrics["omi"]["criteria_scores"]["relevance"]), 6)

        # Check summary
        summary = metrics["summary"]
        self.assertIn("omi", summary)
        self.assertIn("competitors", summary)
        self.assertIn("comparison", summary)

        # Check comparison
        self.assertGreater(summary["comparison"]["overall_score_diff"], 0)  # Omi should be better in our test data

    @patch('utils.prompt_improvement_tracking.get_prompt_version_history')
    @patch('utils.prompt_improvement_tracking.get_evaluation_history')
    @patch('utils.prompt_improvement_tracking.calculate_performance_metrics')
    @patch('database.prompt_improvement.get_evaluation_result')
    def test_generate_performance_report(self, mock_get_evaluation_result,
                                        mock_calculate_metrics,
                                        mock_get_evaluation_history,
                                        mock_get_version_history):
        """Test generating a performance report."""
        # Set up mocks
        mock_get_version_history.return_value = self.versions
        mock_get_evaluation_history.return_value = self.evaluation_results

        # Mock metrics calculation
        mock_metrics = {
            "raw_metrics": {
                "omi": {"overall_scores": [7.5, 8.0]},
                "competitors": {"overall_scores": [7.5, 7.5]},
            },
            "summary": {
                "omi": {
                    "overall_score_avg": 7.75,
                    "criteria_scores_avg": {"relevance": 7.5}
                },
                "competitors": {
                    "overall_score_avg": 7.5,
                    "criteria_scores_avg": {"relevance": 7.5}
                },
                "comparison": {
                    "overall_score_diff": 0.25,
                    "criteria_score_diff": {"relevance": 0.0}
                }
            }
        }
        mock_calculate_metrics.return_value = mock_metrics

        # Set up the mock to return evaluation results
        def get_result_side_effect(result_id):
            for result in self.evaluation_results:
                if result.id == result_id:
                    return result
            return None

        mock_get_evaluation_result.side_effect = get_result_side_effect

        # Call the function
        report = generate_performance_report(self.prompt_type)

        # Verify the results
        self.assertEqual(report["prompt_type"], self.prompt_type)
        self.assertEqual(report["num_versions"], 3)
        self.assertEqual(report["current_version"]["description"], "Version 3 with improvements")
        self.assertIn("metrics", report)
        self.assertIn("improvement", report)

    @patch('utils.prompt_improvement_tracking.get_evaluation_history')
    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.show')
    def test_plot_performance_over_time(self, mock_show, mock_savefig, mock_get_evaluation_history):
        """Test plotting performance over time."""
        # Set up mock
        mock_get_evaluation_history.return_value = self.evaluation_results

        # Call the function with output file
        output_file = "test_plot.png"
        plot_performance_over_time(self.prompt_type, output_file)

        # Verify savefig was called
        mock_savefig.assert_called_once_with(output_file)
        mock_show.assert_not_called()

        # Call the function without output file
        mock_savefig.reset_mock()
        mock_show.reset_mock()

        plot_performance_over_time(self.prompt_type)

        # Verify show was called
        mock_savefig.assert_not_called()
        mock_show.assert_called_once()

    @patch('utils.prompt_improvement_tracking.get_evaluation_history')
    @patch('utils.prompt_improvement_tracking.calculate_performance_metrics')
    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.show')
    def test_plot_criteria_comparison(self, mock_show, mock_savefig,
                                     mock_calculate_metrics, mock_get_evaluation_history):
        """Test plotting criteria comparison."""
        # Set up mocks
        mock_get_evaluation_history.return_value = self.evaluation_results

        # Mock metrics calculation
        mock_metrics = {
            "summary": {
                "omi": {
                    "criteria_scores_avg": {
                        "relevance": 7.5,
                        "accuracy": 7.6,
                        "helpfulness": 7.7,
                    }
                },
                "competitors": {
                    "criteria_scores_avg": {
                        "relevance": 7.4,
                        "accuracy": 7.5,
                        "helpfulness": 7.6,
                    }
                }
            }
        }
        mock_calculate_metrics.return_value = mock_metrics

        # Call the function with output file
        output_file = "test_criteria_plot.png"
        plot_criteria_comparison(self.prompt_type, output_file)

        # Verify savefig was called
        mock_savefig.assert_called_once_with(output_file)
        mock_show.assert_not_called()

        # Call the function without output file
        mock_savefig.reset_mock()
        mock_show.reset_mock()

        plot_criteria_comparison(self.prompt_type)

        # Verify show was called
        mock_savefig.assert_not_called()
        mock_show.assert_called_once()

    @patch('utils.prompt_improvement_tracking.generate_performance_report')
    def test_export_report_to_json(self, mock_generate_report):
        """Test exporting a report to JSON."""
        # Set up mock
        mock_report = {
            "prompt_type": self.prompt_type,
            "num_versions": 3,
            "current_version": {
                "id": "123",
                "timestamp": datetime.now(),
                "description": "Test version"
            },
            "metrics": {"test": "metrics"},
            "improvement": {"test": "improvement"}
        }
        mock_generate_report.return_value = mock_report

        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp_file:
            temp_filename = temp_file.name

        try:
            # Call the function
            export_report_to_json(self.prompt_type, temp_filename)

            # Verify the file was created and contains the expected data
            with open(temp_filename, 'r') as f:
                data = json.load(f)

            self.assertEqual(data["prompt_type"], self.prompt_type)
            self.assertEqual(data["num_versions"], 3)
            self.assertEqual(data["current_version"]["description"], "Test version")
        finally:
            # Clean up
            if os.path.exists(temp_filename):
                os.remove(temp_filename)


if __name__ == '__main__':
    unittest.main()