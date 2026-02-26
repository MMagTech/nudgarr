FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir --no-compile requests flask
COPY nudgarr.py /app/nudgarr.py
VOLUME ["/config"]
EXPOSE 8085
# Set a persistent SECRET_KEY to survive container restarts (optional but recommended)
# ENV SECRET_KEY=your-random-secret-here
ENTRYPOINT ["python","/app/nudgarr.py"]
