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

TOKEN = os.getenv("TOKEN")

tabela = pd.read_excel("precos.xlsx")
print(tabela.columns)
print(tabela.head())

# padroniza tudo
tabela["Modelo"] = tabela["Modelo"].str.lower().str.replace(" ", "").str.strip()
tabela["Servico"] = tabela["Servico"].str.lower().str.strip()


def buscar_preco(modelo, servico):
    resultado = tabela[
        (tabela["Modelo"] == modelo) &
        (tabela["Servico"] == servico)
    ]

    if not resultado.empty:
        preco_vista = resultado.iloc[0]["PrecoVista"]
        preco_cartao = resultado.iloc[0]["PrecoCartao"]

        return (
            f"📱 {modelo.title()} - {servico}\n\n"
            f"💵 À vista: R$ {preco_vista}\n"
            f"💳 Cartão: R$ {preco_cartao}\n\n"
        )
    else:
        return "❌ Não encontrei esse preço"


def interpretar_texto(texto):
    texto = texto.lower()

    modelo = None
    servico = None

    # MODELOS
    if "iphone 11" in texto:
        modelo = "iphone 11"
    elif "iphone 12" in texto:
        modelo = "iphone 12"

    # SERVIÇOS
    if "tela" in texto:
        servico = "tela"
    elif "bateria" in texto:
        servico = "bateria"
    elif "conector" in texto:
        servico = "conector"

    return modelo, servico


# comando /preco
async def preco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)

    if not texto:
        await update.message.reply_text("Ex: /preco tela iphone 11")
        return

    modelo, servico = interpretar_texto(texto)

    if not modelo or not servico:
        await update.message.reply_text("Não entendi. Ex: tela iphone 11")
        return

    resposta = buscar_preco(modelo, servico)
    await update.message.reply_text(resposta)


# mensagem normal (SEM /)
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text

    modelo, servico = interpretar_texto(texto)

    if not modelo or not servico:
        return  # ignora se não entender

    resposta = buscar_preco(modelo, servico)
    await update.message.reply_text(resposta)


# iniciar bot
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("preco", preco))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

print("Bot rodando... 🚀")
app.run_polling()