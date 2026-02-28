FROM python:3.12-alpine

# Install dependencies including su-exec for privilege dropping
RUN pip install --no-cache-dir --no-compile requests flask \
    && apk add --no-cache su-exec shadow

WORKDIR /app
COPY nudgarr.py /app/nudgarr.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/config"]
EXPOSE 8085

# Set a persistent SECRET_KEY to survive container restarts (optional but recommended)
# ENV SECRET_KEY=your-random-secret-here

ENTRYPOINT ["/entrypoint.sh"]
