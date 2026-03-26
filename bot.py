import pandas as pd
import os
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
        """
        Interpreta o texto e encontra o modelo e serviço.
        Prioriza modelos mais longos para evitar conflitos (ex: "iPhone 8 Plus" antes de "iPhone 8")
        """
        texto = texto.lower()
        modelo_encontrado = None
        servico_encontrado = None

        # Ordena os modelos por comprimento (maior primeiro) para priorizar nomes mais específicos
        modelos_ordenados = sorted(self.modelos_disponiveis, key=len, reverse=True)

        # Busca por modelos (prioriza os mais longos)
        for modelo in modelos_ordenados:
            if modelo in texto:
                modelo_encontrado = modelo
                break
        
        # Busca por serviços (apenas se um modelo foi encontrado ou se for uma busca geral)
        if modelo_encontrado:
            # Busca serviços específicos para o modelo encontrado
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo_encontrado]["Servico"].unique().tolist()
            for servico in servicos_para_modelo:
                if servico in texto:
                    servico_encontrado = servico
                    break
        else:
            # Se nenhum modelo foi encontrado, tenta encontrar um serviço de forma geral
            for servico in self.servicos_disponiveis:
                if servico in texto:
                    servico_encontrado = servico
                    break

        return modelo_encontrado, servico_encontrado

    def obter_variacoes(self, modelo, servico):
        """
        Retorna a lista de variações disponíveis para um modelo e serviço.
        Se houver múltiplas variações, retorna a lista.
        Se houver apenas uma, retorna None (não precisa perguntar).
        """
        if "Variacao" not in self.tabela.columns:
            return None
        
        variacoes = self.tabela[
            (self.tabela["Modelo"] == modelo) & 
            (self.tabela["Servico"] == servico)
        ]["Variacao"].unique().tolist()
        
        # Se houver apenas uma variação, não precisa perguntar
        if len(variacoes) <= 1:
            return None
        
        return variacoes

    async def preco_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto_args = " ".join(context.args)
        if not texto_args:
            await update.message.reply_text(
                "Por favor, informe o modelo e o serviço. Ex: /preco tela iphone 11"
            )
            return

        modelo, servico = self.interpretar_texto(texto_args)

        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            
            if variacoes:
                # Se há múltiplas variações, oferece como botões
                keyboard = [
                    [InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}")]
                    for v in variacoes
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Qual tipo de {servico} você precisa?",
                    reply_markup=reply_markup
                )
            else:
                # Se há apenas uma variação, mostra o preço direto
                resposta = self.buscar_preco(modelo, servico)
                await update.message.reply_text(resposta)
        elif modelo and not servico:
            # Se apenas o modelo foi encontrado, oferece os serviços como botões
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_para_modelo:
                keyboard = [
                    [InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}")]
                    for s in servicos_para_modelo
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Qual serviço você precisa para o {modelo.title()}?",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(f"Não encontrei serviços disponíveis para o {modelo.title()}.")
        else:
            # Construindo a mensagem de erro de forma mais robusta
            modelos_str = ', '.join([m.title() for m in self.modelos_disponiveis])
            servicos_str = ', '.join([s.title() for s in self.servicos_disponiveis])
            await update.message.reply_text(
                "Não consegui entender o modelo ou o serviço. Por favor, tente novamente. "
                f"Ex: /preco tela iphone 11. Modelos disponíveis: {modelos_str}. "
                f"Serviços disponíveis: {servicos_str}."
            )

    async def responder_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text
        modelo, servico = self.interpretar_texto(texto)

        if modelo and servico:
            variacoes = self.obter_variacoes(modelo, servico)
            
            if variacoes:
                # Se há múltiplas variações, oferece como botões
                keyboard = [
                    [InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}")]
                    for v in variacoes
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Qual tipo de {servico} você precisa?",
                    reply_markup=reply_markup
                )
            else:
                # Se há apenas uma variação, mostra o preço direto
                resposta = self.buscar_preco(modelo, servico)
                await update.message.reply_text(resposta)
        elif modelo and not servico:
            # Se apenas o modelo foi encontrado, oferece os serviços como botões
            servicos_para_modelo = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_para_modelo:
                keyboard = [
                    [InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}")]
                    for s in servicos_para_modelo
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Qual serviço você precisa para o {modelo.title()}?",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(f"Não encontrei serviços disponíveis para o {modelo.title()}.")
        else:
            # Ignora a mensagem se não conseguir interpretar modelo e serviço
            return

    async def button_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data.split('|')
        
        if len(data) == 2:
            # Callback de serviço (modelo|serviço)
            modelo = data[0]
            servico = data[1]
            
            variacoes = self.obter_variacoes(modelo, servico)
            
            if variacoes:
                # Se há múltiplas variações, oferece como botões
                keyboard = [
                    [InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}")]
                    for v in variacoes
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text=f"Qual tipo de {servico} você precisa?",
                    reply_markup=reply_markup
                )
            else:
                resposta = self.buscar_preco(modelo, servico)
                await query.edit_message_text(text=resposta)
        
        elif len(data) == 3:
            # Callback de variação (modelo|serviço|variacao)
            modelo = data[0]
            servico = data[1]
            variacao = data[2]
            
            resposta = self.buscar_preco(modelo, servico, variacao)
            await query.edit_message_text(text=resposta)

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
    
    # Cria um arquivo de exemplo 'precos.xlsx' se não existir
    if not os.path.exists("precos.xlsx"):
        print("Criando arquivo 'precos.xlsx' de exemplo...")
        dados_exemplo = {
            "Modelo": [
                "Samsung A12", "Samsung A12", "Samsung A12", "Samsung A12",
                "iPhone 8", "iPhone 8",
                "iPhone X", "iPhone X",
                "Samsung A12", "Samsung A12",
                "iPhone 8", "iPhone 8",
                "iPhone X", "iPhone X"
            ],
            "Servico": [
                "Tela", "Tela", "Bateria", "Bateria",
                "Tela", "Tela",
                "Tela", "Tela",
                "Conector", "Conector",
                "Bateria", "Bateria",
                "Bateria", "Bateria"
            ],
            "Variacao": [
                "com aro", "sem aro", "com aro", "sem aro",
                "padrão", "padrão",
                "1ª linha", "oled",
                "com aro", "sem aro",
                "padrão", "padrão",
                "padrão", "padrão"
            ],
            "PrecoVista": [
                200.00, 170.00, 150.00, 150.00,
                400.00, 400.00,
                300.00, 500.00,
                100.00, 100.00,
                200.00, 200.00,
                250.00, 250.00
            ],
            "PrecoCartao": [
                220.00, 187.00, 165.00, 165.00,
                440.00, 440.00,
                330.00, 550.00,
                110.00, 110.00,
                220.00, 220.00,
                275.00, 275.00
            ]
        }
        df_exemplo = pd.DataFrame(dados_exemplo)
        df_exemplo.to_excel("precos.xlsx", index=False)
        print("Arquivo 'precos.xlsx' de exemplo criado com sucesso.")

    bot = BudgetBot(TOKEN)
    bot.run()
