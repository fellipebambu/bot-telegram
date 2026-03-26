import pandas as pd
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    JobQueue
)
from datetime import time
import logging

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BudgetBot:
    def __init__(self, token, excel_file="precos.xlsx"):
        self.token = token
        self.excel_file = excel_file
        self.tabela = self._carregar_tabela()
        self.modelos_disponiveis = self.tabela["Modelo"].unique().tolist()
        self.servicos_disponiveis = self.tabela["Servico"].unique().tolist()
        self.message_history = {} # Dicionário para armazenar IDs de mensagens por chat_id
        logger.info(f"Bot inicializado. Modelos: {self.modelos_disponiveis}, Serviços: {self.servicos_disponiveis}")

    def _carregar_tabela(self):
        try:
            tabela = pd.read_excel(self.excel_file)
            # Padroniza as colunas de modelo e serviço para facilitar a busca
            tabela["Modelo"] = tabela["Modelo"].str.lower().str.strip()
            tabela["Servico"] = tabela["Servico"].str.lower().str.strip()
            return tabela
        except FileNotFoundError:
            logger.error(f"ERRO: O arquivo \'{self.excel_file}\' não foi encontrado.")
            exit(1) # Encerra o bot se a tabela não for encontrada
        except Exception as e:
            logger.error(f"ERRO ao carregar a tabela: {e}")
            exit(1)

    def buscar_preco(self, modelo, servico):
        # A tabela já está padronizada, então não precisamos fazer .lower().strip() aqui novamente
        resultado = self.tabela[
            (self.tabela["Modelo"] == modelo) &
            (self.tabela["Servico"] == servico)
        ]
        if not resultado.empty:
            preco_vista = resultado.iloc[0]["PrecoVista"]
            preco_cartao = resultado.iloc[0]["PrecoCartao"]
            return (
                f"✅ {servico.title()} do {modelo.title()}:\n"
                f"💵 À vista: R$ {preco_vista:.2f}\n"
                f"💳 Cartão: R$ {preco_cartao:.2f}"
            )
        else:
            return f"❌ Não encontrei um orçamento para {modelo.title()} e {servico.title()}."

    def interpretar_texto(self, texto):
        texto = texto.lower()
        modelo_encontrado = None
        servico_encontrado = None

        # Busca por modelos
        for modelo in self.modelos_disponiveis:
            if modelo in texto:
                modelo_encontrado = modelo
                break
        
        # Busca por serviços (apenas se um modelo foi encontrado ou se for uma busca geral)
        if modelo_encontrado:
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo_encontrado]["Servico"].unique().tolist()
            for servico in servicos_para_modelo:
                if servico in texto:
                    servico_encontrado = servico
                    break
        else:
            for servico in self.servicos_disponiveis:
                if servico in texto:
                    servico_encontrado = servico
                    break

        return modelo_encontrado, servico_encontrado

    async def _track_message(self, chat_id, message_id):
        if chat_id not in self.message_history:
            self.message_history[chat_id] = []
        self.message_history[chat_id].append(message_id)
        logger.debug(f"Mensagem {message_id} rastreada para o chat {chat_id}")

    async def preco_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        await self._track_message(chat_id, update.message.message_id) # Rastreia a mensagem do usuário

        texto_args = " ".join(context.args)
        if not texto_args:
            sent_message = await update.message.reply_text(
                "Por favor, informe o modelo e o serviço. Ex: /preco tela iphone 11"
            )
            await self._track_message(chat_id, sent_message.message_id)
            return

        modelo, servico = self.interpretar_texto(texto_args)

        if modelo and servico:
            resposta = self.buscar_preco(modelo, servico)
            sent_message = await update.message.reply_text(resposta)
            await self._track_message(chat_id, sent_message.message_id)
        elif modelo and not servico:
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_para_modelo:
                keyboard = [
                    [InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}")]
                    for s in servicos_para_modelo
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                sent_message = await update.message.reply_text(
                    f"Qual serviço você precisa para o {modelo.title()}?",
                    reply_markup=reply_markup
                )
                await self._track_message(chat_id, sent_message.message_id)
            else:
                sent_message = await update.message.reply_text(f"Não encontrei serviços disponíveis para o {modelo.title()}.")
                await self._track_message(chat_id, sent_message.message_id)
        else:
            modelos_str = ", ".join([m.title() for m in self.modelos_disponiveis])
            servicos_str = ", ".join([s.title() for s in self.servicos_disponiveis])
            sent_message = await update.message.reply_text(
                "Não consegui entender o modelo ou o serviço. Por favor, tente novamente. "
                f"Ex: /preco tela iphone 11. Modelos disponíveis: {modelos_str}. "
                f"Serviços disponíveis: {servicos_str}."
            )
            await self._track_message(chat_id, sent_message.message_id)

    async def responder_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        await self._track_message(chat_id, update.message.message_id) # Rastreia a mensagem do usuário

        texto = update.message.text
        modelo, servico = self.interpretar_texto(texto)

        if modelo and servico:
            resposta = self.buscar_preco(modelo, servico)
            sent_message = await update.message.reply_text(resposta)
            await self._track_message(chat_id, sent_message.message_id)
        elif modelo and not servico:
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_para_modelo:
                keyboard = [
                    [InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}")]
                    for s in servicos_para_modelo
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                sent_message = await update.message.reply_text(
                    f"Qual serviço você precisa para o {modelo.title()}?",
                    reply_markup=reply_markup
                )
                await self._track_message(chat_id, sent_message.message_id)
            else:
                sent_message = await update.message.reply_text(f"Não encontrei serviços disponíveis para o {modelo.title()}.")
                await self._track_message(chat_id, sent_message.message_id)
        else:
            return # Ignora a mensagem se não conseguir interpretar modelo e serviço

    async def button_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        chat_id = query.message.chat_id
        await query.answer() # Responde ao callback para remover o estado de 'carregando' do botão

        data = query.data.split("|")
        modelo = data[0]
        servico = data[1]

        resposta = self.buscar_preco(modelo, servico)
        sent_message = await query.edit_message_text(text=resposta)
        await self._track_message(chat_id, sent_message.message_id)

    async def _clear_history_job(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Iniciando tarefa de limpeza de histórico...")
        bot = context.bot
        for chat_id, message_ids in self.message_history.items():
            logger.info(f"Tentando apagar {len(message_ids)} mensagens no chat {chat_id}...")
            for message_id in message_ids:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=message_id)
                    logger.debug(f"Mensagem {message_id} apagada com sucesso no chat {chat_id}.")
                except Exception as e:
                    logger.warning(f"Erro ao apagar mensagem {message_id} no chat {chat_id}: {e}")
        self.message_history.clear() # Limpa o histórico após tentar apagar todas as mensagens
        logger.info("Histórico de mensagens limpo para todos os chats.")

    def run(self):
        application = ApplicationBuilder().token(self.token).build()
        
        # Verifica se o JobQueue está disponível antes de tentar usá-lo
        if application.job_queue:
            job_queue = application.job_queue
            # Agendar a tarefa de limpeza para rodar todos os dias às 21:52 (para teste)
            job_queue.run_daily(self._clear_history_job, time(hour=21, minute=52), days=(0, 1, 2, 3, 4, 5, 6), data=None, name='daily_clear_history')
            logger.info("Tarefa de limpeza diária agendada para as 21:40.")
        else:
            logger.warning("AVISO: JobQueue não está configurado. A limpeza automática de histórico não será ativada.")
            logger.warning("Para ativar, instale python-telegram-bot com o extra 'job-queue':")
            logger.warning("pip install \"python-telegram-bot[job-queue]\"")

        application.add_handler(CommandHandler("preco", self.preco_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.responder_message))
        application.add_handler(CallbackQueryHandler(self.button_callback_handler))

        logger.info("Bot rodando... 🚀")
        application.run_polling()

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("ERRO: A variável de ambiente 'TOKEN' não está definida.")
        exit(1)
    
    # Cria um arquivo de exemplo 'precos.xlsx' se não existir
    if not os.path.exists("precos.xlsx"):
        logger.info("Criando arquivo 'precos.xlsx' de exemplo...")
        dados_exemplo = {
            "Modelo": ["iPhone 11", "iPhone 11", "iPhone 12", "iPhone 12", "iPhone 13"],
            "Servico": ["Tela", "Bateria", "Tela", "Conector", "Tela"],
            "PrecoVista": [500.00, 250.00, 700.00, 300.00, 900.00],
            "PrecoCartao": [550.00, 280.00, 780.00, 330.00, 990.00]
        }
        df_exemplo = pd.DataFrame(dados_exemplo)
        df_exemplo.to_excel("precos.xlsx", index=False)
        logger.info("Arquivo 'precos.xlsx' de exemplo criado com sucesso.")

    bot = BudgetBot(TOKEN)
    bot.run()
