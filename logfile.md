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

# Generate Certificate
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -subj "/CN=Ropero CA" -out ca.pem

openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/CN=100.99.81.64" -out server.csr
printf "subjectAltName=IP:100.99.81.64\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n" > ext.cnf
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out server.pem -days 825 -sha256 -extfile ext.cnf