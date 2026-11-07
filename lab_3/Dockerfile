FROM python:3.12-slim
WORKDIR /app
COPY . .
CMD ["sh", "-c", "python3 tests.py && python3 compiler.py examples/gcd.c --report && python3 build/generated.py"]
