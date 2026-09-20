from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import UsuarioForm
from .models import Objeto, Emprestimo, ItemEmprestimo
import uuid
from django.utils import timezone
from datetime import timedelta


def registrar(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST)
        if form.is_valid():
            # O save() agora usa a lógica do nosso UsuarioManager e criptografa a senha sozinho
            usuario = form.save(commit=False)
            usuario.set_password(form.cleaned_data["senha"])
            usuario.save()
            return redirect("login")
    else:
        form = UsuarioForm()
    return render(request, "registrar.html", {"form": form})


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
    # Busca apenas os objetos que estão disponíveis para empréstimo
    objetos_disponiveis = Objeto.objects.filter(status='DISPONIVEL')

    contexto = {
        'objetos': objetos_disponiveis
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