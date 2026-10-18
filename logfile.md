sqlite3 ropero.db

CREATE TABLE prendas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    foto      TEXT NOT NULL UNIQUE,
    color     TEXT NOT NULL,
    temporada TEXT NOT NULL
);
