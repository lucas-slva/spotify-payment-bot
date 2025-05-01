# -*- coding: utf-8 -*-
import logging
import os
import json
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import html

from dotenv import load_dotenv

# Imports do Telegram
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ExtBot, JobQueue

# --- Configurações Iniciais ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Leitura de Credenciais e Constantes ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
STATE_FILE = "/data/bot_state.json"
TELEGRAM_GROUP_ID_STR = os.environ.get('TELEGRAM_GROUP_ID')
ADMIN_USER_ID_STR = os.environ.get('ADMIN_USER_ID')
SCHEDULER_TIMEZONE = os.environ.get('SCHEDULER_TIMEZONE', 'America/Fortaleza')

# --- ORDEM DE PAGAMENTO ---
PAYMENT_ORDER = ["Lucas", "Thiago", "Victor", "Alice", "Aline", "Matheus"]
MESES_PT_BR = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}

# --- Verificação Crítica das Credenciais ---
if not TOKEN: logger.critical("ERRO FATAL: TELEGRAM_BOT_TOKEN não configurado."); exit()

# --- Processamento e Validação de IDs (Sintaxe Verificada) ---
telegram_group_id_int = None
if TELEGRAM_GROUP_ID_STR:
    try: # Bloco if/try/except CORRIGIDO E VERIFICADO
        telegram_group_id_int = int(TELEGRAM_GROUP_ID_STR)
    except ValueError:
        logger.error(f"ERRO: TELEGRAM_GROUP_ID ('{TELEGRAM_GROUP_ID_STR}') inválido!")
else:
    logger.warning("AVISO: TELEGRAM_GROUP_ID não definido no .env.")

admin_user_id_int = None
if ADMIN_USER_ID_STR:
    try: # Bloco if/try/except CORRIGIDO E VERIFICADO
        admin_user_id_int = int(ADMIN_USER_ID_STR)
    except ValueError:
        logger.error(f"AVISO: ADMIN_USER_ID ('{ADMIN_USER_ID_STR}') inválido!")
else:
    logger.warning("AVISO: ADMIN_USER_ID não definido.")

# Carregar Timezone
try:
    tz = ZoneInfo(SCHEDULER_TIMEZONE)
except Exception as tz_error:
    logger.error(f"Erro timezone '{SCHEDULER_TIMEZONE}': {tz_error}. Usando UTC.")
    tz = ZoneInfo("UTC")

# --- Funções de Persistência ---
def load_bot_state():
    default_state = {"last_payer_index": -1, "current_payer_index": 0, "current_payer_name": PAYMENT_ORDER[0], "current_cycle_paid": False}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
        state = default_state.copy(); state.update(data)
        state['last_payer_index'] = int(state.get('last_payer_index', -1))
        state['current_payer_index'] = (state['last_payer_index'] + 1) % len(PAYMENT_ORDER)
        state['current_payer_name'] = PAYMENT_ORDER[state['current_payer_index']]
        state['current_cycle_paid'] = bool(state.get('current_cycle_paid', False))
        if not (-1 <= state['last_payer_index'] < len(PAYMENT_ORDER)): state['last_payer_index'] = -1
        if not (0 <= state['current_payer_index'] < len(PAYMENT_ORDER)): state['current_payer_index'] = (state['last_payer_index'] + 1) % len(PAYMENT_ORDER)
        state['current_payer_name'] = PAYMENT_ORDER[state['current_payer_index']]
        logger.info(f"Estado carregado: {state}")
        return state
    except FileNotFoundError: logger.warning(f"'{STATE_FILE}' não encontrado."); return default_state
    except Exception as e: logger.error(f"Erro carregar estado '{STATE_FILE}': {e}"); return default_state

def save_bot_state(state):
    if not isinstance(state.get('last_payer_index'), int) or not isinstance(state.get('current_payer_index'), int) or not isinstance(state.get('current_payer_name'), str) or not isinstance(state.get('current_cycle_paid'), bool):
        logger.error(f"Tentativa salvar estado inválido: {state}"); return
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f: json.dump(state, f, indent=4)
        logger.debug(f"Estado salvo: {state}")
    except Exception as e: logger.error(f"Erro salvar estado '{STATE_FILE}': {e}")

# --- Carrega o estado ao iniciar ---
bot_state = load_bot_state()

# --- Funções Auxiliares ---
def escape_html(text: str) -> str: return html.escape(str(text), quote=False)

# --- Funções Handler de Comandos Telegram ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user;
    if not user or not admin_user_id_int or user.id != admin_user_id_int: logger.warning(f"User {user.id if user else '??'} tentou /start."); return
    await update.message.reply_html(rf"Olá Admin {user.mention_html()}! Bot pronto. Use /help ou /comandos.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user;
    if not user or not admin_user_id_int or user.id != admin_user_id_int: logger.warning(f"User {user.id if user else '??'} tentou /help."); return
    admin_help_text = (
        "--- Comandos de Admin ---\n"
        "/start - Verifica o bot\n"
        "/help - Mostra esta ajuda\n"
        "/pago - (Use no Privado) Marca pagto recebido\n"
        "/reenviar - (Use no Privado) Reenvia lembrete atual\n\n" # RENOMEADO AQUI
        "--- Comandos Públicos (/comandos) ---\n"
        "/lista - Ordem de pagamento\n"
        "/status - Pagador atual e status\n"
        "/nome - Ex: /lucas - Próximo pagamento"
    )
    try: await update.message.reply_text(f"Ajuda (Admin):\n{admin_help_text}")
    except Exception as e: logger.error(f"Erro enviar /help admin {user.id}: {e}")

async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: # RENOMEADO
    message = "📅 Ordem de Pagamento:\n"
    for i, name in enumerate(PAYMENT_ORDER): message += f"\n{i+1}. {escape_html(name)}"
    try: await update.message.reply_html(message)
    except Exception as e: logger.error(f"Erro enviar /lista: {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global bot_state
    current_name = bot_state.get('current_payer_name', 'Indefinido')
    current_index = bot_state.get('current_payer_index', -1)
    is_paid = bot_state.get('current_cycle_paid', False)
    status_text = "✅ Pago" if is_paid else "⏳ Pendente"
    month_now = datetime.now(tz).month; year_now = datetime.now(tz).year
    month_name_pt = MESES_PT_BR.get(month_now, f"Mês {month_now}")
    message = (f"📊 Status Pagamento Atual ({escape_html(month_name_pt)}/{year_now}):\n\n"
               f"👤 Vez de: <b>{escape_html(current_name)}</b> (Posição {current_index + 1})\n\n"
               f"💰 Status: {status_text}")
    try: await update.message.reply_html(message)
    except Exception as e: logger.error(f"Erro enviar /status: {e}")

async def handle_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global bot_state
    if not update.message or not update.message.text or not update.message.text.startswith('/'): return
    command_name = update.message.text[1:].split('@')[0]; search_name_lower = command_name.lower()
    target_index = -1; target_name_exact = None
    for i, name in enumerate(PAYMENT_ORDER):
        if search_name_lower == name.lower(): target_index = i; target_name_exact = name; break
    if target_index == -1: logger.debug(f"Comando /{command_name} não é nome."); return
    try:
        current_index = bot_state.get('current_payer_index', 0)
        if target_index >= current_index: steps = target_index - current_index
        else: steps = len(PAYMENT_ORDER) - current_index + target_index
        today = date.today(); target_month_offset = steps
        target_year = today.year + (today.month + target_month_offset - 1) // 12
        target_month = (today.month + target_month_offset - 1) % 12 + 1
        month_name_pt = MESES_PT_BR.get(target_month, f"Mês {target_month}")
        if steps == 1: prazo_str = "(daqui a 1 mês)"
        else: prazo_str = f"(daqui a {steps} meses)"
        if steps == 0: prazo_str = "(este mês!)"
        message = (f"🗓️ O próximo pagamento de <b>{escape_html(target_name_exact)}</b> será dia 1º de <b>{escape_html(month_name_pt)} de {target_year}</b>\n"
                   f"{prazo_str}")
        await update.message.reply_html(message)
    except Exception as e: logger.error(f"Erro no comando /{command_name}: {e}"); await update.message.reply_text("Erro ao calcular.")

async def pago_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global bot_state
    user = update.effective_user; chat = update.effective_chat
    if not chat or chat.type != 'private': logger.debug("Comando /pago ignorado (não privado)."); return
    if not user or not admin_user_id_int or user.id != admin_user_id_int: logger.warning(f"User {user.id if user else '??'} tentou /pago."); await update.message.reply_text("⛔ Apenas o admin."); return
    current_name = bot_state.get('current_payer_name', 'N/A')
    if bot_state.get('current_cycle_paid', False): await update.message.reply_text(f"✅ Pagamento de <b>{escape_html(current_name)}</b> já registrado.", parse_mode=constants.ParseMode.HTML); return
    bot_state['current_cycle_paid'] = True
    save_bot_state(bot_state)
    logger.info(f"Admin {user.id} marcou pagamento de {current_name} como recebido.")
    await update.message.reply_text(f"✅ Pagamento de <b>{escape_html(current_name)}</b> registrado!", parse_mode=constants.ParseMode.HTML)
    if telegram_group_id_int:
        try:
            group_message = f"🎉 Pagamento de <b>{escape_html(current_name)}</b> confirmado pelo admin!\n\nObrigado!"
            await context.bot.send_message(chat_id=telegram_group_id_int, text=group_message, parse_mode=constants.ParseMode.HTML)
            logger.info(f"Anúncio /pago enviado grupo {telegram_group_id_int}")
        except Exception as group_send_err:
            logger.error(f"Falha anunciar /pago grupo {telegram_group_id_int}: {group_send_err}")
            await update.message.reply_text(f"<i>(AVISO: não anunciei no grupo.)</i>", parse_mode=constants.ParseMode.HTML)
    else: logger.warning("Comando /pago: Anúncio não enviado (ID grupo ausente)."); await update.message.reply_text("<i>(AVISO: Anúncio não enviado - ID grupo não config.)</i>", parse_mode=constants.ParseMode.HTML)

async def comandos_publicos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra os comandos disponíveis para todos os usuários."""
    public_help = ("Comandos disponíveis:\n\n"
                   "/lista - Mostra a ordem de pagamento\n\n"
                   "/status - Mostra pagador atual e status\n\n"
                   "/nome - Ex: /lucas - Mostra quando será o próximo pagamento dessa pessoa") # Clarificado
    try: await update.message.reply_text(public_help)
    except Exception as e: logger.error(f"Erro enviar /comandos: {e}")

# Comando /reenviar (Admin, Privado) - RENOMEADO
async def reenviar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: # RENOMEADO
    """Reenvia manualmente o lembrete do mês atual para o grupo (Admin, Privado)."""
    global bot_state
    user = update.effective_user; chat = update.effective_chat
    if not chat or chat.type != 'private': logger.debug("Comando /reenviar ignorado (não privado)."); return
    if not user or not admin_user_id_int or user.id != admin_user_id_int: logger.warning(f"User {user.id if user else '??'} tentou /reenviar."); await update.message.reply_text("⛔ Apenas o admin."); return

    payer_this_month_name = bot_state.get('current_payer_name', None)
    if not payer_this_month_name: logger.error("Comando /reenviar: Estado 'current_payer_name' não encontrado."); await update.message.reply_text("❌ Erro: Pagador atual não definido."); return

    # Monta a mensagem (mesma lógica do job agendado)
    run_time = datetime.now(tz)
    month_number = run_time.month; month_name_pt = MESES_PT_BR.get(month_number, f"Mês {month_number}")
    year = run_time.year; payer_escaped = escape_html(payer_this_month_name); admin_username_escaped = escape_html("@lucas_gdn")
    message = (f"🚨 <b>Lembrete Pagamento Spotify - {escape_html(month_name_pt)}/{year}</b> 🚨\n\n\n"
               f"👤 Este mês, a vez de pagar é sua: <b>{payer_escaped}</b>\n\n\n"
               f"(Faça um pix de R$ 34,90 para a chave: lucas.stos@gmail.com (Picpay) e peça para o {admin_username_escaped} confirmar no privado!)")

    # Envia para o grupo
    if telegram_group_id_int:
        try:
            await context.bot.send_message(chat_id=telegram_group_id_int, text=message, parse_mode=constants.ParseMode.HTML)
            logger.info(f"Admin {user.id} reenviou lembrete para grupo {telegram_group_id_int}")
            await update.message.reply_text(f"✅ Lembrete para <b>{escape_html(payer_this_month_name)}</b> reenviado para o grupo!", parse_mode=constants.ParseMode.HTML)
        except Exception as send_error:
            logger.error(f"Falha ao reenviar lembrete para grupo {telegram_group_id_int}: {send_error}")
            await update.message.reply_text(f"❌ Falha ao reenviar lembrete. Erro: {send_error}")
    else: logger.warning("Comando /reenviar: Mensagem não enviada (Grupo ID ausente)."); await update.message.reply_text("❌ Não posso reenviar: ID do grupo não configurado.")


# --- Função Agendada ---
async def check_spotify_payment(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Função agendada para enviar lembrete e avançar a rotação."""
    global bot_state
    bot: ExtBot = context.bot; job = context.job; run_time = datetime.now(tz)
    logger.info(f"Executando job '{job.name if job else 'N/A'}' em {run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    check_user_id = admin_user_id_int if admin_user_id_int else (list(bot_state.keys())[0] if bot_state else None)
    if not check_user_id: logger.warning("Job: Nenhum usuário admin encontrado para estado."); return

    # Calcula pagador e define estado atual
    last_payer_index = bot_state.get('last_payer_index', -1)
    current_payer_index = (last_payer_index + 1) % len(PAYMENT_ORDER)
    payer_this_month_name = PAYMENT_ORDER[current_payer_index]
    logger.info(f"Job: Definindo ciclo atual para: {payer_this_month_name} (índice {current_payer_index})")
    bot_state['current_payer_index'] = current_payer_index
    bot_state['current_payer_name'] = payer_this_month_name
    bot_state['current_cycle_paid'] = False # Reseta status

    # Prepara mensagem
    month_number = run_time.month; month_name_pt = MESES_PT_BR.get(month_number, f"Mês {month_number}")
    year = run_time.year; payer_escaped = escape_html(payer_this_month_name); admin_username_escaped = escape_html("@lucas_gdn")
    message = (f"🚨 <b>Lembrete Pagamento Spotify - {escape_html(month_name_pt)}/{year}</b> 🚨\n\n\n"
               f"👤 Este mês, a vez de pagar é sua: <b>{payer_escaped}</b>\n\n\n"
               f"(Faça um pix de R$ 34,90 para a chave: lucas.stos@gmail.com (Picpay) e peça para o {admin_username_escaped} confirmar no privado!)")

    # Envia mensagem e atualiza índice para próximo ciclo
    message_sent_successfully = False
    if telegram_group_id_int:
        try:
            await bot.send_message(chat_id=telegram_group_id_int, text=message, parse_mode=constants.ParseMode.HTML)
            logger.info(f"Mensagem enviada grupo {telegram_group_id_int} (HTML)")
            message_sent_successfully = True
        except Exception as send_error:
            logger.error(f"Falha envio grupo {telegram_group_id_int}: {send_error}")
            # --- Bloco de Notificação Admin CORRIGIDO E VERIFICADO ---
            if admin_user_id_int:
                try: # try indentado
                    await bot.send_message(chat_id=admin_user_id_int, text=f"⚠️ Falha ao enviar lembrete HTML grupo {telegram_group_id_int}. Erro: {send_error}")
                except Exception as notify_error: # except indentado
                    logger.error(f"Falha ao notificar admin {admin_user_id_int}: {notify_error}")
            # --- Fim da Correção ---
    else: logger.warning("Job: TELEGRAM_GROUP_ID inválido.")

    # Atualiza o índice do último pagador e salva o estado completo
    bot_state['last_payer_index'] = current_payer_index
    save_bot_state(bot_state)


# --- Função Principal ---
def main() -> None:
    """Inicia o bot, handlers e agendador via JobQueue."""
    logger.info(f"Iniciando o bot (vFinal v4)... Estado inicial: {bot_state}")
    try:
        application = Application.builder().token(TOKEN).build()
        job_queue: JobQueue = application.job_queue
    except Exception as app_error: logger.critical(f"ERRO FATAL APP TELEGRAM: {app_error}"); exit()

    # --- Registra Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("pago", pago_command))
    application.add_handler(CommandHandler("lista", lista_command)) # Renomeado
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("comandos", comandos_publicos))
    application.add_handler(CommandHandler("reenviar", reenviar_command)) # RENOMEADO

    # Handler para /<Nome>
    application.add_handler(MessageHandler(filters.COMMAND, handle_name_command))

    # --- Agendamento via JobQueue ---
    try:
        # --- TRIGGER DE TESTE (Comente para produção) ---
        # job_queue.run_repeating(callback=check_spotify_payment, interval=30, first=10, name='Lembrete Teste Spotify')
        # logger.info("Usando JobQueue.run_repeating (a cada 30 segundos)")

        # --- Trigger MENSAL REAL (Descomente para produção) ---
        run_time_prod = time(hour=9, minute=0, second=0, tzinfo=tz) # 9:00 no timezone definido
        job_queue.run_monthly(callback=check_spotify_payment, when=run_time_prod, day=1, name='Lembrete Mensal Spotify')
        logger.info(f"Usando JobQueue.run_monthly (Dia 1, 09:00 {SCHEDULER_TIMEZONE})")

    except Exception: logger.exception("Falha ao agendar o job:")

    logger.info("Bot pronto.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()