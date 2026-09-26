# ToolSmith sandbox (P2.1.2). Build: docker build -t toolsmith-sandbox:latest sandbox/
# The runner (backend/app/sandbox/runner.py) mounts the job dir read-only at /job and runs
#   docker run --network none --read-only --tmpfs /tmp --memory 512m --user sandbox ... python /job/bootstrap.py
# Only the packages in the tool-code allow-list are installed (TASKS §3.3).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp

RUN python -m pip install --no-cache-dir \
        "pandas==2.2.*" "numpy<2.2" "openpyxl==3.1.*" "beautifulsoup4==4.12.*" "lxml>=5" "plotly>=5.20"

RUN useradd --create-home --shell /usr/sbin/nologin sandbox
WORKDIR /job
USER sandbox

CMD ["python", "-c", "print('toolsmith sandbox: run through backend/app/sandbox/runner.py')"]
