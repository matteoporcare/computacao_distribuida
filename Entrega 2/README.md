Entrega 2 - Serviço de Agendamento (Flask) e teste de estresse

Arquivos:
- app.py             -> Serviço Flask (cria agendamentos, cientistas, telescópios)
- stress_test.py     -> Script que dispara 10 requisições concorrentes para demonstrar condição de corrida
- requirements.txt   -> Dependências Python

Como rodar:
1) Criar e ativar um virtualenv (recomendado)
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate

2) Instalar dependências
   pip install -r requirements.txt

3) Rodar o serviço
   python app.py

   Isso criará `agendamento.db`, `app.log` e `audit.log` no diretório atual.

4) Em outra janela, rodar o teste de estresse
   python stress_test.py

   Você deverá observar respostas múltiplas 201 e/ou 409 dependendo do timing.
   Verifique `agendamento.db` (sqlite) e os logs `app.log` e `audit.log` para ver os efeitos.
