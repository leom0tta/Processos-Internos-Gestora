#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hub de Processos - Fatorial Capital
Backend Flask
"""

import os
import sys
import json
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


def _build_msal_app():
    return msal.ConfidentialClientApplication(
        APP_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )


def _build_auth_url(state=None):
    return _build_msal_app().get_authorization_request_url(
        SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI,
    )


def login_required(f):
    """Decorator: redireciona para /login se não autenticado"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


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
    """Inicia o fluxo OAuth2 — redireciona para Microsoft"""
    auth_url = _build_auth_url(state="hub")
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    """Recebe o código da Microsoft e troca pelo token"""
    error = request.args.get('error')
    if error:
        return render_template("login.html", error=f"Erro de autenticação: {request.args.get('error_description', error)}")

    code = request.args.get('code')
    if not code:
        return render_template("login.html", error="Código de autorização não recebido.")

    result = _build_msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    if "error" in result:
        return render_template("login.html", error=result.get("error_description", result["error"]))

    session['user'] = result.get('id_token_claims')
    return redirect(url_for('index'))


@app.route("/logout")
def logout():
    session.clear()
    logout_url = (
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={REDIRECT_URI.replace('/auth/callback', '/')}"
    )
    return redirect(logout_url)


# ============================================================
# ROTAS PRINCIPAIS
# ============================================================

@app.route("/")
@login_required
def index():
    return render_template("index.html", user=session.get('user'))


# ============================================================
# API — LAUDO
# ============================================================

@app.route("/api/portfolios")
@login_required
def api_portfolios():
    """Busca lista de portfolios da API Gorila"""
    try:
        system = get_system()
        portfolios = system.buscar_portfolios()
        return jsonify({"ok": True, "portfolios": portfolios})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.route("/api/gerar-laudo", methods=["POST"])
@login_required
def api_gerar_laudo():
    """Gera o laudo e retorna o nome do arquivo para download"""
    data = request.get_json()
    cliente_nome = data.get("cliente_nome", "").strip()
    perfil       = data.get("perfil", "").strip()
    portfolio_id = data.get("portfolio_id", "").strip()

    if not cliente_nome or not perfil or not portfolio_id:
        return jsonify({"ok": False, "erro": "Preencha todos os campos."}), 400

    if perfil not in ["Conservador", "Moderado", "Agressivo"]:
        return jsonify({"ok": False, "erro": "Perfil inválido."}), 400

    try:
        system = get_system()

        posicoes        = system.buscar_posicoes(portfolio_id)
        valores_mercado = system.buscar_valores_mercado(portfolio_id)
        pnl             = system.buscar_pnl(portfolio_id)

        if not posicoes:
            return jsonify({"ok": False, "erro": "Portfolio sem posições."}), 400

        posicoes_proc, _ = system.processar_posicoes(posicoes, valores_mercado, pnl, perfil)

        if not posicoes_proc:
            return jsonify({"ok": False, "erro": "Nenhuma posição pôde ser processada."}), 400

        patrimonio_total, alocacoes = system.calcular_alocacoes(posicoes_proc)
        analise_suit = system.analisar_suitability(alocacoes, perfil)

        data_str  = datetime.now().strftime("%d%m%Y")
        nome_safe = cliente_nome.replace(" ", "_")
        filename  = f"Laudo_{nome_safe}_{data_str}.docx"
        output    = str(OUTPUTS_DIR / filename)

        system.gerar_docx(
            cliente_nome    = cliente_nome,
            perfil          = perfil,
            alocacoes       = alocacoes,
            patrimonio_total= patrimonio_total,
            posicoes        = posicoes_proc,
            analise_suit    = analise_suit,
            output_path     = output,
        )

        return jsonify({"ok": True, "arquivo": filename})

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.route("/api/download/<filename>")
@login_required
def api_download(filename):
    """Serve o arquivo gerado para download"""
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        return jsonify({"ok": False, "erro": "Arquivo não encontrado."}), 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)


def get_system():
    """Inicializa o GorilaLaudo com o .env correto"""
    from gerar_laudo import GorilaLaudo
    return GorilaLaudo(ENV_PATH)


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
    print("   Pressione Ctrl+C para encerrar.\n")

    app.run(host="0.0.0.0", port=port, debug=False)
