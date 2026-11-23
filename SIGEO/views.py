from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .forms import UsuarioForm
from .models import Objeto, Emprestimo, ItemEmprestimo, Categoria, Subcategoria, Usuario
import uuid
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q, Count
import random
import string
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import csv
from django.core.mail import send_mail
from collections import Counter
from django.contrib import messages


def is_atendente_ou_admin(user):
    return user.is_authenticated and (user.perfil in ['ADMIN', 'ATENDENTE'] or user.is_superuser)


def is_admin(user):
    return user.is_authenticated and (user.perfil == 'ADMIN' or user.is_superuser)


def limpar_emprestimos_expirados():
    """
    Função invisível que varre o banco e expira os pedidos não retirados.
    Ela procura tudo que está 'PENDENTE' mas que a data de expiração já ficou no passado.
    """
    pedidos_vencidos = Emprestimo.objects.filter(
        status_geral='PENDENTE',
        data_expiracao__lt=timezone.now()
    )

    for emp in pedidos_vencidos:
        emp.status_geral = 'EXPIRADO'
        emp.save()

        for item in emp.itens.all():
            item.status_item = 'CANCELADO'
            item.save()

            if item.objeto:
                item.objeto.status = 'DISPONIVEL'
                item.objeto.save()

    emprestimos_ativos = Emprestimo.objects.filter(status_geral='ATIVO')
    for emp in emprestimos_ativos:
        if emp.esta_atrasado():
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
            novo_usuario = form.save(commit=False)
            novo_usuario.perfil = 'SOLICITANTE'
            novo_usuario.is_staff = False
            novo_usuario.set_password(form.cleaned_data['senha'])
            novo_usuario.save()

            messages.success(request, "Cadastro concluído com sucesso! Realize o login para continuar.")
            return redirect('login')
        else:
            messages.error(request, "Não foi possível concluir o cadastro. Verifique se o e-mail ou matrícula já estão em uso.")
    else:
        form = UsuarioForm()

    return render(request, 'registrar.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('inicio')
    erro = None
    if request.method == "POST":
        email = request.POST.get("email")
        senha = request.POST.get("senha")

        usuario = authenticate(request, username=email, password=senha)

        if usuario is not None:
            login(request, usuario)
            return redirect("inicio")
        else:
            erro = "Email ou senha incorretos."

    return render(request, "login.html", {"erro": erro})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required(login_url='/login/')
def inicio(request):
    limpar_emprestimos_expirados()

    total_disponiveis = Objeto.objects.filter(status='DISPONIVEL').count()
    meus_ativos = Emprestimo.objects.filter(usuario=request.user, status_geral='ATIVO').count()
    meus_concluidos = Emprestimo.objects.filter(usuario=request.user, status_geral='CONCLUIDO').count()

    emprestimo_destaque = Emprestimo.objects.filter(
        usuario=request.user,
        status_geral__in=['ATIVO', 'PENDENTE']
    ).order_by('-id').first()

    contexto = {
        'total_disponiveis': total_disponiveis,
        'meus_ativos': meus_ativos,
        'meus_concluidos': meus_concluidos,
        'emprestimo_destaque': emprestimo_destaque,
    }
    return render(request, 'inicio.html', contexto)


@login_required(login_url='/login/')
def painel(request):
    limpar_emprestimos_expirados()
    meus_emprestimos = Emprestimo.objects.filter(usuario=request.user).order_by('-id')

    contexto = {
        'emprestimos': meus_emprestimos
    }

    return render(request, 'painel.html', contexto)


@login_required(login_url='/login/')
def catalogo_objetos(request):
    limpar_emprestimos_expirados()

    tem_atraso = False
    emprestimos_ativos = Emprestimo.objects.filter(usuario=request.user, status_geral='ATIVO')
    for emp in emprestimos_ativos:
        if emp.esta_atrasado():
            tem_atraso = True
            break

    usuario_bloqueado = request.user.esta_bloqueado or tem_atraso

    subcategorias = Subcategoria.objects.annotate(
        qtd_disponivel=Count('objetos', filter=Q(objetos__status='DISPONIVEL'))
    ).filter(qtd_disponivel__gt=0)

    categorias = Categoria.objects.all()
    query = request.GET.get('q')
    categoria_id = request.GET.get('categoria')

    if query:
        subcategorias = subcategorias.filter(
            Q(nome_subcategoria__icontains=query) |
            Q(categoria__nome_categoria__icontains=query)
        )

    if categoria_id:
        subcategorias = subcategorias.filter(categoria_id=categoria_id)

    contexto = {
        'subcategorias': subcategorias,
        'categorias': categorias,
        'busca_atual': query,
        'categoria_atual': str(categoria_id) if categoria_id else '',
        'usuario_bloqueado': usuario_bloqueado,
        'tem_atraso': tem_atraso,
    }
    return render(request, 'catalogo.html', contexto)

@login_required(login_url='/login/')
def solicitar_emprestimo(request, objeto_id):
    if request.user.esta_bloqueado:
        messages.error(request, f"Você está suspenso de realizar empréstimos até {request.user.bloqueado_ate.strftime('%d/%m/%Y %H:%M')} devido a atraso na devolução.")
        return redirect('painel')

    objeto = get_object_or_404(Objeto, id=objeto_id, status='DISPONIVEL')

    data_exp = timezone.now() + timedelta(days=1)
    cod_retirada = str(uuid.uuid4())[:8].upper()
    cod_devolucao = str(uuid.uuid4())[:8].upper()

    emprestimo = Emprestimo.objects.create(
        usuario=request.user,
        data_expiracao=data_exp,
        codigo_retirada=cod_retirada,
        codigo_devolucao=cod_devolucao,
        status_geral='PENDENTE'
    )

    subcat = objeto.subcategoria
    if subcat.prazo_unidade == 'HORAS':
        prazo_devolucao = timezone.now() + timedelta(hours=subcat.prazo_valor)
    else:
        prazo_devolucao = timezone.now() + timedelta(days=subcat.prazo_valor)

    ItemEmprestimo.objects.create(
        emprestimo=emprestimo,
        objeto=objeto,
        data_devolucao_prevista=prazo_devolucao,
        status_item='AGUARDANDO_RETIRADA'
    )

    objeto.status = 'EMPRESTADO'
    objeto.save()

    return redirect('painel')


@login_required(login_url='/login/')
def validar_codigo(request):
    if not is_atendente_ou_admin(request.user):
        return redirect('painel')

    mensagem = None
    cor_mensagem = "info"

    if request.method == "POST":
        codigo = request.POST.get("codigo").strip().upper()

        emprestimo_retirada = Emprestimo.objects.filter(codigo_retirada=codigo, status_geral='PENDENTE').first()

        if emprestimo_retirada:
            emprestimo_retirada.status_geral = 'ATIVO'
            emprestimo_retirada.save()

            mensagem = f"Retirada confirmada! Objeto liberado para {emprestimo_retirada.usuario.nome_completo}."
            cor_mensagem = "success"
        else:
            emprestimo_devolucao = Emprestimo.objects.filter(codigo_devolucao=codigo, status_geral='ATIVO').first()

            if emprestimo_devolucao:
                return redirect('avaliar_devolucao', emprestimo_id=emprestimo_devolucao.id)
            else:
                mensagem = "Código inválido, expirado ou não encontrado no sistema."
                cor_mensagem = "danger"

    return render(request, 'validar_codigo.html', {'mensagem': mensagem, 'cor_mensagem': cor_mensagem})


@login_required(login_url='/login/')
def gerenciar_emprestimos(request):
    limpar_emprestimos_expirados()
    if not is_atendente_ou_admin(request.user):
        return redirect('painel')

    todos_emprestimos = Emprestimo.objects.all().order_by('-id')

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
    if not is_atendente_ou_admin(request.user):
        return redirect('painel')

    emprestimo = get_object_or_404(Emprestimo, id=emprestimo_id, status_geral='ATIVO')
    itens_pendentes = ItemEmprestimo.objects.filter(emprestimo=emprestimo).exclude(status_item='DEVOLVIDO')

    if request.method == 'POST':
        itens_devolvidos_agora = 0
        estava_atrasado = emprestimo.esta_atrasado()

        for item in itens_pendentes:
            nova_condicao = request.POST.get(f'condicao_{item.id}')
            observacao = request.POST.get(f'obs_{item.id}')

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

        ainda_pendentes = ItemEmprestimo.objects.filter(emprestimo=emprestimo).exclude(status_item='DEVOLVIDO').count()

        if ainda_pendentes == 0:
            emprestimo.status_geral = 'CONCLUIDO'
            emprestimo.save()

            if estava_atrasado and itens_devolvidos_agora > 0:
                solicitante = emprestimo.usuario
                solicitante.bloqueado_ate = timezone.now() + timedelta(days=3)
                solicitante.motivo_bloqueio = f"Devolução em atraso referente ao Pedido #{emprestimo.id}."
                solicitante.save()
                mensagem = f"Devolução finalizada com atraso! O usuário {solicitante.nome_completo} foi suspenso por 3 dias."
                cor = 'warning'
            else:
                mensagem = "Devolução finalizada! Todos os itens deste pedido foram retornados."
                cor = 'success'
        else:
            mensagem = f"Devolução PARCIAL registrada! {itens_devolvidos_agora} item(ns) retornado(s). O aluno ainda precisa devolver {ainda_pendentes} item(ns)."
            cor = 'success'

        return render(request, 'validar_codigo.html', {
            'mensagem': mensagem,
            'cor_mensagem': cor
        })

    opcoes_condicao = Objeto._meta.get_field('condicao').choices

    return render(request, 'avaliar_devolucao.html', {
        'emprestimo': emprestimo,
        'itens': itens_pendentes,
        'condicoes': opcoes_condicao
    })


@login_required(login_url='/login/')
def gerenciar_manutencao(request):
    if not is_atendente_ou_admin(request.user):
        return redirect('painel')

    objetos_manutencao = Objeto.objects.filter(status='MANUTENCAO').order_by('nome_objeto')

    return render(request, 'manutencao.html', {'objetos': objetos_manutencao})


@login_required(login_url='/login/')
def concluir_manutencao(request, objeto_id):
    if not is_atendente_ou_admin(request.user):
        return redirect('painel')

    objeto = get_object_or_404(Objeto, id=objeto_id, status='MANUTENCAO')

    objeto.condicao = 'INTEGRO'
    objeto.status = 'DISPONIVEL'
    objeto.save()

    return redirect('gerenciar_manutencao')


@login_required(login_url='/login/')
def adicionar_ao_pedido(request, subcategoria_id):
    if request.user.esta_bloqueado:
        messages.error(request, f"Você está suspenso de realizar empréstimos até {request.user.bloqueado_ate.strftime('%d/%m/%Y %H:%M')} devido a atraso na devolução.")
        return redirect('catalogo')

    if 'carrinho' not in request.session:
        request.session['carrinho'] = []

    carrinho = request.session['carrinho']
    quantidade = int(request.POST.get('quantidade', 1))

    subcat = get_object_or_404(Subcategoria, id=subcategoria_id)
    qtd_disponivel = Objeto.objects.filter(subcategoria=subcat, status='DISPONIVEL').count()
    qtd_no_carrinho = carrinho.count(subcategoria_id)

    limite_real = min(qtd_disponivel, subcat.limite_max_itens)

    if (qtd_no_carrinho + quantidade) <= limite_real:
        for _ in range(quantidade):
            carrinho.append(subcategoria_id)
        request.session.modified = True

        messages.success(request, f"Objeto selecionado! Vá até 'Meu Pedido' para finalizar seu pedido de {subcat.nome_subcategoria}.")
    else:
        qtd_permitida = limite_real - qtd_no_carrinho
        if qtd_permitida > 0:
            for _ in range(qtd_permitida):
                carrinho.append(subcategoria_id)
            request.session.modified = True

            messages.warning(request, f"Atenção: Você pediu {quantidade}, mas o limite disponível para você é {qtd_permitida}. Adicionamos {qtd_permitida} item(ns) ao carrinho.")
        else:
            messages.error(request, f"Você já atingiu o limite máximo de {limite_real} para este item no seu carrinho.")

    return redirect('catalogo')


@login_required(login_url='/login/')
def revisar_pedido(request):
    carrinho_ids = request.session.get('carrinho', [])
    contagem = Counter(carrinho_ids)

    itens_carrinho = []
    total_itens = len(carrinho_ids)

    for sub_id, qtd in contagem.items():
        subcat = get_object_or_404(Subcategoria, id=sub_id)
        itens_carrinho.append({
            'subcategoria': subcat,
            'quantidade': qtd
        })

    if request.method == 'POST':
        if request.user.esta_bloqueado:
            messages.error(request, f"Você está suspenso de realizar empréstimos até {request.user.bloqueado_ate.strftime('%d/%m/%Y %H:%M')} devido a atraso na devolução.")
            return redirect('painel')

        if not itens_carrinho:
            return redirect('catalogo')

        data_expiracao = timezone.now() + timedelta(hours=24)
        codigo_ret = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        codigo_dev = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        novo_emprestimo = Emprestimo.objects.create(
            usuario=request.user,
            data_expiracao=data_expiracao,
            codigo_retirada=codigo_ret,
            codigo_devolucao=codigo_dev,
            status_geral='PENDENTE'
        )

        for item in itens_carrinho:
            subcat = item['subcategoria']
            quantidade = item['quantidade']

            objetos_livres = Objeto.objects.filter(subcategoria=subcat, status='DISPONIVEL')[:quantidade]

            for objeto_livre in objetos_livres:
                if subcat.prazo_unidade == 'HORAS':
                    data_devolucao = timezone.now() + timedelta(hours=subcat.prazo_valor)
                else:
                    data_devolucao = timezone.now() + timedelta(days=subcat.prazo_valor)

                ItemEmprestimo.objects.create(
                    emprestimo=novo_emprestimo,
                    objeto=objeto_livre,
                    data_devolucao_prevista=data_devolucao,
                    status_item='AGUARDANDO_RETIRADA'
                )

                objeto_livre.status = 'EMPRESTADO'
                objeto_livre.save()

        request.session['carrinho'] = []
        request.session.modified = True

        return redirect('painel')

    return render(request, 'revisar_pedido.html', {
        'itens_carrinho': itens_carrinho,
        'total_itens': total_itens
    })


@login_required(login_url='/login/')
def remover_do_pedido(request, subcategoria_id):
    carrinho = request.session.get('carrinho', [])
    request.session['carrinho'] = [item_id for item_id in carrinho if item_id != subcategoria_id]
    request.session.modified = True
    return redirect('revisar_pedido')


@login_required(login_url='/login/')
def renovar_emprestimo(request, emprestimo_id):
    emprestimo = get_object_or_404(Emprestimo, id=emprestimo_id, usuario=request.user, status_geral='ATIVO')

    if not emprestimo.esta_atrasado() and not request.user.esta_bloqueado:
        nova_data_maxima = emprestimo.data_expiracao
        itens_pendentes = emprestimo.itens.exclude(status_item='DEVOLVIDO')

        for item in itens_pendentes:
            subcat = item.objeto.subcategoria

            if subcat.prazo_unidade == 'HORAS':
                item.data_devolucao_prevista += timedelta(hours=subcat.prazo_valor)
            else:
                item.data_devolucao_prevista += timedelta(days=subcat.prazo_valor)

            item.save()

            if item.data_devolucao_prevista > nova_data_maxima:
                nova_data_maxima = item.data_devolucao_prevista

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
        foto = request.FILES.get('foto_perfil')

        usuario = request.user
        usuario.telefone = telefone
        if foto:
            usuario.foto_perfil = foto

        if senha or confirmar_senha:
            if senha == confirmar_senha:
                usuario.set_password(senha)
                usuario.save()
                update_session_auth_hash(request, usuario)

                mensagem = "Perfil e senha atualizados com sucesso!"
                cor_mensagem = "success"
            else:
                mensagem = "As senhas não coincidem. Tente novamente."
                cor_mensagem = "danger"
        else:
            usuario.save()
            mensagem = "Perfil atualizado com sucesso!"
            cor_mensagem = "success"

    return render(request, 'meu_perfil.html', {
        'mensagem': mensagem,
        'cor_mensagem': cor_mensagem
    })


@login_required(login_url='/login/')
def relatorio_inventario_pdf(request):
    if not is_atendente_ou_admin(request.user):
        return redirect('painel')

    objetos = Objeto.objects.all().order_by('subcategoria', 'nome_objeto')

    contexto = {
        'objetos': objetos,
        'total': objetos.count(),
        'disponiveis': objetos.filter(status='DISPONIVEL').count(),
        'emprestados': objetos.filter(status='EMPRESTADO').count(),
        'manutencao': objetos.filter(status='MANUTENCAO').count(),
        'data_geracao': timezone.now()
    }

    template = get_template('relatorio_pdf.html')
    html = template.render(contexto)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="inventario_sigeo.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('Tivemos um problema ao gerar o PDF.', status=500)

    return response


@login_required(login_url='/login/')
def relatorio_inventario_csv(request):
    if not is_atendente_ou_admin(request.user):
        return redirect('painel')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventario_sigeo.csv"'

    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Patrimônio', 'Objeto', 'Subcategoria', 'Condição', 'Status Atual'])

    objetos = Objeto.objects.all().order_by('subcategoria', 'nome_objeto')
    for obj in objetos:
        writer.writerow([
            obj.cg_patrimonio if obj.cg_patrimonio else 'S/N',
            obj.nome_objeto,
            str(obj.subcategoria) if obj.subcategoria else 'Sem Subcategoria',
            obj.get_condicao_display(),
            obj.get_status_display()
        ])

    return response


@login_required(login_url='/login/')
def aumentar_qtd_pedido(request, subcategoria_id):
    carrinho = request.session.get('carrinho', [])
    subcat = get_object_or_404(Subcategoria, id=subcategoria_id)

    qtd_disponivel = Objeto.objects.filter(subcategoria=subcat, status='DISPONIVEL').count()
    qtd_no_carrinho = carrinho.count(subcategoria_id)

    limite_real = min(qtd_disponivel, subcat.limite_max_itens)

    if qtd_no_carrinho < limite_real:
        carrinho.append(subcategoria_id)
        request.session.modified = True

    return redirect('revisar_pedido')


@login_required(login_url='/login/')
def diminuir_qtd_pedido(request, subcategoria_id):
    carrinho = request.session.get('carrinho', [])
    if subcategoria_id in carrinho:
        carrinho.remove(subcategoria_id)
        request.session.modified = True
    return redirect('revisar_pedido')


# ==========================================================
# ETAPA 3: GESTÃO DE OBJETOS E USUÁRIOS
# ==========================================================

@login_required(login_url='/login/')
def gerenciar_objetos(request):
    if not is_atendente_ou_admin(request.user):
        messages.error(request, "Você não tem permissão para acessar esta página.")
        return redirect('inicio')

    # Cadastro em lote (Apenas Admin)
    if request.method == 'POST':
        if not is_admin(request.user):
            messages.error(request, "Apenas administradores podem cadastrar novos objetos.")
            return redirect('gerenciar_objetos')

        subcategoria_id = request.POST.get('subcategoria')
        nome_base = request.POST.get('nome_objeto', '').strip()
        quantidade = int(request.POST.get('quantidade', 1))
        patrimonios_texto = request.POST.get('patrimonios', '').strip()

        subcategoria = get_object_or_404(Subcategoria, id=subcategoria_id)
        lista_patrimonios = [p.strip() for p in patrimonios_texto.splitlines() if p.strip()]
        if lista_patrimonios and len(lista_patrimonios) != quantidade:
            messages.error(
                request,
                f"Atenção: Você informou quantidade {quantidade}, mas digitou {len(lista_patrimonios)} patrimônio(s). Ajuste os valores para coincidirem."
            )
            return redirect('gerenciar_objetos')

        criados = 0
        for i in range(quantidade):
            patrimonio = lista_patrimonios[i] if i < len(lista_patrimonios) else None
            nome_final = f"{nome_base} #{i+1}" if (quantidade > 1 and not patrimonio) else nome_base

            Objeto.objects.create(
                subcategoria=subcategoria,
                nome_objeto=nome_final,
                cg_patrimonio=patrimonio,
                status='DISPONIVEL'
            )
            criados += 1

        messages.success(request, f"{criados} objeto(s) cadastrado(s) com sucesso!")
        return redirect('gerenciar_objetos')

    # Filtros de visualização (Atendente e Admin)
    busca = request.GET.get('busca', '').strip()
    filtro_status = request.GET.get('status', '')
    filtro_subcategoria = request.GET.get('subcategoria', '')

    objetos = Objeto.objects.select_related('subcategoria', 'subcategoria__categoria').all().order_by('-id')

    if busca:
        objetos = objetos.filter(Q(nome_objeto__icontains=busca) | Q(cg_patrimonio__icontains=busca))
    if filtro_status:
        objetos = objetos.filter(status=filtro_status)
    if filtro_subcategoria:
        objetos = objetos.filter(subcategoria_id=filtro_subcategoria)

    subcategorias = Subcategoria.objects.select_related('categoria').all().order_by('nome_subcategoria')

    return render(request, 'gerenciar_objetos.html', {
        'objetos': objetos,
        'subcategorias': subcategorias,
        'busca': busca,
        'filtro_status': filtro_status,
        'filtro_subcategoria': filtro_subcategoria,
        'categorias': Categoria.objects.all().order_by('nome_categoria')
    })


@login_required(login_url='/login/')
def editar_objeto(request, objeto_id):
    if not is_admin(request.user):
        messages.error(request, "Apenas administradores podem editar objetos.")
        return redirect('gerenciar_objetos')

    objeto = get_object_or_404(Objeto, id=objeto_id)
    if request.method == 'POST':
        objeto.nome_objeto = request.POST.get('nome_objeto', objeto.nome_objeto).strip()
        patrimonio = request.POST.get('cg_patrimonio', '').strip()
        objeto.cg_patrimonio = patrimonio if patrimonio else None
        subcategoria_id = request.POST.get('subcategoria')
        if subcategoria_id:
            objeto.subcategoria = get_object_or_404(Subcategoria, id=subcategoria_id)
        objeto.save()

        nova_imagem = request.FILES.get('imagem_subcategoria')
        if nova_imagem:
            objeto.subcategoria.imagem = nova_imagem
            objeto.subcategoria.save()

        messages.success(request, f"Objeto '{objeto.nome_objeto}' atualizado!")

    return redirect('gerenciar_objetos')


@login_required(login_url='/login/')
def alternar_status_objeto(request, objeto_id):
    if not is_admin(request.user):
        messages.error(request, "Apenas administradores podem inativar ou reativar objetos.")
        return redirect('gerenciar_objetos')

    objeto = get_object_or_404(Objeto, id=objeto_id)
    if objeto.status == 'EMPRESTADO':
        messages.error(request, "Não é possível inativar um objeto que está emprestado no momento.")
    elif objeto.status == 'INATIVO':
        objeto.status = 'DISPONIVEL'
        objeto.save()
        messages.success(request, f"Objeto '{objeto.nome_objeto}' reativado e disponível no catálogo.")
    else:
        objeto.status = 'INATIVO'
        objeto.save()
        messages.warning(request, f"Objeto '{objeto.nome_objeto}' foi inativado.")

    return redirect('gerenciar_objetos')


@login_required(login_url='/login/')
def gerenciar_usuarios(request):
    if not is_admin(request.user):
        messages.error(request, "Acesso restrito aos administradores.")
        return redirect('inicio')

    if request.method == 'POST':
        nome = request.POST.get('nome_completo', '').strip()
        email = request.POST.get('email', '').strip()
        matricula = request.POST.get('matricula', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        perfil = request.POST.get('perfil', 'SOLICITANTE')
        senha = request.POST.get('senha', '')

        if Usuario.objects.filter(email=email).exists() or Usuario.objects.filter(matricula=matricula).exists():
            messages.error(request, "Já existe um usuário cadastrado com este e-mail ou matrícula.")
        else:
            Usuario.objects.create_user(
                email=email,
                matricula=matricula,
                nome_completo=nome,
                telefone=telefone,
                perfil=perfil,
                password=senha
            )
            messages.success(request, f"Usuário {nome} cadastrado com sucesso!")
        return redirect('gerenciar_usuarios')

    busca = request.GET.get('busca', '').strip()
    filtro_perfil = request.GET.get('perfil', '')
    filtro_bloqueio = request.GET.get('bloqueio', '')

    usuarios = Usuario.objects.all().order_by('nome_completo')
    if busca:
        usuarios = usuarios.filter(
            Q(nome_completo__icontains=busca) |
            Q(email__icontains=busca) |
            Q(matricula__icontains=busca)
        )
    if filtro_perfil:
        usuarios = usuarios.filter(perfil=filtro_perfil)
    if filtro_bloqueio == 'BLOQUEADO':
        usuarios = usuarios.filter(bloqueado_ate__gt=timezone.now())

    return render(request, 'gerenciar_usuarios.html', {
        'usuarios': usuarios,
        'busca': busca,
        'filtro_perfil': filtro_perfil,
        'filtro_bloqueio': filtro_bloqueio,
    })


@login_required(login_url='/login/')
def alterar_usuario(request, usuario_id):
    if not is_admin(request.user):
        return redirect('inicio')

    alvo = get_object_or_404(Usuario, id=usuario_id)
    if request.method == 'POST':
        novo_perfil = request.POST.get('perfil')
        ativo = request.POST.get('is_active') == 'on'
        dias_bloqueio = request.POST.get('dias_bloqueio', '').strip()
        motivo = request.POST.get('motivo_bloqueio', '').strip()

        if alvo == request.user and (novo_perfil != 'ADMIN' or not ativo):
            messages.error(request, "Você não pode remover seu próprio acesso de administrador ou desativar sua conta.")
            return redirect('gerenciar_usuarios')

        if novo_perfil in ['ADMIN', 'ATENDENTE', 'SOLICITANTE']:
            alvo.perfil = novo_perfil
        alvo.is_active = ativo

        if dias_bloqueio and int(dias_bloqueio) > 0:
            alvo.bloqueado_ate = timezone.now() + timedelta(days=int(dias_bloqueio))
            alvo.motivo_bloqueio = motivo if motivo else "Suspensão administrativa aplicada pela coordenação."
        elif motivo and alvo.esta_bloqueado:
            alvo.motivo_bloqueio = motivo

        alvo.save()
        messages.success(request, f"Dados e permissões de {alvo.nome_completo} atualizados!")

    return redirect('gerenciar_usuarios')

@login_required(login_url='/login/')
def liberar_bloqueio(request, usuario_id):
    if not is_admin(request.user):
        return redirect('inicio')

    alvo = get_object_or_404(Usuario, id=usuario_id)
    alvo.bloqueado_ate = None
    alvo.motivo_bloqueio = None
    alvo.save()
    messages.success(request, f"Bloqueio de {alvo.nome_completo} liberado com sucesso!")
    return redirect('gerenciar_usuarios')

@login_required(login_url='/login/')
def cadastrar_categoria(request):
    if not is_admin(request.user):
        messages.error(request, "Apenas administradores podem cadastrar categorias.")
        return redirect('gerenciar_objetos')

    if request.method == 'POST':
        nome = request.POST.get('nome_categoria', '').strip()
        if nome:
            if Categoria.objects.filter(nome_categoria__iexact=nome).exists():
                messages.warning(request, f"A categoria '{nome}' já existe.")
            else:
                Categoria.objects.create(nome_categoria=nome)
                messages.success(request, f"Categoria '{nome}' criada com sucesso!")

    return redirect('gerenciar_objetos')


@login_required(login_url='/login/')
def cadastrar_subcategoria(request):
    if not is_admin(request.user):
        messages.error(request, "Apenas administradores podem cadastrar subcategorias.")
        return redirect('gerenciar_objetos')

    if request.method == 'POST':
        categoria_id = request.POST.get('categoria')
        nome = request.POST.get('nome_subcategoria', '').strip()
        limite_max = int(request.POST.get('limite_max_itens', 1))
        prazo_valor = int(request.POST.get('prazo_valor', 1))
        prazo_unidade = request.POST.get('prazo_unidade', 'DIAS')
        imagem = request.FILES.get('imagem')

        categoria = get_object_or_404(Categoria, id=categoria_id)
        Subcategoria.objects.create(
            categoria=categoria,
            nome_subcategoria=nome,
            limite_max_itens=limite_max,
            prazo_valor=prazo_valor,
            prazo_unidade=prazo_unidade,
            imagem=imagem
        )
        messages.success(request, f"Subcategoria '{nome}' cadastrada com sucesso!")

    return redirect('gerenciar_objetos')