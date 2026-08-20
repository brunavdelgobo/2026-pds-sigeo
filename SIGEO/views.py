from django.shortcuts import render, redirect
from .models import Usuario
from .forms import UsuarioForm

def registrar(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save(commit=False)
            usuario.set_password(form.cleaned_data["senha"])
            usuario.save()
            return redirect("login") # Por enquanto redireciona pra ele mesmo
    else:
        form = UsuarioForm()
    return render(request, "registrar.html", {"form": form})


# Mude o finalzinho da função registrar para:
# return redirect("login")

def login_view(request):
    erro = None
    if request.method == "POST":
        email = request.POST.get("email")
        senha = request.POST.get("senha")
        try:
            usuario = Usuario.objects.get(email=email)
            if usuario.check_password(senha):
                # Cria a sessão
                request.session['usuario_id'] = usuario.id
                request.session['usuario_nome'] = usuario.nome_completo
                request.session['usuario_perfil'] = usuario.perfil  # Já guarda o perfil!
                return redirect("painel")
            else:
                erro = "Senha incorreta."
        except Usuario.DoesNotExist:
            erro = "Email não encontrado."
    return render(request, "login.html", {"erro": erro})


def logout_view(request):
    request.session.flush()  # Limpa a sessão
    return redirect("login")


def painel(request):
    if 'usuario_id' not in request.session:
        return redirect("login")

    contexto = {
        "nome": request.session['usuario_nome'],
        "perfil": request.session['usuario_perfil']
    }
    return render(request, "bemvindo.html", contexto)