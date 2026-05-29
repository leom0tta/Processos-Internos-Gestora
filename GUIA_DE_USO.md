# 🚀 Guia de Uso - Sistema de Laudo de Carteira

## O que foi criado?

Um sistema Python completo que:
- ✅ Consome dados da API Gorila
- ✅ Mapeia tipos de segurança para classes de ativo
- ✅ Compara com perfis de suitability (Conservador, Moderado, Agressivo)
- ✅ Gera DOCX profissional com análise completa

## 📁 Arquivos Criados

Todos os arquivos estão na pasta:
`C:\Users\Lmotta\Fatorial Capital\Fatorial Capital - Documentos\Processos Internos\Laudo`

### Arquivos Principais:
1. **gerar_laudo.py** - Arquivo principal (execute este)
2. **config.json** - Credenciais da API Gorila (EDITAR COM SEUS DADOS)
3. **asset_type_mapping.json** - Mapeamento security.type → classe de ativo
4. **suitability_profiles.json** - Definições de limites por perfil
5. **requirements.txt** - Dependências Python
6. **README.md** - Documentação completa

## ⚡ Quick Start

### 1️⃣ Preparação (fazer uma vez)

```bash
# Navegar até a pasta
cd "C:\Users\Lmotta\Fatorial Capital\Fatorial Capital - Documentos\Processos Internos\Laudo"

# Instalar dependências
pip install -r requirements.txt
```

### 2️⃣ Configurar credenciais com .env

```bash
# Copiar template
cp .env.example .env
```

Editar ``.env``:
```ini
GORILA_API_KEY=sua_api_key_aqui    ← COLOQUE SUA CHAVE AQUI
COMPANY_NAME=Fatorial Capital      ← Customize conforme necessário
COMPANY_PHONE=+55 11 XXXX-XXXX
COMPANY_EMAIL=contato@fatorial.com.br
```

**Onde pegar a API Key?**
- Gorila → Configurações → Integrações → API Keys
- Copie a chave e cole em `GORILA_API_KEY=`

### 3️⃣ Executar

```bash
python gerar_laudo.py
```

Sistema vai pedir:
- Nome do cliente
- Perfil (Conservador, Moderado, Agressivo)
- Qual portfolio usar

## 🔄 Como Funciona

### Fluxo de Execução

```
┌─ Input do Usuário
│  ├─ Nome do cliente
│  └─ Perfil do investidor
│
├─ Conecta na Gorila API
│  ├─ Lista portfolios
│  ├─ Busca posições
│  ├─ Busca valores de mercado
│  └─ Busca PnL
│
├─ Processa Dados
│  ├─ Mapeia security.type → classe de ativo
│  ├─ Se tipo novo → pede confirmação do usuário
│  └─ Salva novo mapeamento automaticamente
│
├─ Calcula Métricas
│  ├─ Alocação por classe (%)
│  ├─ Patrimônio total
│  └─ Compara com limites do perfil
│
└─ Gera DOCX
   ├─ Informações do cliente
   ├─ Alocação da carteira
   ├─ Análise de aderência
   ├─ Detalhes das posições
   └─ Conclusão
```

### Tratamento de Tipos Não Mapeados

Se encontrar um tipo de segurança novo:

```
⚠️  TIPO DE SEGURANÇA NÃO MAPEADO
================================================================================
Type: NOVO_TIPO
Nome: Exemplo de Fundo

Classes de ativo disponíveis:
  1. Renda fixa pública (...)
  2. Fundos multimercado / macro
  3. Renda variável (...)
  ...

Escolha o número (1-12) ou 'skip' para ignorar: 
```

Você escolhe, e o sistema:
- Salva o mapeamento em `asset_type_mapping.json`
- Próximas análises usam esse mapeamento automaticamente
- Nunca pedirá novamente para esse tipo

## 📊 Saída Esperada

Um arquivo DOCX com nome: `Laudo_NomeDoCliente_DDMMYYYY.docx`

Contendo:
- Cabeçalho e rodapé
- Dados do cliente
- Tabela de alocação
- Análise de suitability (com cores: verde=dentro, vermelho=fora)
- Detalhes de cada posição
- Conclusão e recomendações

## 🎨 Exemplo de Saída

```
════════════════════════════════════════════════════════════════════════════

LAUDO DE ANÁLISE DE CARTEIRA

1. INFORMAÇÕES DO CLIENTE
┌─────────────────────────┬──────────────────────┐
│ Cliente                 │ Bernardo Araújo      │
│ Perfil de Investidor    │ Moderado             │
│ Data de Análise         │ 28/05/2026           │
│ Patrimônio Total        │ R$ 191.980,24        │
│ Número de Posições      │ 10                   │
└─────────────────────────┴──────────────────────┘

2. ALOCAÇÃO DA CARTEIRA
┌──────────────────────────────────────────┬──────────┐
│ Classe de Ativo                          │ Aloc. (%)│
├──────────────────────────────────────────┼──────────┤
│ Renda variável (PE Funds)                │ 80,76%   │
│ Inflação (CRA + Debenture)               │ 17,31%   │
│ Pós Fixado (DI Fund)                     │ 1,55%    │
└──────────────────────────────────────────┴──────────┘

3. ANÁLISE DE ADERÊNCIA AO PERFIL
Dentro do Perfil: 12 classes | Fora do Perfil: 0 classes

┌──────────────────────────────────────────┬────┬────┬────┬──────┐
│ Classe de Ativo                          │Atual│Min │Max │Status│
├──────────────────────────────────────────┼────┼────┼────┼──────┤
│ Renda variável (fundos, ações...)        │25% │ 0% │25% │  ✓  │
│ Fundos multimercado / macro              │ 5% │ 0% │30% │  ✓  │
│ ...                                      │... │... │... │ ... │
└──────────────────────────────────────────┴────┴────┴────┴──────┘

4. DETALHES DAS POSIÇÕES
┌──────────────────┬──────────────────┬────────┬─────────┬─────────┐
│ Ativo            │ Classe           │ Valor  │Alocação │  PnL    │
├──────────────────┼──────────────────┼────────┼─────────┼─────────┤
│ SPX PE I         │ Renda Variável   │ R$ ... │  9,31%  │ R$ ...  │
│ Vinci Capital    │ Renda Variável   │ R$ ... │  5,39%  │ R$ ...  │
│ ...              │ ...              │ ...    │  ...    │ ...     │
└──────────────────┴──────────────────┴────────┴─────────┴─────────┘

5. CONCLUSÃO
A carteira de Bernardo Araújo apresenta total aderência ao perfil de 
investidor 'Moderado', com todas as classes de ativos dentro dos limites 
estabelecidos.
```

## 🔧 Personalizações

### Mudar dados da empresa
Editar `.env`:
```ini
COMPANY_NAME=Meu Consultório
COMPANY_PHONE=+55 11 9999-9999
COMPANY_EMAIL=contato@exemplo.com
LOG_LEVEL=DEBUG  (para mais detalhes)
```

### Mudar API ou timeout
Editar `.env`:
```ini
GORILA_API_BASE_URL=https://api.gorila.com.br
GORILA_API_TIMEOUT=60  (aumentar se timeout com muitas posições)
```

### Mudar limites de suitability
Editar `suitability_profiles.json`:
```json
"Moderado": {
  "Renda variável (...)": {
    "min": 0.0,
    "max": 0.25,        ← Mude este valor
    "obs": "..."
  }
}
```

### Adicionar novo tipo de segurança
Editar `asset_type_mapping.json`:
```json
"mappings": {
  "MEU_NOVO_TIPO": "Classe de Ativo Correspondente",
  ...
}
```

## ❓ Perguntas Frequentes

**P: Onde pego a API Key?**
R: Na Gorila, em Configurações → Integrações → API Keys

**P: Posso ter múltiplas carteiras?**
R: Sim! A cada execução, o sistema lista os portfolios e você escolhe qual usar.

**P: O mapeamento é salvo?**
R: Sim! Fica em `asset_type_mapping.json` e é reutilizado automaticamente.

**P: Posso usar para vários clientes?**
R: Sim! É só executar novamente com outro nome de cliente.

**P: Dá pra exportar em outro formato?**
R: Atualmente só DOCX. Para adicionar PDF/Excel, faça PR ou contate desenvolvimento.

## 📝 Checklist de Setup

- [ ] Criar pasta de trabalho
- [ ] Copiar arquivos
- [ ] Instalar Python 3.7+
- [ ] Executar `pip install -r requirements.txt`
- [ ] Copiar `.env.example` para `.env`
- [ ] Editar `.env` com sua API Key Gorila (🔐 PROTEGIDO)
- [ ] Verificar que `.env` está no `.gitignore` (proteção automática)
- [ ] Testar primeira execução
- [ ] Documentar novos tipos de segurança encontrados

## 🐛 Troubleshooting

### "Arquivo .env não encontrado"
```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

### "GORILA_API_KEY não configurada"
Abra o `.env` e verifique:
```ini
GORILA_API_KEY=sua_api_key_aqui  # Mude para sua chave real
```

### "Módulo requests não encontrado"
```bash
pip install requests --break-system-packages
```

### "Módulo docx não encontrado"
```bash
pip install python-docx --break-system-packages
```

### "Módulo dotenv não encontrado"
```bash
pip install python-dotenv --break-system-packages
```

### "API Key inválida"
- Verifique em Gorila → Configurações → API Keys
- Copie exatamente (sem espaços antes/depois)
- Paste em `GORILA_API_KEY=` do seu `.env`

### "Portfolio não encontrado"
- Verifique se existe na Gorila
- Verifique permissões de acesso

### "Tipo de segurança não encontrado"
- O sistema vai pedir para mapear
- Escolha a classe mais apropriada
- Fica salvo automaticamente em `asset_type_mapping.json`

## 💡 Dicas

1. **Rodar em lote**: Crie um script que executa para vários clientes
2. **Integrar com email**: Envie DOCX automaticamente após geração
3. **Agendar**: Use Task Scheduler (Windows) para rodar automaticamente

## 📞 Suporte

Dúvidas? Contate Leo (3613leo@gmail.com)

---

**Versão:** 1.0  
**Data:** 28/05/2026  
**Status:** ✅ Pronto para Produção
