#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hub de Processos - Fatorial Capital
Backend Flask — usa SharePoint como banco de dados (sem PostgreSQL)
"""

import os
import sys
import threading
from datetime import datetime
from functools import wraps
from pathlib import Path

import msal
import requests
from flask import (
    Flask, render_template, request, jsonify,
    send_file, session, redirect, url_for
)

# Adicionar o diretório pai ao path para importar gerar_laudo
sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# ── SharePoint como banco de dados ──────────────────────────
from sharepoint_db import get_sp_db

def sp_db():
    return get_sp_db()

# Seed inicial: popula asset_type_mappings do JSON se estiver vazio
try:
    _json_path = Path(__file__).parent.parent / 'asset_type_mapping.json'
    sp_db().seed_asset_type_mappings(_json_path)
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning(f'Seed ignorado: {_e}')

# ── Diretórios e caminhos ───────────────────────────────────
OUTPUTS_DIR = Path(__file__).parent / 'outputs'
OUTPUTS_DIR.mkdir(exist_ok=True)
ENV_PATH = str(Path(__file__).parent.parent / '.env')

# ============================================================
# CONFIGURAÇÃO MICROSOFT AUTH
# ============================================================

TENANT_ID     = os.environ.get('TENANT_ID', '')
APP_ID        = os.environ.get('APP_ID', '')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET', '')
REDIRECT_URI  = os.environ.get('REDIRECT_URI', 'http://localhost:5000/auth/callback')
AUTHORITY     = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPES        = ['User.Read']
API_KEY       = os.environ.get('API_KEY', '')


def _build_msal_app():
    return msal.ConfidentialClientApplication(
        APP_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET,
    )


def _build_auth_url(state=None):
    return _build_msal_app().get_authorization_request_url(
        SCOPES, state=state, redirect_uri=REDIRECT_URI,
    )


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_KEY and request.headers.get('X-API-Key') == API_KEY:
            return f(*args, **kwargs)
        if not session.get('user'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_system(asset_type_mapping=None, asset_name_mapping=None, liquidity_mapping=None):
    from gerar_laudo import GorilaLaudo
    return GorilaLaudo(
        ENV_PATH,
        asset_type_mapping=asset_type_mapping,
        asset_name_mapping=asset_name_mapping,
        liquidity_mapping=liquidity_mapping,
    )


# ============================================================
# ROTAS DE AUTENTICAÇÃO
# ============================================================

@app.route('/login')
def login():
    if session.get('user'):
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/auth/start')
def auth_start():
    return redirect(_build_auth_url(state='hub'))


@app.route('/auth/callback')
def auth_callback():
    error = request.args.get('error')
    if error:
        return render_template('login.html', error=f"Erro: {request.args.get('error_description', error)}")

    code = request.args.get('code')
    if not code:
        return render_template('login.html', error='Código de autorização não recebido.')

    result = _build_msal_app().acquire_token_by_authorization_code(
        code, scopes=SCOPES, redirect_uri=REDIRECT_URI,
    )

    if 'error' in result:
        return render_template('login.html', error=result.get('error_description', result['error']))

    session['user'] = result.get('id_token_claims')
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    base = REDIRECT_URI.replace('/auth/callback', '/')
    return redirect(
        f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/logout'
        f'?post_logout_redirect_uri={base}'
    )


# ============================================================
# ROTAS PRINCIPAIS
# ============================================================

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=session.get('user'))


# ============================================================
# API — CLIENTES
# ============================================================

@app.route('/api/clientes', methods=['GET'])
@login_required
def api_clientes_list():
    try:
        clientes = sp_db().get_clientes(apenas_ativos=True)
        return jsonify({'ok': True, 'clientes': clientes})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/clientes', methods=['POST'])
@login_required
def api_clientes_create():
    data = request.get_json()
    nome = data.get('nome', '').strip()
    if not nome:
        return jsonify({'ok': False, 'erro': 'Nome é obrigatório.'}), 400
    try:
        cliente = sp_db().create_cliente(data)
        return jsonify({'ok': True, 'cliente': cliente}), 201
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/clientes/<int:cliente_id>', methods=['PUT'])
@login_required
def api_clientes_update(cliente_id):
    data = request.get_json()
    try:
        cliente = sp_db().update_cliente(cliente_id, data)
        if cliente is None:
            return jsonify({'ok': False, 'erro': 'Cliente não encontrado.'}), 404
        return jsonify({'ok': True, 'cliente': cliente})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/clientes/<int:cliente_id>', methods=['DELETE'])
@login_required
def api_clientes_delete(cliente_id):
    try:
        ok = sp_db().delete_cliente(cliente_id)
        if not ok:
            return jsonify({'ok': False, 'erro': 'Cliente não encontrado.'}), 404
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


# ============================================================
# API — MAPEAMENTOS POR TIPO
# ============================================================

@app.route('/api/mappings', methods=['GET'])
@login_required
def api_mappings_list():
    try:
        rows = sp_db().get_asset_type_mappings()
        return jsonify({'ok': True, 'mappings': rows})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/mappings', methods=['POST'])
@login_required
def api_mappings_upsert():
    data          = request.get_json()
    security_type = data.get('security_type', '').strip().upper()
    asset_class   = data.get('asset_class', '').strip()
    if not security_type or not asset_class:
        return jsonify({'ok': False, 'erro': 'security_type e asset_class são obrigatórios.'}), 400
    try:
        sp_db().upsert_asset_type_mapping(security_type, asset_class)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/mappings/<security_type>', methods=['DELETE'])
@login_required
def api_mappings_delete(security_type):
    try:
        ok = sp_db().delete_asset_type_mapping(security_type)
        if not ok:
            return jsonify({'ok': False, 'erro': 'Mapeamento não encontrado.'}), 404
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


# ============================================================
# API — MAPEAMENTOS POR NOME
# ============================================================

@app.route('/api/name-mappings', methods=['GET'])
@login_required
def api_name_mappings_list():
    try:
        rows = sp_db().get_asset_name_mappings()
        return jsonify({'ok': True, 'mappings': rows})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/name-mappings', methods=['POST'])
@login_required
def api_name_mappings_upsert():
    data        = request.get_json()
    asset_name  = data.get('asset_name', '').strip()
    asset_class = data.get('asset_class', '').strip()
    if not asset_name or not asset_class:
        return jsonify({'ok': False, 'erro': 'asset_name e asset_class são obrigatórios.'}), 400
    try:
        sp_db().upsert_asset_name_mapping(asset_name, asset_class)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/name-mappings/<path:asset_name>', methods=['DELETE'])
@login_required
def api_name_mappings_delete(asset_name):
    try:
        ok = sp_db().delete_asset_name_mapping(asset_name)
        if not ok:
            return jsonify({'ok': False, 'erro': 'Mapeamento não encontrado.'}), 404
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


# ============================================================
# API — MAPEAMENTOS DE LIQUIDEZ
# ============================================================

@app.route('/api/liquidity-mappings', methods=['GET'])
@login_required
def api_liquidity_mappings_list():
    try:
        rows = sp_db().get_liquidity_mappings()
        return jsonify({'ok': True, 'mappings': rows})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/liquidity-mappings', methods=['POST'])
@login_required
def api_liquidity_mappings_upsert():
    data               = request.get_json()
    asset_name         = data.get('asset_name', '').strip()
    liquidity_category = data.get('liquidity_category', '').strip()
    if not asset_name or not liquidity_category:
        return jsonify({'ok': False, 'erro': 'asset_name e liquidity_category são obrigatórios.'}), 400
    try:
        sp_db().upsert_liquidity_mapping(asset_name, liquidity_category)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/liquidity-mappings/<path:asset_name>', methods=['DELETE'])
@login_required
def api_liquidity_mappings_delete(asset_name):
    try:
        ok = sp_db().delete_liquidity_mapping(asset_name)
        if not ok:
            return jsonify({'ok': False, 'erro': 'Mapeamento não encontrado.'}), 404
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


# ============================================================
# API — LAUDO
# ============================================================

@app.route('/api/portfolios')
@login_required
def api_portfolios():
    try:
        type_map, name_map, liq_map = sp_db().load_mappings()
        system     = get_system(asset_type_mapping=type_map, asset_name_mapping=name_map, liquidity_mapping=liq_map)
        portfolios = system.buscar_portfolios()
        return jsonify({'ok': True, 'portfolios': portfolios})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/gerar-laudo', methods=['POST'])
@login_required
def api_gerar_laudo():
    data                    = request.get_json()
    cliente_nome            = data.get('cliente_nome', '').strip()
    perfil                  = data.get('perfil', '').strip()
    portfolio_id            = data.get('portfolio_id', '').strip()
    mapeamentos_extras      = data.get('mapeamentos_extras', {})
    mapeamentos_extras_nome = data.get('mapeamentos_extras_nome', {})

    if not cliente_nome or not perfil or not portfolio_id:
        return jsonify({'ok': False, 'erro': 'Preencha todos os campos.'}), 400
    if perfil not in ['Conservador', 'Moderado', 'Agressivo']:
        return jsonify({'ok': False, 'erro': 'Perfil inválido.'}), 400

    try:
        type_map, name_map, liq_map = sp_db().load_mappings()
        system = get_system(
            asset_type_mapping=type_map,
            asset_name_mapping=name_map,
            liquidity_mapping=liq_map,
        )

        posicoes        = system.buscar_posicoes(portfolio_id)
        valores_mercado = system.buscar_valores_mercado(portfolio_id)

        if not posicoes:
            return jsonify({'ok': False, 'erro': 'Portfolio sem posições.'}), 400

        posicoes_proc, ativos_nao_mapeados = system.processar_posicoes(
            posicoes, valores_mercado, perfil,
            mapeamentos_extras=mapeamentos_extras,
            mapeamentos_extras_nome=mapeamentos_extras_nome,
        )

        if ativos_nao_mapeados:
            classes_disponiveis = list(system.suitability_profiles[perfil].keys())
            return jsonify({
                'ok':                  False,
                'needs_mapping':       True,
                'ativos_nao_mapeados': ativos_nao_mapeados,
                'classes_disponiveis': classes_disponiveis,
            })

        # Persiste mapeamentos manuais no SharePoint
        if mapeamentos_extras:
            for sec_type, asset_class in mapeamentos_extras.items():
                sp_db().upsert_asset_type_mapping(sec_type, asset_class)

        if mapeamentos_extras_nome:
            for asset_name, asset_class in mapeamentos_extras_nome.items():
                sp_db().upsert_asset_name_mapping(asset_name, asset_class)

        if not posicoes_proc:
            return jsonify({'ok': False, 'erro': 'Nenhuma posição pôde ser processada.'}), 400

        # Verifica fundos sem liquidez
        from gerar_laudo import GorilaLaudo as _GL
        ativos_sem_liquidez = []
        _vistos_liq = set()
        for pos in posicoes_proc:
            sec  = pos.get('security', {})
            nome = sec.get('name', 'N/A')
            if nome in _vistos_liq:
                continue
            if system.classificar_liquidez(sec) == _GL.LIQUIDITY_UNKNOWN:
                ativos_sem_liquidez.append({
                    'security_name': nome,
                    'security_type': sec.get('type', ''),
                })
                _vistos_liq.add(nome)

        if ativos_sem_liquidez:
            return jsonify({
                'ok':                      False,
                'needs_liquidity_mapping': True,
                'ativos_sem_liquidez':     ativos_sem_liquidez,
                'liquidity_categories': [
                    'Disponível (D+0 / D+1)',
                    'Curto Prazo (D+2 a D+30)',
                    'Médio Prazo (D+31 a D+90)',
                    'Longo Prazo (91 dias a 1 ano)',
                    'Longo Prazo (1 a 2 anos)',
                    'Longo Prazo (2 a 5 anos)',
                    'Longo Prazo (Superior a 5 anos)',
                    'Sem liquidez (ilíquido)',
                ],
            })

        patrimonio_total, alocacoes = system.calcular_alocacoes(posicoes_proc)
        analise_suit = system.analisar_suitability(alocacoes, perfil)

        data_str  = datetime.now().strftime('%d%m%Y')
        nome_safe = cliente_nome.replace(' ', '_')
        filename  = f'Laudo_{nome_safe}_{data_str}.docx'
        output    = str(OUTPUTS_DIR / filename)

        system.gerar_docx(
            cliente_nome     = cliente_nome,
            perfil           = perfil,
            alocacoes        = alocacoes,
            patrimonio_total = patrimonio_total,
            posicoes         = posicoes_proc,
            analise_suit     = analise_suit,
            output_path      = output,
        )
        return jsonify({'ok': True, 'arquivo': filename})

    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/download/<filename>')
@login_required
def api_download(filename):
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        return jsonify({'ok': False, 'erro': 'Arquivo não encontrado.'}), 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)


# ============================================================
# GORILA — SALVAR FUNDOS SEM ENVIAR
# ============================================================

@app.route('/api/gorila/salvar-fundos', methods=['POST'])
@login_required
def api_gorila_salvar_fundos():
    """
    Salva CNPJ, classe e liquidez dos fundos no SharePoint
    sem enviar nada para a Gorila. Útil para cadastrar as
    informações com antecedência e enviar depois.
    """
    data         = request.get_json(force=True)
    cnpjs_fundos = data.get('cnpjs_fundos', {})

    if not cnpjs_fundos:
        return jsonify({'ok': False, 'erro': 'Nenhum fundo informado.'}), 400

    salvos = 0
    import re as _re
    for nome_fundo, info in cnpjs_fundos.items():
        liq_cat    = info.get('liquidity_category', '')
        nome_limpo = _re.sub(r'^\(\d+\)\s*', '', nome_fundo).strip()
        if liq_cat and nome_limpo:
            sp_db().upsert_liquidity_mapping(nome_limpo, liq_cat)
            salvos += 1

    return jsonify({'ok': True, 'salvos': salvos})


# ============================================================
# PARSERS DE EXTRATO
# ============================================================

@app.route('/api/parse-extrato/ion-itau', methods=['POST'])
@login_required
def api_parse_extrato_ion_itau():
    if 'file' not in request.files:
        return jsonify({'ok': False, 'erro': "Nenhum arquivo enviado (campo 'file')."}), 400

    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.pdf'):
        return jsonify({'ok': False, 'erro': 'Arquivo deve ser um PDF.'}), 400

    try:
        from parsers.ion_itau import parse_posicao
        resultado = parse_posicao(f.stream)
        return jsonify({
            'ok':       True,
            'meta':     resultado['meta'],
            'posicoes': resultado['posicoes'],
            'totais':   resultado['totais'],
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception('Erro ao parsear extrato Ion/Itaú')
        return jsonify({'ok': False, 'erro': str(e)}), 500


# ============================================================
# GORILA — UPLOAD DE POSIÇÃO
# ============================================================

@app.route('/api/gorila/upload-posicao-itau', methods=['POST'])
@login_required
def api_gorila_upload_posicao_itau():
    data         = request.get_json(force=True)
    portfolio_id = data.get('portfolio_id')
    posicoes     = data.get('posicoes', [])
    cnpjs_fundos = data.get('cnpjs_fundos', {})

    if not portfolio_id or not posicoes:
        return jsonify({'ok': False, 'erro': 'portfolio_id e posicoes são obrigatórios.'}), 400

    try:
        from gorila_client import GorilaClient
        gorila = GorilaClient()
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500

    resultados = []
    erros      = []

    # ── Busca de uma vez todos os securities já registrados no portfólio ──
    # Evita duplicar INITIAL_CUSTODY_ADJUSTMENT em uploads mensais.
    try:
        existentes = gorila.listar_security_ids_com_transacao(portfolio_id)
    except Exception as e:
        existentes = {}
        import logging as _log
        _log.getLogger(__name__).warning(f"Não foi possível listar transações existentes: {e}")

    for pos in posicoes:
        nome = pos.get('nome', '?')
        try:
            if pos.get('classe') == 'CDB/RF':
                sec_id = gorila.criar_cdb(pos)

                if sec_id in existentes:
                    # Gorila já calcula rendimento CDI — não duplicar
                    resultados.append({
                        'nome': nome, 'classe': pos.get('classe'),
                        'security_id': sec_id, 'transaction_id': existentes[sec_id],
                        'ok': True, 'acao': 'ignorado',
                    })
                    continue

                tx = gorila.criar_transacao(portfolio_id, sec_id, pos)
                resultados.append({
                    'nome': nome, 'classe': pos.get('classe'),
                    'security_id': sec_id, 'transaction_id': tx.get('id'),
                    'ok': True, 'acao': 'criado',
                })

            elif pos.get('classe') == 'Poupança':
                # CUSTOM/CASH: security compartilhado, transação por portfólio.
                # atualizar_ou_criar_transacao_poupanca já faz PATCH se existir.
                sec_id = gorila.criar_ou_buscar_poupanca(pos, sp_db=sp_db())
                tx     = gorila.atualizar_ou_criar_transacao_poupanca(portfolio_id, sec_id, pos)
                acao   = 'atualizado' if sec_id in existentes else 'criado'
                resultados.append({
                    'nome': nome, 'classe': pos.get('classe'),
                    'security_id': sec_id, 'transaction_id': tx.get('id'),
                    'ok': True, 'acao': acao,
                })

            else:
                # Fundo / Previdência — requer CNPJ e classe no modal
                info      = cnpjs_fundos.get(nome, {})
                cnpj      = info.get('cnpj', '')
                asset_cls = info.get('asset_class', 'MULTIMARKET')
                liq_cat   = info.get('liquidity_category', '')
                sec_id    = gorila.buscar_ou_criar_fundo(pos, cnpj=cnpj, asset_class=asset_cls)

                # Salva liquidez no SharePoint para uso futuro nos laudos
                if liq_cat:
                    import re as _re
                    nome_limpo = _re.sub(r'^\(\d+\)\s*', '', nome).strip()
                    sp_db().upsert_liquidity_mapping(nome_limpo, liq_cat)

                if sec_id in existentes:
                    # Gorila busca NAV diário — não duplicar a transação
                    resultados.append({
                        'nome': nome, 'classe': pos.get('classe'),
                        'security_id': sec_id, 'transaction_id': existentes[sec_id],
                        'ok': True, 'acao': 'ignorado',
                    })
                    continue

                tx = gorila.criar_transacao(portfolio_id, sec_id, pos)
                resultados.append({
                    'nome': nome, 'classe': pos.get('classe'),
                    'security_id': sec_id, 'transaction_id': tx.get('id'),
                    'ok': True, 'acao': 'criado',
                })

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Erro ao enviar '{nome}' para Gorila")
            erros.append({'nome': nome, 'erro': str(e)})

    criados     = [r for r in resultados if r.get('acao') == 'criado']
    atualizados = [r for r in resultados if r.get('acao') == 'atualizado']
    ignorados   = [r for r in resultados if r.get('acao') == 'ignorado']

    return jsonify({
        'ok':          len(erros) == 0,
        'total':       len(posicoes),
        'criados':     len(criados),
        'atualizados': len(atualizados),
        'ignorados':   len(ignorados),
        'sucesso':     len(resultados),
        'erros':       erros,
        'resultados':  resultados,
    })


# ============================================================
# MAIN
# ============================================================
# DOCUMENTOS DE CLIENTES (SharePoint)
# ============================================================

import unicodedata as _unicodedata

def _sem_acento(texto: str) -> str:
    """Remove acentos para comparação robusta de nomes de arquivo."""
    return _unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().upper()

_docs_cache: dict = {'data': None, 'ts': 0.0}
_DOCS_CACHE_TTL   = 30 * 60   # 30 minutos

@app.route('/api/documentos-clientes')
@login_required
def api_documentos_clientes():
    import time

    # Retorna cache se ainda válido
    if _docs_cache['data'] and time.time() - _docs_cache['ts'] < _DOCS_CACHE_TTL:
        return jsonify(_docs_cache['data'])

    try:
        db       = sp_db()
        hdrs     = {'Authorization': f'Bearer {db._get_token()}'}
        drive_id = db.drive_id
        pasta    = os.environ.get('SHAREPOINT_DOCS_PATH', 'Documentos Clientes')

        # 1. Lista subpastas dos clientes
        url  = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{pasta}:/children'
        resp = requests.get(url, headers=hdrs,
                            params={'$top': 999, '$select': 'id,name,folder'})
        resp.raise_for_status()
        PASTAS_IGNORADAS = {'0. Documentação Padrão', '0. Documentacao Padrao'}
        pastas_clientes = [
            i for i in resp.json().get('value', [])
            if 'folder' in i and i.get('name', '') not in PASTAS_IGNORADAS
        ]

        def doc_assinado(arquivos: list, *palavras_chave) -> bool:
            """True se existe PDF começando com CONCLUÍ(DO) e contendo todas as palavras-chave."""
            for arq in arquivos:
                s = _sem_acento(arq)
                if not s.endswith('.PDF'):
                    continue
                if not (s.startswith('CONCLUIDO') or s.startswith('CONCLU\xcdDO')):
                    continue
                if all(kw in s for kw in palavras_chave):
                    return True
            return False

        clientes = []
        for pasta_cli in pastas_clientes:
            nome_cli = pasta_cli['name']
            fid      = pasta_cli['id']

            # 2. Lista arquivos da pasta do cliente
            url_f  = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{fid}/children'
            r_f    = requests.get(url_f, headers=hdrs,
                                  params={'$top': 200, '$select': 'name,file'})
            if r_f.status_code != 200:
                continue
            arquivos = [f['name'] for f in r_f.json().get('value', []) if 'file' in f]

            gestao = doc_assinado(arquivos, 'GESTAO')
            kyc    = doc_assinado(arquivos, 'KYC')
            ips    = doc_assinado(arquivos, 'POLITICA')

            clientes.append({
                'nome':     nome_cli,
                'gestao':   gestao,
                'kyc':      kyc,
                'ips':      ips,
                'completo': gestao and kyc and ips,
            })

        # Incompletos primeiro, depois alfabético
        clientes.sort(key=lambda c: (c['completo'], c['nome'].upper()))

        n_completos   = sum(1 for c in clientes if c['completo'])
        n_incompletos = len(clientes) - n_completos
        resultado = {
            'ok':           True,
            'clientes':     clientes,
            'total':        len(clientes),
            'completos':    n_completos,
            'incompletos':  n_incompletos,
        }
        _docs_cache['data'] = resultado
        _docs_cache['ts']   = time.time()
        return jsonify(resultado)

    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)}), 500


@app.route('/api/documentos-clientes/refresh', methods=['POST'])
@login_required
def api_documentos_clientes_refresh():
    """Invalida o cache para forçar nova leitura do SharePoint."""
    _docs_cache['data'] = None
    _docs_cache['ts']   = 0.0
    return jsonify({'ok': True})


# ============================================================

if __name__ == '__main__':
    import webbrowser
    port = int(os.environ.get('PORT', 5000))

    def open_browser():
        import time
        time.sleep(1)
        webbrowser.open(f'http://localhost:{port}')

    threading.Thread(target=open_browser, daemon=True).start()
    print(f'\n🚀 Hub de Processos iniciado em http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=False)
