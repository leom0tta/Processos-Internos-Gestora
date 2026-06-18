import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from datetime import datetime
import os

# pip install openpyxl requests

API_KEY = os.getenv("GORILA_API_KEY")
BASE_URL = "https://core.gorila.com.br"

# ── Feriados nacionais de maio 2026 ───────────────────────────
feriados = [
    "2026-05-01",  # Dia do Trabalho
    # adicione outros feriados que caírem no período
]
# ─────────────────────────────────────────────────────────────

# ── Insira os clientes aqui ───────────────────────────────────
clientes = [
    {"name": "PABLO NAVARRO DIAS LANGENBACH", "portfolioId": "582f637d-0bbf-4045-9840-4a352294f1b0"},
    {"name": "WILLIAM GOMES BORGES LESSA",    "portfolioId": "9d5cdd99-d904-4aa8-985e-c700bad0896c"},
    {"name": "RAPHAEL SANTOS DE ALMEIDA REZENDE DE MATTOS",    "portfolioId": "6f3fcf6b-06c3-4f5b-8d2f-c02e905fcd71"},
]
# ─────────────────────────────────────────────────────────────

headers_api = {"authorization": API_KEY}

def is_dia_util(date_str):
    """Retorna True se a data for dia útil (seg–sex, fora dos feriados listados)."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return d.weekday() < 5 and date_str not in feriados

def get_nav_diario(portfolio_id, start="2026-05-01", end="2026-05-31"):
    url = f"{BASE_URL}/portfolios/{portfolio_id}/nav"
    params = {"frequency": "DAILY", "startDate": start, "endDate": end}
    resp = requests.get(url, headers=headers_api, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

# ── Coleta dados ──────────────────────────────────────────────
linhas = []
for cliente in clientes:
    print(f"Buscando: {cliente['name']}...")
    try:
        data = get_nav_diario(cliente["portfolioId"])
        serie = data.get("timeseries", [])

        uteis = [
            p for p in serie
            if p["nav"] is not None and is_dia_util(p["referenceDate"])
        ]
        navs = [p["nav"] for p in uteis]

        linhas.append({
            "Cliente":               cliente["name"],
            "ID":                    cliente["portfolioId"],
            "Dias úteis com dados":  len(navs),
            "Mínimo (R$)":           min(navs) if navs else None,
            "Máximo (R$)":           max(navs) if navs else None,
            "Média pro rata (R$)":   sum(navs) / len(navs) if navs else None,
            "Último dia útil":       uteis[-1]["referenceDate"] if uteis else None,
            "Patrimônio final (R$)": uteis[-1]["nav"] if uteis else None,
        })
    except Exception as e:
        print(f"  ⚠️  Erro em {cliente['name']}: {e}")
        linhas.append({
            "Cliente": cliente["name"], "ID": cliente["portfolioId"],
            "Dias úteis com dados": None, "Mínimo (R$)": None, "Máximo (R$)": None,
            "Média pro rata (R$)": None, "Último dia útil": None, "Patrimônio final (R$)": None,
        })

# ── Gera Excel ────────────────────────────────────────────────
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Patrimônio Maio 2026"

colunas = ["Cliente", "ID", "Dias úteis com dados", "Mínimo (R$)",
           "Máximo (R$)", "Média pro rata (R$)", "Último dia útil", "Patrimônio final (R$)"]

header_fill = PatternFill("solid", fgColor="1E3A5F")
header_font = Font(bold=True, color="FFFFFF", size=11)
for col_idx, col_name in enumerate(colunas, 1):
    cell = ws.cell(row=1, column=col_idx, value=col_name)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center", vertical="center")

moeda_fmt = 'R$ #,##0.00'
for row_idx, linha in enumerate(linhas, 2):
    ws.cell(row=row_idx, column=1, value=linha["Cliente"])
    ws.cell(row=row_idx, column=2, value=linha["ID"]).font = Font(size=9, color="888888")
    ws.cell(row=row_idx, column=3, value=linha["Dias úteis com dados"]).alignment = Alignment(horizontal="center")
    for col, key in [(4, "Mínimo (R$)"), (5, "Máximo (R$)"),
                     (6, "Média pro rata (R$)"), (8, "Patrimônio final (R$)")]:
        cell = ws.cell(row=row_idx, column=col, value=linha[key])
        cell.number_format = moeda_fmt
    ws.cell(row=row_idx, column=7, value=linha["Último dia útil"]).alignment = Alignment(horizontal="center")
    if row_idx % 2 == 0:
        for col in range(1, len(colunas) + 1):
            ws.cell(row=row_idx, column=col).fill = PatternFill("solid", fgColor="F0F4F8")

larguras = [40, 38, 20, 18, 18, 22, 16, 22]
for i, w in enumerate(larguras, 1):
    ws.column_dimensions[get_column_letter(i)].width = w

ws.row_dimensions[1].height = 22
ws.freeze_panes = "A2"

wb.save("patrimonio_pro_rata_maio_2026.xlsx")
print("✅ Arquivo gerado: patrimonio_pro_rata_maio_2026.xlsx")