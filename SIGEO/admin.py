from django.contrib import admin
from .models import Usuario, Categoria, Objeto, Emprestimo, ItemEmprestimo

# Registra os models para aparecerem no painel administrativo do Django
admin.site.register(Usuario)
admin.site.register(Categoria)
admin.site.register(Objeto)
admin.site.register(Emprestimo)
admin.site.register(ItemEmprestimo)