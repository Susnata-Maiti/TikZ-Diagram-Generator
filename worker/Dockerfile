FROM python:3.11-slim

# Install TeX Live (full) for pdflatex compilation
# Uses the lightweight texlive-latex-extra set; swap for texlive-full if needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-science \
    texlive-pictures \
    lmodern \
    fontconfig \
    fonts-texgyre \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY backend/ ./backend/
COPY worker/  ./worker/

# Optional: install Times New Roman font (requires font file)
# COPY fonts/times.ttf /usr/share/fonts/truetype/msttcorefonts/
# RUN fc-cache -fv

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info"]
