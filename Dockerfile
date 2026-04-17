FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=10000
EXPOSE $PORT
CMD gunicorn app_supabase:app --bind 0.0.0.0:$PORT
