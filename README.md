# Muse Shopping Agent

An AI shopping assistant built with LangGraph. Muse understands a shopping
request, asks for only the details that matter, searches products, ranks the
matches, and presents the results in a browser UI.

## 1. Use the deployed website

Open the deployed AWS website:

https://s6tro35z7guy66qg26d4yy52ty0kvgut.lambda-url.us-east-1.on.aws/

The demo runs on AWS Lambda, uses Amazon Bedrock for AI responses, and uses
SearchAPI for live product results.

No Python, AWS CLI, Groq key, or SearchAPI key is needed to use the website.

## 2. Run locally with Groq

Use this option for local development without AWS. You need a Groq API key.

## 3. Run locally with AWS Bedrock

Use this option to run the UI on your computer while sending AI requests to
Amazon Bedrock. You need working AWS credentials.

The project supports two providers:

- **Amazon Bedrock** with Amazon Nova Lite, recommended for the hackathon.
- **Groq**, useful for local development when Bedrock access is unavailable.

## Choose a run mode

These are the three supported ways to use Muse:

- **Local Bedrock mode:** Python and the browser UI run on your computer, but
  the AI request is sent to Amazon Bedrock using your AWS credentials.
- **AWS mode:** Lambda runs the Python handler in AWS and exposes the browser UI
  through a Function URL. This is the mode used for the hackathon deployment.

Running locally with Bedrock still calls AWS; only the Python process stays on
your computer. AWS deployment moves that same process to Lambda.

| Mode | AI provider | Product data | Where the UI runs |
| --- | --- | --- | --- |
| Local demo | Bedrock or Groq | Mock catalog | Your computer |
| Local live search | Bedrock or Groq | SearchAPI | Your computer |
| AWS deployment | Bedrock | SearchAPI | Lambda Function URL |

## Prerequisites

- Python 3.10 or newer
- An AWS account with Bedrock access in `us-east-1` for Bedrock mode
- AWS CLI configured with valid credentials for Bedrock mode
- A SearchAPI.io key for live product results

Verify AWS access before starting:

```powershell
aws sts get-caller-identity
```

Temporary hackathon credentials expire. Refresh them from the AWS Access
Portal when this command stops working. Never commit credentials or API keys.

## Configure the project

There are two equivalent ways to configure application settings. Use either
one; do not copy real secrets into both places.

### Option 1: Set variables in the terminal

PowerShell values apply to the current terminal window only:

```powershell
$env:LLM_PROVIDER="bedrock"
$env:BEDROCK_MODEL_ID="amazon.nova-lite-v1:0"
$env:SHOPPING_TOOL_MODE="searchapi"
$env:SEARCHAPI_API_KEY="YOUR_SEARCHAPI_KEY"
```

Use `set NAME=value` in Windows Command Prompt or `export NAME=value` in
Linux/macOS Bash. The full commands are shown in the run sections below.

### Option 2: Create a `.env` file

Copy the safe template and fill in your local values:

```powershell
Copy-Item .env.example .env
notepad .env
```

The `.env` file is loaded automatically when the application starts. It is
ignored by git. Terminal variables take priority over matching `.env` values,
which is useful for temporarily changing a setting.

Do not put temporary AWS access keys in `.env`. Keep those in the AWS CLI
environment or an AWS profile because they expire. Never commit `.env` or paste
any real key into `.env.example`.

## Local AWS Bedrock setup

Install the project from the repository root. Start with mock products to
verify the UI and Bedrock connection before enabling live search.

### Windows PowerShell

```powershell
python -m pip install -e .
$env:LLM_PROVIDER="bedrock"
$env:BEDROCK_MODEL_ID="amazon.nova-lite-v1:0"
$env:SHOPPING_TOOL_MODE="mock"
$env:AWS_DEFAULT_REGION="us-east-1"
python -m shopping_agent.ui
```

### Windows Command Prompt

```cmd
python -m pip install -e .
set LLM_PROVIDER=bedrock
set BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
set SHOPPING_TOOL_MODE=mock
set AWS_DEFAULT_REGION=us-east-1
python -m shopping_agent.ui
```

### Linux or macOS

```bash
python3 -m pip install -e .
export LLM_PROVIDER=bedrock
export BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
export SHOPPING_TOOL_MODE=mock
export AWS_DEFAULT_REGION=us-east-1
python3 -m shopping_agent.ui
```

Open `http://127.0.0.1:8000` after the server starts. The AWS credentials must
already be available to the AWS CLI or environment. Temporary hackathon keys
expire, so refresh them from the AWS Access Portal when needed.

Stop the local server with `Ctrl+C`.

## Local AWS Bedrock with live SearchAPI products

SearchAPI is separate from AWS and requires its own API key. Use the same
Bedrock settings above, but change the product tool mode to `searchapi`.

### Windows PowerShell

```powershell
$env:LLM_PROVIDER="bedrock"
$env:BEDROCK_MODEL_ID="amazon.nova-lite-v1:0"
$env:SHOPPING_TOOL_MODE="searchapi"
$env:SEARCHAPI_API_KEY="YOUR_SEARCHAPI_KEY"
$env:SEARCHAPI_GL="sg"
$env:SEARCHAPI_HL="en"
python -m shopping_agent.ui
```

### Windows Command Prompt

```cmd
set LLM_PROVIDER=bedrock
set BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
set SHOPPING_TOOL_MODE=searchapi
set SEARCHAPI_API_KEY=YOUR_SEARCHAPI_KEY
set SEARCHAPI_GL=sg
set SEARCHAPI_HL=en
python -m shopping_agent.ui
```

### Linux or macOS

```bash
export LLM_PROVIDER=bedrock
export BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
export SHOPPING_TOOL_MODE=searchapi
export SEARCHAPI_API_KEY=YOUR_SEARCHAPI_KEY
export SEARCHAPI_GL=sg
export SEARCHAPI_HL=en
python3 -m shopping_agent.ui
```

The live integration searches and displays real product listings. It opens the
seller's product page; it does not perform authenticated marketplace checkout.

## Local Groq setup

AWS is not needed for this mode. Create a local `.env` file and keep it out of
git:

```env
GROQ_API_KEY=your_groq_key
GROQ_MODEL=your_groq_model
```

Then run the following commands.

### Windows PowerShell

```powershell
python -m pip install -e .
$env:LLM_PROVIDER="groq"
$env:SHOPPING_TOOL_MODE="mock"
python -m shopping_agent.ui
```

### Windows Command Prompt

```cmd
python -m pip install -e .
set LLM_PROVIDER=groq
set SHOPPING_TOOL_MODE=mock
python -m shopping_agent.ui
```

### Linux or macOS

```bash
python3 -m pip install -e .
export LLM_PROVIDER=groq
export SHOPPING_TOOL_MODE=mock
python3 -m shopping_agent.ui
```

## Automated mock flow

The integration tests replace the LLM, product search, reviews, and cart with
test-only deterministic adapters. They exercise the full graph without a key
or any external marketplace service.

```bash
python3 -m pip install -e '.[test]'
pytest
```

## Deploy to AWS Lambda

The AWS path uses Bedrock and a Lambda Function URL. Install the AWS SAM CLI,
make sure `aws sts get-caller-identity` succeeds, and run these commands from
the repository root:

```text
sam build
sam deploy --guided --region us-east-1
```

Accept the generated stack name and allow SAM to create the IAM role. At the
end, SAM prints the Function URL. Open that URL in a browser; the existing HTML
UI and `/api/chat` routes are handled by `shopping_agent.lambda_function`.

The template uses Amazon Nova Lite and live SearchAPI product search. During
`sam deploy --guided`, enter your SearchAPI.io key when SAM prompts for the
`SearchApiKey` parameter. It is marked `NoEcho` and is not printed in the
terminal. Groq is not needed for the AWS deployment.

The current Lambda adapter keeps sessions in the warm execution environment,
which is sufficient for a single-user demo. A multi-user production version
should move `ShoppingSession` state to DynamoDB.

To remove the demo stack later:

```text
sam delete --stack-name YOUR_STACK_NAME --region us-east-1
```

## Architecture

```text
User
  -> main.py
  -> LangGraph
  -> routing
  -> node
  -> updated state
  -> routing / node / ...
  -> assistant response
  -> main.py
  -> User
```

The graph loops internally until it needs another user answer or has completed
the requested action. `main.py` retains the returned state and passes it back
on the next user turn.

## Project structure

- `src/shopping_agent/main.py` — outer user ↔ agent conversation loop.
- `src/shopping_agent/agent/graph.py` — builds and compiles the LangGraph workflow.
- `src/shopping_agent/agent/state.py` — shared `ShoppingState` observed by all nodes and routing.
- `src/shopping_agent/agent/routing.py` — reactive next-action decision based on the current state.
- `src/shopping_agent/agent/nodes.py` — individual state-transition operations, such as search or clarification.
- `src/shopping_agent/llm/` — provider-specific LLM integrations; Groq is the current option.
- `src/shopping_agent/tools/` — external capabilities, currently mock search, review, and cart tools.
- `src/shopping_agent/processing/` — deterministic product processing, including hard-constraint filtering and ranking.
- `src/shopping_agent/schemas/` — typed data structures for requirements, products, and reviews.
- `src/shopping_agent/platforms/` — platform-specific marketplace implementations, to be added by adapters.
