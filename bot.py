import pandas as pd
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# pega o token das variáveis do Railway
TOKEN = os.getenv("TOKEN")

# IDs permitidos (opcional)
USUARIOS_PERMITIDOS = [79998188730, 79999811507]

# carrega a planilha
tabela = pd.read_excel("precos.xlsx")

# padroniza os dados
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
    # (opcional) bloquear usuários não permitidos
    # if update.effective_user.id not in USUARIOS_PERMITIDOS:
    #     return

    texto = " ".join(context.args).lower()

    if not texto:
        await update.message.reply_text("Ex: /preco tela iphone 11")
        return

    # detectar modelo
    if "iphone 11" in texto:
        modelo = "iphone 11"
    elif "iphone 12" in texto:
        modelo = "iphone 12"
    else:
        modelo = None

    # detectar serviço
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
    await update.message.reply_text(f"💰 {resposta
    
    async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower()

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
        await update.message.reply_text("🤔 Fala tipo: tela iphone 11")
        return

    resposta = buscar_preco(modelo, servico)
    await update.message.reply_text(f"💰 {resposta}")

# inicia o bot
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("preco", preco))

print("Bot rodando...")
app.run_polling()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))