FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir requests flask
COPY nudgarr.py /app/nudgarr.py
VOLUME ["/config"]
EXPOSE 8085
ENTRYPOINT ["python","/app/nudgarr.py"]
