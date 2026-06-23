#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hub de Processos - Fatorial Capital
Backend Flask
"""

import os
import sys
import threading
from datetime import datetime
from functools import wraps
from pathlib import Path

import msal
from flask import (
    Flask, render_template, request, jsonify,
    send_file, session, redirect, url_for
)

# Adicionar o diretório pai ao path para importar gerar_laudo
sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# ── Banco de dados ──────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

import json as _json

def _seed_mappings():
    """Popula asset_type_mappings a partir do JSON se a tabela estiver vazia."""
    if AssetTypeMapping.query.first():
        return  # já tem dados, não faz nada
    json_path = Path(__file__).parent.parent / "asset_type_mapping.json"
    if not json_path.exists():
        return
    with open(json_path, 'r', encoding='utf-8') as f:
        data = _json.load(f)
    for security_type, asset_class in data.get('mappings', {}).items():
        db.session.add(AssetTypeMapping(security_type=security_type, asset_class=asset_class))
    db.session.commit()
    import logging
    logging.getLogger(__name__).info(f"Seed: {len(data['mappings'])} mapeamentos inseridos.")

# Render fornece URLs com prefixo "postgres://"; SQLAlchemy exige "postgresql://"
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

if DATABASE_URL:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    from database import db, AssetTypeMapping, AssetNameMapping, LiquidityMapping, Cliente
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _seed_mappings()
    USE_DB = True
else:
    USE_DB = False

# ── Diretórios e caminhos ───────────────────────────────────
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
ENV_PATH = str(Path(__file__).parent.parent / ".env")

# ============================================================
# CONFIGURAÇÃO MICROSOFT AUTH
# ============================================================

TENANT_ID     = os.environ.get('TENANT_ID', '')
APP_ID        = os.environ.get('APP_ID', '')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET', '')
REDIRECT_URI  = os.environ.get('REDIRECT_URI', 'http://localhost:5000/auth/callback')
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES        = ["User.Read"]
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
        # Permite acesso via API Key no header X-API-Key
        if API_KEY and request.headers.get('X-API-Key') == API_KEY:
            return f(*args, **kwargs)
        if not session.get('user'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_system(asset_type_mapping=None, asset_name_mapping=None, liquidity_mapping=None):
    """Inicializa o GorilaLaudo, injetando mappings do BD se disponível"""
    from gerar_laudo import GorilaLaudo
    return GorilaLaudo(
        ENV_PATH,
        asset_type_mapping=asset_type_mapping,
        asset_name_mapping=asset_name_mapping,
        liquidity_mapping=liquidity_mapping,
    )


def load_mappings_from_db():
    """Carrega todos os mappings do BD. Retorna (type_mapping, name_mapping, liquidity_mapping)."""
    if not USE_DB:
        return None, None, None
    type_map      = {'mappings': {r.security_type: r.asset_class         for r in AssetTypeMapping.query.all()}}
    name_map      = {'mappings': {r.asset_name:    r.asset_class         for r in AssetNameMapping.query.all()}}
    liquidity_map = {'mappings': {r.asset_name:    r.liquidity_category  for r in LiquidityMapping.query.all()}}
    return type_map, name_map, liquidity_map


# ============================================================
# ROTAS DE AUTENTICAÇÃO
# ============================================================

@app.route("/login")
def login():
    if session.get('user'):
        return redirect(url_for('index'))
    return render_template("login.html")


@app.route("/auth/start")
def auth_start():
    return redirect(_build_auth_url(state="hub"))


@app.route("/auth/callback")
def auth_callback():
    error = request.args.get('error')
    if error:
        return render_template("login.html", error=f"Erro: {request.args.get('error_description', error)}")

    code = request.args.get('code')
    if not code:
        return render_template("login.html", error="Código de autorização não recebido.")

    result = _build_msal_app().acquire_token_by_authorization_code(
        code, scopes=SCOPES, redirect_uri=REDIRECT_URI,
    )

    if "error" in result:
        return render_template("login.html", error=result.get("error_description", result["error"]))

    session['user'] = result.get('id_token_claims')
    return redirect(url_for('index'))


@app.route("/logout")
def logout():
    session.clear()
    base = REDIRECT_URI.replace('/auth/callback', '/')
    return redirect(f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/logout?post_logout_redirect_uri={base}")


# ============================================================
# ROTAS PRINCIPAIS
# ============================================================

@app.route("/")
@login_required
def index():
    return render_template("index.html", user=session.get('user'))


# ============================================================
# API — CLIENTES
# ============================================================

@app.route("/api/clientes", methods=["GET"])
@login_required
def api_clientes_list():
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    return jsonify({"ok": True, "clientes": [c.to_dict() for c in clientes]})


@app.route("/api/clientes", methods=["POST"])
@login_required
def api_clientes_create():
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    data = request.get_json()
    nome = data.get("nome", "").strip()
    if not nome:
        return jsonify({"ok": False, "erro": "Nome é obrigatório."}), 400

    cliente = Cliente(
        nome                  = nome.upper(),
        cpf                   = data.get("cpf", "").strip() or None,
        email                 = data.get("email", "").strip() or None,
        perfil                = data.get("perfil") or None,
        portfolio_id          = data.get("portfolio_id") or None,
        gorila_portfolio_name = data.get("gorila_portfolio_name") or None,
    )
    db.session.add(cliente)
    db.session.commit()
    return jsonify({"ok": True, "cliente": cliente.to_dict()}), 201


@app.route("/api/clientes/<int:cliente_id>", methods=["PUT"])
@login_required
def api_clientes_update(cliente_id):
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    cliente = Cliente.query.get_or_404(cliente_id)
    data = request.get_json()

    if "nome"                  in data: cliente.nome                  = data["nome"].strip().upper()
    if "cpf"                   in data: cliente.cpf                   = data["cpf"] or None
    if "email"                 in data: cliente.email                 = data["email"] or None
    if "perfil"                in data: cliente.perfil                = data["perfil"] or None
    if "portfolio_id"          in data: cliente.portfolio_id          = data["portfolio_id"] or None
    if "gorila_portfolio_name" in data: cliente.gorila_portfolio_name = data["gorila_portfolio_name"] or None
    if "ativo"                 in data: cliente.ativo                 = bool(data["ativo"])

    cliente.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "cliente": cliente.to_dict()})


@app.route("/api/clientes/<int:cliente_id>", methods=["DELETE"])
@login_required
def api_clientes_delete(cliente_id):
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.ativo = False  # soft delete
    cliente.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})

# ============================================================
# API — MAPEAMENTOS
# ============================================================

@app.route("/api/mappings", methods=["GET"])
@login_required
def api_mappings_list():
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    rows = AssetTypeMapping.query.order_by(AssetTypeMapping.security_type).all()
    return jsonify({"ok": True, "mappings": [r.to_dict() for r in rows]})


@app.route("/api/mappings", methods=["POST"])
@login_required
def api_mappings_upsert():
    """Cria ou atualiza um mapeamento"""
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    data = request.get_json()
    security_type = data.get("security_type", "").strip().upper()
    asset_class   = data.get("asset_class", "").strip()
    if not security_type or not asset_class:
        return jsonify({"ok": False, "erro": "security_type e asset_class são obrigatórios."}), 400

    row = AssetTypeMapping.query.get(security_type)
    if row:
        row.asset_class = asset_class
        row.updated_at  = datetime.utcnow()
    else:
        db.session.add(AssetTypeMapping(security_type=security_type, asset_class=asset_class))
    db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# API — MAPEAMENTOS POR NOME
# ============================================================

@app.route("/api/mappings/<security_type>", methods=["DELETE"])
@login_required
def api_mappings_delete(security_type):
    """Remove um mapeamento por security_type"""
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    row = AssetTypeMapping.query.get(security_type)
    if not row:
        return jsonify({"ok": False, "erro": "Mapeamento não encontrado."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/name-mappings", methods=["GET"])
@login_required
def api_name_mappings_list():
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    rows = AssetNameMapping.query.order_by(AssetNameMapping.asset_name).all()
    return jsonify({"ok": True, "mappings": [r.to_dict() for r in rows]})


@app.route("/api/name-mappings", methods=["POST"])
@login_required
def api_name_mappings_upsert():
    """Cria ou atualiza um mapeamento por nome de ativo"""
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    data       = request.get_json()
    asset_name  = data.get("asset_name", "").strip()
    asset_class = data.get("asset_class", "").strip()
    if not asset_name or not asset_class:
        return jsonify({"ok": False, "erro": "asset_name e asset_class são obrigatórios."}), 400

    row = AssetNameMapping.query.get(asset_name)
    if row:
        row.asset_class = asset_class
        row.updated_at  = datetime.utcnow()
    else:
        db.session.add(AssetNameMapping(asset_name=asset_name, asset_class=asset_class))
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/name-mappings/<path:asset_name>", methods=["DELETE"])
@login_required
def api_name_mappings_delete(asset_name):
    """Remove um mapeamento por nome de ativo"""
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    row = AssetNameMapping.query.get(asset_name)
    if not row:
        return jsonify({"ok": False, "erro": "Mapeamento não encontrado."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# API — MAPEAMENTOS DE LIQUIDEZ
# ============================================================

@app.route("/api/liquidity-mappings", methods=["GET"])
@login_required
def api_liquidity_mappings_list():
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    rows = LiquidityMapping.query.order_by(LiquidityMapping.asset_name).all()
    return jsonify({"ok": True, "mappings": [r.to_dict() for r in rows]})


@app.route("/api/liquidity-mappings", methods=["POST"])
@login_required
def api_liquidity_mappings_upsert():
    """Cria ou atualiza um mapeamento de liquidez por nome de ativo"""
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    data               = request.get_json()
    asset_name         = data.get("asset_name", "").strip()
    liquidity_category = data.get("liquidity_category", "").strip()
    if not asset_name or not liquidity_category:
        return jsonify({"ok": False, "erro": "asset_name e liquidity_category são obrigatórios."}), 400

    row = LiquidityMapping.query.get(asset_name)
    if row:
        row.liquidity_category = liquidity_category
        row.updated_at         = datetime.utcnow()
    else:
        db.session.add(LiquidityMapping(asset_name=asset_name, liquidity_category=liquidity_category))
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/liquidity-mappings/<path:asset_name>", methods=["DELETE"])
@login_required
def api_liquidity_mappings_delete(asset_name):
    """Remove um mapeamento de liquidez"""
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503
    row = LiquidityMapping.query.get(asset_name)
    if not row:
        return jsonify({"ok": False, "erro": "Mapeamento não encontrado."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# API — LAUDO
# ============================================================

@app.route("/api/portfolios")
@login_required
def api_portfolios():
    try:
        type_map, name_map, liq_map = load_mappings_from_db()
        system = get_system(asset_type_mapping=type_map, asset_name_mapping=name_map, liquidity_mapping=liq_map)
        portfolios = system.buscar_portfolios()
        return jsonify({"ok": True, "portfolios": portfolios})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.route("/api/gerar-laudo", methods=["POST"])
@login_required
def api_gerar_laudo():
    data = request.get_json()
    cliente_nome            = data.get("cliente_nome", "").strip()
    perfil                  = data.get("perfil", "").strip()
    portfolio_id            = data.get("portfolio_id", "").strip()
    mapeamentos_extras      = data.get("mapeamentos_extras", {})       # {security_type: asset_class}
    mapeamentos_extras_nome = data.get("mapeamentos_extras_nome", {})  # {security_name: asset_class}

    if not cliente_nome or not perfil or not portfolio_id:
        return jsonify({"ok": False, "erro": "Preencha todos os campos."}), 400
    if perfil not in ["Conservador", "Moderado", "Agressivo"]:
        return jsonify({"ok": False, "erro": "Perfil inválido."}), 400

    try:
        type_map, name_map, liq_map = load_mappings_from_db()
        system = get_system(asset_type_mapping=type_map, asset_name_mapping=name_map, liquidity_mapping=liq_map)

        posicoes        = system.buscar_posicoes(portfolio_id)
        valores_mercado = system.buscar_valores_mercado(portfolio_id)

        if not posicoes:
            return jsonify({"ok": False, "erro": "Portfolio sem posições."}), 400

        posicoes_proc, ativos_nao_mapeados = system.processar_posicoes(
            posicoes, valores_mercado, perfil,
            mapeamentos_extras=mapeamentos_extras,
            mapeamentos_extras_nome=mapeamentos_extras_nome,
        )

        # Se ainda há ativos não mapeados, devolve para o frontend classificar
        if ativos_nao_mapeados:
            classes_disponiveis = list(system.suitability_profiles[perfil].keys())
            return jsonify({
                "ok":                   False,
                "needs_mapping":        True,
                "ativos_nao_mapeados":  ativos_nao_mapeados,
                "classes_disponiveis":  classes_disponiveis,
            })

        # Persiste no BD os mapeamentos manuais por tipo
        if USE_DB and mapeamentos_extras:
            for sec_type, asset_class in mapeamentos_extras.items():
                row = AssetTypeMapping.query.get(sec_type)
                if row:
                    row.asset_class = asset_class
                    row.updated_at  = datetime.utcnow()
                else:
                    db.session.add(AssetTypeMapping(
                        security_type=sec_type,
                        asset_class=asset_class,
                    ))
            db.session.commit()

        # Persiste no BD os mapeamentos manuais por nome
        if USE_DB and mapeamentos_extras_nome:
            for asset_name, asset_class in mapeamentos_extras_nome.items():
                row = AssetNameMapping.query.get(asset_name)
                if row:
                    row.asset_class = asset_class
                    row.updated_at  = datetime.utcnow()
                else:
                    db.session.add(AssetNameMapping(
                        asset_name=asset_name,
                        asset_class=asset_class,
                    ))
            db.session.commit()

        if not posicoes_proc:
            return jsonify({"ok": False, "erro": "Nenhuma posição pôde ser processada."}), 400

        # Verificar fundos sem liquidez determinada (não encontrados no guia)
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
                "ok":                      False,
                "needs_liquidity_mapping": True,
                "ativos_sem_liquidez":     ativos_sem_liquidez,
                "liquidity_categories": [
                    "Disponível (D+0 / D+1)",
                    "Curto Prazo (D+2 a D+30)",
                    "Médio Prazo (D+31 a D+90)",
                    "Longo Prazo (91 dias a 1 ano)",
                    "Longo Prazo (1 a 2 anos)",
                    "Longo Prazo (2 a 5 anos)",
                    "Longo Prazo (Superior a 5 anos)",
                    "Sem liquidez (ilíquido)",
                ],
            })

        patrimonio_total, alocacoes = system.calcular_alocacoes(posicoes_proc)
        analise_suit = system.analisar_suitability(alocacoes, perfil)

        data_str  = datetime.now().strftime("%d%m%Y")
        nome_safe = cliente_nome.replace(" ", "_")
        filename  = f"Laudo_{nome_safe}_{data_str}.docx"
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
        return jsonify({"ok": True, "arquivo": filename})

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.route("/api/download/<filename>")
@login_required
def api_download(filename):
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        return jsonify({"ok": False, "erro": "Arquivo não encontrado."}), 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)


# ============================================================
# PARSERS DE EXTRATO
# ============================================================

@app.route("/api/parse-extrato/ion-itau", methods=["POST"])
@login_required
def api_parse_extrato_ion_itau():
    """
    Recebe upload de PDF Ion/Itaú e retorna as posições parseadas como JSON.

    Request: multipart/form-data com campo "file" (PDF)
    Response: {
        ok: true,
        meta: { data_posicao, conta },
        posicoes: [ { nome, tipo, classe, emissor, indexador, taxa_cdi,
                      data_inicio, data_vencimento, saldo_atual, alocacao }, ... ],
        totais: { saldo_total, por_classe }
    }
    """
    if 'file' not in request.files:
        return jsonify({"ok": False, "erro": "Nenhum arquivo enviado (campo 'file')."}), 400

    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.pdf'):
        return jsonify({"ok": False, "erro": "Arquivo deve ser um PDF."}), 400

    try:
        from parsers.ion_itau import parse_posicao
        resultado = parse_posicao(f.stream)
        return jsonify({
            "ok":       True,
            "meta":     resultado["meta"],
            "posicoes": resultado["posicoes"],
            "totais":   resultado["totais"],
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Erro ao parsear extrato Ion/Itaú")
        return jsonify({"ok": False, "erro": str(e)}), 500


# ============================================================
# GORILA — UPLOAD DE POSIÇÃO
# ============================================================

@app.route("/api/gorila/upload-posicao-itau", methods=["POST"])
@login_required
def api_gorila_upload_posicao_itau():
    """
    Envia posições parseadas do extrato Ion/Itaú para o Gorila.

    Request JSON:
    {
      "cliente_id":   123,
      "posicoes":     [ <dicts do parser ion_itau> ],
      "cnpjs_fundos": {
        "NOME DO FUNDO": { "cnpj": "12345678000190", "asset_class": "FIXED_INCOME" },
        ...
      }
    }

    Response:
    {
      "ok":        true/false,
      "total":     N,
      "sucesso":   N,
      "erros":     [ { "nome": "...", "erro": "..." } ],
      "resultados":[ { "nome", "classe", "security_id", "transaction_id", "ok" } ]
    }
    """
    if not USE_DB:
        return jsonify({"ok": False, "erro": "Banco de dados não configurado."}), 503

    data         = request.get_json(force=True)
    cliente_id   = data.get('cliente_id')
    posicoes     = data.get('posicoes', [])
    cnpjs_fundos = data.get('cnpjs_fundos', {})

    if not cliente_id or not posicoes:
        return jsonify({"ok": False, "erro": "cliente_id e posicoes são obrigatórios."}), 400

    cliente = Cliente.query.get(cliente_id)
    if not cliente:
        return jsonify({"ok": False, "erro": "Cliente não encontrado."}), 404

    portfolio_id = cliente.portfolio_id
    if not portfolio_id:
        return jsonify({
            "ok": False,
            "erro": f"Cliente '{cliente.nome}' não tem Portfolio ID Gorila configurado. "
                    "Configure em Cadastro de Clientes antes de prosseguir."
        }), 400

    try:
        from gorila_client import GorilaClient, GorilaError
        gorila = GorilaClient()
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500

    resultados = []
    erros      = []

    for pos in posicoes:
        nome = pos.get('nome', '?')
        try:
            if pos.get('classe') == 'CDB/RF':
                sec_id = gorila.criar_cdb(pos)
            else:
                info      = cnpjs_fundos.get(nome, {})
                cnpj      = info.get('cnpj', '')
                asset_cls = info.get('asset_class', 'MULTIMARKET')
                sec_id    = gorila.buscar_ou_criar_fundo(pos, cnpj=cnpj, asset_class=asset_cls)

            tx = gorila.criar_transacao(portfolio_id, sec_id, pos)
            resultados.append({
                'nome':           nome,
                'classe':         pos.get('classe'),
                'security_id':    sec_id,
                'transaction_id': tx.get('id'),
                'ok':             True,
            })

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Erro ao enviar '{nome}' para Gorila")
            erros.append({'nome': nome, 'erro': str(e)})

    return jsonify({
        'ok':         len(erros) == 0,
        'total':      len(posicoes),
        'sucesso':    len(resultados),
        'erros':      erros,
        'resultados': resultados,
    })


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import webbrowser
    port = int(os.environ.get("PORT", 5000))

    def open_browser():
        import time
        time.sleep(1)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"\n🚀 Hub de Processos iniciado em http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
