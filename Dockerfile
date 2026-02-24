FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY nudgarr.py /app/nudgarr.py
VOLUME ["/config"]
ENTRYPOINT ["python","/app/nudgarr.py"]
