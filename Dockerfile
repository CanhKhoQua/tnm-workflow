FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONPATH=/app/scripts
ENV PYTHONIOENCODING=utf-8
EXPOSE 5000
CMD ["python", "-u", "scripts/webapp/app.py"]
