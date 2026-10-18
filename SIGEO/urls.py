"""
URL configuration for SIGEO project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.login_view, name="login"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("registrar/", views.registrar, name="registrar"),
    path("painel/", views.painel, name="painel"),
    path('catalogo/', views.catalogo_objetos, name='catalogo'),
    path('validar/', views.validar_codigo, name='validar_codigo'),
    path('solicitar/<int:objeto_id>/', views.solicitar_emprestimo, name='solicitar_emprestimo'),
    path('gerenciar/', views.gerenciar_emprestimos, name='gerenciar_emprestimos'),
    path('cancelar/<int:emprestimo_id>/', views.cancelar_emprestimo, name='cancelar_emprestimo'),
    path('avaliar-devolucao/<int:emprestimo_id>/', views.avaliar_devolucao, name='avaliar_devolucao'),
    path('manutencao/', views.gerenciar_manutencao, name='gerenciar_manutencao'),
    path('manutencao/concluir/<int:objeto_id>/', views.concluir_manutencao, name='concluir_manutencao'),
    path('adicionar-pedido/<int:subcategoria_id>/', views.adicionar_ao_pedido, name='adicionar_ao_pedido'),
    path('remover-pedido/<int:subcategoria_id>/', views.remover_do_pedido, name='remover_do_pedido'),
    path('revisar-pedido/', views.revisar_pedido, name='revisar_pedido'),
    path('renovar/<int:emprestimo_id>/', views.renovar_emprestimo, name='renovar_emprestimo'),
    path('perfil/', views.meu_perfil, name='meu_perfil'),
    path('relatorio/inventario/', views.relatorio_inventario_pdf, name='relatorio_inventario_pdf'),
    path('relatorio/inventario/csv/', views.relatorio_inventario_csv, name='relatorio_inventario_csv'),
    path('aumentar-pedido/<int:subcategoria_id>/', views.aumentar_qtd_pedido, name='aumentar_qtd_pedido'),
    path('diminuir-pedido/<int:subcategoria_id>/', views.diminuir_qtd_pedido, name='diminuir_qtd_pedido'),
    path('recuperar-senha/', auth_views.PasswordResetView.as_view(template_name='senha_reset.html'), name='password_reset'),
    path('recuperar-senha/enviado/', auth_views.PasswordResetDoneView.as_view(template_name='senha_reset_done.html'), name='password_reset_done'),
    path('recuperar-senha/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='senha_reset_confirm.html'), name='password_reset_confirm'),
    path('recuperar-senha/concluido/', auth_views.PasswordResetCompleteView.as_view(template_name='senha_reset_complete.html'), name='password_reset_complete'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)