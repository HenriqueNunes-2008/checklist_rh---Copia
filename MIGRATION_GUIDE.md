# Documentação de Migração e Atualizações - Checklist RH

Este documento descreve as alterações arquiteturais para migração do Supabase para infraestrutura própria na **Magalu Cloud (Ubuntu)** utilizando **PostgreSQL** e **SQLAlchemy**.

## 1. Migração de Banco de Dados: Supabase -> PostgreSQL (SQLAlchemy)

A aplicação agora utiliza o **SQLAlchemy** como ORM. Isso elimina a dependência da API do Supabase e permite o uso de qualquer banco SQL (PostgreSQL recomendado).

### Estrutura de Classes (Models)
As tabelas foram migradas para o arquivo `app.py` sob as classes `Usuario`, `Funcionario`, `ChecklistModelo` e `ChecklistResposta`.
A tabela `ChecklistModelo` agora conta com o campo `responsavel`, permitindo a segregação de tarefas entre RH e Administrativo.

### Vantagens:
- Consultas mais rápidas e tipadas.
- Facilidade de migração entre diferentes provedores de SQL.
- Maior segurança com controle transacional (`db.session.rollback()`).

---

## 2. Fluxo de Aprovação de Usuário

Implementamos uma trava de segurança no `app.py`:

1.  **Cadastro**: Novos usuários são criados com `ativo=False`.
2.  **Login**: Bloqueia o acesso caso `ativo` seja falso, exibindo mensagem de espera.
3.  **Aprovação**: Deve ser feita manualmente no banco de dados (via `psql` ou ferramenta gráfica) alterando a coluna `ativo` para `true`.

---

## 3. Controle Granular de Responsabilidade

Implementamos uma lógica de permissão por item:
1. **Atribuição**: No cadastro de modelos, o RH define item a item quem é o responsável pela validação (RH ou Administrativo).
2. **Visibilidade**: O usuário com cargo "Administrativo" visualiza apenas os itens atribuídos a ele, evitando exposição de dados sensíveis (ex: benefícios).
3. **Segurança**: O backend valida se o usuário tem permissão para alterar o status de um item específico durante o salvamento.

---

## 3. Guia de Implantação: Magalu Cloud (Ubuntu)

Siga estes passos para configurar sua instância Ubuntu na Magalu Cloud:

### 3.1. Preparação do Sistema
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv libpq-dev postgresql postgresql-contrib nginx -y
```

### 3.2. Configuração do Ambiente Python
```bash
cd /caminho/do/projeto
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3.3. Configuração do PostgreSQL (Local na VM)
Se não estiver usando um banco gerenciado, configure localmente:
```bash
sudo -u postgres psql
# No prompt do PSQL:
CREATE DATABASE rh_db;
CREATE USER checklist_user WITH PASSWORD 'sua_senha_forte';
GRANT ALL PRIVILEGES ON DATABASE rh_db TO checklist_user;
-- Caso a tabela já exista, execute para atualizar a estrutura:
-- ALTER TABLE checklist_modelos ADD COLUMN responsavel VARCHAR(50) DEFAULT 'RH';
\q
```

### 3.4. Variáveis de Ambiente
Crie um arquivo `.env` ou adicione ao `~/.bashrc`:
```bash
export DATABASE_URL="postgresql://checklist_user:sua_senha_forte@localhost/checklist_db"
export FLASK_SECRET_KEY="sua_chave_secreta"
```

## 5. Próximos Passos Recomendados

1.  Instalar `flask-sqlalchemy` e `psycopg2-binary`.
2.  Criar script de migração de dados do Supabase para o novo PostgreSQL.
3.  Ajustar as rotas no `app.py` para utilizar `db.session` em vez de `supabase.table`.
4.  Configurar o Dashboard para que o RH possa ver uma lista de usuários "Pendentes de Ativação".

+### 3.5. Execução em Produção (Gunicorn + Systemd) +Crie um arquivo de serviço: sudo nano /etc/systemd/system/checklist.service +```ini +[Unit] +Description=Gunicorn instance to serve Checklist RH +After=network.target

-1. Instalar flask-sqlalchemy e psycopg2-binary. -2. Criar script de migração de dados do Supabase para o novo PostgreSQL. -3. Ajustar as rotas no app.py para utilizar db.session em vez de supabase.table. -4. Configurar o Dashboard para que o RH possa ver uma lista de usuários "Pendentes de Ativação". +[Service] +User=ubuntu +Group=www-data +WorkingDirectory=/home/ubuntu/checklist_rh +Environment="PATH=/home/ubuntu/checklist_rh/venv/bin" +Environment="DATABASE_URL=postgresql://checklist_user:senha@localhost/checklist_db" +ExecStart=/home/ubuntu/checklist_rh/venv/bin/gunicorn --workers 3 --bind unix:checklist.sock -m 007 app:app + +[Install] +WantedBy=multi-user.target +``` + +### 3.6. Proxy Reverso (Nginx) +Configure o Nginx para apontar para o socket do Gunicorn para melhor performance e suporte a HTTPS.

+## 4. Notas Importantes de Código + +- Segurança: O código agora utiliza generate_password_hash e check_password_hash de forma nativa com SQLAlchemy. +- Datas: O campo data_admissao agora é tratado como objeto date do Python, garantindo consistência no banco. +- Migração Inicial: Ao rodar o app pela primeira vez em um banco vazio, o comando db.create_all() (dentro do if __name__ == '__main__':) criará as tabelas automaticamente. + +--- Documentação gerada para suporte à migração de infraestrutura e lógica de negócio.


### O que mudou na prática:
*   **Segurança de Acesso**: O login agora verifica se o usuário está `ativo`. No cadastro, o usuário é salvo como `ativo=False`.
*   **Confiabilidade**: O uso de `db.session.rollback()` em blocos `except` garante que, se houver um erro ao salvar o funcionário ou o checklist, nada seja gravado pela metade no banco de dados.
*   **Infraestrutura**: As orientações para Magalu Cloud (Ubuntu) incluem a criação de um serviço `systemd`, que garante que sua aplicação reinicie automaticamente caso o servidor caia.

<!--
[PROMPT_SUGGESTION]Como posso criar um comando personalizado no Flask para ativar usuários via terminal no servidor Ubuntu?[/PROMPT_SUGGESTION]
[PROMPT_SUGGESTION]Como configurar o Nginx na Magalu Cloud para servir arquivos estáticos e suportar HTTPS (SSL)?[/PROMPT_SUGGESTION]
-->

---
*Documentação gerada para suporte à migração de infraestrutura e lógica de negócio.*