<div align="center">

# LLM Observability & Polling Pipeline

**Real-time monitoring and evaluation of production LLM systems across GCP and AWS**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![GCP](https://img.shields.io/badge/Google_Cloud-Vertex_AI-4285F4?style=flat-square&logo=google-cloud&logoColor=white)](https://cloud.google.com/vertex-ai)
[![AWS](https://img.shields.io/badge/AWS-SageMaker-FF9900?style=flat-square&logo=amazon-aws&logoColor=white)](https://aws.amazon.com/sagemaker/)
[![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC?style=flat-square&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Arize](https://img.shields.io/badge/Arize-Observability-FF6B35?style=flat-square)](https://arize.com/)

</div>

---

> When an LLM starts returning poor-quality answers in production, you want to know in 5 minutes — not when a customer complaint lands in your inbox.

This pipeline continuously polls LLM trace data from Arize, evaluates every response using a Vertex AI judge model, exports structured results to GCP Storage, and deploys as a containerized service on Cloud Run — triggered on a schedule via Cloud Scheduler. The entire infrastructure is defined in Terraform and deployable in a single command.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Arize Platform                                                      │
│  (LLM traces: inputs, outputs, latency, token counts, metadata)     │
└────────────────────────┬────────────────────────────────────────────┘
                         │  REST API (every 60s)
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ArizePoller  (src/poller.py)                                        │
│  ├── Fetches traces for last N minutes                               │
│  ├── Normalises to Pandas DataFrame                                  │
│  └── Exports to GCS as Parquet                                       │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LLMEvaluator  (src/evaluator.py)                                    │
│  ├── Vertex AI Gemini-1.5-Flash as judge                             │
│  ├── Scores: relevance, coherence, groundedness, safety, overall     │
│  └── Aggregates batch summary with mean/min/max per dimension        │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  GCP Cloud Run  (containerized pipeline service)                      │
│  ├── Triggered every 5 min by Cloud Scheduler                         │
│  ├── Secrets via Secret Manager (no credentials in code or config)    │
│  └── Container images stored in Artifact Registry                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## What It Does

**Real-Time Trace Polling**
The Arize poller runs on a configurable interval (default: every 60 seconds) and fetches LLM traces from the last N minutes. Traces include the prompt, model response, token counts, latency, and any custom metadata you instrumented. Everything lands in a Pandas DataFrame for downstream processing.

**Automated LLM Evaluation (LLM-as-a-Judge)**
Each trace is scored by a Vertex AI Gemini judge model against four quality dimensions: relevance (does the response address the question?), coherence (is it well-structured?), groundedness (is it factually grounded?), and safety (is it appropriate?). The judge uses a structured JSON output format for consistent, parseable scores.

**Multi-Cloud Deployment**
Container images are built and tested against AWS SageMaker instances, then pushed to both Google Artifact Registry and AWS ECR for redundancy. The production service runs on GCP Cloud Run.

**Infrastructure as Code**
Every GCP resource — Cloud Run service, Artifact Registry, service accounts, IAM bindings, Secret Manager entries, and Cloud Scheduler job — is defined in Terraform. Reproducible from scratch with `terraform apply`.

**Structured Observability Export**
Evaluation results export to Parquet (efficient, columnar) with a companion JSON summary per batch. Summaries include mean/min/max scores per quality dimension and alert flags when scores drop below configured thresholds.

---

## Project Structure

```
llm-observability-pipeline/
│
├── main.py                     ← Entry point (continuous or one-shot)
├── Dockerfile                  ← Container definition
├── requirements.txt
│
├── src/
│   ├── poller.py               ← Arize polling + DataFrame export
│   ├── evaluator.py            ← Vertex AI LLM judge evaluation
│   └── pipeline.py             ← Orchestrator: poll → evaluate → export
│
├── config/
│   ├── config.yaml             ← Model IDs, thresholds, intervals
│   └── .env.example            ← Credentials template
│
├── terraform/
│   ├── main.tf                 ← Cloud Run, Artifact Registry, Scheduler
│   ├── variables.tf
│   └── outputs.tf
│
└── .github/
    └── workflows/
        └── deploy.yml          ← CI/CD: build → push → deploy on push to main
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- GCP project with Vertex AI and Cloud Run enabled
- Arize account with an instrumented model
- Terraform 1.5+ (for infrastructure deployment)
- Docker (for local testing)

### Local Development

```bash
git clone https://github.com/SSG-YERRAMSETTI/llm-observability-pipeline.git
cd llm-observability-pipeline

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

**Configure environment:**
```bash
cp config/.env.example .env
```

Edit `.env`:
```env
ARIZE_API_KEY=your_arize_api_key
ARIZE_SPACE_ID=your_arize_space_id
GCP_PROJECT_ID=your-gcp-project
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

Update `config/config.yaml` with your Arize model ID and GCP project.

**Run a single pipeline cycle:**
```bash
RUN_MODE=once python main.py
```

**Run continuous polling:**
```bash
python main.py
```

**Run in Docker:**
```bash
docker build -t llm-obs-pipeline .
docker run --env-file .env llm-obs-pipeline
```

---

### Deploy to GCP with Terraform

```bash
cd terraform

terraform init

terraform plan \
  -var="gcp_project=your-project-id" \
  -var="region=us-central1"

terraform apply \
  -var="gcp_project=your-project-id" \
  -var="image_tag=latest"
```

The pipeline will deploy as a Cloud Run service triggered every 5 minutes by Cloud Scheduler.

---

### CI/CD Pipeline

Push to `main` automatically:
1. Authenticates to GCP via service account (stored in GitHub Secrets)
2. Builds and pushes the Docker image to Artifact Registry
3. Deploys the new image to Cloud Run

Set these secrets in your GitHub repository:
- `GCP_PROJECT_ID`
- `GCP_SA_KEY` (service account JSON)

---

## Evaluation Output Example

```json
{
  "total_traces":  124,
  "evaluated":     121,
  "failed":        3,
  "relevance":     { "mean": 4.2, "min": 2, "max": 5, "count": 121 },
  "coherence":     { "mean": 4.5, "min": 3, "max": 5, "count": 121 },
  "groundedness":  { "mean": 3.8, "min": 1, "max": 5, "count": 121 },
  "safety":        { "mean": 4.9, "min": 4, "max": 5, "count": 121 },
  "overall":       { "mean": 4.1, "min": 2, "max": 5, "count": 121 }
}
```

---

## Author

**Satya Sai Ganesh Yerramsetti**
MS Computer Science — University of North Texas

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat-square&logo=linkedin)](https://linkedin.com/in/satya-sai-ganesh-yerramsetti-2a204424b)
[![GitHub](https://img.shields.io/badge/GitHub-SSG--YERRAMSETTI-181717?style=flat-square&logo=github)](https://github.com/SSG-YERRAMSETTI)

<div align="center"><sub>⭐ if this saved your team from finding out about a degraded model from a customer report</sub></div>
