from django.db import models
import hashlib

class Usuario(models.Model):
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
    senha = models.CharField(max_length=200)

    def set_password(self, raw_password):
        hash_obj = hashlib.sha256(raw_password.encode('utf-8'))
        self.senha = hash_obj.hexdigest()

    def check_password(self, raw_password):
        hash_obj = hashlib.sha256(raw_password.encode('utf-8'))
        return self.senha == hash_obj.hexdigest()

    def __str__(self):
        return self.nome_completo