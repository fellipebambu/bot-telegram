import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8797052763:AAGlpCRCq-fVncEqyFjqjPTUqVrF6bgVyaw"
USUARIOS_PERMITIDOS = [79998188730, 79999811507]

tabela = pd.read_excel("precos.xlsx")

def buscar_preco(modelo, servico):
    resultado = tabela[
        (tabela["Modelo"] == modelo) &
        (tabela["Servico"] == servico)
    ]

    if not resultado.empty:
        preco = resultado.iloc[0]["Preco"]
        return f"{modelo} - {servico}: R$ {preco}"
    else:
        return "Preço não encontrado"

async def preco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #if update.effective_user.id not in USUARIOS_PERMITIDOS:
      #  return

    try:
        modelo = context.args[0]
        servico = context.args[1]
        resposta = buscar_preco(modelo, servico)
    except:
        resposta = "Use assim: /preco iphone11 tela"

    await update.message.reply_text(resposta)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("preco", preco))

app.run_polling()