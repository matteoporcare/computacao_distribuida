# LOGGING.md

> Objetivo: padronizar o formato dos logs de auditoria e logs de aplicação para tornar os eventos auditáveis e machine-readable.

## Formato de Log de Auditoria (JSON — imutável)
- **Formato padrão** (uma linha JSON por evento):
```json
{
  "timestamp_utc": "2025-10-26T18:00:05.123Z",
  "level": "AUDIT",
  "event_type": "AGENDAMENTO_CRIADO",
  "service": "servico-agendamento",
  "details": {
    "agendamento_id": 123,
    "cientista_id": 7,
    "telescopio_id": 1,
    "horario_inicio_utc": "2025-12-01T03:00:00Z"
  }
}
```
- **Campos recomendados**:
  - `timestamp_utc` (ISO 8601 UTC, millisecond precision)
  - `level` (`AUDIT`, `INFO`, `WARNING`, `ERROR`)
  - `event_type` (string, uppercase underscore)
  - `service` (identificador do serviço)
  - `details` (objeto livre com campos de negócio)

## Exemplo de Logs de Aplicação (plain text / console)
- Linha exemplo (INFO):
```
INFO:2025-10-26T18:00:04.500Z:servico-agendamento:Requisição recebida para POST /agendamentos
```
- Sequência esperada durante uma criação bem-sucedida:
  1. INFO: Requisição recebida para POST /agendamentos
  2. INFO: Tentando adquirir lock para o recurso X
  3. INFO: Lock adquirido com sucesso
  4. INFO: Iniciando verificação de conflito no BD
  5. INFO: Salvando novo agendamento no BD
  6. AUDIT: (linha JSON) AGENDAMENTO_CRIADO
  7. INFO: Liberando lock para o recurso X

## Onde escrever os logs
- **app.log** — logs de aplicação e audit (ambos podem conviver, mas recomenda-se escrever audit em formato JSON em arquivo separado para facilitar ingestão em ELK / Splunk).

## Boas práticas
- Timestamp sempre em UTC.
- Logs de auditoria **não devem** ser truncados nem sobrescritos — preferir append-only e rotação baseada em data/tamanho.
- Logs de audit devem conter identificação suficiente para rastrear pedidos (ex: request_id, cientista_id) quando aplicável.
