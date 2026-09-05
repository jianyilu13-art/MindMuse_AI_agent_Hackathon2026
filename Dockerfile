# Muse Shopping Agent — deploy image.
# Set SEARCHAPI_API_KEY as an environment variable on your host/PaaS to serve
# live Google Shopping results to all visitors from one key (never committed).
FROM python:3.11-slim

WORKDIR /app
COPY . .

# install the package + live search + the Groq LLM provider
RUN pip install --no-cache-dir -e ".[live,llm]"

# bind on all interfaces; the platform injects $PORT (defaults to 8000 locally)
ENV HOST=0.0.0.0
EXPOSE 8000

CMD ["python", "-m", "shopping_agent.ui"]
