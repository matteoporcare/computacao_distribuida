import requests
import concurrent.futures
import json
import time

API_URL = "http://localhost:5000/agendamentos"

payload = {
    "cientista_id": 1,
    "telescopio_id": 1,
    "horario_inicio_utc": "2025-01-01T10:00:00Z",
    "horario_fim_utc": "2025-01-01T11:00:00Z"
}

def send_request(n):
    try:
        r = requests.post(API_URL, json=payload, timeout=5)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def main():
    print("Executando stress test com 10 requisições simultâneas...\n")
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_request, i) for i in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Sumário
    print("\n===== RESULTADO RESUMIDO =====")
    counts = {}
    for status, _ in results:
        counts[status] = counts.get(status, 0) + 1

    for status, count in counts.items():
        print(f"{status}: {count}")

    print("\n===== DETALHES =====")
    for status, body in results:
        print(f"[{status}] {body}")

if __name__ == "__main__":
    main()
