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
            return tabela
        except FileNotFoundError:
            print(f"ERRO: O arquivo '{self.excel_file}' não foi encontrado.")
            exit(1) # Encerra o bot se a tabela não for encontrada
        except Exception as e:
            print(f"ERRO ao carregar a tabela: {e}")
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
        # Se um modelo foi encontrado, podemos querer oferecer serviços para ele.
        # Se nenhum modelo for encontrado, ainda podemos interpretar um serviço se for uma consulta autônoma.
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

    async def preco_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto_args = " ".join(context.args)
        if not texto_args:
            await update.message.reply_text(
                "Por favor, informe o modelo e o serviço. Ex: /preco tela iphone 11"
            )
            return

        modelo, servico = self.interpretar_texto(texto_args)

        if modelo and servico:
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
        await query.answer() # Responde ao callback para remover o estado de 'carregando' do botão

        data = query.data.split('|')
        modelo = data[0]
        servico = data[1]

        resposta = self.buscar_preco(modelo, servico)
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
            "Modelo": ["iPhone 11", "iPhone 11", "iPhone 12", "iPhone 12", "iPhone 13"],
            "Servico": ["Tela", "Bateria", "Tela", "Conector", "Tela"],
            "PrecoVista": [500.00, 250.00, 700.00, 300.00, 900.00],
            "PrecoCartao": [550.00, 280.00, 780.00, 330.00, 990.00]
        }
        df_exemplo = pd.DataFrame(dados_exemplo)
        df_exemplo.to_excel("precos.xlsx", index=False)
        print("Arquivo 'precos.xlsx' de exemplo criado com sucesso.")

    bot = BudgetBot(TOKEN)
    bot.run()
