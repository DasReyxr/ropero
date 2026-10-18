sqlite3 ropero.db

CREATE TABLE prendas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    foto      TEXT NOT NULL UNIQUE,
    color     TEXT NOT NULL,
    temporada TEXT NOT NULL
);


# Create Docker

scp -P 8022 -r ropero/src u0_a298@100.99.81.64:~/ropero/

udocker pull python:3.12-slim
udocker create --name=ropero-py python:3.12-slim
udocker setup --execmode=F1 ropero-py   