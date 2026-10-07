FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

# Do not bake DATABASE_URL. Image ENV beats Fly secrets and pins sqlite forever.
# Local docker: -e DATABASE_URL=sqlite:///app/data/testnet.db
# Fly: fly mpg attach / fly secrets set DATABASE_URL=postgresql://...
EXPOSE 8090

CMD ["python", "-m", "demo.run_testnet"]
