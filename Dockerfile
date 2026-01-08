FROM python:3.11

WORKDIR /app

COPY library_req.txt .

RUN pip install --no-cache-dir -r library_req.txt

COPY . .

EXPOSE 8501

CMD ["python", "main_louncher_docker.py"]
