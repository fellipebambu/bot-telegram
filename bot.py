# budget_bot.py
import pandas as pd
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
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
                f"✅ Orçamento para {modelo.title()} - {servico.title()}:\n"
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
                break # Encontra o primeiro e sai
        
        # Busca por serviços
        for servico in self.servicos_disponiveis:
            if servico in texto:
                servico_encontrado = servico
                break # Encontra o primeiro e sai

        return modelo_encontrado, servico_encontrado

    async def preco_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto_args = " ".join(context.args)
        if not texto_args:
            await update.message.reply_text(
                "Por favor, informe o modelo e o serviço. Ex: /preco tela iphone 11"
            )
            return

        modelo, servico = self.interpretar_texto(texto_args)

        if not modelo or not servico:
            await update.message.reply_text(
                "Não consegui entender o modelo ou o serviço. Por favor, tente novamente. "
                "Ex: /preco tela iphone 11. Modelos disponíveis: "
                f"{', '.join([m.title() for m in self.modelos_disponiveis])}. "
                f"Serviços disponíveis: {', '.join([s.title() for s in self.servicos_disponiveis])}."
            )
            return

        resposta = self.buscar_preco(modelo, servico)
        await update.message.reply_text(resposta)

    async def responder_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text
        modelo, servico = self.interpretar_texto(texto)

        if not modelo or not servico:
            # Ignora a mensagem se não conseguir interpretar modelo e serviço
            return

        resposta = self.buscar_preco(modelo, servico)
        await update.message.reply_text(resposta)

    def run(self):
        application = ApplicationBuilder().token(self.token).build()

        application.add_handler(CommandHandler("preco", self.preco_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.responder_message))

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
            "Modelo": ["iPhone 11", "iPhone 11", "iPhone 12", "iPhone 12"],
            "Servico": ["Tela", "Bateria", "Tela", "Conector"],
            "PrecoVista": [500.00, 250.00, 700.00, 300.00],
            "PrecoCartao": [550.00, 280.00, 780.00, 330.00]
        }
        df_exemplo = pd.DataFrame(dados_exemplo)
        df_exemplo.to_excel("precos.xlsx", index=False)
        print("Arquivo 'precos.xlsx' de exemplo criado com sucesso.")

    bot = BudgetBot(TOKEN)
    bot.run()
