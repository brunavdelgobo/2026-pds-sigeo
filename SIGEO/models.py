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


# Acervo
class Categoria(models.Model):
    nome_categoria = models.CharField(max_length=100, unique=True)
    limite_max_itens = models.PositiveIntegerField(default=1)
    prazo_dias = models.PositiveIntegerField(default=7)

    def __str__(self):
        return self.nome_categoria


class Objeto(models.Model):
    STATUS_OBJETO = (
        ('DISPONIVEL', 'Disponível'),
        ('EMPRESTADO', 'Emprestado'),
        ('MANUTENCAO', 'Em Manutenção'),
        ('INATIVO', 'Inativo'),
    )
    CONDICAO_FISICA = (
        ('INTEGRO', 'Íntegro/Perfeito'),
        ('AVARIADO', 'Com Avaria'),
    )

    cg_patrimonio = models.CharField(max_length=50, unique=True, null=True, blank=True)
    nome_objeto = models.CharField(max_length=150)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='objetos')
    status = models.CharField(max_length=15, choices=STATUS_OBJETO, default='DISPONIVEL')
    condicao = models.CharField(max_length=15, choices=CONDICAO_FISICA, default='INTEGRO')
    descricao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.nome_objeto} ({self.cg_patrimonio})"


# --- 3. MODELOS DE EMPRÉSTIMO ---

class Emprestimo(models.Model):
    STATUS_GERAL = (
        ('PENDENTE', 'Pendente de Retirada'),
        ('ATIVO', 'Ativo/Em Andamento'),
        ('CONCLUIDO', 'Concluído'),
        ('EXPIRADO', 'Expirado (Não retirado)'),
        ('CANCELADO', 'Cancelado'),
    )

    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='emprestimos')
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    data_expiracao = models.DateTimeField()
    cg_validacao = models.CharField(max_length=10, unique=True)
    status_geral = models.CharField(max_length=15, choices=STATUS_GERAL, default='PENDENTE')

    def __str__(self):
        return f"Empréstimo #{self.id} - {self.usuario.nome_completo}"


class ItemEmprestimo(models.Model):
    STATUS_ITEM = (
        ('AGUARDANDO_RETIRADA', 'Aguardando Retirada'),
        ('COM_USUARIO', 'Com o Usuário'),
        ('DEVOLVIDO', 'Devolvido'),
        ('ATRASADO', 'Em Atraso'),
    )

    emprestimo = models.ForeignKey(Emprestimo, on_delete=models.CASCADE, related_name='itens')
    objeto = models.ForeignKey(Objeto, on_delete=models.PROTECT, related_name='historico_emprestimos')
    data_devolucao_prevista = models.DateTimeField()
    data_devolucao_real = models.DateTimeField(null=True, blank=True)
    status_item = models.CharField(max_length=20, choices=STATUS_ITEM, default='AGUARDANDO_RETIRADA')
    condicao_retorno = models.CharField(max_length=15, null=True, blank=True)

    def __str__(self):
        return f"Item: {self.objeto.nome_objeto} (Emp: #{self.emprestimo.id})"