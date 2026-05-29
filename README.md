# 📊 Gerador de Laudo de Carteira - Fatorial Capital

Sistema para gerar laudos de análise de carteira consumindo dados da API Gorila e comparando com perfis de suitability.

## 📋 Pré-requisitos

- Python 3.7+
- Conta ativa na Gorila com API Key
- Carteiras cadastradas na Gorila

## ⚙️ Instalação

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar credenciais

Editar `config.json` com sua API Key da Gorila:

```json
{
  "gorila_api": {
    "base_url": "https://api.gorila.com.br",
    "api_key": "SUA_API_KEY_AQUI",
    "timeout": 30
  },
  ...
}
```

## 🚀 Como Usar

### Execução básica

```bash
python gerar_laudo.py
```

### Fluxo de execução

1. **Sistema solicita dados do cliente:**
   - Nome do cliente
   - Perfil de investidor (Conservador, Moderado, Agressivo)

2. **Busca na API Gorila:**
   - Lista portfolios disponíveis
   - Você seleciona qual portfolio analisar
   - Busca posições, valores de mercado e PnL

3. **Mapeamento de tipos:**
   - Se encontrar um tipo de segurança não mapeado:
     - Mostra as classes disponíveis
     - Pede para você escolher a classe
     - Salva o mapeamento para futuras análises

4. **Geração do laudo:**
   - Calcula alocações
   - Compara com limites do suitability
   - Gera DOCX com análise completa

## 📁 Arquivos

### `gerar_laudo.py`
Arquivo principal com toda a lógica.

### `config.json`
Configurações de conexão com API Gorila e dados da empresa.

### `asset_type_mapping.json`
Mapeamento de `security.type` (da Gorila) para `classe de ativo` (Suitability).

**Como funciona:**
- Mantém registro de todos os tipos encontrados
- Se tipo não encontrado, pede confirmação do usuário
- Salva novos mapeamentos automaticamente

### `suitability_profiles.json`
Definições de limites para cada perfil de investidor:
- Conservador
- Moderado
- Agressivo

Cada perfil tem limites mín/máx para cada classe de ativo.

## 📊 Saídas

O sistema gera um arquivo DOCX com:

1. **Informações do cliente**
   - Nome, perfil, data, patrimônio, quantidade de posições

2. **Alocação da carteira**
   - Tabela com % de cada classe de ativo

3. **Análise de aderência ao perfil**
   - Comparação alocação atual vs limites
   - Status (dentro/fora do perfil)

4. **Detalhes das posições**
   - Nome, classe, valor, alocação %, PnL

5. **Conclusão**
   - Resumo e recomendações

## 🔍 Exemplo de Execução

```
================================================================================
GERADOR DE LAUDO DE CARTEIRA - API GORILA
================================================================================

Nome do cliente: Bernardo Araújo
Perfil de investidor: Moderado

3 portfolio(s) encontrado(s):
  1. Carteira Principal
  2. Carteira Especulativa
  3. Carteira de Renda Fixa

Escolha o número do portfolio: 1

⏳ Buscando dados do portfolio...
⏳ Processando 10 posições...

⚠️  TIPO DE SEGURANÇA NÃO MAPEADO
================================================================================
Type: SPX_PE_FUND
Nome: SPX PE I Advisory FIP Classe A - Trend PE XII FIC FIRF Simpl

Classes de ativo disponíveis:
  1. Renda fixa pública (Tesouro Direto / LFT / LTN / NTN-B)
  2. Fundos multimercado / macro
  3. Renda variável (fundos, ações, FIIs, ETFs, exceto de renda fixa)
  ...

Escolha o número (1-12) ou 'skip' para ignorar: 3

⏳ Gerando documento...

✅ Laudo gerado com sucesso!
📄 Arquivo: Laudo_Bernardo_Araujo_20260528.docx
```

## 🛠️ Troubleshooting

### Erro: "Missing or invalid API key"
- Verifique se a API Key está correta em `config.json`
- Verifique permissões da API Key na Gorila

### Erro: "Access to target portfolio denied"
- Verifique se o portfolio existe
- Verifique permissões de acesso

### Erro: "Nenhum portfolio encontrado"
- Verifique se existem portfolios cadastrados na Gorila
- Verifique autenticação

## 📝 Estrutura de Dados Esperada

### Posição (da API)
```json
{
  "id": "pos_123",
  "referenceDate": "2026-05-28",
  "security": {
    "id": 1234,
    "name": "SPX PE I",
    "type": "PRIVATE_EQUITY_FUND",
    "assetClass": "STOCKS"
  },
  "quantity": 100,
  "state": "OPEN"
}
```

### Valor de Mercado (da API)
```json
{
  "security": {
    "id": 1234
  },
  "value": 50000.00,
  "date": "2026-05-28"
}
```

## 🔐 Segurança

- Nunca comita `config.json` com API Key real
- Considere usar variáveis de ambiente para credenciais
- Proteja o arquivo `config.json` com permissões restritas

## 📧 Suporte

Para dúvidas ou problemas, contate a equipe de desenvolvimento.

---

**Versão:** 1.0  
**Data:** Maio 2026  
**Desenvolvido para:** Fatorial Capital
