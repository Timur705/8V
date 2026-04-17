FROM python:3.12-slim

WORKDIR /app

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Порт, который будет слушать приложение (Render требует 10000)
ENV PORT=10000
EXPOSE $PORT

# Запускаем Gunicorn
CMD gunicorn app_supabase:app --bind 0.0.0.0:$PORT