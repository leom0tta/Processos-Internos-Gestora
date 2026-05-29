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
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

# Adicionar o diretório pai ao path para importar gerar_laudo
sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

ENV_PATH = str(Path(__file__).parent.parent / ".env")


def get_system():
    """Inicializa o GorilaLaudo com o .env correto"""
    from gerar_laudo import GorilaLaudo
    return GorilaLaudo(ENV_PATH)


# ============================================================
# ROTAS PRINCIPAIS
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# API — LAUDO
# ============================================================

@app.route("/api/portfolios")
def api_portfolios():
    """Busca lista de portfolios da API Gorila"""
    try:
        system = get_system()
        portfolios = system.buscar_portfolios()
        return jsonify({"ok": True, "portfolios": portfolios})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.route("/api/gerar-laudo", methods=["POST"])
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
def api_download(filename):
    """Serve o arquivo gerado para download"""
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        return jsonify({"ok": False, "erro": "Arquivo não encontrado."}), 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import webbrowser
    port = int(os.environ.get("PORT", 5000))

    # Abrir browser automaticamente após 1s
    def open_browser():
        import time
        time.sleep(1)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n🚀 Hub de Processos iniciado em http://localhost:{port}")
    print("   Pressione Ctrl+C para encerrar.\n")

    app.run(host="0.0.0.0", port=port, debug=False)
