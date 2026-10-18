from django import forms
from django.contrib import admin
from .models import Usuario, Categoria, Subcategoria, Objeto, Emprestimo, ItemEmprestimo


# 1. CRIAMOS UM FORMULÁRIO CUSTOMIZADO PARA INJETAR O CAMPO DE QUANTIDADE
class ObjetoForm(forms.ModelForm):
    quantidade_cadastro = forms.IntegerField(
        initial=1,
        min_value=1,
        label='Quantidade a cadastrar',
        help_text='Quantos itens idênticos deseja cadastrar de uma vez? (Deixe 1 para itens com patrimônio único)'
    )

    class Meta:
        model = Objeto
        fields = '__all__'


# 2. CONFIGURAMOS O ADMIN PARA USAR ESSE FORMULÁRIO E INTERCEPTAR O SALVAMENTO
class ObjetoAdmin(admin.ModelAdmin):
    form = ObjetoForm
    list_display = ('nome_objeto', 'subcategoria', 'status', 'cg_patrimonio')
    list_filter = ('subcategoria', 'status')

    # Esta função intercepta o exato momento em que o administrador clica em "Salvar"
    def save_model(self, request, obj, form, change):
        # Descobre qual quantidade o usuário digitou
        quantidade = form.cleaned_data.get('quantidade_cadastro', 1)

        # Primeiro, salva o objeto original (o item número 1)
        super().save_model(request, obj, form, change)

        # Se for um cadastro NOVO (not change) e a quantidade for maior que 1, criamos os clones
        if not change and quantidade > 1:
            for _ in range(quantidade - 1):
                Objeto.objects.create(
                    nome_objeto=obj.nome_objeto,
                    subcategoria=obj.subcategoria,
                    status=obj.status,
                    condicao=obj.condicao,
                    descricao=obj.descricao,
                    # Forçamos o patrimônio a ser nulo nas cópias para não duplicar números de série sem querer
                    cg_patrimonio=None
                )


# Registra os models
admin.site.register(Usuario)
admin.site.register(Categoria)
admin.site.register(Subcategoria)
admin.site.register(Objeto, ObjetoAdmin)  # <-- Objeto usando nossa lógica nova
admin.site.register(Emprestimo)
admin.site.register(ItemEmprestimo)