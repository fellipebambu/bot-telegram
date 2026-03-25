import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "SEU_TOKEN_AQUI"

tabela = pd.read_excel("precos.xlsx")

tabela["Modelo"] = tabela["Modelo"].str.lower().str.strip()
tabela["Servico"] = tabela["Servico"].str.lower().str.strip()

def buscar_preco(modelo, servico):
    resultado = tabela[
        (tabela["Modelo"] == modelo) &
        (tabela["Servico"] == servico)
    ]

    if not resultado.empty:
        preco = resultado.iloc[0]["Preco"]
        return f"{modelo.title()} - {servico}: R$ {preco}"
    else:
        return "❌ Não encontrei esse preço."

async def preco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args).lower()

    if not texto:
        await update.message.reply_text("Ex: /preco tela iphone 11")
        return

    if "iphone 11" in texto:
        modelo = "iphone 11"
    elif "iphone 12" in texto:
        modelo = "iphone 12"
    else:
        modelo = None

    if "tela" in texto:
        servico = "tela"
    elif "bateria" in texto:
        servico = "bateria"
    elif "conector" in texto:
        servico = "conector"
    else:
        servico = None

    if not modelo or not servico:
        await update.message.reply_text("🤔 Não entendi. Ex: tela iphone 11")
        return

    resposta = buscar_preco(modelo, servico)
    await update.message.reply_text(f"💰 {resposta}")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("preco", preco))

app.run_polling()