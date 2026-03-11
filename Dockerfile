FROM python:3.12-alpine

# Upgrade all Alpine packages to pull latest security patches at build time
RUN apk upgrade --no-cache

# Install dependencies including su-exec for privilege dropping
RUN pip install --no-cache-dir --no-compile requests flask apprise croniter \
    && apk add --no-cache su-exec

WORKDIR /app
COPY main.py /app/main.py
COPY nudgarr/ /app/nudgarr/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/config"]
EXPOSE 8085

# Set a persistent SECRET_KEY to survive container restarts (optional but recommended)
# ENV SECRET_KEY=your-random-secret-here

ENTRYPOINT ["/entrypoint.sh"]
