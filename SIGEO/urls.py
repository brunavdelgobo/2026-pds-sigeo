"""
URL configuration for SIGEO project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from . import views

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
    path('adicionar-pedido/<int:objeto_id>/', views.adicionar_ao_pedido, name='adicionar_ao_pedido'),
    path('revisar-pedido/', views.revisar_pedido, name='revisar_pedido'),
    path('remover-pedido/<int:objeto_id>/', views.remover_do_pedido, name='remover_do_pedido'),
    path('renovar/<int:emprestimo_id>/', views.renovar_emprestimo, name='renovar_emprestimo'),
    path('perfil/', views.meu_perfil, name='meu_perfil'),
]
