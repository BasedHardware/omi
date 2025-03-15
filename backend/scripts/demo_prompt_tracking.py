#!/usr/bin/env python3
"""
Demo script for the prompt improvement tracking module.
This script creates sample data and demonstrates the tracking functionality.
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
import random
from pathlib import Path

# Add the parent directory to the path for imports
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from backend.utils.prompt_evaluation import EvaluationResult
from backend.utils.prompt_improvement import PromptVersion
from backend.utils.prompt_improvement_tracking import (
    calculate_performance_metrics,
    generate_performance_report,
    plot_performance_over_time,
    plot_criteria_comparison,
    export_report_to_json,
)

# Mock database functions
class MockDB:
    def __init__(self):
        self.prompt_versions = {}
        self.evaluation_results = {}

    def get_prompt_versions(self, prompt_type, include_inactive=False, sort_by=None, sort_order=None):
        versions = self.prompt_versions.get(prompt_type, [])
        if not include_inactive:
            versions = [v for v in versions if v.active]

        if sort_by == "timestamp":
            versions = sorted(versions, key=lambda v: v.timestamp)
            if sort_order == "desc":
                versions = list(reversed(versions))

        return versions

    def get_evaluation_result(self, result_id):
        return self.evaluation_results.get(result_id)

    def add_prompt_version(self, version):
        if version.prompt_type not in self.prompt_versions:
            self.prompt_versions[version.prompt_type] = []
        self.prompt_versions[version.prompt_type].append(version)

    def add_evaluation_result(self, result):
        self.evaluation_results[result.id] = result


# Create mock database
mock_db = MockDB()

# Monkey patch the database module
import backend.database.prompt_improvement as db
db.get_prompt_versions = mock_db.get_prompt_versions
db.get_evaluation_result = mock_db.get_evaluation_result


def create_sample_data():
    """Create sample data for demonstration purposes."""
    prompt_types = ["simple_message", "question_answering", "summarization"]

    for prompt_type in prompt_types:
        # Create 5 versions of each prompt type
        for i in range(5):
            # Create a prompt version
            version_id = str(uuid.uuid4())
            timestamp = datetime.now() - timedelta(days=30-i*7)  # Spread over a month

            version = PromptVersion(
                id=version_id,
                timestamp=timestamp,
                prompt_type=prompt_type,
                prompt=f"This is version {i+1} of the {prompt_type} prompt.",
                description=f"Version {i+1} with improvements to {random.choice(['relevance', 'accuracy', 'helpfulness'])}",
                active=(i == 4),  # Only the latest version is active
                evaluation_results=[]
            )

            # Create 3 evaluation results for each version
            for j in range(3):
                result_id = str(uuid.uuid4())

                # Create scores that improve over time
                base_omi_score = 7.0 + i * 0.5  # Starts at 7.0, increases by 0.5 each version
                base_competitor_score = 7.5  # Stays relatively constant

                # Add some randomness
                omi_score = min(10.0, base_omi_score + random.uniform(-0.3, 0.3))
                competitor_score = min(10.0, base_competitor_score + random.uniform(-0.3, 0.3))

                # Create criteria scores
                criteria = ["relevance", "accuracy", "helpfulness", "naturalness",
                           "personalization", "conciseness", "creativity"]

                omi_criteria = {}
                competitor_criteria = {}

                for criterion in criteria:
                    # Omi improves more in certain criteria
                    if criterion in ["relevance", "helpfulness", "personalization"]:
                        omi_criteria[criterion] = min(10.0, 7.0 + i * 0.6 + random.uniform(-0.2, 0.2))
                    else:
                        omi_criteria[criterion] = min(10.0, 7.0 + i * 0.4 + random.uniform(-0.2, 0.2))

                    competitor_criteria[criterion] = min(10.0, 7.5 + random.uniform(-0.3, 0.3))

                # Create the evaluation result
                result = EvaluationResult(
                    id=result_id,
                    timestamp=timestamp + timedelta(hours=j),
                    prompt_version_id=version_id,
                    conversation=[],  # Not needed for this demo
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

                # Add the result to the database
                mock_db.add_evaluation_result(result)

                # Add the result ID to the version
                version.evaluation_results.append(result_id)

            # Add the version to the database
            mock_db.add_prompt_version(version)


def demo_tracking():
    """Demonstrate the tracking functionality."""
    prompt_type = "simple_message"

    print(f"\n{'='*80}")
    print(f"Demonstrating prompt improvement tracking for '{prompt_type}'")
    print(f"{'='*80}\n")

    # Generate a performance report
    report = generate_performance_report(prompt_type)

    print("Performance Report:")
    print(f"Number of versions: {report['num_versions']}")
    print(f"Current version: {report['current_version']['description']}")

    print("\nPerformance Metrics:")
    print(f"Omi overall score: {report['metrics']['summary']['omi']['overall_score_avg']:.2f}")
    print(f"Competitors overall score: {report['metrics']['summary']['competitors']['overall_score_avg']:.2f}")
    print(f"Difference: {report['metrics']['summary']['comparison']['overall_score_diff']:.2f}")

    print("\nCriteria Scores (Omi):")
    for criterion, score in report['metrics']['summary']['omi']['criteria_scores_avg'].items():
        print(f"{criterion}: {score:.2f}")

    if report['improvement']['overall_score']:
        print("\nImprovement since first version:")
        print(f"Overall score: {report['improvement']['overall_score']:.2f}")
        for criterion, score in report['improvement']['criteria_scores'].items():
            print(f"{criterion}: {score:.2f}")

    # Create output directory if it doesn't exist
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Export report to JSON
    json_file = output_dir / f"{prompt_type}_report.json"
    export_report_to_json(prompt_type, str(json_file))
    print(f"\nReport exported to {json_file}")

    # Plot performance over time
    time_plot_file = output_dir / f"{prompt_type}_performance_time.png"
    plot_performance_over_time(prompt_type, str(time_plot_file))
    print(f"Performance over time plot saved to {time_plot_file}")

    # Plot criteria comparison
    criteria_plot_file = output_dir / f"{prompt_type}_criteria_comparison.png"
    plot_criteria_comparison(prompt_type, str(criteria_plot_file))
    print(f"Criteria comparison plot saved to {criteria_plot_file}")


if __name__ == "__main__":
    # Create sample data
    create_sample_data()

    # Demonstrate tracking for each prompt type
    for prompt_type in ["simple_message", "question_answering", "summarization"]:
        demo_tracking()