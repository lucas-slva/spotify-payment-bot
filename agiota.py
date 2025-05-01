import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from splitwise import Splitwise
# from splitwise.group import Group # Descomente se precisar dos tipos
# from splitwise.user import User
# from splitwise.expense import Expense

# Carrega variáveis do arquivo .env para o ambiente (se existir)
# É seguro chamar mesmo antes do arquivo .env ser criado
load_dotenv()

# Configuração básica de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Ler Credenciais do Ambiente ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SPLITWISE_CONSUMER_KEY = os.environ.get('SPLITWISE_CONSUMER_KEY')
SPLITWISE_CONSUMER_SECRET = os.environ.get('SPLITWISE_CONSUMER_SECRET')

# --- Verificação Crítica das Credenciais ---
# Sai imediatamente se alguma variável essencial não estiver definida
if not TOKEN:
    logger.critical("ERRO FATAL: TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente!")
    exit("ERRO FATAL: TELEGRAM_BOT_TOKEN não configurado.")
if not SPLITWISE_CONSUMER_KEY:
    logger.critical("ERRO FATAL: SPLITWISE_CONSUMER_KEY não encontrado nas variáveis de ambiente!")
    exit("ERRO FATAL: SPLITWISE_CONSUMER_KEY não configurado.")
if not SPLITWISE_CONSUMER_SECRET:
    logger.critical("ERRO FATAL: SPLITWISE_CONSUMER_SECRET não encontrado nas variáveis de ambiente!")
    exit("ERRO FATAL: SPLITWISE_CONSUMER_SECRET não configurado.")

# --- Constantes ---
# Usaremos uma URL genérica aqui, mas lembre-se que o fluxo de callback precisa ser tratado
SPLITWISE_CALLBACK_URL = os.environ.get('SPLITWISE_CALLBACK_URL', 'http://localhost:8080/callback')

# --- Armazenamento Temporário (Substituir por DB em produção) ---
# ATENÇÃO: Isso ainda é em memória e será perdido ao reiniciar o bot.
user_data = {}

# --- Funções Handler de Comandos ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia mensagem de boas-vindas."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Olá {user.mention_html()}! Pronto para gerenciar os pagamentos."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra a lista de comandos."""
    help_text = (
        "Comandos disponíveis:\n"
        "/start - Inicia o bot\n"
        "/help - Mostra esta ajuda\n"
        "/connect_splitwise - Conecta sua conta Splitwise\n"
        "/authorize_code <code> - Finaliza a conexão (use o código da URL)\n"
        "/meus_grupos - Lista seus grupos no Splitwise (requer conexão)"
        # Adicionar mais comandos aqui depois
    )
    await update.message.reply_text(help_text)

async def connect_splitwise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia o processo de autorização OAuth 2.0 com Splitwise."""
    user_id = update.effective_user.id
    # Usa as chaves lidas do ambiente
    s_obj = Splitwise(SPLITWISE_CONSUMER_KEY, SPLITWISE_CONSUMER_SECRET)
    try:
        auth_url, state = s_obj.getOAuth2AuthorizeURL(SPLITWISE_CALLBACK_URL)
        # Armazena o state para validação futura (associado ao user_id)
        user_data[user_id] = {'oauth_state': state}
        logger.info(f"Gerada URL de autorização para user {user_id}. State: {state[:5]}...") # Log reduzido
        message = (
            "Para conectar ao Splitwise:\n\n"
            f"1. Clique no link e autorize o app:\n{auth_url}\n\n"
            "2. Após autorizar, copie o parâmetro 'code' da URL.\n"
            "3. Envie para mim: `/authorize_code SEU_CODIGO_AQUI`"
        )
        await update.message.reply_text(message, disable_web_page_preview=True)
    except Exception as e:
        logger.exception(f"Erro ao gerar URL de autorização Splitwise para user {user_id}:")
        await update.message.reply_text("Erro ao iniciar conexão com Splitwise. Tente novamente.")

async def authorize_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recebe o código OAuth e tenta obter o access token."""
    user_id = update.effective_user.id
    code = ' '.join(context.args)
    if not code:
        await update.message.reply_text("Uso: /authorize_code <código_da_url>")
        return

    # Verificar o state seria ideal aqui para segurança, comparando com user_data[user_id]['oauth_state']

    s_obj = Splitwise(SPLITWISE_CONSUMER_KEY, SPLITWISE_CONSUMER_SECRET)
    try:
        # Troca o código pelo token de acesso
        access_token_data = s_obj.getOAuth2AccessToken(code, SPLITWISE_CALLBACK_URL)
        access_token = access_token_data['access_token']
        logger.info(f"Access Token obtido com sucesso para user {user_id}")

        # Guarda o token de forma segura (aqui, no dicionário de teste)
        if user_id not in user_data: user_data[user_id] = {}
        user_data[user_id]['splitwise_token'] = access_token
        if 'oauth_state' in user_data[user_id]:
             del user_data[user_id]['oauth_state'] # Limpa o state

        await update.message.reply_text("✅ Conectado ao Splitwise com sucesso! Use /meus_grupos.")

    except Exception as e:
        logger.exception(f"Erro ao obter Access Token do Splitwise para user {user_id}:")
        await update.message.reply_text(f"❌ Erro ao autorizar com o código. Verifique-o ou use /connect_splitwise novamente.")


async def get_my_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Busca e lista os grupos do usuário no Splitwise."""
    user_id = update.effective_user.id
    access_token = user_data.get(user_id, {}).get('splitwise_token')

    if not access_token:
        await update.message.reply_text("⚠️ Você precisa conectar sua conta Splitwise primeiro usando /connect_splitwise.")
        return

    s_obj = Splitwise(SPLITWISE_CONSUMER_KEY, SPLITWISE_CONSUMER_SECRET)
    # Configura o objeto Splitwise com o token de acesso do usuário
    s_obj.setOAuth2AccessToken({'access_token': access_token})

    try:
        logger.info(f"Buscando grupos do Splitwise para user {user_id}")
        groups = s_obj.getGroups()

        if groups:
            message = "Seus grupos no Splitwise:\n"
            for group in groups:
                message += f"  - {group.getName()} (ID: {group.getId()})\n"
        else:
            message = "Você não parece estar em nenhum grupo no Splitwise."

        await update.message.reply_text(message)

    except Exception as e:
        logger.exception(f"Erro ao buscar grupos do Splitwise para user {user_id}:")
        # Idealmente, verificar tipo de erro (ex: token expirado?)
        await update.message.reply_text("❌ Erro ao buscar seus grupos no Splitwise. Tente mais tarde ou reconecte.")


# --- Função Principal ---
def main() -> None:
    """Inicia o bot e configura os handlers."""
    logger.info("Iniciando o bot...")

    # Cria a Application e passa o token lido do ambiente
    application = Application.builder().token(TOKEN).build()

    # Registra os handlers de comando
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("connect_splitwise", connect_splitwise))
    application.add_handler(CommandHandler("authorize_code", authorize_code))
    application.add_handler(CommandHandler("meus_grupos", get_my_groups))

    # Adicionar handlers para mensagens desconhecidas ou outros tipos, se necessário

    logger.info("Bot pronto e aguardando comandos.")
    # Inicia o bot (modo polling)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()