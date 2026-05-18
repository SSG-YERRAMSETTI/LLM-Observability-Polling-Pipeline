"""
main.py  —  LLM Observability Pipeline Entry Point
"""

import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)

from src.pipeline import ObservabilityPipeline
from src.poller   import ArizePoller

if __name__ == "__main__":
    pipeline = ObservabilityPipeline(config_path="config/config.yaml")

    mode = os.getenv("RUN_MODE", "continuous")

    if mode == "once":
        result = pipeline.run_once()
        print(f"Pipeline result: {result}")
    else:
        # Continuous polling loop
        poller = ArizePoller(config_path="config/config.yaml")
        poller.run(on_data=lambda df: pipeline.evaluator.evaluate_batch(df.to_dict("records")))
