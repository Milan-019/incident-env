# ============================================================
# IncidentEnv — Dockerfile (place at project ROOT)
# ============================================================

FROM ghcr.io/meta-pytorch/openenv-base:latest

# ---- Working directory -------------------------------------
WORKDIR /app/env

# ---- Copy project files ------------------------------------
COPY . /app/env/

# ---- Install dependencies ----------------------------------
# openenv-core is the correct package (not openenv)
RUN pip install --no-cache-dir \
        "openenv-core[core]>=0.2.2" \
        fastapi>=0.115.0 \
        uvicorn>=0.24.0 \
        openai>=1.0.0 \
        pydantic>=2.0.0 \
        python-dotenv>=1.0.0

# ---- Verify openenv.core is importable ---------------------
RUN python -c "from openenv.core.env_server import Environment; print('openenv.core OK')"

# ---- Environment variables (Groq) --------------------------
ENV API_BASE_URL="https://api.groq.com/openai/v1"
ENV MODEL_NAME="llama-3.1-8b-instant"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/env

# ---- Expose port -------------------------------------------
EXPOSE 7860

# ---- Healthcheck -------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# ---- Start server ------------------------------------------
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]