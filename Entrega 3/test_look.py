import requests, time

COORD = "http://localhost:3000"
resource = "telescopio-1_2025-01-01T10:00:00Z"

print("POST /lock")
r = requests.post(f"{COORD}/lock", json={"resource": resource, "ttl_ms": 10000}, timeout=2)
print(r.status_code, r.text)

print("POST /lock (segunda tentativa deve retornar 409)")
r = requests.post(f"{COORD}/lock", json={"resource": resource, "ttl_ms": 10000}, timeout=2)
print(r.status_code, r.text)

print("POST /unlock")
# se o primeiro POST devolveu JSON com owner, use-o; senão manda sem owner
try:
    owner = r.json().get("owner")
except:
    owner = None

r2 = requests.post(f"{COORD}/unlock", json={"resource": resource, "owner": owner}, timeout=2)
print(r2.status_code, r2.text)
