# MODELOS.md

> Objetivo: definir as entidades que serão usadas pelo Serviço de Agendamento.

## Entidades principais

### Cientista
- **Tabela**: `cientistas`
- **Campos**:
  - `id` (integer, PK, autoincrement)
  - `nome` (string, obrigatório)
  - `email` (string, único, obrigatório)
  - `instituicao` (string, opcional)
  - `criado_em` (timestamp UTC)
  - `atualizado_em` (timestamp UTC)

### Telescopio
- **Tabela**: `telescopios`
- **Campos**:
  - `id` (integer, PK)
  - `nome` (string, único, ex: `Hubble-Acad`)
  - `timezone` (string, IANA, opcional)
  - `disponivel` (boolean)
  - `criado_em`, `atualizado_em`

### Agendamento
- **Tabela**: `agendamentos`
- **Campos**:
  - `id` (integer, PK)
  - `cientista_id` (FK -> cientistas.id)
  - `telescopio_id` (FK -> telescopios.id)
  - `horario_inicio_utc` (timestamp UTC)
  - `horario_fim_utc` (timestamp UTC)
  - `status` (enum: `PENDING`, `CONFIRMED`, `CANCELLED`, `REJECTED`)
  - `criado_em`, `atualizado_em`

- **Regras de negócio**:
  - `horario_inicio_utc` < `horario_fim_utc`.
  - Duração mínima e máxima configuráveis (ex: min 1 min, max 6 horas).
  - Não podem existir dois agendamentos com sobreposição para o mesmo `telescopio_id` quando `status = CONFIRMED`.

### Lock (conceito, não necessariamente persistido em BD)
- Será gerenciado pelo **serviço coordenador** (Node.js).
- Identificador do recurso: `telescopio-{id}_{horario_inicio_utc}` (string).
- O lock é temporário e mantido pelo coordenador até a liberação (unlock).
