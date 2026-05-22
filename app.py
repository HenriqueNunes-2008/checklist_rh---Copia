import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Importando a lógica do novo arquivo de PDF
from pdf_generator import criar_pdf_buffer

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "uma-chave-padrao-segura")

# --- CONFIGURAÇÃO DO BANCO DE DADOS (POSTGRESQL / MAGALU CLOUD) ---
# No Ubuntu da Magalu Cloud, exporte a variável: 
# export DATABASE_URL="postgresql://usuario:senha@host_da_instancia:5432/nome_do_banco"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///checklist.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS (TABLES) ---

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    cargo = db.Column(db.String(50))
    ativo = db.Column(db.Boolean, default=False)  # Novo campo para aprovação manual

class Funcionario(db.Model):
    __tablename__ = 'funcionarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(14), unique=True)
    data_admissao = db.Column(db.Date)
    status = db.Column(db.String(50), default='Em Aberto')
    foi_desligado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Relacionamento para facilitar acesso às respostas
    respostas = db.relationship('ChecklistResposta', backref='funcionario', lazy=True)

class ChecklistModelo(db.Model):
    __tablename__ = 'checklist_modelos'
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(50))  # admissao / desligamento
    nome_checklist = db.Column(db.String(100))
    excluido = db.Column(db.Boolean, default=False)

class ChecklistResposta(db.Model):
    __tablename__ = 'checklist_respostas'
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('checklist_modelos.id'), nullable=False)
    validado_rh = db.Column(db.Boolean, default=False)
    validado_executivo = db.Column(db.Boolean, default=False)
    # Relacionamento para facilitar acesso ao modelo
    item_modelo = db.relationship('ChecklistModelo')

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/cadastro')
def cadastro_page():
    return render_template('cadastro.html')

@app.route('/auth/cadastro', methods=['POST'])
def realizar_cadastro():
    nome = request.form.get('nome')
    email = request.form.get('email')
    senha = request.form.get('senha')
    cargo = str(request.form.get('cargo')).strip()
    senha_hash = generate_password_hash(senha)

    if Usuario.query.filter_by(email=email).first():
        flash("E-mail já cadastrado.", "danger")
        return redirect(url_for('cadastro_page'))

    try:
        novo_usuario = Usuario(
            nome=nome, email=email, senha=senha_hash, 
            cargo=cargo, ativo=False # Criado como inativo por padrão
        )
        db.session.add(novo_usuario)
        db.session.commit()
        flash("Cadastro realizado! Aguarde a ativação pelo administrador.", "success")
        return redirect(url_for('login_page'))
    except Exception as e:
        db.session.rollback()
        flash(f"Erro: {str(e)}", "danger")
        return redirect(url_for('cadastro_page'))

@app.route('/auth/login', methods=['POST'])
def realizar_login():
    email = request.form.get('email')
    senha = request.form.get('senha')
    email = request.form.get('email')
    senha = request.form.get('senha')
    user = Usuario.query.filter_by(email=email).first()
    
    if user and check_password_hash(user.senha, senha):
        if not user.ativo:
            flash("Sua conta ainda não foi ativada pelo administrador.", "warning")
            return redirect(url_for('login_page'))
            
        session['user_id'] = user.id
        session['user_nome'] = user.nome
        session['user_role'] = str(user.cargo).strip()
        return redirect(url_for('dashboard'))
    
    flash("E-mail ou senha incorretos.", "danger")
    return redirect(url_for('login_page'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# --- ROTAS DE DASHBOARD E NAVEGAÇÃO ---

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: 
        return redirect(url_for('login_page'))
    
    try:
        # Consultas SQLAlchemy
        funcionarios = Funcionario.query.order_by(Funcionario.created_at.desc()).all()
        itens_master = ChecklistModelo.query.filter_by(excluido=False).all()
        
        # Agrupar nomes de modelos únicos para os selects do formulário
        modelos_admissao = sorted(list(set(item.nome_checklist for item in itens_master if item.tipo == 'admissao')))
        modelos_desligamento = sorted(list(set(item.nome_checklist for item in itens_master if item.tipo == 'desligamento')))

        # Converte objetos SQLAlchemy para listas de dicionários se os templates esperarem dicionários
        # ou ajuste os templates para acessar objeto.atributo

        if session['user_role'] == 'RH':
            return render_template('dashboard_rh.html', 
                                   nome=session['user_nome'], 
                                   funcionarios=funcionarios,
                                   itens_master=itens_master,
                                   modelos_admissao=modelos_admissao,
                                   modelos_desligamento=modelos_desligamento)
        else:
            return render_template('dashboard_administrativo.html', 
                                   nome=session['user_nome'], 
                                   funcionarios=funcionarios)
    except Exception as e:
        flash(f"Erro ao carregar dados: {str(e)}", "danger")
        return render_template('login.html')

# --- OPERAÇÕES DE NEGÓCIO (RH) ---

@app.route('/cadastrar_funcionario', methods=['POST'])
def cadastrar_funcionario():
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    
    nome = request.form.get('nome')
    cpf = request.form.get('cpf')
    data_adm_str = request.form.get('data_admissao')
    data_adm = datetime.strptime(data_adm_str, '%Y-%m-%d').date() if data_adm_str else None
    modelo_nome = request.form.get('modelo_checklist')
    
    try:
        # 1. Cria o Funcionário
        novo_func = Funcionario(nome=nome, cpf=cpf, data_admissao=data_adm)
        db.session.add(novo_func)
        db.session.flush() # Para obter o ID antes do commit final
        
        # 2. Busca itens do modelo selecionado
        itens_modelo = ChecklistModelo.query.filter_by(nome_checklist=modelo_nome, excluido=False).all()
        
        # 3. Cria as respostas iniciais
        for item in itens_modelo:
            nova_resp = ChecklistResposta(
                funcionario_id=novo_func.id,
                item_id=item.id,
                validado_rh=False,
                validado_executivo=False
            )
            db.session.add(nova_resp)

        db.session.commit()
        flash("Funcionário e Checklist de Admissão criados!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao cadastrar funcionário: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))

@app.route('/cadastrar_item_checklist_massa', methods=['POST'])
def cadastrar_item_checklist_massa():
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    
    descricoes = request.form.getlist('descricao[]')
    tipo_global = request.form.get('tipo_global')
    nome_checklist = request.form.get('nome_checklist') # Novo campo solicitado
    
    try:
        for d in descricoes:
            if d.strip(): 
                novo_item = ChecklistModelo(descricao=d, tipo=tipo_global, nome_checklist=nome_checklist)
                db.session.add(novo_item)
        
        db.session.commit()
        flash("Itens adicionados ao modelo global!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao salvar modelos: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))

# --- SISTEMA DE CHECKLIST E VALIDAÇÃO ---

@app.route('/validar/<id_funcionario>')
def tela_validacao(id_funcionario):
    if 'user_id' not in session: return redirect(url_for('login_page'))
    
    print(f"DEBUG: Cargo do usuário na sessão: '{session.get('user_role')}'")

    try:
        funcionario = Funcionario.query.get_or_404(id_funcionario)
        # As respostas são carregadas via o relationship 'respostas' definido no model
        
        return render_template('validar_checklist.html', funcionario=funcionario, checklists=funcionario.respostas)
    except Exception as e:
        flash(f"Erro ao carregar checklist: {str(e)}", "danger")
        return redirect(url_for('dashboard'))

@app.route('/salvar_checklist/<id_funcionario>', methods=['POST'])
def salvar_checklist(id_funcionario):
    user_role = str(session.get('user_role', '')).upper()
    
    # Verifica se o checklist já está encerrado
    funcionario = Funcionario.query.get_or_404(id_funcionario)
    if funcionario.status == 'Finalizado':
        flash("Este checklist está finalizado e não pode mais ser editado.", "warning")
        return redirect(url_for('dashboard'))
    
    try:
        for r in funcionario.respostas:
            id_res = r.id
            
            if user_role == 'RH':
                val_rh = True if request.form.get(f"item_{id_res}_rh") == 'on' else False
                val_adm = True if request.form.get(f"item_{id_res}_adm") == 'on' else False
                
                r.validado_rh = val_rh
                r.validado_executivo = val_adm
                
            elif user_role in ['EXECUTIVO', 'ADMINISTRATIVO']:
                campo_nome = f"item_{id_res}_adm"
                valor = True if request.form.get(campo_nome) == 'on' else False
                r.validado_executivo = valor
        
        db.session.commit()
        flash("Validações salvas com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao salvar: {str(e)}", "danger")
        
    return redirect(url_for('dashboard'))

# --- NOVAS ROTAS DE CONTROLE DE FLUXO ---

@app.route('/iniciar_desligamento/<id_funcionario>', methods=['POST'])
def iniciar_desligamento(id_funcionario):
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    modelo_nome = request.form.get('modelo_desligamento')

    try:
        funcionario = Funcionario.query.get_or_404(id_funcionario)
        # Marcar que o desligamento foi iniciado
        funcionario.foi_desligado = True
        
        # Adicionar itens do modelo de desligamento ao checklist do funcionário
        itens_modelo = ChecklistModelo.query.filter_by(nome_checklist=modelo_nome, excluido=False).all()
        
        for item in itens_modelo:
            nova_resp = ChecklistResposta(
                funcionario_id=id_funcionario,
                item_id=item.id,
                validado_rh=False,
                validado_executivo=False
            )
            db.session.add(nova_resp)
            
        db.session.commit()
        flash("Checklist de Desligamento iniciado!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao iniciar desligamento: {str(e)}", "danger")
    return redirect(url_for('dashboard'))

@app.route('/encerrar_processo/<id_funcionario>')
def encerrar_processo(id_funcionario):
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    try:
        funcionario = Funcionario.query.get_or_404(id_funcionario)
        funcionario.status = "Finalizado"
        db.session.commit()
        flash("Processo encerrado com sucesso! Nenhuma alteração futura será permitida.", "success")
    except Exception as e:
        flash(f"Erro ao encerrar: {str(e)}", "danger")
    return redirect(url_for('dashboard'))

# --- ROTA PARA GERAR PDF ---

@app.route('/gerar_pdf/<id_funcionario>/<tipo>')
def gerar_pdf(id_funcionario, tipo):
    if 'user_id' not in session: 
        return redirect(url_for('login_page'))
    
    try:
        funcionario = Funcionario.query.get_or_404(id_funcionario)
        
        # Filtra as respostas pelo tipo de modelo associado
        respostas_filtradas = [
            r for r in funcionario.respostas 
            if r.item_modelo.tipo == tipo
        ]

        # Mapeamento para o formato esperado pelo gerador de PDF (compatibilidade)
        func_data = {
            "nome": funcionario.nome,
            "cpf": funcionario.cpf
        }
        check_data = []
        for r in respostas_filtradas:
            check_data.append({
                "checklist_modelos": {"descricao": r.item_modelo.descricao},
                "validado_rh": r.validado_rh,
                "validado_executivo": r.validado_executivo
            })

        # Gera o PDF usando a função do arquivo externo
        pdf_buffer = criar_pdf_buffer(func_data, check_data, tipo.capitalize())

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"Checklist_{tipo}_{funcionario.nome.replace(' ', '_')}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        flash(f"Erro ao gerar PDF: {str(e)}", "danger")
        return redirect(url_for('dashboard'))

# --- ADMINISTRAÇÃO DE MODELOS ---

@app.route('/excluir_item_modelo/<id_item>')
def excluir_item_modelo(id_item):
    if session.get('user_role') != 'RH': 
        return redirect(url_for('index'))
    
    try:
        item = ChecklistModelo.query.get_or_404(id_item)
        item.excluido = True
        db.session.commit()
        flash("Item removido do modelo com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir item: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        # Cria as tabelas se não existirem
        db.create_all()
    app.run(debug=True)
