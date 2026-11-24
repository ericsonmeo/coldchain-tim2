\# Cold-Chain IoT Monitoring System – Team 2



\## Deskripsi

Sistem IoT untuk memantau kondisi penyimpanan cold-chain secara real-time menggunakan MQTT, Node-RED, dan InfluxDB.



Sistem memantau suhu, kelembapan, dan status pintu pada tiga chamber penyimpanan.



\## Arsitektur

\- \*\*MQTT Broker:\*\* Eclipse Mosquitto

\- \*\*Data Processing:\*\* Node-RED

\- \*\*Time-Series Database:\*\* InfluxDB 2

\- \*\*Simulator:\*\* Python dan Paho MQTT



\## Struktur Proyek

```text

coldchain-tim2/

├── mosquitto/

│   └── config/

├── nodered/

│   └── data/

├── simulator/

│   ├── coldchain\_simulator.py

│   └── requirements.txt

├── docker-compose.yml

├── .env.example

├── .gitignore

└── README.md

```



\## Perangkat yang Disimulasikan



| Device ID | Gedung | Ruang |

|---|---|---|

| cc-01 | bsd-a | gudang-a |

| cc-02 | bsd-a | gudang-a |

| cc-03 | bsd-a | gudang-b |



\## MQTT Topic

Format:

`kampus/{domain}/{gedung}/{ruang}/{device\_id}/{channel}`



Contoh:

`kampus/coldchain/bsd-a/gudang-a/cc-01/telemetry`



\## Persyaratan

\- Docker Desktop

\- Python

\- Git



\## Cara Menjalankan



\### 1. Clone repository

```bash

git clone https://github.com/ericsonmeo/coldchain-tim2.git

cd coldchain-tim2

```



\### 2. Konfigurasi environment

Salin `.env.example` menjadi `.env`, kemudian isi kredensial yang diperlukan.



\### 3. Jalankan infrastruktur

```bash

docker compose up -d

```



\### 4. Instal dependensi simulator

```bash

py -m pip install -r simulator/requirements.txt

```



\### 5. Jalankan simulator

```bash

py simulator/coldchain\_simulator.py

```



\## Akses Layanan

| Layanan | URL |

|---|---|

| Node-RED | http://localhost:1880 |

| InfluxDB | http://localhost:8086 |

| MQTT Broker | localhost:1883 |



\## Catatan Keamanan

\- Jangan mengunggah file `.env`.

\- Jangan membagikan token InfluxDB dan password MQTT.

\- Gunakan `.env.example` sebagai template konfigurasi.

