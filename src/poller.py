"""
poller.py  —  Arize LLM Trace Polling Engine
Polls the Arize platform at configurable intervals, exports trace data
to Pandas DataFrames, and feeds evaluations downstream.
"""

import time
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd
import requests
import yaml

logger = logging.getLogger(__name__)


class ArizePoller:
    """
    Scheduled poller for Arize LLM trace data.

    Arize stores LLM inputs, outputs, token counts, latencies, and
    any custom metadata you instrument. This poller retrieves those
    traces on a schedule and makes them available for evaluation.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.api_key    = os.getenv("ARIZE_API_KEY")
        self.space_id   = os.getenv("ARIZE_SPACE_ID")
        self.base_url   = self.config.get("arize", {}).get("base_url", "https://api.arize.com/v1")
        self.model_id   = self.config.get("arize", {}).get("model_id")
        self.interval   = self.config.get("poll_interval_seconds", 60)
        self.lookback   = self.config.get("lookback_minutes", 10)
        self.output_dir = self.config.get("output_dir", "exports")

        if not self.api_key or not self.space_id:
            raise ValueError(
                "ARIZE_API_KEY and ARIZE_SPACE_ID must be set as environment variables."
            )

        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"ArizePoller initialized — polling every {self.interval}s")

    # ── Polling ───────────────────────────────────────────────────────────────

    def poll_once(self) -> pd.DataFrame:
        """
        Fetch LLM traces from Arize for the last N minutes.
        Returns a DataFrame with one row per trace.
        """
        end_time   = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=self.lookback)

        logger.info(f"Polling traces: {start_time.isoformat()} → {end_time.isoformat()}")

        params = {
            "model_id":   self.model_id,
            "start_time": start_time.isoformat(),
            "end_time":   end_time.isoformat(),
            "limit":      self.config.get("arize", {}).get("batch_size", 500),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "x-space-id":    self.space_id,
            "Content-Type":  "application/json",
        }

        response = requests.get(
            f"{self.base_url}/traces",
            params=params,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        records = response.json().get("data", [])
        logger.info(f"Retrieved {len(records)} traces")

        if not records:
            return pd.DataFrame()

        df = pd.json_normalize(records)
        df["polled_at"] = end_time.isoformat()
        return df

    # ── Export ────────────────────────────────────────────────────────────────

    def export(self, df: pd.DataFrame, fmt: str = "parquet") -> str:
        """
        Export trace DataFrame to disk.
        Supports: parquet (default, efficient), csv (human-readable), json.
        """
        if df.empty:
            logger.info("No data to export.")
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"traces_{timestamp}.{fmt}"
        filepath  = os.path.join(self.output_dir, filename)

        if fmt == "parquet":
            df.to_parquet(filepath, index=False)
        elif fmt == "csv":
            df.to_csv(filepath, index=False)
        elif fmt == "json":
            df.to_json(filepath, orient="records", indent=2)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        logger.info(f"Exported {len(df)} rows → {filepath}")
        return filepath

    # ── Continuous polling loop ───────────────────────────────────────────────

    def run(self, on_data=None):
        """
        Run the polling loop indefinitely.
        Calls on_data(df) after each successful poll if provided.
        """
        logger.info("Starting polling loop. Press Ctrl+C to stop.")
        consecutive_errors = 0

        while True:
            try:
                df = self.poll_once()

                if not df.empty:
                    path = self.export(df, fmt=self.config.get("export_format", "parquet"))
                    if on_data:
                        on_data(df)

                consecutive_errors = 0

            except requests.HTTPError as e:
                consecutive_errors += 1
                logger.error(f"HTTP error polling Arize (attempt {consecutive_errors}): {e}")
                if consecutive_errors >= 5:
                    logger.critical("5 consecutive failures — stopping poller.")
                    raise

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Unexpected error (attempt {consecutive_errors}): {e}")

            time.sleep(self.interval)
