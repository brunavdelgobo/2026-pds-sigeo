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
            return redirect("registrar") # Por enquanto redireciona pra ele mesmo
    else:
        form = UsuarioForm()
    return render(request, "registrar.html", {"form": form})