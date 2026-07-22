#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cliente HTTP para a API Gorila Core
====================================
Encapsula as chamadas necessárias para importar posições de um extrato
Ion/Itaú para o Gorila via API.

Fluxo para CDB:
    1. criar_cdb(posicao) → security_id
    2. criar_transacao(portfolio_id, security_id, posicao) → transaction

Fluxo para Fundo / Previdência:
    1. buscar_ou_criar_fundo(posicao, cnpj, asset_class) → security_id
    2. criar_transacao(portfolio_id, security_id, posicao) → transaction
"""

import os
import re
import logging
from datetime import date
from urllib.parse import urlparse, parse_qs

import requests

logger = logging.getLogger(__name__)

GORILA_BASE  = "https://core.gorila.com.br"
ITAU_CNPJ    = "60701190000104"   # Itaú Unibanco S.A.


class GorilaError(Exception):
    """Erro de negócio da API Gorila (4xx, 5xx ou config faltando)."""
    pass


class GorilaClient:
    def __init__(self):
        self.api_key = os.getenv('GORILA_API_KEY', '').strip()
        if not self.api_key:
            raise GorilaError("GORILA_API_KEY não configurada no ambiente.")
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': self.api_key,
            'Content-Type':  'application/json',
        })

    # ── Helpers internos ───────────────────────────────────────────────────

    def _get(self, path, params=None):
        r = self.session.get(f"{GORILA_BASE}{path}", params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
        raise GorilaError(f"GET {path} → HTTP {r.status_code}: {r.text[:300]}")

    def _post(self, path, payload):
        r = self.session.post(f"{GORILA_BASE}{path}", json=payload, timeout=20)
        if r.status_code in (200, 201):
            return r.json()
        raise GorilaError(f"POST {path} → HTTP {r.status_code}: {r.text[:300]}")

    @staticmethod
    def _fmt_date(s):
        """Converte "DD/MM/YYYY" → "YYYY-MM-DD". Retorna None para "-"."""
        if not s or s == '-':
            return None
        d, m, y = s.split('/')
        return f"{y}-{m}-{d}"

    @staticmethod
    def _limpar_nome_fundo(nome):
        """Remove prefixo de código interno Ion: "(50636) EXCELLENCE RF" → "EXCELLENCE RF"."""
        return re.sub(r'^\(\d+\)\s*', '', nome).strip()

    @staticmethod
    def _limpar_cnpj(cnpj):
        """Remove caracteres não-numéricos do CNPJ."""
        return re.sub(r'\D', '', cnpj or '')

    # ── Securities ─────────────────────────────────────────────────────────

    def buscar_security(self, search_term, security_type=None):
        """Busca securities pelo termo (nome ou CNPJ). Retorna lista de items."""
        params = {'search': search_term, 'limit': 10}
        if security_type:
            params['securityType'] = security_type
        result = self._get('/securities', params)
        return result.get('items', result.get('data', []))

    def criar_cdb(self, posicao):
        """
        Cria um CDB CDI (FLOATING_RATE_BANKING_BOND) no Gorila.
        Retorna o security_id criado.
        """
        taxa_cdi   = posicao.get('taxa_cdi', 100) or 100
        multiplier = round(taxa_cdi / 100, 4)

        payload = {
            'type':                   'FLOATING_RATE_BANKING_BOND',
            'bankingBondType':        'CDB',
            'initialDate':            self._fmt_date(posicao['data_inicio']),
            'issuerId':               ITAU_CNPJ,
            'index':                  'CDI',
            'multiplier':             multiplier,
            'issuanceFaceValue':      1.0,
            'interestPaymentPeriod':  'BULLET',
        }
        venc = self._fmt_date(posicao.get('data_vencimento'))
        if venc:
            payload['maturityDate'] = venc

        # Remove nulos
        payload = {k: v for k, v in payload.items() if v is not None}
        result = self._post('/securities', payload)
        logger.info(f"CDB criado: id={result['id']} — {posicao['nome']}")
        return result['id']

    def buscar_ou_criar_fundo(self, posicao, cnpj=None, asset_class='MULTIMARKET'):
        """
        Tenta localizar o fundo no Gorila. Se não encontrar, cria com CNPJ.

        Estratégia de busca:
          1. Por CNPJ (mais preciso) se fornecido
          2. Por nome limpo
          3. Cria via POST /securities (requer CNPJ)

        Retorna o security_id.
        """
        nome_limpo = self._limpar_nome_fundo(posicao['nome'])
        cnpj_limpo = self._limpar_cnpj(cnpj) if cnpj else None

        # 1. Busca por CNPJ
        if cnpj_limpo and len(cnpj_limpo) == 14:
            items = self.buscar_security(cnpj_limpo, 'MANAGED_FUND')
            if items:
                logger.info(f"Fundo encontrado por CNPJ: id={items[0]['id']} — {nome_limpo}")
                return items[0]['id']

        # 2. Busca por nome
        items = self.buscar_security(nome_limpo, 'MANAGED_FUND')
        if len(items) == 1:
            logger.info(f"Fundo encontrado por nome: id={items[0]['id']} — {nome_limpo}")
            return items[0]['id']

        # 3. Cria (precisa de CNPJ válido)
        if not cnpj_limpo or len(cnpj_limpo) != 14:
            raise GorilaError(
                f"Fundo '{nome_limpo}' não encontrado na Gorila e CNPJ não fornecido (ou inválido). "
                "Informe o CNPJ do fundo para prosseguir."
            )

        initial_date = self._fmt_date(posicao.get('data_inicio'))
        payload = {
            'type':        'MANAGED_FUND',
            'cnpj':        cnpj_limpo,
            'initialDate': initial_date or str(date.today()),
            'assetClass':  asset_class,
            'name':        nome_limpo,
            'description': nome_limpo,
        }
        result = self._post('/securities', payload)
        logger.info(f"Fundo criado: id={result['id']} — {nome_limpo}")
        return result['id']

    # ── Consulta de posições existentes ───────────────────────────────────

    def listar_security_ids_com_transacao(self, portfolio_id, broker_id=None) -> dict:
        """
        Retorna dict {security_id: transaction_id} das transações do portfólio,
        paginando automaticamente.

        Se broker_id for fornecido (ex: ITAU_CNPJ), filtra pelo custodiante —
        útil para evitar falsos positivos quando o portfólio tem posições de
        múltiplos brokers (XP + Itaú, etc.).

        Usado no início do upload para saber quais ativos já existem,
        evitando duplicação de INITIAL_CUSTODY_ADJUSTMENT.
        """
        registrados = {}   # security_id (int) → transaction_id (str)
        page_token  = None

        while True:
            params = {'limit': 1000}
            if page_token:
                params['pageToken'] = page_token
            if broker_id:
                params['brokerId'] = broker_id   # filtro server-side (se a API suportar)

            result  = self._get(f'/portfolios/{portfolio_id}/transactions', params=params)
            records = result.get('records', [])

            for tx in records:
                # Filtro client-side por broker (garante mesmo que a API ignore o param)
                if broker_id:
                    broker_obj = tx.get('broker') or {}
                    tx_broker  = (
                        broker_obj.get('taxId') or
                        broker_obj.get('id')    or
                        tx.get('brokerId')      or ''
                    )
                    # Remove caracteres não-numéricos antes de comparar CNPJs
                    import re as _re
                    if _re.sub(r'\D', '', str(tx_broker)) != _re.sub(r'\D', '', str(broker_id)):
                        continue

                sec = tx.get('security') or {}
                sid = sec.get('id')
                tid = tx.get('id')
                if sid and tid and sid not in registrados:
                    registrados[sid] = tid

            next_url = result.get('next')
            if not next_url:
                break
            token = parse_qs(urlparse(next_url).query).get('pageToken', [None])[0]
            if not token:
                break
            page_token = token

        logger.info(f"[Gorila] {len(registrados)} securities com transação em {portfolio_id}"
                    + (f" (broker={broker_id})" if broker_id else ""))
        return registrados

    # ── Poupança (CUSTOM/CASH) ─────────────────────────────────────────────

    def criar_ou_buscar_poupanca(self, posicao, sp_db=None):
        """
        Localiza ou cria um security CUSTOM/CASH para uma conta poupança.

        O security é global no Gorila (compartilhado entre portfólios).
        O mapeamento nome → security_id é cacheado no SharePoint para evitar
        duplicatas entre uploads mensais e entre clientes distintos.

        Retorna o security_id (int).
        """
        nome_limpo = self._limpar_nome_fundo(posicao['nome']) or 'Poupança Itaú'

        # 1. Consulta cache do SharePoint
        if sp_db is not None:
            cached = sp_db.get_custom_security_id(nome_limpo)
            if cached:
                logger.info(f"[Poupança] security_id em cache: {cached} — {nome_limpo}")
                return cached

        # 2. Busca no Gorila por nome
        items = self.buscar_security(nome_limpo)
        for item in items:
            if item.get('name', '').upper() == nome_limpo.upper():
                sec_id = item['id']
                logger.info(f"[Poupança] Encontrado no Gorila: id={sec_id} — {nome_limpo}")
                if sp_db is not None:
                    sp_db.save_custom_security_id(nome_limpo, sec_id)
                return sec_id

        # 3. Cria como CUSTOM/CASH
        initial_date = self._fmt_date(posicao.get('data_inicio')) or str(date.today())
        payload = {
            'type':        'CUSTOM',
            'initialDate': initial_date,
            'assetClass':  'CASH',
            'name':        nome_limpo,
            'description': f'Conta poupança — {nome_limpo}',
        }
        result = self._post('/securities', payload)
        sec_id = result['id']
        logger.info(f"[Poupança] Criado no Gorila: id={sec_id} — {nome_limpo}")
        if sp_db is not None:
            sp_db.save_custom_security_id(nome_limpo, sec_id)
        return sec_id

    def atualizar_ou_criar_transacao_poupanca(self, portfolio_id, security_id, posicao):
        """
        Mês 1: cria INITIAL_CUSTODY_ADJUSTMENT com saldo_atual como quantity.
        Mês 2+: faz PATCH na transação existente com o novo saldo.

        Isso garante que cada portfólio tenha exatamente UMA transação
        para a poupança, sempre refletindo o saldo mais recente.
        """
        saldo = round(float(posicao['saldo_atual']), 2)
        transact_date = self._fmt_date(posicao.get('data_inicio')) or str(date.today())

        # Busca transação existente para esse security nesse portfólio
        result = self._get(
            f'/portfolios/{portfolio_id}/transactions',
            params={'securityId': security_id, 'limit': 10},
        )
        records = result.get('records', result.get('items', []))

        if records:
            # Atualiza a mais recente
            tx_id = records[0]['id']
            r = self.session.patch(
                f"{GORILA_BASE}/portfolios/{portfolio_id}/transactions/{tx_id}",
                json={'quantity': saldo, 'transactDate': transact_date},
                timeout=20,
            )
            if r.status_code not in (200, 201):
                raise GorilaError(
                    f"PATCH transação poupança → HTTP {r.status_code}: {r.text[:300]}"
                )
            tx = r.json()
            logger.info(f"[Poupança] Transação atualizada: id={tx_id}, quantity={saldo}")
            return tx
        else:
            # Primeira vez: cria
            payload = {
                'type':         'INITIAL_CUSTODY_ADJUSTMENT',
                'transactDate': transact_date,
                'side':         'BUY',
                'quantity':     saldo,
                'price':        1.0,
                'brokerId':     ITAU_CNPJ,
                'security':     {'id': security_id},
            }
            tx = self._post(f'/portfolios/{portfolio_id}/transactions', payload)
            logger.info(f"[Poupança] Transação criada: id={tx.get('id')}, quantity={saldo}")
            return tx

    # ── Transações ─────────────────────────────────────────────────────────

    def criar_transacao(self, portfolio_id, security_id, posicao):
        """
        Registra posição existente como INITIAL_CUSTODY_ADJUSTMENT.

        Para CDBs usa valor_original reconstruído (saldo / (1 + rent)).
        Para fundos usa saldo_atual como quantity (price = 1.0).
        Assim o saldo refletido na Gorila bate com o extrato.
        """
        transact_date = self._fmt_date(posicao.get('data_inicio')) or str(date.today())
        quantity = posicao.get('valor_original') or posicao['saldo_atual']

        payload = {
            'type':         'INITIAL_CUSTODY_ADJUSTMENT',
            'transactDate': transact_date,
            'side':         'BUY',
            'quantity':     round(float(quantity), 2),
            'price':        1.0,
            'brokerId':     ITAU_CNPJ,
            'security':     {'id': security_id},
        }
        result = self._post(f'/portfolios/{portfolio_id}/transactions', payload)
        logger.info(f"Transação criada: id={result.get('id')} — security={security_id}")
        return result
