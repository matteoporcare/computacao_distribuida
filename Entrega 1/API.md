# API.md

> Convenção: todas as datas/hora no payload usam **ISO 8601 UTC** (ex: `2025-12-01T03:00:00Z`).

## Prefixo base
- Base URL (exemplo local): `http://localhost:5000`

## Endpoints principais

### GET /time
- **Descrição**: retorna o tempo oficial do servidor (fonte da verdade) — usado pelo cliente para sincronizar relógio.
- **Resposta 200**:
```json
{
  "server_time_utc": "2025-10-26T18:00:05.123Z",
  "links": [{ "rel": "self", "href": "/time" }]
}
```

### POST /cientistas
- **Descrição**: cria um cientista.
- **Body**:
```json
{ "nome": "Marie Curie", "email": "marie@example.com", "instituicao": "Univ X" }
```
- **Resposta 201**:
```json
{
  "id": 7,
  "nome": "Marie Curie",
  "email": "marie@example.com",
  "links": [
    { "rel": "self", "href": "/cientistas/7" },
    { "rel": "agendamentos", "href": "/cientistas/7/agendamentos" }
  ]
}
```

### GET /telescopios
- **Descrição**: lista telescópios disponíveis.
- **Resposta 200**: lista com HATEOAS links para cada telescópio.

### POST /agendamentos
- **Descrição**: tenta criar um agendamento — **fluxo coordenado** oculta a complexidade do lock (o Flask chamará o coordenador antes de tocar no BD).
- **Body**:
```json
{
  "cientista_id": 7,
  "telescopio_id": 1,
  "horario_inicio_utc": "2025-12-01T03:00:00Z",
  "horario_fim_utc": "2025-12-01T03:05:00Z",
  "client_timestamp_utc": "2025-12-01T02:59:59.500Z" // opcional
}
```
- **Possíveis respostas**:
  - `201 Created` — sucesso. Corpo contém o recurso criado e links HATEOAS.
  - `409 Conflict` — recurso ocupado / lock negado. Corpo indica motivo e link para `GET /agendamentos?telescopio=1&from=...`.
  - `400 Bad Request` — validação falhou.

- **Resposta 201 (exemplo)**:
```json
{
  "id": 123,
  "cientista_id": 7,
  "telescopio_id": 1,
  "horario_inicio_utc": "2025-12-01T03:00:00Z",
  "horario_fim_utc": "2025-12-01T03:05:00Z",
  "status": "CONFIRMED",
  "links": [
    { "rel": "self", "href": "/agendamentos/123" },
    { "rel": "cancel", "method": "POST", "href": "/agendamentos/123/cancel" },
    { "rel": "telescopio", "href": "/telescopios/1" }
  ]
}
```

### GET /agendamentos/{id}
- **Descrição**: retorna detalhe do agendamento com links para ações possíveis (HATEOAS), ex: cancelar.

### POST /agendamentos/{id}/cancel
- **Descrição**: cancela um agendamento — gera log de auditoria `AGENDAMENTO_CANCELADO`.
- **Resposta 200**: agendamento com `status: CANCELLED` e links.

### Endpoints auxiliares (coordenação)
> Observação: esses endpoints pertencem ao **serviço coordenador (Node.js)**; aqui apenas documentamos a interface usada pelo Cérebro (Flask).

#### POST /lock
- **Body**:
```json
{ "resource": "telescopio-1_2025-12-01T03:00:00Z", "ttl_ms": 30000 }
```
- **Respostas**:
  - `200 OK` — lock concedido.
  - `409 Conflict` — lock não concedido (já ocupado). Resposta deve indicar `owner` ou `since` opcional.

#### POST /unlock
- **Body**:
```json
{ "resource": "telescopio-1_2025-12-01T03:00:00Z" }
```
- **Resposta 200** — lock liberado.
