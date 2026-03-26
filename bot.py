import os
import csv
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# Configuração de log para ver tudo no terminal
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

class BudgetBot:
    def __init__(self, token, csv_file="precos.csv"):
    self.token = token
    self.csv_file = csv_file
    self.tabela = self._carregar_tabela()
        self.token = token
        self.excel_file = excel_file
        self.tabela = self._carregar_tabela()
        self.modelos_disponiveis = list(set(item["Modelo"] for item in self.tabela))
        self.servicos_disponiveis = list(set(item["Servico"] for item in self.tabela))
        print(f"Bot inicializado. Modelos: {self.modelos_disponiveis}, Serviços: {self.servicos_disponiveis}")

    def _carregar_tabela(self):
    tabela = []
    try:
        with open(self.csv_file, newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tabela.append({
                    "Modelo": row["modelo"].lower().strip(),
                    "Servico": row["servico"].lower().strip(),
                    "Variacao": row.get("variacao", "").lower().strip(),
                    "PrecoVista": float(row["precovista"]),
                    "PrecoCartao": float(row["precocartao"])
                })
        return tabela
    except Exception as e:
        print(f"ERRO ao carregar CSV: {e}")
        return []
    def buscar_preco(self, modelo, servico, variacao=None):
        filtro = (self.tabela["Modelo"] == modelo) & (self.tabela["Servico"] == servico)
        if variacao and "Variacao" in self.tabela.columns:
            filtro = filtro & (self.tabela["Variacao"] == variacao.lower().strip())
        resultado = [
        item for item in self.tabela
        if item["Modelo"] == modelo and item["Servico"] == servico
        and (not variacao or item["Variacao"] == variacao)
        ]if resultado:
            item = resultado[0]
            preco_vista = item["PrecoVista"]
            preco_cartao = item["PrecoCartao"]
        if not resultado.empty:
            preco_vista = resultado.iloc[0]["PrecoVista"]
            preco_cartao = resultado.iloc[0]["PrecoCartao"]
            variacao_str = f" ({variacao})" if variacao else ""
            return f"✅ {servico.title()} do {modelo.title()}{variacao_str}:\n💵 À vista: R$ {preco_vista:.2f}\n💳 Cartão: R$ {preco_cartao:.2f}"
        return f"❌ Não encontrei um orçamento para {modelo.title()} e {servico.title()}."

    def interpretar_texto(self, texto):
        texto = texto.lower()
        modelo_encontrado = None
        servico_encontrado = None
        modelos_ordenados = sorted(self.modelos_disponiveis, key=len, reverse=True)
        for modelo in modelos_ordenados:
            if modelo in texto:
                modelo_encontrado = modelo
                break
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

        def obter_variacoes(self, modelo, servico):
        variacoes = list(set(
            item["Variacao"]
            for item in self.tabela
            if item["Modelo"] == modelo and item["Servico"] == servico and item["Variacao"]
        ))
    return variacoes if len(variacoes) > 1 else None

    async def apagar_depois(self, chat_id, message_ids, delay=15):
        """Espera 15 segundos e apaga as mensagens."""
        await asyncio.sleep(delay)
        for msg_id in message_ids:
            try:
                await bot_app.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                print(f"LIMPEZA: Mensagem {msg_id} apagada!")
            except Exception as e:
                print(f"AVISO: Não apaguei {msg_id} (talvez já apagada). Erro: {e}")

    async def preco_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto_args = " ".join(context.args)
        if not texto_args:
            sent = await update.message.reply_text("Por favor, informe o modelo e o serviço. Ex: /preco tela iphone 11")
            asyncio.create_task(self.apagar_depois(update.effective_chat.id, [update.message.message_id, sent.message_id]))
            return
        modelo, servico = self.interpretar_texto(texto_args)
        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            if variacoes:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}|{update.message.message_id}")] for v in variacoes]
                await update.message.reply_text(f"Qual tipo de {servico} você precisa?", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                res = self.buscar_preco(modelo, servico)
                sent = await update.message.reply_text(res)
                asyncio.create_task(self.apagar_depois(update.effective_chat.id, [update.message.message_id, sent.message_id]))

    async def responder_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text: return
        modelo, servico = self.interpretar_texto(update.message.text)
        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            if variacoes:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}|{update.message.message_id}")] for v in variacoes]
                await update.message.reply_text(f"Qual tipo de {servico} você precisa?", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                res = self.buscar_preco(modelo, servico)
                sent = await update.message.reply_text(res)
                asyncio.create_task(self.apagar_depois(update.effective_chat.id, [update.message.message_id, sent.message_id]))
        elif modelo:
            servicos = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos:
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}|initial|{update.message.message_id}")] for s in servicos]
                await update.message.reply_text(f"Qual serviço você precisa para o {modelo.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))

    async def button_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data.split('|')
        if len(data) >= 4:
            modelo, servico, extra, user_msg_id = data[0], data[1], data[2], int(data[3])
            if extra == "initial":
                variacoes = self.obter_variacoes(modelo, servico)
                if variacoes:
                    keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}|{user_msg_id}")] for v in variacoes]
                    await query.edit_message_text(text=f"Qual tipo de {servico} você precisa?", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    res = self.buscar_preco(modelo, servico)
                    await query.edit_message_text(text=res)
                    asyncio.create_task(self.apagar_depois(query.message.chat_id, [user_msg_id, query.message.message_id]))
            else:
                res = self.buscar_preco(modelo, servico, extra)
                await query.edit_message_text(text=res)
                asyncio.create_task(self.apagar_depois(query.message.chat_id, [user_msg_id, query.message.message_id]))
    def run(self):
        global bot_app
        # Criamos a aplicação
        bot_app = ApplicationBuilder().token(self.token).build()
        
        # Adicionamos os handlers
        bot_app.add_handler(CommandHandler("preco", self.preco_command))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.responder_message))
        bot_app.add_handler(CallbackQueryHandler(self.button_callback_handler))
        
        print("Bot rodando com LIMPEZA ATIVADA (Python 3.14+)... 🚀🧹")
        
        # Esta é a forma correta para versões novas do Python
        import asyncio
        try:
            bot_app.run_polling()
        except RuntimeError:
            # Caso o loop já esteja rodando ou precise ser iniciado manualmente
            asyncio.run(bot_app.run_polling())

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        print("ERRO: A variável de ambiente 'TOKEN' não está definida.")
        exit(1)
    
    bot = BudgetBot(TOKEN)
    bot.run()
