import requests
from concurrent.futures import ThreadPoolExecutor
import time

BASE = "http://localhost:5000"

PAY = {
    "cientista_id": 1,
    "telescopio_id": 1,
    "horario_inicio_utc": "2025-01-01T00:00:00Z",
    "horario_fim_utc": "2025-01-01T02:00:00Z"
}

def test_basic():
    r = requests.get(f"{BASE}/time")
    assert r.status_code == 200

def test_concurrent():
    time.sleep(0.5)  # tempo para serviços ficarem de pé

    def p():
        return requests.post(f"{BASE}/agendamentos", json=PAY, timeout=5)

    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(p) for _ in range(10)]
        for f in futures:
            results.append(f.result())

    # extração dos códigos
    codes = [r.status_code for r in results]
    created = codes.count(201)
    conflicts = codes.count(409)

    # PRINTS VISÍVEIS NO TERMINAL
    print("\n=== RESULTADO DO TESTE DE CONCORRÊNCIA ===")
    print("Códigos retornados:", codes)
    print("Criados (201):", created)
    print("Conflitos (409):", conflicts)
    print("==========================================\n")

    assert created == 1
    assert conflicts == 9
