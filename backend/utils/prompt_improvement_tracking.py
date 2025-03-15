"""
Module for tracking the progress of prompt improvements over time.
"""

import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import database.prompt_improvement as db
from utils.prompt_evaluation import EvaluationResult
from utils.prompt_improvement import PromptVersion


def get_prompt_version_history(prompt_type: str) -> List[PromptVersion]:
    """
    Get the history of prompt versions for a given prompt type.

    Args:
        prompt_type: The type of prompt to get the history for

    Returns:
        A list of PromptVersion objects sorted by timestamp
    """
    versions = db.get_prompt_versions(
        prompt_type=prompt_type,
        include_inactive=True,
        sort_by="timestamp",
        sort_order="asc",
    )
    return versions


def get_evaluation_history(prompt_type: str) -> List[EvaluationResult]:
    """
    Get the history of evaluation results for a given prompt type.

    Args:
        prompt_type: The type of prompt to get the evaluation history for

    Returns:
        A list of EvaluationResult objects sorted by timestamp
    """
    # Get all prompt versions for the given type
    versions = get_prompt_version_history(prompt_type)

    # Get all evaluation results for each version
    evaluation_results = []
    for version in versions:
        for result_id in version.evaluation_results:
            result = db.get_evaluation_result(result_id)
            if result:
                evaluation_results.append(result)

    # Sort by timestamp
    evaluation_results.sort(key=lambda x: x.timestamp)

    return evaluation_results


def calculate_performance_metrics(evaluation_results: List[EvaluationResult]) -> Dict[str, Any]:
    """
    Calculate performance metrics from evaluation results.

    Args:
        evaluation_results: List of evaluation results

    Returns:
        A dictionary of performance metrics
    """
    if not evaluation_results:
        return {}

    # Initialize metrics
    metrics = {
        "omi": {
            "overall_scores": [],
            "criteria_scores": {
                "relevance": [],
                "accuracy": [],
                "helpfulness": [],
                "naturalness": [],
                "personalization": [],
                "conciseness": [],
                "creativity": [],
            },
        },
        "competitors": {
            "overall_scores": [],
            "criteria_scores": {
                "relevance": [],
                "accuracy": [],
                "helpfulness": [],
                "naturalness": [],
                "personalization": [],
                "conciseness": [],
                "creativity": [],
            },
        },
    }

    # Collect metrics from evaluation results
    for result in evaluation_results:
        # Overall scores
        if "omi" in result.overall_scores:
            metrics["omi"]["overall_scores"].append(result.overall_scores["omi"])

        # Criteria scores for Omi
        if "omi" in result.scores:
            for criterion, score in result.scores["omi"].items():
                if criterion in metrics["omi"]["criteria_scores"]:
                    metrics["omi"]["criteria_scores"][criterion].append(score)

        # Competitor scores
        competitor_overall_scores = []
        competitor_criteria_scores = {
            "relevance": [],
            "accuracy": [],
            "helpfulness": [],
            "naturalness": [],
            "personalization": [],
            "conciseness": [],
            "creativity": [],
        }

        for competitor, score in result.overall_scores.items():
            if competitor != "omi":
                competitor_overall_scores.append(score)

                # Criteria scores for competitors
                if competitor in result.scores:
                    for criterion, score in result.scores[competitor].items():
                        if criterion in competitor_criteria_scores:
                            competitor_criteria_scores[criterion].append(score)

        if competitor_overall_scores:
            metrics["competitors"]["overall_scores"].append(
                sum(competitor_overall_scores) / len(competitor_overall_scores)
            )

            # Average criteria scores for competitors
            for criterion, scores in competitor_criteria_scores.items():
                if scores:
                    metrics["competitors"]["criteria_scores"][criterion].append(
                        sum(scores) / len(scores)
                    )

    # Calculate summary statistics
    summary = {
        "omi": {
            "overall_score_avg": np.mean(metrics["omi"]["overall_scores"]) if metrics["omi"]["overall_scores"] else 0,
            "overall_score_min": np.min(metrics["omi"]["overall_scores"]) if metrics["omi"]["overall_scores"] else 0,
            "overall_score_max": np.max(metrics["omi"]["overall_scores"]) if metrics["omi"]["overall_scores"] else 0,
            "criteria_scores_avg": {
                criterion: np.mean(scores) if scores else 0
                for criterion, scores in metrics["omi"]["criteria_scores"].items()
            },
        },
        "competitors": {
            "overall_score_avg": np.mean(metrics["competitors"]["overall_scores"]) if metrics["competitors"]["overall_scores"] else 0,
            "overall_score_min": np.min(metrics["competitors"]["overall_scores"]) if metrics["competitors"]["overall_scores"] else 0,
            "overall_score_max": np.max(metrics["competitors"]["overall_scores"]) if metrics["competitors"]["overall_scores"] else 0,
            "criteria_scores_avg": {
                criterion: np.mean(scores) if scores else 0
                for criterion, scores in metrics["competitors"]["criteria_scores"].items()
            },
        },
        "comparison": {
            "overall_score_diff": 0,
            "criteria_score_diff": {},
        },
    }

    # Calculate comparison metrics
    if metrics["omi"]["overall_scores"] and metrics["competitors"]["overall_scores"]:
        summary["comparison"]["overall_score_diff"] = (
            summary["omi"]["overall_score_avg"] - summary["competitors"]["overall_score_avg"]
        )

        for criterion in metrics["omi"]["criteria_scores"]:
            omi_avg = summary["omi"]["criteria_scores_avg"][criterion]
            comp_avg = summary["competitors"]["criteria_scores_avg"][criterion]
            summary["comparison"]["criteria_score_diff"][criterion] = omi_avg - comp_avg

    return {
        "raw_metrics": metrics,
        "summary": summary,
    }


def generate_performance_report(prompt_type: str) -> Dict[str, Any]:
    """
    Generate a performance report for a given prompt type.

    Args:
        prompt_type: The type of prompt to generate the report for

    Returns:
        A dictionary containing the performance report
    """
    # Get prompt version history
    versions = get_prompt_version_history(prompt_type)
    if not versions:
        return {"error": f"No prompt versions found for type: {prompt_type}"}

    # Get evaluation history
    evaluation_results = get_evaluation_history(prompt_type)
    if not evaluation_results:
        return {"error": f"No evaluation results found for prompt type: {prompt_type}"}

    # Calculate performance metrics
    metrics = calculate_performance_metrics(evaluation_results)

    # Generate report
    report = {
        "prompt_type": prompt_type,
        "num_versions": len(versions),
        "current_version": {
            "id": versions[-1].id,
            "timestamp": versions[-1].timestamp,
            "description": versions[-1].description,
        },
        "metrics": metrics,
        "improvement": {
            "overall_score": 0,
            "criteria_scores": {},
        },
    }

    # Calculate improvement if there are at least two versions
    if len(versions) >= 2:
        # Get evaluation results for the first and last versions
        first_version_results = [
            db.get_evaluation_result(result_id)
            for result_id in versions[0].evaluation_results
        ]
        first_version_results = [r for r in first_version_results if r]

        last_version_results = [
            db.get_evaluation_result(result_id)
            for result_id in versions[-1].evaluation_results
        ]
        last_version_results = [r for r in last_version_results if r]

        if first_version_results and last_version_results:
            # Calculate metrics for first and last versions
            first_metrics = calculate_performance_metrics(first_version_results)
            last_metrics = calculate_performance_metrics(last_version_results)

            # Calculate improvement
            report["improvement"]["overall_score"] = (
                last_metrics["summary"]["omi"]["overall_score_avg"] -
                first_metrics["summary"]["omi"]["overall_score_avg"]
            )

            for criterion in first_metrics["summary"]["omi"]["criteria_scores_avg"]:
                report["improvement"]["criteria_scores"][criterion] = (
                    last_metrics["summary"]["omi"]["criteria_scores_avg"][criterion] -
                    first_metrics["summary"]["omi"]["criteria_scores_avg"][criterion]
                )

    return report


def plot_performance_over_time(prompt_type: str, output_file: Optional[str] = None) -> None:
    """
    Plot the performance of a prompt type over time.

    Args:
        prompt_type: The type of prompt to plot
        output_file: Optional file path to save the plot
    """
    # Get evaluation history
    evaluation_results = get_evaluation_history(prompt_type)
    if not evaluation_results:
        print(f"No evaluation results found for prompt type: {prompt_type}")
        return

    # Extract data for plotting
    timestamps = [result.timestamp for result in evaluation_results]
    omi_scores = [result.overall_scores.get("omi", 0) for result in evaluation_results]

    # Calculate average competitor scores
    competitor_scores = []
    for result in evaluation_results:
        comp_scores = [score for comp, score in result.overall_scores.items() if comp != "omi"]
        if comp_scores:
            competitor_scores.append(sum(comp_scores) / len(comp_scores))
        else:
            competitor_scores.append(0)

    # Create a DataFrame for easier plotting
    df = pd.DataFrame({
        "timestamp": timestamps,
        "omi_score": omi_scores,
        "competitor_score": competitor_scores,
    })

    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(df["timestamp"], df["omi_score"], marker="o", label="Omi")
    plt.plot(df["timestamp"], df["competitor_score"], marker="x", label="Competitors (avg)")
    plt.axhline(y=df["competitor_score"].mean(), color="r", linestyle="--", alpha=0.5, label="Competitor avg")

    plt.title(f"Performance Over Time - {prompt_type}")
    plt.xlabel("Time")
    plt.ylabel("Overall Score")
    plt.legend()
    plt.grid(True, alpha=0.3)

    # Format x-axis dates
    plt.gcf().autofmt_xdate()

    # Save or show the plot
    if output_file:
        plt.savefig(output_file)
    else:
        plt.show()


def plot_criteria_comparison(prompt_type: str, output_file: Optional[str] = None) -> None:
    """
    Plot a comparison of criteria scores between Omi and competitors.

    Args:
        prompt_type: The type of prompt to plot
        output_file: Optional file path to save the plot
    """
    # Get evaluation history
    evaluation_results = get_evaluation_history(prompt_type)
    if not evaluation_results:
        print(f"No evaluation results found for prompt type: {prompt_type}")
        return

    # Calculate metrics
    metrics = calculate_performance_metrics(evaluation_results)

    # Extract criteria scores
    criteria = list(metrics["summary"]["omi"]["criteria_scores_avg"].keys())
    omi_scores = [metrics["summary"]["omi"]["criteria_scores_avg"][c] for c in criteria]
    comp_scores = [metrics["summary"]["competitors"]["criteria_scores_avg"][c] for c in criteria]

    # Create bar chart
    x = np.arange(len(criteria))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 6))
    rects1 = ax.bar(x - width/2, omi_scores, width, label="Omi")
    rects2 = ax.bar(x + width/2, comp_scores, width, label="Competitors")

    ax.set_title(f"Criteria Comparison - {prompt_type}")
    ax.set_xlabel("Criteria")
    ax.set_ylabel("Average Score")
    ax.set_xticks(x)
    ax.set_xticklabels(criteria)
    ax.legend()

    # Add value labels
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f"{height:.1f}",
                        xy=(rect.get_x() + rect.get_width()/2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center", va="bottom")

    autolabel(rects1)
    autolabel(rects2)

    fig.tight_layout()

    # Save or show the plot
    if output_file:
        plt.savefig(output_file)
    else:
        plt.show()


def export_report_to_json(prompt_type: str, output_file: str) -> None:
    """
    Export a performance report to a JSON file.

    Args:
        prompt_type: The type of prompt to generate the report for
        output_file: File path to save the report
    """
    report = generate_performance_report(prompt_type)

    # Convert datetime objects to strings
    def json_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    with open(output_file, "w") as f:
        json.dump(report, f, default=json_serializer, indent=2)

    print(f"Report exported to {output_file}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Track prompt improvement progress")
    parser.add_argument("prompt_type", help="The type of prompt to track")
    parser.add_argument("--report", help="Generate a report and save to the specified file")
    parser.add_argument("--plot-time", help="Plot performance over time and save to the specified file")
    parser.add_argument("--plot-criteria", help="Plot criteria comparison and save to the specified file")

    args = parser.parse_args()

    if args.report:
        export_report_to_json(args.prompt_type, args.report)

    if args.plot_time:
        plot_performance_over_time(args.prompt_type, args.plot_time)

    if args.plot_criteria:
        plot_criteria_comparison(args.prompt_type, args.plot_criteria)

    if not (args.report or args.plot_time or args.plot_criteria):
        # Print a summary report
        report = generate_performance_report(args.prompt_type)
        print(f"Performance Report for {args.prompt_type}:")
        print(f"Number of versions: {report['num_versions']}")
        print(f"Current version: {report['current_version']['description']}")
        print("\nPerformance Metrics:")
        print(f"Omi overall score: {report['metrics']['summary']['omi']['overall_score_avg']:.2f}")
        print(f"Competitors overall score: {report['metrics']['summary']['competitors']['overall_score_avg']:.2f}")
        print(f"Difference: {report['metrics']['summary']['comparison']['overall_score_diff']:.2f}")

        if report['improvement']['overall_score']:
            print("\nImprovement since first version:")
            print(f"Overall score: {report['improvement']['overall_score']:.2f}")
            for criterion, score in report['improvement']['criteria_scores'].items():
                print(f"{criterion}: {score:.2f}")