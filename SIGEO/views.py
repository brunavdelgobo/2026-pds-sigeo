from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import UsuarioForm


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
    # O Django injeta o usuário logado no request.user
    contexto = {
        "nome": request.user.nome_completo,
        "perfil": request.user.perfil
    }
    return render(request, "bemvindo.html", contexto)