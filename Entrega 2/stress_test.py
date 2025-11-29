# stress_test.py
# Script de teste de estresse que envia 10 requisições simultâneas tentando agendar o mesmo slot
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

URL = "http://127.0.0.1:5000/agendamentos"
payload = {
    "cientista_id": 1,
    "telescopio_id": 1,
    "horario_inicio_utc": "2025-12-01T03:00:00Z",
    "horario_fim_utc": "2025-12-01T03:05:00Z"
}

def send():
    r = requests.post(URL, json=payload)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

def main():
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(send) for _ in range(10)]
        for f in as_completed(futures):
            code, body = f.result()
            print(code, body)

if __name__ == '__main__':
    main()
