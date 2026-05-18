"""
pipeline.py  —  Observability Pipeline Orchestrator
Ties together polling → evaluation → export in one schedulable unit.
"""

import logging
import os
import yaml
import pandas as pd
from datetime import datetime

from src.poller    import ArizePoller
from src.evaluator import LLMEvaluator

logger = logging.getLogger(__name__)


class ObservabilityPipeline:
    """
    Full pipeline: Arize traces → Vertex AI evaluation → export.
    Can be run as a one-shot job or a continuous loop.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.poller    = ArizePoller(config_path=config_path)
        self.evaluator = LLMEvaluator(self.config)
        self.run_id    = datetime.now().strftime("%Y%m%d_%H%M%S")

    def run_once(self) -> dict:
        """
        Single pipeline execution:
        1. Poll Arize for recent traces
        2. Evaluate with Vertex AI judge
        3. Export results
        4. Return summary
        """
        logger.info(f"Pipeline run {self.run_id} starting...")

        # Step 1: Poll
        df = self.poller.poll_once()
        if df.empty:
            logger.info("No new traces — nothing to evaluate.")
            return {"status": "no_data", "traces": 0}

        traces = df.to_dict(orient="records")
        logger.info(f"Polled {len(traces)} traces")

        # Step 2: Evaluate
        evaluated = self.evaluator.evaluate_batch(traces)
        summary   = self.evaluator.score_summary(evaluated)

        # Step 3: Export results
        result_df = pd.DataFrame(evaluated)
        export_path = self.poller.export(result_df, fmt="parquet")

        # Also save summary as JSON
        import json
        summary_path = export_path.replace(".parquet", "_summary.json")
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Pipeline complete. Summary: {summary}")
        return {
            "status": "success",
            "traces": len(traces),
            "export": export_path,
            "summary": summary,
        }
