import requests
import concurrent.futures
import json

FLASK_URL = "http://localhost:5000/agendamentos"

# Aqui estamos usando sempre o mesmo horário para gerar disputa
payload = {
    "cientista_id": 1,
    "telescopio_id": 1,
    "horario_inicio_utc": "2025-01-01T10:00:00Z",
    "horario_fim_utc": "2025-01-01T11:00:00Z"
}

def send_request(n):
    try:
        r = requests.post(FLASK_URL, json=payload, timeout=5)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def main():
    results = []

    print("Executando stress test com 10 requisições simultâneas...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_request, i) for i in range(10)]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    # Contabiliza resultados
    status_count = {}
    for status, _ in results:
        status_count[status] = status_count.get(status, 0) + 1

    print("\nResultados do teste:")
    for status, count in status_count.items():
        print(f"  {status}: {count} ocorrências")

    print("\nDetalhes:")
    for status, body in results:
        print(f"[{status}] {body}")

if __name__ == "__main__":
    main()
