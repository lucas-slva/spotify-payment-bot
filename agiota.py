import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from splitwise import Splitwise

# Configuração básica de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = '***REMOVED_TOKEN***' # Substitua pelo seu token

# Função para o comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Olá! Sou seu bot gerenciador do Spotify/Splitwise. Use /help para ver os comandos.')

# Função para ecoar mensagens (apenas para teste inicial)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Você disse: {update.message.text}")

# Função para o comando /help (exemplo)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Comandos disponíveis:\n/start - Inicia o bot\n/help - Mostra esta ajuda')

def main() -> None:
    """Inicia o bot."""
    # Cria a aplicação e passa o token
    application = Application.builder().token(TOKEN).build()

    # Registra os handlers (comandos, mensagens)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    # Vamos comentar o echo por enquanto para não poluir
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logger.info("Bot iniciado e aguardando...")
    # Roda o bot até que Ctrl-C seja pressionado
    application.run_polling()

if __name__ == '__main__':
    main()