# The opportunity site (opportunity.sustenaut.eu). Build from the repo root:
#   podman build -f opportunity-site/Dockerfile -t opportunity-site .
# oauth2-proxy in front of the site handles the login and passes the email on
# (opportunity-site/opportunity/auth.py). The cards are not baked in: the site
# clones business-plan main into OPPORTUNITY_REPO_DIR and pulls it once a minute.
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8080 \
    PYTHONPATH=/app OPPORTUNITY_REPO_DIR=/data/business-plan \
    OPPORTUNITY_REPO_URL=https://github.com/schryer/business-plan.git
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock opportunity-site/requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt -c /tmp/requirements.lock
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app /data
# bizplan reads the cards and works out the matrix columns, as `make check` does.
COPY --chown=app bizplan/ bizplan/
COPY --chown=app opportunity-site/opportunity/ opportunity/
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn opportunity.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
