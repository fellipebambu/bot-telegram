import pandas as pd
import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# Configuração básica de log corrigida
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class BudgetBot:
    def __init__(self, token, excel_file="precos.xlsx", whitelist_file="usuarios_autorizados.json"):
        self.token = token
        self.excel_file = excel_file
        self.whitelist_file = whitelist_file
        self.tabela = self._carregar_tabela()
        self.usuarios_autorizados = self._carregar_whitelist()
        self.modelos_disponiveis = self.tabela["Modelo"].unique().tolist()
        self.servicos_disponiveis = self.tabela["Servico"].unique().tolist()
        print(f"Bot inicializado. Modelos: {self.modelos_disponiveis}, Serviços: {self.servicos_disponiveis}")
        print(f"Usuários autorizados: {len(self.usuarios_autorizados)}")

    def _carregar_tabela(self):
        try:
            tabela = pd.read_excel(self.excel_file)
            tabela["Modelo"] = tabela["Modelo"].astype(str).str.lower().str.strip()
            tabela["Servico"] = tabela["Servico"].astype(str).str.lower().str.strip()
            if "Variacao" in tabela.columns:
                tabela["Variacao"] = tabela["Variacao"].astype(str).str.lower().str.strip()
            return tabela
        except Exception as e:
            print(f"ERRO ao carregar a tabela: {e}")
            return pd.DataFrame(columns=["Modelo", "Servico", "Variacao", "PrecoVista", "PrecoCartao"])

    def _carregar_whitelist(self):
        """Carrega a lista de usuários autorizados do arquivo JSON"""
        try:
            if os.path.exists(self.whitelist_file):
                with open(self.whitelist_file, 'r') as f:
                    dados = json.load(f)
                    return dados.get("usuarios_autorizados", [])
            else:
                self._criar_whitelist_exemplo()
                return []
        except Exception as e:
            print(f"ERRO ao carregar whitelist: {e}")
            return []

    def _criar_whitelist_exemplo(self):
        """Cria um arquivo de exemplo de whitelist"""
        exemplo = {
            "usuarios_autorizados": [
                {"id": 123456789, "nome": "Seu Nome", "descricao": "Proprietário"}
            ],
            "comentario": "Adicione os IDs do Telegram dos usuários autorizados aqui."
        }
        with open(self.whitelist_file, 'w') as f:
            json.dump(exemplo, f, indent=2, ensure_ascii=False)

    def usuario_autorizado(self, user_id):
        """Verifica se o usuário está na whitelist"""
        ids_autorizados = [u["id"] for u in self.usuarios_autorizados]
        return user_id in ids_autorizados

    def registrar_tentativa_nao_autorizada(self, user_id, username, first_name):
        """Registra tentativas de acesso não autorizado"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] ⚠️  ACESSO NEGADO - ID: {user_id} | Username: @{username} | Nome: {first_name}")

    def buscar_preco(self, modelo, servico, variacao=None):
        filtro = (self.tabela["Modelo"] == modelo) & (self.tabela["Servico"] == servico)
        if variacao and "Variacao" in self.tabela.columns:
            filtro = filtro & (self.tabela["Variacao"] == variacao.lower().strip())
        
        resultado = self.tabela[filtro]
        if not resultado.empty:
            preco_vista = resultado.iloc[0]["PrecoVista"]
            preco_cartao = resultado.iloc[0]["PrecoCartao"]
            variacao_str = f" ({variacao})" if variacao else ""
            return (
                f"✅ {servico.title()} do {modelo.title()}{variacao_str}:\n"
                f"💵 À vista: R$ {preco_vista:.2f}\n"
                f"💳 Cartão: R$ {preco_cartao:.2f}"
            )
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
        if "Variacao" not in self.tabela.columns:
            return None
        variacoes = self.tabela[(self.tabela["Modelo"] == modelo) & (self.tabela["Servico"] == servico)]["Variacao"].unique().tolist()
        return variacoes if len(variacoes) > 1 else None

    async def apagar_mensagens(self, context: ContextTypes.DEFAULT_TYPE):
        job = context.job
        chat_id = job.chat_id
        message_ids = job.data
        for msg_id in message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    def agendar_limpeza(self, context: ContextTypes.DEFAULT_TYPE, chat_id, message_ids):
        if not isinstance(message_ids, list):
            message_ids = [message_ids]
        message_ids = [m for m in message_ids if m is not None]
        if message_ids:
            context.job_queue.run_once(self.apagar_mensagens, when=15, data=message_ids, chat_id=chat_id)

    async def preco_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.usuario_autorizado(user_id):
            self.registrar_tentativa_nao_autorizada(user_id, update.effective_user.username, update.effective_user.first_name)
            await update.message.reply_text(f"❌ Acesso negado. Seu ID: `{user_id}`")
            return

        texto_args = " ".join(context.args)
        if not texto_args:
            sent_msg = await update.message.reply_text("Informe o modelo e serviço. Ex: /preco tela iphone 11")
            self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
            return

        modelo, servico = self.interpretar_texto(texto_args)
        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            if variacoes:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}|{update.message.message_id}")] for v in variacoes]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"Qual tipo de {servico} você precisa?", reply_markup=reply_markup)
            else:
                resposta = self.buscar_preco(modelo, servico)
                sent_msg = await update.message.reply_text(resposta)
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
        else:
            sent_msg = await update.message.reply_text("Não entendi o modelo ou serviço.")
            self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])

    async def responder_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        
        user_id = update.effective_user.id
        if not self.usuario_autorizado(user_id):
            self.registrar_tentativa_nao_autorizada(user_id, update.effective_user.username, update.effective_user.first_name)
            await update.message.reply_text(f"❌ Acesso negado. Seu ID: `{user_id}`")
            return

        texto = update.message.text
        modelo, servico = self.interpretar_texto(texto)

        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            if variacoes:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}|{update.message.message_id}")] for v in variacoes]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"Qual tipo de {servico} você precisa?", reply_markup=reply_markup)
            else:
                resposta = self.buscar_preco(modelo, servico)
                sent_msg = await update.message.reply_text(resposta)
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
        elif modelo:
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_para_modelo:
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}|initial|{update.message.message_id}")] for s in servicos_para_modelo]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"Qual serviço você precisa para o {modelo.title()}?", reply_markup=reply_markup)

    async def button_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.usuario_autorizado(user_id):
            await update.callback_query.answer("❌ Sem acesso.", show_alert=True)
            return

        query = update.callback_query
        await query.answer()
        data = query.data.split('|')
        
        if len(data) >= 4:
            modelo, servico, extra, user_msg_id = data[0], data[1], data[2], data[3]
            user_msg_id = int(user_msg_id)
            
            if extra == "initial":
                variacoes = self.obter_variacoes(modelo, servico)
                if variacoes:
                    keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}|{user_msg_id}")] for v in variacoes]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(text=f"Qual tipo de {servico} você precisa?", reply_markup=reply_markup)
                else:
                    resposta = self.buscar_preco(modelo, servico)
                    await query.edit_message_text(text=resposta)
                    self.agendar_limpeza(context, query.message.chat_id, [user_msg_id, query.message.message_id])
            else:
                resposta = self.buscar_preco(modelo, servico, extra)
                await query.edit_message_text(text=resposta)
                self.agendar_limpeza(context, query.message.chat_id, [user_msg_id, query.message.message_id])

    def run(self):
        application = ApplicationBuilder().token(self.token).build()
        application.add_handler(CommandHandler("preco", self.preco_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.responder_message))
        application.add_handler(CallbackQueryHandler(self.button_callback_handler))
        print("Bot rodando com Segurança e JobQueue... 🚀")
        application.run_polling()

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        print("ERRO: TOKEN não definido.")
        exit(1)
    bot = BudgetBot(TOKEN)
    bot.run()
