import pandas as pd
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

class BudgetBot:
    def __init__(self, token, excel_file="precos.xlsx"):
        self.token = token
        self.excel_file = excel_file
        self.tabela = self._carregar_tabela()
        self.modelos_disponiveis = self.tabela["Modelo"].unique().tolist()
        self.servicos_disponiveis = self.tabela["Servico"].unique().tolist()
        print(f"Bot inicializado. Modelos: {self.modelos_disponiveis}, Serviços: {self.servicos_disponiveis}")

    def _carregar_tabela(self):
        try:
            tabela = pd.read_excel(self.excel_file)
            # Padroniza as colunas de modelo e serviço para facilitar a busca
            tabela["Modelo"] = tabela["Modelo"].str.lower().str.strip()
            tabela["Servico"] = tabela["Servico"].str.lower().str.strip()
            if "Variacao" in tabela.columns:
                tabela["Variacao"] = tabela["Variacao"].str.lower().str.strip()
            return tabela
        except FileNotFoundError:
            print(f"ERRO: O arquivo '{self.excel_file}' não foi encontrado.")
            exit(1)
        except Exception as e:
            print(f"ERRO ao carregar a tabela: {e}")
            exit(1)

    def buscar_preco(self, modelo, servico, variacao=None):
        """Busca o preço baseado em modelo, serviço e variação (opcional)"""
        filtro = (self.tabela["Modelo"] == modelo) & (self.tabela["Servico"] == servico)
        
        # Se variação foi especificada, adiciona ao filtro
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
        else:
            return f"❌ Não encontrei um orçamento para {modelo.title()} e {servico.title()}."

    def interpretar_texto(self, texto):
        """Interpreta o texto e encontra o modelo e serviço."""
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
        """Retorna a lista de variações disponíveis para um modelo e serviço."""
        if "Variacao" not in self.tabela.columns:
            return None
        
        variacoes = self.tabela[
            (self.tabela["Modelo"] == modelo) & 
            (self.tabela["Servico"] == servico)
        ]["Variacao"].unique().tolist()
        
        if len(variacoes) <= 1:
            return None
        
        return variacoes

    async def apagar_mensagens(self, context: ContextTypes.DEFAULT_TYPE):
        """Tarefa agendada para apagar as mensagens após 15 segundos."""
        job = context.job
        chat_id = job.chat_id
        message_ids = job.data # Lista de IDs das mensagens para apagar
        
        for msg_id in message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                print(f"Erro ao apagar mensagem {msg_id}: {e}")

    def agendar_limpeza(self, context: ContextTypes.DEFAULT_TYPE, chat_id, message_ids):
        """Agenda a limpeza das mensagens em 15 segundos."""
        context.job_queue.run_once(self.apagar_mensagens, 15, data=message_ids, chat_id=chat_id)

    async def preco_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto_args = " ".join(context.args)
        if not texto_args:
            sent_msg = await update.message.reply_text(
                "Por favor, informe o modelo e o serviço. Ex: /preco tela iphone 11"
            )
            self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
            return

        modelo, servico = self.interpretar_texto(texto_args)

        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            
            if variacoes:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}")] for v in variacoes]
                reply_markup = InlineKeyboardMarkup(keyboard)
                sent_msg = await update.message.reply_text(f"Qual tipo de {servico} você precisa?", reply_markup=reply_markup)
                # Não agendamos limpeza aqui porque o usuário ainda vai interagir com os botões
            else:
                resposta = self.buscar_preco(modelo, servico)
                sent_msg = await update.message.reply_text(resposta)
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
        elif modelo and not servico:
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_para_modelo:
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}")] for s in servicos_para_modelo]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"Qual serviço você precisa para o {modelo.title()}?", reply_markup=reply_markup)
            else:
                sent_msg = await update.message.reply_text(f"Não encontrei serviços disponíveis para o {modelo.title()}.")
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
        else:
            sent_msg = await update.message.reply_text("Não consegui entender o modelo ou o serviço.")
            self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])

    async def responder_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text
        modelo, servico = self.interpretar_texto(texto)

        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            
            if variacoes:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}")] for v in variacoes]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"Qual tipo de {servico} você precisa?", reply_markup=reply_markup)
            else:
                resposta = self.buscar_preco(modelo, servico)
                sent_msg = await update.message.reply_text(resposta)
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
        elif modelo and not servico:
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_para_modelo:
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}|initial")] for s in servicos_para_modelo]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"Qual serviço você precisa para o {modelo.title()}?", reply_markup=reply_markup)
            else:
                sent_msg = await update.message.reply_text(f"Não encontrei serviços disponíveis para o {modelo.title()}.")
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent_msg.message_id])
        else:
            return

    async def button_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data.split('|')
        
        # Tenta recuperar o ID da mensagem que iniciou o processo (se possível)
        # Como o bot apaga a pergunta do usuário e a resposta final, precisamos ser cuidadosos
        
        if len(data) >= 2:
            modelo = data[0]
            servico = data[1]
            
            if len(data) == 2 or (len(data) == 3 and data[2] == "initial"):
                variacoes = self.obter_variacoes(modelo, servico)
                
                if variacoes:
                    keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}")] for v in variacoes]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(text=f"Qual tipo de {servico} você precisa?", reply_markup=reply_markup)
                else:
                    resposta = self.buscar_preco(modelo, servico)
                    await query.edit_message_text(text=resposta)
                    # Agenda limpeza da mensagem do bot (o query.message)
                    # Nota: Não temos acesso fácil ao ID da mensagem original do usuário aqui via 'update.message'
                    # Mas podemos apagar a resposta do bot.
                    self.agendar_limpeza(context, query.message.chat_id, [query.message.message_id])
            
            elif len(data) == 3:
                variacao = data[2]
                resposta = self.buscar_preco(modelo, servico, variacao)
                await query.edit_message_text(text=resposta)
                self.agendar_limpeza(context, query.message.chat_id, [query.message.message_id])

    def run(self):
        application = ApplicationBuilder().token(self.token).build()

        application.add_handler(CommandHandler("preco", self.preco_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.responder_message))
        application.add_handler(CallbackQueryHandler(self.button_callback_handler))

        print("Bot rodando... 🚀")
        application.run_polling()

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        print("ERRO: A variável de ambiente 'TOKEN' não está definida.")
        exit(1)
    
    if not os.path.exists("precos.xlsx"):
        print("Criando arquivo 'precos.xlsx' de exemplo...")
        dados_exemplo = {
            "Modelo": ["Samsung A12", "iPhone 8", "iPhone X"],
            "Servico": ["Tela", "Bateria", "Tela"],
            "Variacao": ["com aro", "padrão", "oled"],
            "PrecoVista": [200.00, 150.00, 500.00],
            "PrecoCartao": [220.00, 165.00, 550.00]
        }
        df_exemplo = pd.DataFrame(dados_exemplo)
        df_exemplo.to_excel("precos.xlsx", index=False)

    bot = BudgetBot(TOKEN)
    bot.run()
