from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class UsuarioManager(BaseUserManager):
    def create_user(self, email, matricula, nome_completo, password=None, **extra_fields):
        if not email:
            raise ValueError('O endereço de email é obrigatório')
        email = self.normalize_email(email)
        user = self.model(email=email, matricula=matricula, nome_completo=nome_completo, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, matricula, nome_completo, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('perfil', 'ADMIN')
        return self.create_user(email, matricula, nome_completo, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    PERFIS = (
        ('ADMIN', 'Administrador'),
        ('ATENDENTE', 'Atendente'),
        ('SOLICITANTE', 'Solicitante'),
    )
    nome_completo = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    matricula = models.CharField(max_length=20, unique=True)
    telefone = models.CharField(max_length=20)
    perfil = models.CharField(max_length=15, choices=PERFIS, default='SOLICITANTE')

    # Campos de controle nativos do Django
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'  # Define o email como chave de login
    REQUIRED_FIELDS = ['matricula', 'nome_completo']

    def __str__(self):
        return self.nome_completo