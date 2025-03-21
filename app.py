from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from io import StringIO
from io import BytesIO
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
import csv

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})  # Ajusta o CORS pra permitir o frontend

# Configuração do MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456789@localhost/mstarsupply'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelos das tabelas
class Mercadoria(db.Model):
    __tablename__ = 'Mercadorias'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    numero_registro = db.Column(db.String(50), unique=True, nullable=False)
    fabricante = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text)
    custo_unitario = db.Column(db.Float, nullable=False, default=0.0)  # Novo campo pra custo unitário

class Entrada(db.Model):
    __tablename__ = 'Entradas'
    id = db.Column(db.Integer, primary_key=True)
    mercadoria_id = db.Column(db.Integer, db.ForeignKey('Mercadorias.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False)
    local = db.Column(db.String(100), nullable=False)

class Saida(db.Model):
    __tablename__ = 'Saidas'
    id = db.Column(db.Integer, primary_key=True)
    mercadoria_id = db.Column(db.Integer, db.ForeignKey('Mercadorias.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False)
    local = db.Column(db.String(100), nullable=False)

# Cria as tabelas
with app.app_context():
    db.create_all()

# API pra cadastrar mercadoria
@app.route('/api/mercadorias', methods=['POST'])
def cadastrar_mercadoria():
    data = request.json
    nova_mercadoria = Mercadoria(
        nome=data['nome'],
        numero_registro=data['numero_registro'],
        fabricante=data['fabricante'],
        tipo=data['tipo'],
        descricao=data.get('descricao', ''),
        custo_unitario=float(data.get('custo_unitario', 0.0))  # Novo campo no cadastro
    )
    db.session.add(nova_mercadoria)
    db.session.commit()
    return jsonify({"message": "Mercadoria cadastrada"}), 201

# API pra listar mercadorias
@app.route('/api/mercadorias', methods=['GET'])
def listar_mercadorias():
    mercadorias = Mercadoria.query.all()
    return jsonify([{"id": m.id, "nome": m.nome, "custo_unitario": m.custo_unitario} for m in mercadorias])

# API pra verificar disponibilidade de uma mercadoria
@app.route('/api/mercadorias/<int:id>/disponibilidade', methods=['GET'])
def verificar_disponibilidade(id):
    entradas = Entrada.query.filter_by(mercadoria_id=id).all()
    saidas = Saida.query.filter_by(mercadoria_id=id).all()
    total_entradas = sum(e.quantidade for e in entradas)
    total_saidas = sum(s.quantidade for s in saidas)
    disponibilidade = total_entradas - total_saidas
    return jsonify({"disponibilidade": disponibilidade})

# API pra cadastrar entrada
@app.route('/api/entradas', methods=['POST'])
def cadastrar_entrada():
    data = request.json
    nova_entrada = Entrada(
        mercadoria_id=data['mercadoria_id'],
        quantidade=data['quantidade'],
        data_hora=datetime.strptime(data['data_hora'], '%Y-%m-%d %H:%M:%S'),
        local=data['local']
    )
    db.session.add(nova_entrada)
    db.session.commit()
    return jsonify({"message": "Entrada registrada"}), 201

# API pra cadastrar saída
@app.route('/api/saidas', methods=['POST'])
def cadastrar_saida():
    data = request.json
    # Verifica disponibilidade antes de registrar a saída
    entradas = Entrada.query.filter_by(mercadoria_id=data['mercadoria_id']).all()
    saidas = Saida.query.filter_by(mercadoria_id=data['mercadoria_id']).all()
    total_entradas = sum(e.quantidade for e in entradas)
    total_saidas = sum(s.quantidade for s in saidas)
    disponibilidade = total_entradas - total_saidas
    if disponibilidade < data['quantidade']:
        return jsonify({"error": "Quantidade insuficiente em estoque"}), 400

    nova_saida = Saida(
        mercadoria_id=data['mercadoria_id'],
        quantidade=data['quantidade'],
        data_hora=datetime.strptime(data['data_hora'], '%Y-%m-%d %H:%M:%S'),
        local=data['local']
    )
    db.session.add(nova_saida)
    db.session.commit()
    return jsonify({"message": "Saída registrada"}), 201

# API pra listar entradas e saídas por mês e ano (pra usar no gráfico e relatório)
@app.route('/api/movimentacoes/<int:mes>/<int:ano>', methods=['GET'])
def listar_movimentacoes(mes, ano):
    entradas = Entrada.query.filter(
        db.extract('month', Entrada.data_hora) == mes,
        db.extract('year', Entrada.data_hora) == ano
    ).all()
    saidas = Saida.query.filter(
        db.extract('month', Saida.data_hora) == mes,
        db.extract('year', Saida.data_hora) == ano
    ).all()
    entradas_data = [{"id": e.id, "mercadoria_id": e.mercadoria_id, "quantidade": e.quantidade, "data_hora": e.data_hora.isoformat(), "local": e.local} for e in entradas]
    saidas_data = [{"id": s.id, "mercadoria_id": s.mercadoria_id, "quantidade": s.quantidade, "data_hora": s.data_hora.isoformat(), "local": s.local} for s in saidas]
    return jsonify({"entradas": entradas_data, "saidas": saidas_data})

# API pra dashboard (resumo)
@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    total_mercadorias = Mercadoria.query.count()
    entradas_recentes = Entrada.query.order_by(Entrada.data_hora.desc()).limit(5).all()
    saidas_recentes = Saida.query.order_by(Saida.data_hora.desc()).limit(5).all()
    entradas_data = [{"mercadoria_id": e.mercadoria_id, "quantidade": e.quantidade, "data_hora": e.data_hora.isoformat()} for e in entradas_recentes]
    saidas_data = [{"mercadoria_id": s.mercadoria_id, "quantidade": s.quantidade, "data_hora": s.data_hora.isoformat()} for s in saidas_recentes]
    return jsonify({
        "total_mercadorias": total_mercadorias,
        "entradas_recentes": entradas_data,
        "saidas_recentes": saidas_data
    })

# API pra gráfico
@app.route('/api/grafico/<int:mes>/<int:ano>', methods=['GET'])
def gerar_grafico(mes, ano):
    entradas = Entrada.query.filter(
        db.extract('month', Entrada.data_hora) == mes,
        db.extract('year', Entrada.data_hora) == ano
    ).all()
    saidas = Saida.query.filter(
        db.extract('month', Saida.data_hora) == mes,
        db.extract('year', Saida.data_hora) == ano
    ).all()
    mercadorias = Mercadoria.query.all()
    mercadorias_dict = {m.id: m.nome for m in mercadorias}

    # Agrupa por mercadoria
    entradas_por_mercadoria = {}
    saidas_por_mercadoria = {}
    for e in entradas:
        mercadoria_nome = mercadorias_dict.get(e.mercadoria_id, "Desconhecido")
        if mercadoria_nome not in entradas_por_mercadoria:
            entradas_por_mercadoria[mercadoria_nome] = 0
        entradas_por_mercadoria[mercadoria_nome] += e.quantidade
    for s in saidas:
        mercadoria_nome = mercadorias_dict.get(s.mercadoria_id, "Desconhecido")
        if mercadoria_nome not in saidas_por_mercadoria:
            saidas_por_mercadoria[mercadoria_nome] = 0
        saidas_por_mercadoria[mercadoria_nome] += s.quantidade

    # Cria o gráfico
    plt.figure(figsize=(10, 5))
    mercadorias_unicas = list(set(list(entradas_por_mercadoria.keys()) + list(saidas_por_mercadoria.keys())))
    entradas_vals = [entradas_por_mercadoria.get(m, 0) for m in mercadorias_unicas]
    saidas_vals = [saidas_por_mercadoria.get(m, 0) for m in mercadorias_unicas]

    bar_width = 0.35
    x = range(len(mercadorias_unicas))
    plt.bar([i - bar_width/2 for i in x], entradas_vals, bar_width, label="Entradas", color="#007aff")
    plt.bar([i + bar_width/2 for i in x], saidas_vals, bar_width, label="Saídas", color="#ff3b30")
    plt.xticks(x, mercadorias_unicas, rotation=45)
    plt.legend()
    plt.title(f"Movimentações - Mês {mes}/{ano}")
    plt.xlabel("Mercadoria")
    plt.ylabel("Quantidade")
    plt.tight_layout()
    img = BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    return send_file(img, mimetype='image/png')

# API pra relatório PDF
@app.route('/api/relatorio/<int:mes>/<int:ano>', methods=['GET'])
def gerar_relatorio(mes, ano):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter  # Dimensões da página (612 x 792 pontos)

    # Configurações de estilo
    margem_esquerda = 40
    margem_direita = 40
    margem_topo = 40
    margem_fundo = 40
    largura_util = width - margem_esquerda - margem_direita  # 532 pontos
    y = height - margem_topo  # Posição inicial no topo

    # Configurações da tabela
    colunas = [
        ("Código", 40),
        ("Descrição", 110),
        ("U.M.", 30),
        ("Entradas", 50),
        ("Custo (R$)", 50),
        ("Saídas", 50),
        ("Custo (R$)", 50),
        ("Saldo", 50),
    ]
    largura_total = sum(col[1] for col in colunas)
    x_inicio = margem_esquerda

    # Função pra desenhar uma linha de separação
    def draw_line(y_pos, line_width=0.5):
        p.setStrokeColorRGB(0.9, 0.9, 0.9)  # Cinza claro
        p.setLineWidth(line_width)
        p.line(margem_esquerda, y_pos, margem_esquerda + largura_total, y_pos)

    # Função pra desenhar bordas verticais da tabela
    def draw_vertical_lines(y_start, y_end):
        p.setStrokeColorRGB(0.9, 0.9, 0.9)  # Cinza claro
        p.setLineWidth(0.5)
        x = x_inicio
        for _, largura in colunas:
            p.line(x, y_start, x, y_end)
            x += largura
        p.line(x, y_start, x, y_end)  # Última borda

    # Função pra desenhar o cabeçalho da tabela
    def draw_table_header():
        nonlocal y
        # Fundo cinza claro pro cabeçalho
        p.setFillColorRGB(0.95, 0.95, 0.95)  # Cinza muito claro
        p.rect(margem_esquerda, y - 15, largura_total, 20, fill=1, stroke=0)

        # Texto do cabeçalho
        p.setFont("Helvetica-Bold", 9)
        p.setFillColorRGB(0.2, 0.2, 0.2)  # Cinza escuro
        x = x_inicio
        for i, (titulo, largura) in enumerate(colunas):
            if i in [0, 1, 2]:  # Código, Descrição, U.M.
                p.drawString(x + 5, y, titulo)
            else:  # Entradas, Custo, Saídas, Saldo
                p.drawCentredString(x + largura / 2, y, titulo)
            x += largura

        y -= 15
        draw_line(y, 1.0)
        draw_vertical_lines(y, y + 15)

    # Função pra desenhar uma linha da tabela
    def draw_table_row(mercadoria, entradas_qty, saidas_qty):
        nonlocal y
        if y < margem_fundo + 60:  # Se não houver espaço suficiente
            p.showPage()
            y = height - margem_topo
            # Redesenha o cabeçalho na nova página
            p.setFont("Helvetica-Bold", 20)
            p.setFillColorRGB(0, 0, 0)
            p.drawString(margem_esquerda, y, "Relatório de Estoque - MStarSupply")
            y -= 25
            p.setFont("Helvetica", 12)
            p.setFillColorRGB(0.4, 0.4, 0.4)
            p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
            y -= 20
            draw_line(y)
            y -= 20
            draw_table_header()
            y -= 5

        p.setFont("Helvetica", 9)
        x = x_inicio
        saldo_qty = entradas_qty - saidas_qty
        custo_unitario = mercadoria.custo_unitario  # Usa o custo da mercadoria
        custo_entradas = entradas_qty * custo_unitario
        custo_saidas = saidas_qty * custo_unitario
        custo_saldo = saldo_qty * custo_unitario

        # Colunas
        p.setFillColorRGB(0.3, 0.3, 0.3)  # Cinza médio
        p.drawString(x + 5, y, str(mercadoria.id))
        x += colunas[0][1]
        p.drawString(x + 5, y, mercadoria.nome[:18])  # Limita o tamanho do nome
        x += colunas[1][1]
        p.drawString(x + 5, y, "UNID")
        x += colunas[2][1]
        p.setFillColorRGB(0, 0.48, 1)  # Azul pra entradas
        p.drawCentredString(x + colunas[3][1] / 2, y, str(entradas_qty))
        x += colunas[3][1]
        p.setFillColorRGB(0.3, 0.3, 0.3)  # Cinza médio
        p.drawCentredString(x + colunas[4][1] / 2, y, f"{custo_entradas:.2f}")
        x += colunas[4][1]
        p.setFillColorRGB(1, 0.23, 0.19)  # Vermelho pra saídas
        p.drawCentredString(x + colunas[5][1] / 2, y, str(saidas_qty))
        x += colunas[5][1]
        p.setFillColorRGB(0.3, 0.3, 0.3)  # Cinza médio
        p.drawCentredString(x + colunas[6][1] / 2, y, f"{custo_saidas:.2f}")
        x += colunas[6][1]
        # Saldo com cor condicional
        if saldo_qty < 5:  # Alerta de estoque baixo
            p.setFillColorRGB(1, 0.23, 0.19)  # Vermelho
        elif saldo_qty > 0:
            p.setFillColorRGB(0, 0.5, 0)  # Verde
        else:
            p.setFillColorRGB(0.3, 0.3, 0.3)  # Cinza
        p.drawCentredString(x + colunas[7][1] / 2, y, str(saldo_qty))
        y -= 15
        draw_line(y)
        draw_vertical_lines(y, y + 15)

    # Cabeçalho
    p.setFont("Helvetica-Bold", 20)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(margem_esquerda, y, "Relatório de Estoque - MStarSupply")
    y -= 25

    p.setFont("Helvetica", 12)
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
    y -= 20

    draw_line(y)
    y -= 20

    # Resumo Inicial
    entradas = Entrada.query.filter(
        db.extract('month', Entrada.data_hora) == mes,
        db.extract('year', Entrada.data_hora) == ano
    ).all()
    saidas = Saida.query.filter(
        db.extract('month', Saida.data_hora) == mes,
        db.extract('year', Saida.data_hora) == ano
    ).all()
    mercadorias = Mercadoria.query.all()
    mercadorias_movimentadas = len([m for m in mercadorias if any(e.mercadoria_id == m.id for e in entradas) or any(s.mercadoria_id == m.id for s in saidas)])

    p.setFont("Helvetica-Bold", 14)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(margem_esquerda, y, "Resumo Geral")
    y -= 20

    p.setFont("Helvetica", 10)
    p.setFillColorRGB(0.3, 0.3, 0.3)
    p.drawString(margem_esquerda + 10, y, f"Mercadorias Movimentadas: {mercadorias_movimentadas}")
    y -= 15
    p.setFillColorRGB(0, 0.48, 1)  # Azul
    p.drawString(margem_esquerda + 10, y, f"Total Entradas: {sum(e.quantidade for e in entradas)}")
    y -= 15
    p.setFillColorRGB(1, 0.23, 0.19)  # Vermelho
    p.drawString(margem_esquerda + 10, y, f"Total Saídas: {sum(s.quantidade for s in saidas)}")
    y -= 20

    draw_line(y)
    y -= 20

    # Tabela
    draw_table_header()
    y -= 5

    # Dados da tabela
    y_inicio_tabela = y  # Salva a posição inicial da tabela pra desenhar as bordas verticais
    for mercadoria in mercadorias:
        entradas_mercadoria = [e for e in entradas if e.mercadoria_id == mercadoria.id]
        saidas_mercadoria = [s for s in saidas if s.mercadoria_id == mercadoria.id]
        total_entradas = sum(e.quantidade for e in entradas_mercadoria)
        total_saidas = sum(s.quantidade for s in saidas_mercadoria)
        if total_entradas > 0 or total_saidas > 0:  # Só inclui mercadorias com movimentações
            draw_table_row(mercadoria, total_entradas, total_saidas)

    # Desenha as bordas verticais da tabela inteira
    draw_vertical_lines(y_inicio_tabela, y)

    # Totais gerais
    y -= 10
    total_entradas_geral = sum(e.quantidade for e in entradas)
    total_saidas_geral = sum(s.quantidade for s in saidas)
    total_saldo_geral = total_entradas_geral - total_saidas_geral

    # Calcula os custos totais usando os custos unitários de cada mercadoria
    custo_entradas_geral = 0
    custo_saidas_geral = 0
    for mercadoria in mercadorias:
        entradas_mercadoria = [e for e in entradas if e.mercadoria_id == mercadoria.id]
        saidas_mercadoria = [s for s in saidas if s.mercadoria_id == mercadoria.id]
        total_entradas = sum(e.quantidade for e in entradas_mercadoria)
        total_saidas = sum(s.quantidade for s in saidas_mercadoria)
        custo_entradas_geral += total_entradas * mercadoria.custo_unitario
        custo_saidas_geral += total_saidas * mercadoria.custo_unitario

    # Fundo cinza claro pro total geral
    p.setFillColorRGB(0.95, 0.95, 0.95)  # Cinza muito claro
    p.rect(margem_esquerda, y - 15, largura_total, 20, fill=1, stroke=0)

    p.setFont("Helvetica-Bold", 9)
    p.setFillColorRGB(0, 0, 0)
    x = x_inicio
    p.drawString(x + 5, y, "Total Geral")
    x += colunas[0][1] + colunas[1][1] + colunas[2][1]
    p.setFillColorRGB(0, 0.48, 1)  # Azul pra entradas
    p.drawCentredString(x + colunas[3][1] / 2, y, str(total_entradas_geral))
    x += colunas[3][1]
    p.setFillColorRGB(0.3, 0.3, 0.3)  # Cinza médio
    p.drawCentredString(x + colunas[4][1] / 2, y, f"{custo_entradas_geral:.2f}")
    x += colunas[4][1]
    p.setFillColorRGB(1, 0.23, 0.19)  # Vermelho pra saídas
    p.drawCentredString(x + colunas[5][1] / 2, y, str(total_saidas_geral))
    x += colunas[5][1]
    p.setFillColorRGB(0.3, 0.3, 0.3)  # Cinza médio
    p.drawCentredString(x + colunas[6][1] / 2, y, f"{custo_saidas_geral:.2f}")
    x += colunas[6][1]
    if total_saldo_geral < 5:  # Alerta de estoque baixo
        p.setFillColorRGB(1, 0.23, 0.19)  # Vermelho
    elif total_saldo_geral > 0:
        p.setFillColorRGB(0, 0.5, 0)  # Verde
    else:
        p.setFillColorRGB(0.3, 0.3, 0.3)  # Cinza
    p.drawCentredString(x + colunas[7][1] / 2, y, str(total_saldo_geral))
    y -= 15
    draw_line(y, 1.0)
    draw_vertical_lines(y, y + 15)

    # Desenha as bordas verticais do total geral
    draw_vertical_lines(y_inicio_tabela, y)

    # Histórico de Movimentações
    y -= 20
    if y < margem_fundo + 100:
        p.showPage()
        y = height - margem_topo
        p.setFont("Helvetica-Bold", 20)
        p.setFillColorRGB(0, 0, 0)
        p.drawString(margem_esquerda, y, "Relatório de Estoque - MStarSupply")
        y -= 25
        p.setFont("Helvetica", 12)
        p.setFillColorRGB(0.4, 0.4, 0.4)
        p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
        y -= 20
        draw_line(y)
        y -= 20

    p.setFont("Helvetica-Bold", 14)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(margem_esquerda, y, "Histórico de Movimentações")
    y -= 20

    for mercadoria in mercadorias:
        entradas_mercadoria = [e for e in entradas if e.mercadoria_id == mercadoria.id]
        saidas_mercadoria = [s for s in saidas if s.mercadoria_id == mercadoria.id]
        if entradas_mercadoria or saidas_mercadoria:
            if y < margem_fundo + 60:
                p.showPage()
                y = height - margem_topo
                p.setFont("Helvetica-Bold", 20)
                p.setFillColorRGB(0, 0, 0)
                p.drawString(margem_esquerda, y, "Relatório de Estoque - MStarSupply")
                y -= 25
                p.setFont("Helvetica", 12)
                p.setFillColorRGB(0.4, 0.4, 0.4)
                p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
                y -= 20
                draw_line(y)
                y -= 20
                p.setFont("Helvetica-Bold", 14)
                p.setFillColorRGB(0, 0, 0)
                p.drawString(margem_esquerda, y, "Histórico de Movimentações")
                y -= 20

            p.setFont("Helvetica-Bold", 10)
            p.setFillColorRGB(0, 0, 0)
            p.drawString(margem_esquerda + 10, y, f"Mercadoria: {mercadoria.nome}")
            y -= 15

            p.setFont("Helvetica", 9)
            for e in entradas_mercadoria:
                if y < margem_fundo + 20:
                    p.showPage()
                    y = height - margem_topo
                    p.setFont("Helvetica-Bold", 20)
                    p.setFillColorRGB(0, 0, 0)
                    p.drawString(margem_esquerda, y, "Relatório de Estoque - MStarSupply")
                    y -= 25
                    p.setFont("Helvetica", 12)
                    p.setFillColorRGB(0.4, 0.4, 0.4)
                    p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
                    y -= 20
                    draw_line(y)
                    y -= 20
                    p.setFont("Helvetica-Bold", 14)
                    p.setFillColorRGB(0, 0, 0)
                    p.drawString(margem_esquerda, y, "Histórico de Movimentações")
                    y -= 20

                p.setFillColorRGB(0, 0.48, 1)  # Azul
                p.drawString(margem_esquerda + 20, y, f"Entrada: {e.quantidade} unidades - {e.data_hora.strftime('%d/%m/%Y %H:%M')} - {e.local}")
                y -= 15

            for s in saidas_mercadoria:
                if y < margem_fundo + 20:
                    p.showPage()
                    y = height - margem_topo
                    p.setFont("Helvetica-Bold", 20)
                    p.setFillColorRGB(0, 0, 0)
                    p.drawString(margem_esquerda, y, "Relatório de Estoque - MStarSupply")
                    y -= 25
                    p.setFont("Helvetica", 12)
                    p.setFillColorRGB(0.4, 0.4, 0.4)
                    p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
                    y -= 20
                    draw_line(y)
                    y -= 20
                    p.setFont("Helvetica-Bold", 14)
                    p.setFillColorRGB(0, 0, 0)
                    p.drawString(margem_esquerda, y, "Histórico de Movimentações")
                    y -= 20

                p.setFillColorRGB(1, 0.23, 0.19)  # Vermelho
                p.drawString(margem_esquerda + 20, y, f"Saída: {s.quantidade} unidades - {s.data_hora.strftime('%d/%m/%Y %H:%M')} - {s.local}")
                y -= 15

            y -= 10

    # Rodapé
    p.setFont("Helvetica", 8)
    p.setFillColorRGB(0.6, 0.6, 0.6)  # Cinza médio
    data_geracao = datetime.now().strftime('%d/%m/%Y %H:%M')
    p.drawString(margem_esquerda, margem_fundo - 10, f"Gerado em: {data_geracao}")
    p.drawString(width - margem_direita - 50, margem_fundo - 10, f"Página {p.getPageNumber()}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"relatorio_{mes}_{ano}.pdf")

# API pra verificar disponibilidade detalhada de todas as mercadorias
@app.route('/api/disponibilidade', methods=['GET'])
def verificar_disponibilidade_todas():
    mercadorias = Mercadoria.query.all()
    resultado = []
    for mercadoria in mercadorias:
        entradas = Entrada.query.filter_by(mercadoria_id=mercadoria.id).all()
        saidas = Saida.query.filter_by(mercadoria_id=mercadoria.id).all()
        total_entradas = sum(e.quantidade for e in entradas)
        total_saidas = sum(s.quantidade for s in saidas)
        disponibilidade = total_entradas - total_saidas
        alerta = "Estoque Baixo" if disponibilidade < 5 else "Normal"
        resultado.append({
            "id": mercadoria.id,
            "nome": mercadoria.nome,
            "disponibilidade": disponibilidade,
            "alerta": alerta
        })
    return jsonify(resultado)

# API pra relatório gerencial (mercadorias mais movimentadas)
@app.route('/api/relatorio_gerencial/<int:mes>/<int:ano>', methods=['GET'])
def gerar_relatorio_gerencial(mes, ano):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter  # Dimensões da página (612 x 792 pontos)

    # Configurações de estilo
    margem_esquerda = 40
    margem_direita = 40
    margem_topo = 40
    margem_fundo = 40
    largura_util = width - margem_esquerda - margem_direita
    y = height - margem_topo

    # Função pra desenhar uma linha de separação
    def draw_line(y_pos, line_width=0.5):
        p.setStrokeColorRGB(0.9, 0.9, 0.9)
        p.setLineWidth(line_width)
        p.line(margem_esquerda, y_pos, width - margem_direita, y_pos)

    # Cabeçalho
    p.setFont("Helvetica-Bold", 20)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(margem_esquerda, y, "Relatório Gerencial - MStarSupply")
    y -= 25

    p.setFont("Helvetica", 12)
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
    y -= 20

    draw_line(y)
    y -= 20

    # Dados
    entradas = Entrada.query.filter(
        db.extract('month', Entrada.data_hora) == mes,
        db.extract('year', Entrada.data_hora) == ano
    ).all()
    saidas = Saida.query.filter(
        db.extract('month', Saida.data_hora) == mes,
        db.extract('year', Saida.data_hora) == ano
    ).all()
    mercadorias = Mercadoria.query.all()
    mercadorias_dict = {m.id: m.nome for m in mercadorias}

    # Agrupa por mercadoria
    entradas_por_mercadoria = {}
    saidas_por_mercadoria = {}
    for e in entradas:
        mercadoria_id = e.mercadoria_id
        mercadoria_nome = mercadorias_dict.get(mercadoria_id, f"Desconhecido (ID: {mercadoria_id})")
        if mercadoria_nome not in entradas_por_mercadoria:
            entradas_por_mercadoria[mercadoria_nome] = 0
        entradas_por_mercadoria[mercadoria_nome] += e.quantidade

    for s in saidas:
        mercadoria_id = s.mercadoria_id
        mercadoria_nome = mercadorias_dict.get(mercadoria_id, f"Desconhecido (ID: {mercadoria_id})")
        if mercadoria_nome not in saidas_por_mercadoria:
            saidas_por_mercadoria[mercadoria_nome] = 0
        saidas_por_mercadoria[mercadoria_nome] += s.quantidade

    # Mercadorias mais movimentadas (top 5)
    movimentacoes = {}
    todas_mercadorias = set(list(entradas_por_mercadoria.keys()) + list(saidas_por_mercadoria.keys()))
    for mercadoria in todas_mercadorias:
        total_movimentacao = entradas_por_mercadoria.get(mercadoria, 0) + saidas_por_mercadoria.get(mercadoria, 0)
        movimentacoes[mercadoria] = total_movimentacao

    top_mercadorias = sorted(movimentacoes.items(), key=lambda x: x[1], reverse=True)[:5]

    # Se não houver movimentações, exibe uma mensagem
    if not top_mercadorias:
        p.setFont("Helvetica", 12)
        p.setFillColorRGB(0.4, 0.4, 0.4)
        p.drawString(margem_esquerda, y, "Nenhuma movimentação encontrada para o período selecionado.")
        y -= 20
    else:
        p.setFont("Helvetica-Bold", 14)
        p.setFillColorRGB(0, 0, 0)
        p.drawString(margem_esquerda, y, "Mercadorias Mais Movimentadas")
        y -= 20

        p.setFont("Helvetica", 10)
        for mercadoria, total in top_mercadorias:
            entradas_qty = entradas_por_mercadoria.get(mercadoria, 0)
            saidas_qty = saidas_por_mercadoria.get(mercadoria, 0)
            p.setFillColorRGB(0.3, 0.3, 0.3)
            p.drawString(margem_esquerda + 10, y, f"{mercadoria}:")
            p.setFillColorRGB(0, 0.48, 1)
            p.drawString(margem_esquerda + 150, y, f"Entradas: {entradas_qty}")
            p.setFillColorRGB(1, 0.23, 0.19)
            p.drawString(margem_esquerda + 250, y, f"Saídas: {saidas_qty}")
            p.setFillColorRGB(0.3, 0.3, 0.3)
            p.drawString(margem_esquerda + 350, y, f"Total: {total}")
            y -= 15

        # Gráfico simples (barras)
        y -= 20
        if y < margem_fundo + 200:
            p.showPage()
            y = height - margem_topo
            p.setFont("Helvetica-Bold", 20)
            p.setFillColorRGB(0, 0, 0)
            p.drawString(margem_esquerda, y, "Relatório Gerencial - MStarSupply")
            y -= 25
            p.setFont("Helvetica", 12)
            p.setFillColorRGB(0.4, 0.4, 0.4)
            p.drawString(margem_esquerda, y, f"Mês {mes:02d}/{ano}")
            y -= 20
            draw_line(y)
            y -= 20

        p.setFont("Helvetica-Bold", 14)
        p.setFillColorRGB(0, 0, 0)
        p.drawString(margem_esquerda, y, "Gráfico de Movimentações")
        y -= 20

        # Desenha o gráfico
        max_valor = max([total for _, total in top_mercadorias], default=1)
        bar_width = 60
        bar_spacing = 20
        max_height = 150
        x = margem_esquerda
        for mercadoria, total in top_mercadorias:
            bar_height = (total / max_valor) * max_height
            p.setFillColorRGB(0.6, 0.6, 0.6)
            p.rect(x, y - bar_height, bar_width, bar_height, fill=1, stroke=0)
            p.setFont("Helvetica", 8)
            p.setFillColorRGB(0.3, 0.3, 0.3)
            p.drawCentredString(x + bar_width / 2, y - bar_height - 10, str(total))
            p.drawCentredString(x + bar_width / 2, y + 10, mercadoria[:10])
            x += bar_width + bar_spacing

        y -= max_height + 40

    # Rodapé
    p.setFont("Helvetica", 8)
    p.setFillColorRGB(0.6, 0.6, 0.6)
    data_geracao = datetime.now().strftime('%d/%m/%Y %H:%M')
    p.drawString(margem_esquerda, margem_fundo - 10, f"Gerado em: {data_geracao}")
    p.drawString(width - margem_direita - 50, margem_fundo - 10, f"Página {p.getPageNumber()}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"relatorio_gerencial_{mes}_{ano}.pdf")

# API pra exportar relatório em CSV
@app.route('/api/relatorio_csv/<int:mes>/<int:ano>', methods=['GET'])
def exportar_relatorio_csv(mes, ano):
    # Dados
    entradas = Entrada.query.filter(
        db.extract('month', Entrada.data_hora) == mes,
        db.extract('year', Entrada.data_hora) == ano
    ).all()
    saidas = Saida.query.filter(
        db.extract('month', Saida.data_hora) == mes,
        db.extract('year', Saida.data_hora) == ano
    ).all()
    mercadorias = Mercadoria.query.all()

    # Debug: Verifica se os dados estão sendo carregados corretamente
    print("Entradas:", [(e.mercadoria_id, e.quantidade, e.data_hora) for e in entradas])
    print("Saídas:", [(s.mercadoria_id, s.quantidade, s.data_hora) for s in saidas])
    print("Mercadorias:", [(m.id, m.nome, m.custo_unitario) for m in mercadorias])

    # Prepara o CSV
    output = StringIO()
    writer = csv.writer(output, lineterminator='\n', delimiter=',', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["Código", "Descrição", "U.M.", "Entradas", "Custo (R$)", "Saídas", "Custo (R$)", "Saldo"])

    for mercadoria in mercadorias:
        entradas_mercadoria = [e for e in entradas if e.mercadoria_id == mercadoria.id]
        saidas_mercadoria = [s for s in saidas if s.mercadoria_id == mercadoria.id]
        total_entradas = sum(e.quantidade for e in entradas_mercadoria)
        total_saidas = sum(s.quantidade for s in saidas_mercadoria)
        if total_entradas > 0 or total_saidas > 0:
            saldo = total_entradas - total_saidas
            custo_unitario = mercadoria.custo_unitario  # Usa o custo da mercadoria
            custo_entradas = total_entradas * custo_unitario
            custo_saidas = total_saidas * custo_unitario
            writer.writerow([
                str(mercadoria.id),
                mercadoria.nome,
                "UNID",
                str(total_entradas),
                f"{custo_entradas:.2f}",
                str(total_saidas),
                f"{custo_saidas:.2f}",
                str(saldo)
            ])

    # Total Geral
    total_entradas_geral = sum(e.quantidade for e in entradas)
    total_saidas_geral = sum(s.quantidade for s in saidas)
    total_saldo_geral = total_entradas_geral - total_saidas_geral
    custo_entradas_geral = 0
    custo_saidas_geral = 0
    for mercadoria in mercadorias:
        entradas_mercadoria = [e for e in entradas if e.mercadoria_id == mercadoria.id]
        saidas_mercadoria = [s for s in saidas if s.mercadoria_id == mercadoria.id]
        total_entradas = sum(e.quantidade for e in entradas_mercadoria)
        total_saidas = sum(s.quantidade for s in saidas_mercadoria)
        custo_entradas_geral += total_entradas * mercadoria.custo_unitario
        custo_saidas_geral += total_saidas * mercadoria.custo_unitario

    writer.writerow([
        "Total Geral", "", "", str(total_entradas_geral), f"{custo_entradas_geral:.2f}", str(total_saidas_geral), f"{custo_saidas_geral:.2f}", str(total_saldo_geral)
    ])

    # Adiciona o BOM (Byte Order Mark) pra UTF-8 pra compatibilidade com Excel
    output.seek(0)
    csv_data = output.getvalue()
    output.close()

    # Adiciona o BOM no início do arquivo
    bom = '\ufeff'  # BOM pra UTF-8
    csv_with_bom = bom + csv_data

    # Debug: Imprime o conteúdo do CSV pra verificar
    print("Conteúdo do CSV:\n", csv_with_bom)

    return send_file(
        BytesIO(csv_with_bom.encode('utf-8')),
        as_attachment=True,
        download_name=f"relatorio_{mes}_{ano}.csv",
        mimetype='text/csv'
    )

# API pra busca
@app.route('/api/busca', methods=['GET'])
def buscar():
    termo = request.args.get('q', '').lower()
    tipo = request.args.get('tipo', 'mercadorias')

    if tipo == 'mercadorias':
        # Busca mercadorias por nome, número de registro, fabricante ou tipo
        resultados = Mercadoria.query.filter(
            db.or_(
                Mercadoria.nome.ilike(f'%{termo}%'),
                Mercadoria.numero_registro.ilike(f'%{termo}%'),
                Mercadoria.fabricante.ilike(f'%{termo}%'),
                Mercadoria.tipo.ilike(f'%{termo}%')
            )
        ).all()
        return jsonify([
            {
                'id': m.id,
                'nome': m.nome,
                'numero_registro': m.numero_registro,
                'fabricante': m.fabricante,
                'tipo': m.tipo,
                'descricao': m.descricao,
                'custo_unitario': m.custo_unitario
            } for m in resultados
        ])

    elif tipo == 'entradas':
        # Busca entradas por nome da mercadoria, data ou local
        entradas = Entrada.query.filter(
            Entrada.local.ilike(f'%{termo}%')
        ).all()
        mercadorias = {m.id: m.nome for m in Mercadoria.query.all()}
        resultados = [
            {
                'id': e.id,
                'mercadoria': mercadorias.get(e.mercadoria_id, 'Desconhecido'),
                'quantidade': e.quantidade,
                'data_hora': e.data_hora.isoformat(),
                'local': e.local
            }
            for e in entradas
            if termo in mercadorias.get(e.mercadoria_id, '').lower() or termo in e.data_hora.strftime('%d/%m/%Y').lower()
        ]
        return jsonify(resultados)

    elif tipo == 'saidas':
        # Busca saídas por nome da mercadoria, data ou local
        saidas = Saida.query.filter(
            Saida.local.ilike(f'%{termo}%')
        ).all()
        mercadorias = {m.id: m.nome for m in Mercadoria.query.all()}
        resultados = [
            {
                'id': s.id,
                'mercadoria': mercadorias.get(s.mercadoria_id, 'Desconhecido'),
                'quantidade': s.quantidade,
                'data_hora': s.data_hora.isoformat(),
                'local': s.local
            }
            for s in saidas
            if termo in mercadorias.get(s.mercadoria_id, '').lower() or termo in s.data_hora.strftime('%d/%m/%Y').lower()
        ]
        return jsonify(resultados)

    return jsonify({'error': 'Tipo de busca inválido!'}), 400

if __name__ == '__main__':
    app.run(debug=True, port=8000)