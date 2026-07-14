#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sharepoint_db.py — Substitui o PostgreSQL pelo SharePoint como backend.

Cada "tabela" é uma aba de um único arquivo Excel no SharePoint:
  - clientes
  - asset_type_mappings
  - asset_name_mappings
  - liquidity_mappings

Variáveis de ambiente necessárias:
  SHAREPOINT_TENANT_ID      — ID do tenant Azure AD
  SHAREPOINT_CLIENT_ID      — client_id do app registration
  SHAREPOINT_CLIENT_SECRET  — client_secret do app registration
  SHAREPOINT_DRIVE_ID       — ID do drive no SharePoint
  SHAREPOINT_DB_PATH        — Caminho do arquivo Excel dentro do drive
                              (ex: "Hub/database.xlsx")
"""

import io
import os
import json
import logging
import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Colunas de cada aba ──────────────────────────────────────
SHEET_COLUMNS = {
    'clientes': [
        'id', 'nome', 'cpf', 'email', 'perfil',
        'portfolio_id', 'gorila_portfolio_name',
        'ativo', 'created_at', 'updated_at',
    ],
    'asset_type_mappings':  ['security_type', 'asset_class', 'updated_at'],
    'asset_name_mappings':  ['asset_name',    'asset_class', 'updated_at'],
    'liquidity_mappings':   ['asset_name',    'liquidity_category', 'updated_at'],
}


class SharePointDB:
    """
    Backend SharePoint que substitui o SQLAlchemy.
    Mantém uma única instância por processo (singleton via módulo).
    """

    def __init__(self):
        self.tenant_id     = os.environ['SHAREPOINT_TENANT_ID']
        self.client_id     = os.environ['SHAREPOINT_CLIENT_ID']
        self.client_secret = os.environ['SHAREPOINT_CLIENT_SECRET']
        self.drive_id      = os.environ['SHAREPOINT_DRIVE_ID']
        self.file_path     = os.environ.get('SHAREPOINT_DB_PATH', 'Hub/database.xlsx')
        self._token        = None
        self._token_expiry = 0  # timestamp unix

    # ── Autenticação ─────────────────────────────────────────

    def _get_token(self) -> str:
        import time
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        url = f'https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token'
        resp = requests.post(url, data={
            'grant_type':    'client_credentials',
            'client_id':     self.client_id,
            'client_secret': self.client_secret,
            'scope':         'https://graph.microsoft.com/.default',
        })
        resp.raise_for_status()
        result = resp.json()
        self._token = result['access_token']
        import time as _time
        self._token_expiry = _time.time() + result.get('expires_in', 3600)
        return self._token

    def _headers(self) -> dict:
        return {'Authorization': f'Bearer {self._get_token()}'}

    # ── Leitura / escrita do arquivo Excel ───────────────────

    def _read_all(self) -> dict:
        """Baixa o Excel do SharePoint e retorna dict {sheet_name: DataFrame}."""
        url = (
            f'https://graph.microsoft.com/v1.0/drives/{self.drive_id}'
            f'/root:/{self.file_path}:/content'
        )
        resp = requests.get(url, headers=self._headers())

        if resp.status_code == 404:
            logger.info('[SharePointDB] Arquivo não encontrado — iniciando vazio.')
            return {s: pd.DataFrame(columns=c) for s, c in SHEET_COLUMNS.items()}

        resp.raise_for_status()
        try:
            dfs = pd.read_excel(io.BytesIO(resp.content), sheet_name=None)
        except Exception as e:
            logger.warning(f'[SharePointDB] Erro ao ler Excel: {e} — iniciando vazio.')
            return {s: pd.DataFrame(columns=c) for s, c in SHEET_COLUMNS.items()}

        # Garante que todas as abas existam com as colunas corretas
        for sheet, cols in SHEET_COLUMNS.items():
            if sheet not in dfs:
                dfs[sheet] = pd.DataFrame(columns=cols)
            else:
                for col in cols:
                    if col not in dfs[sheet].columns:
                        dfs[sheet][col] = None

        return dfs

    def _write_all(self, dfs: dict):
        """Salva o dict de DataFrames de volta no SharePoint."""
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            for sheet_name, df in dfs.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        buffer.seek(0)

        url = (
            f'https://graph.microsoft.com/v1.0/drives/{self.drive_id}'
            f'/root:/{self.file_path}:/content'
        )
        headers = {
            **self._headers(),
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
        resp = requests.put(url, headers=headers, data=buffer)
        resp.raise_for_status()
        logger.info('[SharePointDB] Arquivo salvo no SharePoint.')

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ════════════════════════════════════════════════════════
    # CLIENTES
    # ════════════════════════════════════════════════════════

    def get_clientes(self, apenas_ativos=True) -> list:
        dfs = self._read_all()
        df  = dfs['clientes'].copy()
        if df.empty:
            return []
        if apenas_ativos and 'ativo' in df.columns:
            df = df[df['ativo'].astype(str).str.lower().isin(['true', '1', 'yes'])]
        df = df.sort_values('nome', na_position='last')
        return self._df_to_dicts(df)

    def get_cliente_by_id(self, cliente_id: int):
        dfs = self._read_all()
        df  = dfs['clientes']
        row = df[df['id'] == cliente_id]
        if row.empty:
            return None
        return self._df_to_dicts(row)[0]

    def create_cliente(self, data: dict) -> dict:
        dfs = self._read_all()
        df  = dfs['clientes']
        now = self._now()

        existing_ids = pd.to_numeric(df['id'], errors='coerce').dropna()
        new_id = int(existing_ids.max() + 1) if len(existing_ids) > 0 else 1

        new_row = {
            'id':                    new_id,
            'nome':                  data.get('nome', '').strip().upper(),
            'cpf':                   data.get('cpf') or None,
            'email':                 data.get('email') or None,
            'perfil':                data.get('perfil') or None,
            'portfolio_id':          data.get('portfolio_id') or None,
            'gorila_portfolio_name': data.get('gorila_portfolio_name') or None,
            'ativo':                 True,
            'created_at':            now,
            'updated_at':            now,
        }
        dfs['clientes'] = pd.concat(
            [df, pd.DataFrame([new_row])], ignore_index=True
        )
        self._write_all(dfs)
        return new_row

    def update_cliente(self, cliente_id: int, data: dict):
        dfs  = self._read_all()
        df   = dfs['clientes']
        mask = df['id'] == cliente_id
        if not mask.any():
            return None

        campos = [
            'nome', 'cpf', 'email', 'perfil',
            'portfolio_id', 'gorila_portfolio_name', 'ativo',
        ]
        for campo in campos:
            if campo in data:
                val = data[campo]
                if campo == 'nome' and isinstance(val, str):
                    val = val.strip().upper()
                df.loc[mask, campo] = val

        df.loc[mask, 'updated_at'] = self._now()
        dfs['clientes'] = df
        self._write_all(dfs)
        return self._df_to_dicts(df[mask])[0]

    def delete_cliente(self, cliente_id: int) -> bool:
        dfs  = self._read_all()
        df   = dfs['clientes']
        mask = df['id'] == cliente_id
        if not mask.any():
            return False
        df.loc[mask, 'ativo']      = False
        df.loc[mask, 'updated_at'] = self._now()
        dfs['clientes'] = df
        self._write_all(dfs)
        return True

    # ════════════════════════════════════════════════════════
    # ASSET TYPE MAPPINGS
    # ════════════════════════════════════════════════════════

    def get_asset_type_mappings(self) -> list:
        dfs = self._read_all()
        df  = dfs['asset_type_mappings']
        if df.empty:
            return []
        return self._df_to_dicts(df.sort_values('security_type'))

    def upsert_asset_type_mapping(self, security_type: str, asset_class: str):
        dfs  = self._read_all()
        df   = dfs['asset_type_mappings']
        mask = df['security_type'] == security_type
        now  = self._now()
        if mask.any():
            df.loc[mask, 'asset_class'] = asset_class
            df.loc[mask, 'updated_at']  = now
        else:
            df = pd.concat([df, pd.DataFrame([{
                'security_type': security_type,
                'asset_class':   asset_class,
                'updated_at':    now,
            }])], ignore_index=True)
        dfs['asset_type_mappings'] = df
        self._write_all(dfs)

    def delete_asset_type_mapping(self, security_type: str) -> bool:
        dfs = self._read_all()
        df  = dfs['asset_type_mappings']
        new = df[df['security_type'] != security_type]
        if len(new) == len(df):
            return False
        dfs['asset_type_mappings'] = new.reset_index(drop=True)
        self._write_all(dfs)
        return True

    # ════════════════════════════════════════════════════════
    # ASSET NAME MAPPINGS
    # ════════════════════════════════════════════════════════

    def get_asset_name_mappings(self) -> list:
        dfs = self._read_all()
        df  = dfs['asset_name_mappings']
        if df.empty:
            return []
        return self._df_to_dicts(df.sort_values('asset_name'))

    def upsert_asset_name_mapping(self, asset_name: str, asset_class: str):
        dfs  = self._read_all()
        df   = dfs['asset_name_mappings']
        mask = df['asset_name'] == asset_name
        now  = self._now()
        if mask.any():
            df.loc[mask, 'asset_class'] = asset_class
            df.loc[mask, 'updated_at']  = now
        else:
            df = pd.concat([df, pd.DataFrame([{
                'asset_name':  asset_name,
                'asset_class': asset_class,
                'updated_at':  now,
            }])], ignore_index=True)
        dfs['asset_name_mappings'] = df
        self._write_all(dfs)

    def delete_asset_name_mapping(self, asset_name: str) -> bool:
        dfs = self._read_all()
        df  = dfs['asset_name_mappings']
        new = df[df['asset_name'] != asset_name]
        if len(new) == len(df):
            return False
        dfs['asset_name_mappings'] = new.reset_index(drop=True)
        self._write_all(dfs)
        return True

    # ════════════════════════════════════════════════════════
    # LIQUIDITY MAPPINGS
    # ════════════════════════════════════════════════════════

    def get_liquidity_mappings(self) -> list:
        dfs = self._read_all()
        df  = dfs['liquidity_mappings']
        if df.empty:
            return []
        return self._df_to_dicts(df.sort_values('asset_name'))

    def upsert_liquidity_mapping(self, asset_name: str, liquidity_category: str):
        dfs  = self._read_all()
        df   = dfs['liquidity_mappings']
        mask = df['asset_name'] == asset_name
        now  = self._now()
        if mask.any():
            df.loc[mask, 'liquidity_category'] = liquidity_category
            df.loc[mask, 'updated_at']         = now
        else:
            df = pd.concat([df, pd.DataFrame([{
                'asset_name':         asset_name,
                'liquidity_category': liquidity_category,
                'updated_at':         now,
            }])], ignore_index=True)
        dfs['liquidity_mappings'] = df
        self._write_all(dfs)

    def delete_liquidity_mapping(self, asset_name: str) -> bool:
        dfs = self._read_all()
        df  = dfs['liquidity_mappings']
        new = df[df['asset_name'] != asset_name]
        if len(new) == len(df):
            return False
        dfs['liquidity_mappings'] = new.reset_index(drop=True)
        self._write_all(dfs)
        return True

    # ════════════════════════════════════════════════════════
    # HELPERS PARA GERAR LAUDO
    # ════════════════════════════════════════════════════════

    def load_mappings(self) -> tuple:
        """
        Retorna (type_map, name_map, liquidity_map) no formato
        que o GorilaLaudo espera: {'mappings': {chave: valor}}
        """
        dfs = self._read_all()

        type_map = {'mappings': {
            str(r['security_type']): str(r['asset_class'])
            for r in self._df_to_dicts(dfs['asset_type_mappings'])
            if r.get('security_type') and r.get('asset_class')
        }}
        name_map = {'mappings': {
            str(r['asset_name']): str(r['asset_class'])
            for r in self._df_to_dicts(dfs['asset_name_mappings'])
            if r.get('asset_name') and r.get('asset_class')
        }}
        liq_map = {'mappings': {
            str(r['asset_name']): str(r['liquidity_category'])
            for r in self._df_to_dicts(dfs['liquidity_mappings'])
            if r.get('asset_name') and r.get('liquidity_category')
        }}
        return type_map, name_map, liq_map

    def seed_asset_type_mappings(self, json_path: Path):
        """
        Popula asset_type_mappings a partir do JSON se a aba estiver vazia.
        Equivalente ao seed_db.py anterior.
        """
        dfs = self._read_all()
        df  = dfs['asset_type_mappings']

        if not df.empty and len(df) > 0:
            logger.info('[SharePointDB] Seed ignorado — asset_type_mappings já tem dados.')
            return

        if not json_path.exists():
            logger.warning(f'[SharePointDB] JSON não encontrado: {json_path}')
            return

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        rows = []
        now  = self._now()
        for security_type, asset_class in data.get('mappings', {}).items():
            rows.append({
                'security_type': security_type,
                'asset_class':   asset_class,
                'updated_at':    now,
            })

        dfs['asset_type_mappings'] = pd.DataFrame(rows, columns=SHEET_COLUMNS['asset_type_mappings'])
        self._write_all(dfs)
        logger.info(f'[SharePointDB] Seed: {len(rows)} mapeamentos inseridos.')

    # ════════════════════════════════════════════════════════
    # UTILITÁRIOS
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _df_to_dicts(df: pd.DataFrame) -> list:
        """Converte DataFrame para lista de dicts, tratando NaN como None."""
        records = df.to_dict('records')
        cleaned = []
        for rec in records:
            cleaned.append({
                k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                for k, v in rec.items()
            })
        return cleaned


# ── Singleton ─────────────────────────────────────────────────
_sp_db_instance = None

def get_sp_db() -> SharePointDB:
    """Retorna a instância singleton do SharePointDB."""
    global _sp_db_instance
    if _sp_db_instance is None:
        _sp_db_instance = SharePointDB()
    return _sp_db_instance
