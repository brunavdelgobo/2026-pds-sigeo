import threading
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone


def _enviar_em_background(assunto, mensagem, destinatario):
    if not destinatario:
        return

    def tarefa():
        try:
            send_mail(
                subject=assunto,
                message=mensagem,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[destinatario],
                fail_silently=True,
            )
        except Exception:
            pass

    threading.Thread(target=tarefa, daemon=True).start()


def notificar_solicitacao_criada(emprestimo):
    usuario = emprestimo.usuario
    itens_txt = "\n".join([f"• {item.objeto.nome_objeto}" for item in emprestimo.itens.all()])
    prazo_retirada = timezone.localtime(emprestimo.data_expiracao).strftime("%d/%m/%Y às %H:%M")

    assunto = f"[SIGEO] Solicitação #{emprestimo.id} registrada — Código {emprestimo.codigo_retirada}"
    mensagem = (
        f"Olá, {usuario.nome_completo}!\n\n"
        f"Sua solicitação de empréstimo #{emprestimo.id} foi registrada com sucesso.\n\n"
        f"Código de Retirada: {emprestimo.codigo_retirada}\n"
        f"Retirar até: {prazo_retirada}\n\n"
        f"Itens solicitados:\n{itens_txt}\n\n"
        f"Apresente o código ou QR Code no balcão de atendimento para retirar os materiais.\n\n"
        f"Atenciosamente,\nEquipe SIGEO"
    )
    _enviar_em_background(assunto, mensagem, usuario.email)


def notificar_retirada_confirmada(emprestimo):
    usuario = emprestimo.usuario
    itens_txt = "\n".join([f"• {item.objeto.nome_objeto}" for item in emprestimo.itens.all()])
    prazo_devolucao = timezone.localtime(emprestimo.data_expiracao).strftime("%d/%m/%Y às %H:%M")

    assunto = f"[SIGEO] Retirada confirmada — Pedido #{emprestimo.id}"
    mensagem = (
        f"Olá, {usuario.nome_completo}!\n\n"
        f"A retirada dos materiais do Pedido #{emprestimo.id} foi confirmada.\n\n"
        f"Prazo máximo para devolução: {prazo_devolucao}\n"
        f"Código de Devolução: {emprestimo.codigo_devolucao}\n\n"
        f"Itens retirados:\n{itens_txt}\n\n"
        f"Lembre-se de devolver dentro do prazo para evitar bloqueios automáticos no sistema.\n\n"
        f"Atenciosamente,\nEquipe SIGEO"
    )
    _enviar_em_background(assunto, mensagem, usuario.email)


def notificar_lembrete_vencimento(emprestimo):
    usuario = emprestimo.usuario
    prazo_devolucao = timezone.localtime(emprestimo.data_expiracao).strftime("%d/%m/%Y às %H:%M")

    assunto = f"[SIGEO] Lembrete: Devolução próxima — Pedido #{emprestimo.id}"
    mensagem = (
        f"Olá, {usuario.nome_completo}!\n\n"
        f"O prazo para devolução do seu Pedido #{emprestimo.id} vence em breve ({prazo_devolucao}).\n"
        f"Compareça ao balcão de atendimento para realizar a entrega.\n\n"
        f"Atenciosamente,\nEquipe SIGEO"
    )
    _enviar_em_background(assunto, mensagem, usuario.email)


def notificar_atraso(emprestimo):
    usuario = emprestimo.usuario
    prazo_devolucao = timezone.localtime(emprestimo.data_expiracao).strftime("%d/%m/%Y às %H:%M")

    assunto = f"[SIGEO] ATENÇÃO: Empréstimo em atraso — Pedido #{emprestimo.id}"
    mensagem = (
        f"Olá, {usuario.nome_completo}!\n\n"
        f"O prazo de devolução do Pedido #{emprestimo.id} expirou em {prazo_devolucao}.\n"
        f"Novas solicitações no catálogo estão bloqueadas até a devolução dos materiais no balcão.\n\n"
        f"Atenciosamente,\nEquipe SIGEO"
    )
    _enviar_em_background(assunto, mensagem, usuario.email)


def notificar_suspensao(usuario):
    if not usuario.esta_bloqueado:
        return
    ate_txt = timezone.localtime(usuario.bloqueado_ate).strftime("%d/%m/%Y às %H:%M")
    motivo = usuario.motivo_bloqueio or "Suspensão administrativa."

    assunto = "[SIGEO] Aviso de Suspensão Temporária"
    mensagem = (
        f"Olá, {usuario.nome_completo}!\n\n"
        f"Informamos que seu acesso para realizar novas solicitações no SIGEO está suspenso até {ate_txt}.\n"
        f"Motivo: {motivo}\n\n"
        f"Atenciosamente,\nEquipe SIGEO"
    )
    _enviar_em_background(assunto, mensagem, usuario.email)

def notificar_devolucao_confirmada(emprestimo, parcial=False):
    usuario = emprestimo.usuario
    devolvidos = [f"• {item.objeto.nome_objeto}" for item in emprestimo.itens.filter(status_item='DEVOLVIDO')]
    pendentes = [f"• {item.objeto.nome_objeto}" for item in emprestimo.itens.exclude(status_item='DEVOLVIDO')]

    itens_dev_txt = "\n".join(devolvidos) if devolvidos else "Nenhum"

    if parcial and pendentes:
        itens_pend_txt = "\n".join(pendentes)
        assunto = f"[SIGEO] Devolução parcial registrada — Pedido #{emprestimo.id}"
        mensagem = (
            f"Olá, {usuario.nome_completo}!\n\n"
            f"Registramos a devolução parcial referente ao Pedido #{emprestimo.id}.\n\n"
            f"Itens já devolvidos:\n{itens_dev_txt}\n\n"
            f"Itens ainda pendentes de devolução:\n{itens_pend_txt}\n\n"
            f"Atenciosamente,\nEquipe SIGEO"
        )
    else:
        assunto = f"[SIGEO] Devolução concluída — Pedido #{emprestimo.id}"
        mensagem = (
            f"Olá, {usuario.nome_completo}!\n\n"
            f"Confirmamos a devolução de todos os itens do Pedido #{emprestimo.id}.\n\n"
            f"Itens devolvidos:\n{itens_dev_txt}\n\n"
            f"Obrigado por utilizar o SIGEO!\n\n"
            f"Atenciosamente,\nEquipe SIGEO"
        )

    _enviar_em_background(assunto, mensagem, usuario.email)

def notificar_cancelamento(emprestimo):
    usuario = emprestimo.usuario
    itens_txt = "\n".join([f"• {item.objeto.nome_objeto}" for item in emprestimo.itens.all()])

    assunto = f"[SIGEO] Solicitação #{emprestimo.id} cancelada"
    mensagem = (
        f"Olá, {usuario.nome_completo}!\n\n"
        f"Confirmamos o cancelamento da sua solicitação #{emprestimo.id}.\n\n"
        f"Itens liberados:\n{itens_txt}\n\n"
        f"Atenciosamente,\nEquipe SIGEO"
    )
    _enviar_em_background(assunto, mensagem, usuario.email)