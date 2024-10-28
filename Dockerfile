FROM python:3.12

RUN pip install poetry

WORKDIR /app

COPY . /app

RUN poetry config virtualenvs.create false && poetry install

EXPOSE 8000

ENTRYPOINT ["poetry", "run"]
