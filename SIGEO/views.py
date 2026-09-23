from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import UsuarioForm
from .models import Objeto, Emprestimo, ItemEmprestimo, Categoria
import uuid
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
import random
import string
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import csv
from django.core.mail import send_mail


def limpar_emprestimos_expirados():
    """
    Função invisível que varre o banco e expira os pedidos não retirados.
    Ela procura tudo que está 'PENDENTE' mas que a data de expiração já ficou no passado.
    """
    # Filtra os pedidos não retirados que venceram
    pedidos_vencidos = Emprestimo.objects.filter(
        status_geral='PENDENTE',
        data_expiracao__lt=timezone.now()
    )

    for emp in pedidos_vencidos:
        # Muda o status do pedido para EXPIRADO
        emp.status_geral = 'EXPIRADO'
        emp.save()

        # Devolve os objetos para a prateleira (catálogo)
        for item in emp.itens.all():
            # Aqui podemos usar o mesmo status de cancelado para o item
            item.status_item = 'CANCELADO'
            item.save()

            if item.objeto:
                item.objeto.status = 'DISPONIVEL'
                item.objeto.save()

        # 2. Identifica empréstimos ATIVOS que estão em ATRASO
        # Buscamos todos os ativos e usamos o método esta_atrasado() que você já tem no model
        emprestimos_ativos = Emprestimo.objects.filter(status_geral='ATIVO')

        for emp in emprestimos_ativos:
            if emp.esta_atrasado():
                # Aqui você pode disparar o e-mail de aviso de atraso
                data_local = timezone.localtime(emp.data_expiracao)
                data_formatada = data_local.strftime('%d/%m/%Y às %H:%M')

                assunto = f"SIGEO - AVISO DE ATRASO (Pedido #{emp.id})"
                mensagem = (
                    f"Olá, {emp.usuario.nome_completo}!\n\n"
                    f"Constatamos que o seu empréstimo (Pedido #{emp.id}) está com a devolução em ATRASO.\n"
                    f"O prazo limite era {data_formatada}.\n\n"
                    f"Por favor, realize a devolução dos itens o mais rápido possível "
                    f"para evitar bloqueios no seu cadastro.\n\n"
                    f"Atenciosamente,\nEquipe SIGEO - IFPR"
                )

def registrar(request):
    if request.method == 'POST':
        form = UsuarioForm(request.POST)
        if form.is_valid():
            # Pausa o salvamento para aplicar as regras de segurança
            novo_usuario = form.save(commit=False)

            # Força o perfil padrão e blinda contra elevação de privilégio
            novo_usuario.perfil = 'SOLICITANTE'
            novo_usuario.is_staff = False

            # Criptografa a senha corretamente para o login funcionar
            novo_usuario.set_password(form.cleaned_data['senha'])

            # Grava no banco de dados
            novo_usuario.save()

            return redirect('login')
    else:
        form = UsuarioForm()

    return render(request, 'registrar.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('painel')
    erro = None
    if request.method == "POST":
        email = request.POST.get("email")
        senha = request.POST.get("senha")

        # O Django compara a senha digitada com o hash salvo no banco automaticamente
        usuario = authenticate(request, username=email, password=senha)

        if usuario is not None:
            login(request, usuario)  # Cria a sessão segura nativa
            return redirect("painel")
        else:
            erro = "Email ou senha incorretos."

    return render(request, "login.html", {"erro": erro})


def logout_view(request):
    logout(request)  # Destrói a sessão nativa com segurança
    return redirect("login")


# Este decorador atende ao seu RNF02 (Controle de Acesso no backend)
@login_required(login_url='/login/')
def painel(request):
    limpar_emprestimos_expirados()
    # Filtra apenas os empréstimos do usuário logado e ordena do mais recente para o mais antigo
    meus_emprestimos = Emprestimo.objects.filter(usuario=request.user).order_by('-id')

    # Verifica se o usuário é administrador ou solicitante comum
    perfil_usuario = 'Administrador' if request.user.is_staff else 'Solicitante'

    contexto = {
        'nome': request.user.nome_completo,  # Usa o campo nome_completo que você criou no seu model
        'perfil': perfil_usuario,
        'emprestimos': meus_emprestimos
    }

    return render(request, 'painel.html', contexto)


@login_required(login_url='/login/')
def catalogo_objetos(request):
    limpar_emprestimos_expirados()

    # --- LÓGICA DE BLOQUEIO (RF24) ---
    usuario_bloqueado = False
    # Puxa os empréstimos ativos do usuário logado
    emprestimos_ativos = Emprestimo.objects.filter(usuario=request.user, status_geral='ATIVO')
    for emp in emprestimos_ativos:
        if emp.esta_atrasado():
            usuario_bloqueado = True
            break  # Achou um atrasado, já pode parar de procurar e aplicar o bloqueio
    # --------------------------------

    objetos_disponiveis = Objeto.objects.filter(status='DISPONIVEL')
    categorias = Categoria.objects.all()

    query = request.GET.get('q')
    categoria_id = request.GET.get('categoria')

    if query:
        objetos_disponiveis = objetos_disponiveis.filter(
            Q(nome_objeto__icontains=query) |
            Q(descricao__icontains=query) |
            Q(cg_patrimonio__icontains=query)
        )

    if categoria_id:
        objetos_disponiveis = objetos_disponiveis.filter(categoria_id=categoria_id)

    contexto = {
        'objetos': objetos_disponiveis,
        'categorias': categorias,
        'busca_atual': query,
        'categoria_atual': str(categoria_id) if categoria_id else '',
        'usuario_bloqueado': usuario_bloqueado  # Mandamos a informação para a tela!
    }
    return render(request, 'catalogo.html', contexto)

@login_required(login_url='/login/')
def solicitar_emprestimo(request, objeto_id):
    # Busca o objeto ou retorna erro 404 se não existir
    objeto = get_object_or_404(Objeto, id=objeto_id, status='DISPONIVEL')

    # Define a data de expiração da solicitação (ex: 24 horas para retirar)
    data_exp = timezone.now() + timedelta(days=1)

    # Gera códigos únicos de retirada e devolução (8 caracteres)
    cod_retirada = str(uuid.uuid4())[:8].upper()
    cod_devolucao = str(uuid.uuid4())[:8].upper()

    # Cria o Empréstimo principal com os novos códigos
    emprestimo = Emprestimo.objects.create(
        usuario=request.user,
        data_expiracao=data_exp,
        codigo_retirada=cod_retirada,
        codigo_devolucao=cod_devolucao,
        status_geral='PENDENTE'
    )

    # Cria o Item do Empréstimo vinculando o objeto
    prazo_devolucao = timezone.now() + timedelta(days=objeto.categoria.prazo_dias)
    ItemEmprestimo.objects.create(
        emprestimo=emprestimo,
        objeto=objeto,
        data_devolucao_prevista=prazo_devolucao,
        status_item='AGUARDANDO_RETIRADA'
    )

    # Altera o status do objeto para emprestado/reservado
    objeto.status = 'EMPRESTADO'
    objeto.save()

    return redirect('painel')


@login_required(login_url='/login/')
def validar_codigo(request):
    # Se não for funcionário/admin, manda de volta pro painel
    if not request.user.is_staff:
        return redirect('painel')

    mensagem = None
    cor_mensagem = "info"

    if request.method == "POST":
        codigo = request.POST.get("codigo").strip().upper()

        # 1. Verifica se é um código de RETIRADA
        emprestimo_retirada = Emprestimo.objects.filter(codigo_retirada=codigo, status_geral='PENDENTE').first()

        if emprestimo_retirada:
            emprestimo_retirada.status_geral = 'ATIVO'  # Altera o status do empréstimo
            emprestimo_retirada.save()

            mensagem = f"Retirada confirmada! Objeto liberado para {emprestimo_retirada.usuario.nome_completo}."
            cor_mensagem = "success"

        else:
            # 2. Se não for retirada, verifica se é um código de DEVOLUÇÃO
            emprestimo_devolucao = Emprestimo.objects.filter(codigo_devolucao=codigo, status_geral='ATIVO').first()

            if emprestimo_devolucao:
                # AQUI ACONTECE A MÁGICA: Em vez de concluir, redireciona para a tela de avaliação!
                return redirect('avaliar_devolucao', emprestimo_id=emprestimo_devolucao.id)

            else:
                mensagem = "Código inválido, expirado ou não encontrado no sistema."
                cor_mensagem = "danger"

    return render(request, 'validar_codigo.html', {'mensagem': mensagem, 'cor_mensagem': cor_mensagem})


@login_required(login_url='/login/')
def gerenciar_emprestimos(request):
    limpar_emprestimos_expirados()
    # Bloqueia se não for funcionário
    if not request.user.is_staff:
        return redirect('painel')

    todos_emprestimos = Emprestimo.objects.all().order_by('-id')

    # --- Lógica das Estatísticas ---
    total_objetos = Objeto.objects.count()
    disponiveis = Objeto.objects.filter(status='DISPONIVEL').count()
    emprestados = Objeto.objects.filter(status='EMPRESTADO').count()
    em_manutencao = Objeto.objects.filter(status='MANUTENCAO').count()

    contexto = {
        'emprestimos': todos_emprestimos,
        'total_objetos': total_objetos,
        'disponiveis': disponiveis,
        'emprestados': emprestados,
        'em_manutencao': em_manutencao,
    }

    return render(request, 'gerenciar_emprestimos.html', contexto)


@login_required(login_url='/login/')
def cancelar_emprestimo(request, emprestimo_id):
    emprestimo = get_object_or_404(Emprestimo, id=emprestimo_id, usuario=request.user, status_geral='PENDENTE')

    emprestimo.status_geral = 'CANCELADO'
    emprestimo.save()

    # AGORA BUSCAMOS TODOS OS ITENS DO PEDIDO E NÃO SÓ O PRIMEIRO
    itens = ItemEmprestimo.objects.filter(emprestimo=emprestimo)
    for item in itens:
        item.status_item = 'CANCELADO'
        item.save()

        if item.objeto:
            item.objeto.status = 'DISPONIVEL'
            item.objeto.save()

    return redirect('painel')

@login_required(login_url='/login/')
def avaliar_devolucao(request, emprestimo_id):
    if not request.user.is_staff:
        return redirect('painel')

    emprestimo = get_object_or_404(Emprestimo, id=emprestimo_id, status_geral='ATIVO')

    # Filtra APENAS os itens que ainda NÃO foram devolvidos
    itens_pendentes = ItemEmprestimo.objects.filter(emprestimo=emprestimo).exclude(status_item='DEVOLVIDO')

    if request.method == 'POST':
        itens_devolvidos_agora = 0

        for item in itens_pendentes:
            nova_condicao = request.POST.get(f'condicao_{item.id}')
            # A observacao está sendo capturada aqui (podemos salvar no banco no futuro se quiser)
            observacao = request.POST.get(f'obs_{item.id}')

            # Se o funcionário marcou uma condição e NÃO escolheu "Ainda com o aluno"
            if nova_condicao and nova_condicao != 'NAO_DEVOLVIDO':
                objeto = item.objeto
                objeto.condicao = nova_condicao

                if nova_condicao == 'AVARIADO':
                    objeto.status = 'MANUTENCAO'
                else:
                    objeto.status = 'DISPONIVEL'
                objeto.save()

                item.status_item = 'DEVOLVIDO'
                item.condicao_retorno = nova_condicao
                item.save()

                itens_devolvidos_agora += 1

        # Verifica se ainda sobrou algum item com o aluno após essa devolução
        ainda_pendentes = ItemEmprestimo.objects.filter(emprestimo=emprestimo).exclude(status_item='DEVOLVIDO').count()

        if ainda_pendentes == 0:
            # Tudo devolvido! Conclui o pedido
            emprestimo.status_geral = 'CONCLUIDO'
            emprestimo.save()
            mensagem = "Devolução finalizada! Todos os itens deste pedido foram retornados."
        else:
            # Faltam itens, mantém o empréstimo ATIVO
            mensagem = f"Devolução PARCIAL registrada! {itens_devolvidos_agora} item(ns) retornado(s). O aluno ainda precisa devolver {ainda_pendentes} item(ns)."

        return render(request, 'validar_codigo.html', {
            'mensagem': mensagem,
            'cor_mensagem': 'success'
        })

    opcoes_condicao = Objeto._meta.get_field('condicao').choices

    return render(request, 'avaliar_devolucao.html', {
        'emprestimo': emprestimo,
        'itens': itens_pendentes,
        'condicoes': opcoes_condicao
    })


@login_required(login_url='/login/')
def gerenciar_manutencao(request):
    if not request.user.is_staff:
        return redirect('painel')

    # Busca apenas os objetos que estão com status de manutenção
    objetos_manutencao = Objeto.objects.filter(status='MANUTENCAO').order_by('nome_objeto')

    return render(request, 'manutencao.html', {'objetos': objetos_manutencao})


@login_required(login_url='/login/')
def concluir_manutencao(request, objeto_id):
    if not request.user.is_staff:
        return redirect('painel')

    objeto = get_object_or_404(Objeto, id=objeto_id, status='MANUTENCAO')

    # Restaura a condição para perfeito e o status para disponível
    objeto.condicao = 'INTEGRO'
    objeto.status = 'DISPONIVEL'
    objeto.save()

    return redirect('gerenciar_manutencao')


@login_required(login_url='/login/')
def adicionar_ao_pedido(request, objeto_id):
    # Se o carrinho não existir na sessão do usuario, cria uma lista vazia
    if 'carrinho' not in request.session:
        request.session['carrinho'] = []

    carrinho = request.session['carrinho']

    # Só adiciona se o objeto já não estiver no carrinho
    if objeto_id not in carrinho:
        carrinho.append(objeto_id)
        # Avisa o Django que a sessão foi modificada e precisa ser salva
        request.session.modified = True

        # Redireciona de volta para o catálogo para ele continuar escolhendo
    return redirect('catalogo')


@login_required(login_url='/login/')
def revisar_pedido(request):
    # Pega os IDs salvos na sessão (ou uma lista vazia se não tiver nada)
    carrinho_ids = request.session.get('carrinho', [])

    # Busca no banco os objetos reais usando os IDs
    objetos_no_carrinho = Objeto.objects.filter(id__in=carrinho_ids)

    if request.method == 'POST':
        if not objetos_no_carrinho:
            return redirect('catalogo')

        # 1. Cria o "Guarda-chuva" (O Empréstimo principal)
        # Exemplo: o aluno tem 24h para ir retirar no balcão
        data_expiracao = timezone.now() + timedelta(hours=3)
        codigo_ret = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        codigo_dev = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        novo_emprestimo = Emprestimo.objects.create(
            usuario=request.user,
            data_expiracao=data_expiracao,
            codigo_retirada=codigo_ret,
            codigo_devolucao=codigo_dev,
            status_geral='PENDENTE'
        )

        # 2. Cria os Itens individuais dentro deste empréstimo
        for obj in objetos_no_carrinho:
            # Puxa o prazo de dias diretamente da categoria do objeto
            prazo = obj.categoria.prazo_dias
            data_devolucao = timezone.now() + timedelta(days=prazo)

            ItemEmprestimo.objects.create(
                emprestimo=novo_emprestimo,
                objeto=obj,
                data_devolucao_prevista=data_devolucao,
                status_item='AGUARDANDO_RETIRADA'
            )

            # Muda o status do objeto para que ninguém mais pegue no catálogo
            obj.status = 'EMPRESTADO'
            obj.save()

            # 3. Limpa o carrinho
            request.session['carrinho'] = []
            request.session.modified = True

            # Converte a data para o fuso horário local antes de formatar para o texto
            data_local = timezone.localtime(novo_emprestimo.data_expiracao)
            data_formatada = data_local.strftime('%d/%m/%Y às %H:%M')

            # 4. Envia o e-mail de confirmação para o aluno
            assunto = f"SIGEO - Pedido Solicitado (Código: {novo_emprestimo.codigo_retirada})"
            mensagem = (
                f"Olá, {request.user.nome_completo}!\n\n"
                f"Sua solicitação foi registrada com sucesso.\n\n"
                f"Você tem até o dia {data_formatada} "
                f"para ir ao balcão retirar seus itens.\n\n"
                f"Apresente este código de retirada: {novo_emprestimo.codigo_retirada}\n\n"
                f"Atenciosamente,\nEquipe SIGEO - IFPR"
            )

            # Parâmetros: Assunto, Mensagem, Remetente, Lista de Destinatários
            send_mail(
                assunto,
                mensagem,
                None,  # Usa o DEFAULT_FROM_EMAIL do settings
                [request.user.email]
            )

            return redirect('painel')

    return render(request, 'revisar_pedido.html', {'objetos': objetos_no_carrinho})


@login_required(login_url='/login/')
def remover_do_pedido(request, objeto_id):
    carrinho = request.session.get('carrinho', [])
    if objeto_id in carrinho:
        carrinho.remove(objeto_id)
        request.session.modified = True
    return redirect('revisar_pedido')


@login_required(login_url='/login/')
def renovar_emprestimo(request, emprestimo_id):
    emprestimo = get_object_or_404(Emprestimo, id=emprestimo_id, usuario=request.user, status_geral='ATIVO')

    # Só renova se não estiver atrasado
    if not emprestimo.esta_atrasado():
        nova_data_maxima = emprestimo.data_expiracao
        itens_pendentes = emprestimo.itens.exclude(status_item='DEVOLVIDO')

        # 1. Atualiza cada item com o seu prazo específico da categoria
        for item in itens_pendentes:
            # Puxa o prazo dinâmico da categoria daquele objeto específico
            prazo_dias = item.objeto.categoria.prazo_dias

            # Adiciona os dias específicos
            item.data_devolucao_prevista += timedelta(days=prazo_dias)
            item.save()

            # Descobre qual é a data mais distante para atualizar o pedido principal
            if item.data_devolucao_prevista > nova_data_maxima:
                nova_data_maxima = item.data_devolucao_prevista

        # 2. Atualiza a data geral do empréstimo para bater com o último item a ser devolvido
        if itens_pendentes.exists():
            emprestimo.data_expiracao = nova_data_maxima
            emprestimo.save()

    return redirect('painel')


@login_required(login_url='/login/')
def meu_perfil(request):
    mensagem = None
    cor_mensagem = None

    if request.method == 'POST':
        telefone = request.POST.get('telefone')
        senha = request.POST.get('senha')
        confirmar_senha = request.POST.get('confirmar_senha')

        usuario = request.user

        # 1. Atualiza o telefone
        usuario.telefone = telefone

        # 2. Verifica se o aluno preencheu algo na senha
        if senha or confirmar_senha:
            if senha == confirmar_senha:
                usuario.set_password(senha)
                usuario.save()
                # Mantém o aluno logado após mudar a senha
                update_session_auth_hash(request, usuario)

                mensagem = "Perfil e senha atualizados com sucesso!"
                cor_mensagem = "success"
            else:
                mensagem = "As senhas não coincidem. Tente novamente."
                cor_mensagem = "danger"
        else:
            # Se não mexeu na senha, só salva o telefone
            usuario.save()
            mensagem = "Telefone atualizado com sucesso!"
            cor_mensagem = "success"

    return render(request, 'meu_perfil.html', {
        'mensagem': mensagem,
        'cor_mensagem': cor_mensagem
    })


@login_required(login_url='/login/')
def relatorio_inventario_pdf(request):
    if not request.user.is_staff:
        return redirect('painel')

    # Busca todos os objetos ordenados primeiro por categoria, depois por nome
    objetos = Objeto.objects.all().order_by('categoria__nome_categoria', 'nome_objeto')

    contexto = {
        'objetos': objetos,
        'total': objetos.count(),
        'disponiveis': objetos.filter(status='DISPONIVEL').count(),
        'emprestados': objetos.filter(status='EMPRESTADO').count(),
        'manutencao': objetos.filter(status='MANUTENCAO').count(),
        'data_geracao': timezone.now()
    }

    # Carrega o HTML que será usado como "molde"
    template = get_template('relatorio_pdf.html')
    html = template.render(contexto)

    # Configura a resposta para forçar o download de um arquivo PDF
    response = HttpResponse(content_type='application/pdf')
    # Use 'attachment' para baixar direto, ou 'inline' para abrir no navegador antes
    response['Content-Disposition'] = 'attachment; filename="inventario_sigeo.pdf"'

    # Converte o HTML em PDF
    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('Tivemos um problema ao gerar o PDF.', status=500)

    return response


@login_required(login_url='/login/')
def relatorio_inventario_csv(request):
    if not request.user.is_staff:
        return redirect('painel')

    # Configura a resposta para baixar um arquivo CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventario_sigeo.csv"'

    response.write('\ufeff')

    # Cria o "escritor" do arquivo
    writer = csv.writer(response, delimiter=';')

    # Escreve a primeira linha (Cabeçalhos das colunas)
    writer.writerow(['Patrimônio', 'Objeto', 'Categoria', 'Condição', 'Status Atual'])

    # Busca os objetos e escreve uma linha para cada um
    objetos = Objeto.objects.all().order_by('categoria__nome_categoria', 'nome_objeto')
    for obj in objetos:
        writer.writerow([
            obj.cg_patrimonio if obj.cg_patrimonio else 'S/N',
            obj.nome_objeto,
            obj.categoria.nome_categoria,
            obj.get_condicao_display(),
            obj.get_status_display()
        ])

    return response