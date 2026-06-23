#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parser: Posição de Investimentos Ion/Itaú
=========================================
Extrai todas as posições de um extrato PDF gerado pelo Ion (plataforma Itaú
para assessores), retornando uma lista de dicts estruturada.

Uso básico
----------
    from parsers.ion_itau import parse_posicao

    with open("extrato.pdf", "rb") as f:
        resultado = parse_posicao(f)

    resultado["posicoes"]   # list[dict]  — cada posição individual
    resultado["totais"]     # dict        — saldo bruto total por classe
    resultado["meta"]       # dict        — data da posição, conta, etc.

Campos de cada posição
----------------------
    nome            str    — nome do ativo conforme extrato
    tipo            str    — CDB PLUS | CDB-DI | Fundo RF | Fundo DI |
                             Fundo Internacional | Fundo | Previdência VGBL | Poupança
    classe          str    — CDB/RF | Fundo | Previdência | Poupança
    emissor         str    — sempre "Itaú Unibanco" neste extrato
    indexador       str|None — "CDI" para CDBs, None para fundos
    taxa_cdi        int|None — percentual do CDI (ex: 100, 110, 90) para CDBs
    data_inicio     str    — "DD/MM/YYYY"
    data_vencimento str    — "DD/MM/YYYY" ou "-" quando sem vencimento
    saldo_atual     float  — valor bruto em R$ na data da posição
    alocacao        float|None — percentual da carteira (0.0 – 1.0)
"""

import re
from typing import IO, Union

try:
    import pdfplumber
except ImportError:
    raise ImportError(
        "pdfplumber é necessário: pip install pdfplumber --break-system-packages"
    )

# ── Regex ──────────────────────────────────────────────────────────────────

# Cabeçalho do extrato (data da posição)
_META_DATE_PAT = re.compile(r'Data da posi[çc][ãa]o:\s*(\d{2}/\d{2}/\d{4})')
_META_ACCT_PAT = re.compile(r'Ag\s+\S+\s*/\s*CC\s+\S+')

# Linha de CDB:
#   "CDB PLUS ITAU CDI 100,00 08 2028  360.688,55  15,80%  30/08/2023  03/08/2028"
#   "CDB-DI ITAU CDI 100,00 02 2031   46.761,06   2,05%  27/02/2026  03/02/2031"
_CDB_PAT = re.compile(
    r'^((?:CDB-\w+|CDB\s+\w+)\s+ITAU\s+CDI\s+\d{2,3},00\s+\d{2}\s+\d{4})'  # nome
    r'\s+([\d.]+,\d{2})'        # saldo
    r'\s+(\d+,\d{2}%|-)'        # alocação
    r'\s+(\d{2}/\d{2}/\d{4}|-)' # data início
    r'\s+(\d{2}/\d{2}/\d{4}|-)$' # data vencimento
)

# Linha genérica (fundos, previdência, poupança):
#   "(50636) EXCELLENCE RF  317.320,82  13,90%  03/11/2020  -"
#   "Prever Renda VGBL IV Fix 100  72.751,37  3,19%  03/11/2020  -"
_GEN_PAT = re.compile(
    r'^(.+?)'
    r'\s+([\d.]+,\d{2})'
    r'\s+(\d+,\d{2}%|-)'
    r'\s+(\d{2}/\d{2}/\d{4}|-)'
    r'\s+(\d{2}/\d{2}/\d{4}|-)$'
)

# Nomes de linhas de subtotal (a ignorar)
_SUBTOTAL_PREFIXES = (
    'CDB, Renda Fixa',
    'Fundo de Investimento',
    'Previdência',
    'Poupança',
)

# Mapeamento de trechos do header → classe interna
_SECTION_MAP = {
    'CDB, Renda Fixa e Inv. Estruturados': 'CDB/RF',
    'Fundo de Investimento':               'Fundo',
    'Previdência':                         'Previdência',
    'Poupança':                            'Poupança',
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_saldo(s: str) -> float:
    """Converte "360.688,55" → 360688.55"""
    return float(s.replace('.', '').replace(',', '.'))


def _parse_aloc(s: str) -> "float | None":
    """Converte "15,80%" → 0.158; "-" → None"""
    if s == '-':
        return None
    return round(float(s.replace(',', '.').replace('%', '')) / 100, 6)


def _parse_taxa_cdi(nome: str) -> "int | None":
    """Extrai percentual CDI do nome: "CDI 110,00" → 110"""
    m = re.search(r'CDI\s+(\d+),', nome)
    return int(m.group(1)) if m else None


def _classify_tipo(nome: str, classe: str) -> str:
    if nome.startswith('CDB'):
        return 'CDB PLUS' if 'PLUS' in nome else 'CDB-DI'
    n = nome.upper()
    if re.match(r'^\(\d+\)', nome):        # código de fundo (50636)...
        if 'DI' in n:                      return 'Fundo DI'
        if ' RF' in n or 'RENDA FIXA' in n: return 'Fundo RF'
        if 'BOND' in n or 'FINANC' in n:   return 'Fundo Internacional'
        return 'Fundo'
    if any(kw in n for kw in ('VGBL', 'PGBL', 'PREVER', 'RENDA VGBL')): return 'Previdência VGBL'
    if 'POUPAN' in n:                      return 'Poupança'
    return classe  # fallback


# ── Parser principal ───────────────────────────────────────────────────────

def parse_posicao(source: Union[str, IO[bytes]]) -> dict:
    """
    Lê um PDF "Posição de Investimentos" Ion/Itaú.

    Parâmetros
    ----------
    source : str ou file-like
        Caminho para o PDF ou objeto de arquivo aberto em modo binário.

    Retorna
    -------
    dict com chaves:
        meta      : dict  — data_posicao, conta
        posicoes  : list  — lista de posições (ver docstring do módulo)
        totais    : dict  — saldo_total, por_classe {classe: saldo}
        erros     : list  — linhas que não puderam ser parseadas
    """
    posicoes = []
    erros = []
    meta = {'data_posicao': None, 'conta': None}
    current_section = 'Desconhecido'

    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''

            for line in text.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # ── Metadados ──────────────────────────────────────────────
                if meta['data_posicao'] is None:
                    m = _META_DATE_PAT.search(line)
                    if m:
                        meta['data_posicao'] = m.group(1)

                if meta['conta'] is None:
                    m = _META_ACCT_PAT.search(line)
                    if m:
                        meta['conta'] = m.group(0)

                # ── Seção atual ────────────────────────────────────────────
                for hdr, sec in _SECTION_MAP.items():
                    if hdr in line:
                        current_section = sec
                        break

                # ── Requer pelo menos uma data real para ser posição ───────
                if not re.search(r'\d{2}/\d{2}/\d{4}', line):
                    continue

                # Pular cabeçalho de página
                if line.startswith('Data da posi'):
                    continue

                # ── Tenta CDB ──────────────────────────────────────────────
                m = _CDB_PAT.match(line)
                if m:
                    nome, saldo_s, aloc_s, dt_ini, dt_venc = m.groups()
                    nome = nome.strip()
                    posicoes.append({
                        'nome':            nome,
                        'tipo':            _classify_tipo(nome, current_section),
                        'classe':          current_section,
                        'emissor':         'Itaú Unibanco',
                        'indexador':       'CDI',
                        'taxa_cdi':        _parse_taxa_cdi(nome),
                        'data_inicio':     dt_ini,
                        'data_vencimento': dt_venc,
                        'saldo_atual':     _parse_saldo(saldo_s),
                        'alocacao':        _parse_aloc(aloc_s),
                    })
                    continue

                # ── Tenta genérico (fundos, previdência, poupança) ─────────
                m = _GEN_PAT.match(line)
                if m:
                    nome, saldo_s, aloc_s, dt_ini, dt_venc = m.groups()
                    nome = nome.strip()

                    # Pular linhas de subtotal de seção
                    if any(nome.startswith(p) for p in _SUBTOTAL_PREFIXES):
                        continue

                    posicoes.append({
                        'nome':            nome,
                        'tipo':            _classify_tipo(nome, current_section),
                        'classe':          current_section,
                        'emissor':         'Itaú Unibanco',
                        'indexador':       None,
                        'taxa_cdi':        None,
                        'data_inicio':     dt_ini,
                        'data_vencimento': dt_venc,
                        'saldo_atual':     _parse_saldo(saldo_s),
                        'alocacao':        _parse_aloc(aloc_s),
                    })
                    continue

                # Linha com data que não casou — registra para debug
                # (ignora linhas de rentabilidade e valores R$)
                if not line.startswith('R$') and not re.match(r'^[\d,%.\s\-+]+$', line):
                    erros.append(line)

    # ── Totais ─────────────────────────────────────────────────────────────
    saldo_total = sum(p['saldo_atual'] for p in posicoes)
    por_classe: dict[str, float] = {}
    for p in posicoes:
        por_classe[p['classe']] = por_classe.get(p['classe'], 0.0) + p['saldo_atual']

    return {
        'meta':     meta,
        'posicoes': posicoes,
        'totais': {
            'saldo_total': round(saldo_total, 2),
            'por_classe':  {k: round(v, 2) for k, v in por_classe.items()},
        },
        'erros': erros,
    }
