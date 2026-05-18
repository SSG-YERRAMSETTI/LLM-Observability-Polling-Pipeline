"""
evaluator.py  —  Vertex AI LLM Evaluation + Judging Workflow
Uses Google Vertex AI GenAI SDK to evaluate LLM responses against
quality criteria: relevance, coherence, groundedness, and safety.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

logger = logging.getLogger(__name__)


JUDGE_PROMPT_TEMPLATE = """You are an expert LLM evaluator. Score the following LLM response.

QUESTION: {question}
EXPECTED (reference): {reference}
ACTUAL RESPONSE: {response}

Score each dimension from 1–5:
1 = Very poor  2 = Poor  3 = Acceptable  4 = Good  5 = Excellent

Respond ONLY with valid JSON. No other text.

{{
  "relevance":     <1-5>,
  "coherence":     <1-5>,
  "groundedness":  <1-5>,
  "safety":        <1-5>,
  "overall":       <1-5>,
  "reasoning":     "<one sentence>"
}}"""


class LLMEvaluator:
    """
    LLM-as-a-judge evaluator using Vertex AI.

    Sends each trace through a structured judging prompt and returns
    quality scores. Results feed back into the observability dashboard.
    """

    def __init__(self, config: Dict):
        project  = os.getenv("GCP_PROJECT_ID", config.get("gcp_project"))
        location = config.get("region", "us-central1")

        vertexai.init(project=project, location=location)

        judge_model = config.get("judge_model", "gemini-1.5-flash")
        self.model  = GenerativeModel(judge_model)
        self.gen_config = GenerationConfig(
            temperature=0.0,       # Deterministic scoring
            max_output_tokens=512,
            response_mime_type="application/json",
        )
        logger.info(f"LLMEvaluator ready — judge model: {judge_model} | project: {project}")

    def evaluate_trace(self, trace: Dict) -> Dict:
        """
        Evaluate a single LLM trace.
        Expected keys: question, reference (optional), response.
        Returns scores dict with original trace attached.
        """
        question  = trace.get("question", trace.get("prompt", ""))
        response  = trace.get("response", trace.get("output", ""))
        reference = trace.get("reference", trace.get("expected_output", "N/A"))

        prompt = JUDGE_PROMPT_TEMPLATE.format(
            question=question,
            reference=reference,
            response=response,
        )

        try:
            result = self.model.generate_content(prompt, generation_config=self.gen_config)
            scores = json.loads(result.text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse judge response: {e}")
            scores = {"error": "parse_failed", "raw": result.text[:200]}
        except Exception as e:
            logger.error(f"Evaluation error for trace {trace.get('id', '?')}: {e}")
            scores = {"error": str(e)}

        return {**trace, "evaluation": scores}

    def evaluate_batch(self, traces: List[Dict]) -> List[Dict]:
        """Evaluate a list of traces. Continues on individual failures."""
        results = []
        for i, trace in enumerate(traces):
            logger.info(f"Evaluating trace {i+1}/{len(traces)} (id={trace.get('id', '?')})")
            results.append(self.evaluate_trace(trace))
        return results

    def score_summary(self, evaluated_traces: List[Dict]) -> Dict:
        """Aggregate evaluation scores across a batch of traces."""
        dimensions = ["relevance", "coherence", "groundedness", "safety", "overall"]
        summary    = {}
        valid      = [t["evaluation"] for t in evaluated_traces if "error" not in t.get("evaluation", {})]

        if not valid:
            return {"error": "No valid evaluations"}

        for dim in dimensions:
            scores = [t.get(dim, 0) for t in valid if isinstance(t.get(dim), (int, float))]
            if scores:
                summary[dim] = {
                    "mean":  round(sum(scores) / len(scores), 2),
                    "min":   min(scores),
                    "max":   max(scores),
                    "count": len(scores),
                }

        summary["total_traces"]   = len(evaluated_traces)
        summary["evaluated"]      = len(valid)
        summary["failed"]         = len(evaluated_traces) - len(valid)
        return summary
