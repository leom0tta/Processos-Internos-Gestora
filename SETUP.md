# 🔐 Configuração Segura com .env

Este projeto usa variáveis de ambiente (`.env`) para armazenar credenciais de forma **segura e privada**.

## ⚠️ Segurança

- **Nunca** commit do `.env` (arquivo de credenciais)
- O arquivo `.gitignore` **protege automaticamente** o `.env`
- Sempre use `.env.example` como base
- Cada desenvolvedor tem seu próprio `.env` local

## 📋 Passo a Passo

### 1. Copiar template do .env

```bash
# No diretório do projeto
cp .env.example .env
```

Ou simplesmente copie o arquivo:
- De: `.env.example`
- Para: `.env`

### 2. Editar .env com suas credenciais

Abra o arquivo `.env` com um editor de texto:

```ini
# ============================================================================
# CONFIGURAÇÕES DA API GORILA
# ============================================================================
GORILA_API_KEY=sua_api_key_aqui          ← SUBSTITUA AQUI!
GORILA_API_BASE_URL=https://api.gorila.com.br
GORILA_API_TIMEOUT=30

# ============================================================================
# CONFIGURAÇÕES DA EMPRESA
# ============================================================================
COMPANY_NAME=Fatorial Capital             ← CUSTOMIZE CONFORME NECESSÁRIO
COMPANY_PHONE=+55 11 XXXX-XXXX           ← COLOQUE SEU TELEFONE
COMPANY_EMAIL=contato@fatorial.com.br    ← COLOQUE SEU EMAIL

# ============================================================================
# CONFIGURAÇÕES DE LOG
# ============================================================================
LOG_LEVEL=INFO
```

### 3. Onde obter a API Key?

1. Acesse sua conta Gorila: https://gorila.com.br
2. Clique em **Configurações** ou **Settings**
3. Procure por **Integrações** ou **Integrations**
4. Selecione **API Keys** ou **API Tokens**
5. Crie ou copie uma chave existente
6. Cole em `GORILA_API_KEY=` no arquivo `.env`

Exemplo de como fica preenchido:
```ini
GORILA_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 4. Instalar dependências

```bash
pip install -r requirements.txt
```

Isso instala o `python-dotenv` que é responsável por ler o `.env`.

### 5. Testar configuração

Execute o script:
```bash
python gerar_laudo.py
```

Se tudo estiver correto, o sistema vai:
1. ✅ Carregar as variáveis do `.env`
2. ✅ Validar a API Key
3. ✅ Pedir dados do cliente

Se houver erro:
```
❌ Erro: GORILA_API_KEY não configurada!
   Edite o arquivo .env e configure sua chave de API da Gorila
```

Significa que você precisa editar o `.env` com a chave correta.

## 🔍 O que está protegido?

Arquivo `.gitignore` protege automaticamente:

```
.env                          ← Seu arquivo de credenciais
.env.local                    ← Variações locais
.env.*.local                  ← Variações por ambiente
Laudo_*.docx                  ← Laudos gerados
*.docx                        ← Qualquer documento Word
```

**O que NÃO está protegido** (são públicos no Git):
```
.env.example                  ← Template (sem valores reais)
config.json                   ← Configurações públicas
asset_type_mapping.json       ← Mapeamentos
suitability_profiles.json     ← Regras de suitability
```

## 🚀 Workflow de Desenvolvimento

### Primeira execução (setup)
```bash
# 1. Clone ou baixe o projeto
# 2. Copie o template
cp .env.example .env

# 3. Edite e configure
# (abra .env em seu editor favorito e preencha GORILA_API_KEY)

# 4. Instale dependências
pip install -r requirements.txt

# 5. Teste
python gerar_laudo.py
```

### Execuções seguintes
```bash
# Só execute (credenciais já estão em .env)
python gerar_laudo.py
```

## 📦 Se trabalha em equipe

### Novo desenvolvedor entra no projeto:
```bash
# 1. Clone o repositório
git clone https://github.com/seu-repo.git
cd seu-repo

# 2. Crie seu próprio .env
cp .env.example .env

# 3. Peça a chave API ao gerente do projeto
# (Não tira do Git, ele não está lá!)

# 4. Cole a chave em seu .env local

# 5. Pronto! Seu .env é privado
# (Git ignora automaticamente via .gitignore)
```

### O que acontece quando faz git push?
```
✓ Código (.py, .json) é enviado
✓ Documentação (.md) é enviada
✗ .env é IGNORADO (não sobe no Git!)
✗ Laudos gerados (.docx) são IGNORADOS
✗ Cache Python (__pycache__) é IGNORADO
```

## 🔐 Variáveis Disponíveis

| Variável | Obrigatório | Padrão | Uso |
|----------|-------------|--------|-----|
| `GORILA_API_KEY` | ✅ SIM | - | Autenticação na API Gorila |
| `GORILA_API_BASE_URL` | ❌ Não | `https://api.gorila.com.br` | URL base da API |
| `GORILA_API_TIMEOUT` | ❌ Não | `30` | Timeout das requisições (segundos) |
| `COMPANY_NAME` | ❌ Não | `Fatorial Capital` | Nome da empresa no laudo |
| `COMPANY_PHONE` | ❌ Não | `+55 11 XXXX-XXXX` | Telefone no laudo |
| `COMPANY_EMAIL` | ❌ Não | `contato@fatorial.com.br` | Email no laudo |
| `LOG_LEVEL` | ❌ Não | `INFO` | Nível de log (DEBUG, INFO, WARNING, ERROR) |

## 🛠️ Troubleshooting

### "Erro: Arquivo .env não encontrado"
```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

### "Erro: GORILA_API_KEY não configurada"
Abra o `.env` e verifique:
```ini
GORILA_API_KEY=sua_api_key_aqui  ← Ainda está com o padrão?
```
Mude para:
```ini
GORILA_API_KEY=eyJhbGc...  ← Sua chave real
```

### "ModuleNotFoundError: No module named 'dotenv'"
```bash
pip install python-dotenv
# Ou reinstale todas:
pip install -r requirements.txt
```

### Quero usar variáveis de ambiente do sistema?
O `python-dotenv` lê nesta ordem:
1. Arquivo `.env` (se existir)
2. Variáveis do sistema operacional
3. Padrão do código

Então você pode também fazer:
```bash
# Linux/Mac
export GORILA_API_KEY=sua_chave_aqui
python gerar_laudo.py

# Windows (PowerShell)
$env:GORILA_API_KEY="sua_chave_aqui"
python gerar_laudo.py

# Windows (CMD)
set GORILA_API_KEY=sua_chave_aqui
python gerar_laudo.py
```

## 📝 Boas Práticas

✅ **FAÇA:**
- Copie `.env.example` para `.env`
- Preencha `.env` com suas credenciais reais
- Mantenha `.env.example` sem credenciais
- Adicione novos parâmetros em ambos os arquivos
- Use nomes descritivos: `EMPRESA_API_KEY`, não `key`

❌ **NÃO FAÇA:**
- Commitar `.env` no Git
- Hardcoder credenciais no código `.py`
- Compartilhar `.env` por email
- Deixar credenciais em comentários
- Usar credenciais de produção em desenvolvimento

## 🔄 Adicionar nova variável

Se precisar de uma nova configuração:

### 1. Adicione em `.env.example`:
```ini
NOVA_VARIAVEL=valor_padrao
```

### 2. Adicione em `.env` (seu arquivo local):
```ini
NOVA_VARIAVEL=seu_valor_real
```

### 3. Use no código:
```python
valor = os.getenv('NOVA_VARIAVEL', 'valor_padrao')
```

## 📚 Referências

- [Python-dotenv Documentation](https://python-dotenv.readthedocs.io/)
- [12 Factor App - Config](https://12factor.net/config)
- [Git Ignore Documentation](https://git-scm.com/docs/gitignore)

---

**Próximo passo:** [GUIA_DE_USO.md](GUIA_DE_USO.md)
