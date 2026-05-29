# 📝 Changelog - Implementação de Segurança com .env

## v1.1.0 - Refatoração de Segurança (28/05/2026)

### ✨ Adições
- ✅ Suporte a variáveis de ambiente (`.env`)
- ✅ Arquivo `.gitignore` para proteção automática de credenciais
- ✅ Arquivo `.env.example` como template
- ✅ Validação de credenciais na inicialização
- ✅ Documentação de segurança em `SETUP.md`
- ✅ Dependency: `python-dotenv` adicionado

### 🔐 Melhorias de Segurança
- ❌ Removida API Key hardcoded do `config.json`
- 🔒 Credenciais agora isoladas em `.env` (não commitado)
- 📋 `config.json` agora serve apenas como exemplo/documentação
- ⚙️ Variáveis de ambiente carregadas via `python-dotenv`

### 🔄 Mudanças na Inicialização
```python
# Antes (v1.0)
system = GorilaLaudo()
# Lia credenciais de config.json

# Depois (v1.1)
system = GorilaLaudo(".env")
# Lê credenciais de .env, com validação
```

### 📁 Novos Arquivos
```
.env.example          ← Template de variáveis (público, sem credenciais)
.gitignore           ← Proteção automática de .env, __pycache__, etc
SETUP.md             ← Guia completo de configuração e segurança
```

### 🔧 Arquivos Atualizados
```
gerar_laudo.py       ← Agora lê do .env com validação
config.json          ← Simplificado, apenas referência
requirements.txt     ← Adicionado python-dotenv==1.0.0
GUIA_DE_USO.md       ← Atualizado com instruções de .env
```

### 🚨 Ações Necessárias do Usuário

#### Primeira vez (setup):
1. `cp .env.example .env`
2. Edite `.env` com sua API Key
3. `pip install -r requirements.txt` (instala python-dotenv)
4. `python gerar_laudo.py`

#### Próximas vezes:
- Nada! Sistema lê do `.env` automaticamente

### 📋 Variáveis de Ambiente Suportadas

```ini
# Obrigatório
GORILA_API_KEY=sua_chave_aqui

# Opcionais (têm padrão)
GORILA_API_BASE_URL=https://api.gorila.com.br
GORILA_API_TIMEOUT=30
COMPANY_NAME=Fatorial Capital
COMPANY_PHONE=+55 11 XXXX-XXXX
COMPANY_EMAIL=contato@fatorial.com.br
LOG_LEVEL=INFO
```

### ✅ O que está Protegido

Arquivo `.gitignore` previne que esses arquivos sejam commitados:

```
.env                  ← Sua chave secreta (PROTEGIDO!)
*.docx               ← Laudos gerados (PROTEGIDO!)
__pycache__/         ← Cache Python (PROTEGIDO!)
.venv/               ← Virtual env (PROTEGIDO!)
```

### ❌ O que PERMANECE Público (no Git)

```
.env.example         ← Template (sem valores reais)
config.json          ← Configurações públicas
asset_type_mapping.json
suitability_profiles.json
*.py, *.md           ← Código e documentação
```

### 🎯 Benefícios

1. **Segurança**: Credenciais nunca commitadas no Git
2. **Flexibilidade**: Cada desenvolvedor pode ter suas próprias credenciais
3. **Best Practice**: Segue padrão da indústria (12Factor App)
4. **CI/CD Ready**: Fácil de integrar em pipelines
5. **Validação**: Sistema verifica credenciais antes de usar

### 🔍 Verificação Pós-Atualização

Execute isto para confirmar que tudo está funcionando:

```bash
# 1. Verificar que .env não está no Git
git status
# Você NÃO deve ver ".env" na lista

# 2. Verificar que .gitignore existe
ls -la .gitignore

# 3. Testar o script
python gerar_laudo.py
# Deve pedir dados do cliente (significa que credenciais carregaram OK)
```

### 📚 Documentação

- **Leia PRIMEIRO**: `SETUP.md` - Setup de segurança e .env
- **Depois**: `GUIA_DE_USO.md` - Como usar o sistema
- **Referência**: `README.md` - Documentação técnica completa

### 🔗 Referências de Segurança

- [12 Factor App - Config](https://12factor.net/config)
- [OWASP - Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Python-dotenv Docs](https://python-dotenv.readthedocs.io/)

---

## v1.0.0 - Lançamento Inicial (27/05/2026)

Versão inicial do sistema com:
- Consumo de API Gorila
- Geração de laudos DOCX
- Mapeamento de tipos de segurança
- Análise de suitability

---

**Próximas melhorias planejadas:**
- [ ] Suporte a múltiplos perfis de acesso
- [ ] Dashboard web para visualização
- [ ] Exportação em PDF
- [ ] Integração com email automático
- [ ] Cache de dados para performance
