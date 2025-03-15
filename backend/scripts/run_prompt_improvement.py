#!/usr/bin/env python3
"""
Script to run the prompt improvement loop.

This script can be run as a standalone process or as a scheduled task.
It periodically evaluates and improves prompts used by Omi.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add the parent directory to the path for imports
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from backend.utils.prompt_improvement_loop import run_improvement_cycle, run_improvement_cycles
from backend.utils.prompt_improvement_tracking import (
    generate_performance_report,
    plot_performance_over_time,
    plot_criteria_comparison,
    export_report_to_json,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("prompt_improvement.log"),
    ],
)

logger = logging.getLogger(__name__)

# Default prompt types to improve
DEFAULT_PROMPT_TYPES = [
    "simple_message",
    "question_answering",
    "summarization",
]

# Flag to indicate if the process should exit
should_exit = False


def signal_handler(sig, frame):
    """Handle signals to gracefully exit the process."""
    global should_exit
    logger.info(f"Received signal {sig}, exiting...")
    should_exit = True


async def run_improvement_loop(
    prompt_types: List[str],
    interval_hours: float,
    run_once: bool = False,
    generate_reports: bool = True,
) -> None:
    """
    Run the prompt improvement loop.

    Args:
        prompt_types: List of prompt types to improve
        interval_hours: Interval between improvement cycles in hours
        run_once: Whether to run the improvement cycle only once
        generate_reports: Whether to generate performance reports
    """
    global should_exit

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create output directory for reports
    if generate_reports:
        output_dir = Path("data/prompt_improvement/reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Reports will be saved to {output_dir}")

    # Run the improvement cycle
    while not should_exit:
        start_time = time.time()
        logger.info(f"Starting improvement cycle for prompt types: {prompt_types}")

        try:
            # Run improvement cycles for all prompt types
            results = await run_improvement_cycles(prompt_types)

            # Log results
            for prompt_type, result in results.items():
                if result.get("success", False):
                    logger.info(f"Successfully improved prompt type: {prompt_type}")
                    if result.get("activated", False):
                        logger.info(f"Activated improved prompt for {prompt_type}")
                else:
                    logger.error(f"Failed to improve prompt type: {prompt_type}")
                    if "error" in result:
                        logger.error(f"Error: {result['error']}")

            # Generate additional reports if requested
            if generate_reports:
                await generate_additional_reports(prompt_types, output_dir)

        except Exception as e:
            logger.exception(f"Error in improvement cycle: {str(e)}")

        # Exit if run_once is True
        if run_once:
            logger.info("Run once mode, exiting...")
            break

        # Calculate time to sleep
        elapsed_time = time.time() - start_time
        sleep_time = max(0, interval_hours * 3600 - elapsed_time)

        if sleep_time > 0:
            logger.info(f"Sleeping for {sleep_time:.2f} seconds until next cycle...")
            # Sleep in small increments to check for exit signal
            for _ in range(int(sleep_time / 10) + 1):
                if should_exit:
                    break
                await asyncio.sleep(min(10, sleep_time))
                sleep_time -= 10


async def generate_additional_reports(prompt_types: List[str], output_dir: Path) -> None:
    """
    Generate additional performance reports and visualizations.

    Args:
        prompt_types: List of prompt types to generate reports for
        output_dir: Directory to save reports
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for prompt_type in prompt_types:
        try:
            # Generate performance report
            report = generate_performance_report(prompt_type)

            # Skip if no data
            if "error" in report:
                logger.warning(f"Could not generate report for {prompt_type}: {report['error']}")
                continue

            # Generate plots
            plot_time_file = output_dir / f"{prompt_type}_performance_{timestamp}.png"
            plot_criteria_file = output_dir / f"{prompt_type}_criteria_{timestamp}.png"
            report_file = output_dir / f"{prompt_type}_report_{timestamp}.json"

            # Save plots and report
            plot_performance_over_time(prompt_type, str(plot_time_file))
            plot_criteria_comparison(prompt_type, str(plot_criteria_file))
            export_report_to_json(prompt_type, str(report_file))

            logger.info(f"Generated additional reports for {prompt_type}")
            logger.info(f"Performance plot: {plot_time_file}")
            logger.info(f"Criteria plot: {plot_criteria_file}")
            logger.info(f"Report file: {report_file}")

            # Generate summary
            if "improvement" in report and report["improvement"]["overall_score"]:
                logger.info(f"Improvement since first version for {prompt_type}:")
                logger.info(f"Overall score: {report['improvement']['overall_score']:.2f}")
                for criterion, score in report["improvement"]["criteria_scores"].items():
                    logger.info(f"{criterion}: {score:.2f}")

        except Exception as e:
            logger.exception(f"Error generating reports for {prompt_type}: {str(e)}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Run the prompt improvement loop")
    parser.add_argument(
        "--prompt-types",
        nargs="+",
        default=DEFAULT_PROMPT_TYPES,
        help="List of prompt types to improve",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=24.0,
        help="Interval between improvement cycles in hours",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run the improvement cycle only once",
    )
    parser.add_argument(
        "--no-reports",
        action="store_true",
        help="Disable generation of performance reports",
    )

    args = parser.parse_args()

    logger.info(f"Starting prompt improvement loop with arguments: {args}")

    # Run the improvement loop
    asyncio.run(
        run_improvement_loop(
            prompt_types=args.prompt_types,
            interval_hours=args.interval,
            run_once=args.run_once,
            generate_reports=not args.no_reports,
        )
    )


if __name__ == "__main__":
    main()