FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

# Fly/local default: file DB. docker-compose overrides this with Postgres.
ENV DATABASE_URL=sqlite:///app/data/testnet.db
EXPOSE 8090

CMD ["python", "-m", "demo.run_testnet"]
