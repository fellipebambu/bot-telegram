import pandas as pd
import os
import json
import logging
import asyncio
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

# Configuração de log detalhada para depuração
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BudgetBot:
    def __init__(self, token, excel_file="precos.xlsx", whitelist_file="usuarios_autorizados.json"):
        self.token = token
        self.excel_file = excel_file
        self.whitelist_file = whitelist_file
        self.tabela = self._carregar_tabela()
        self.usuarios_autorizados = self._carregar_whitelist()
        
        # Inicializa listas vazias se a tabela falhar
        if self.tabela is not None and not self.tabela.empty:
            self.modelos_disponiveis = self.tabela["Modelo"].unique().tolist()
            self.servicos_disponiveis = self.tabela["Servico"].unique().tolist()
        else:
            self.modelos_disponiveis = []
            self.servicos_disponiveis = []
            
        logger.info(f"Bot inicializado. Modelos: {len(self.modelos_disponiveis)}, Serviços: {len(self.servicos_disponiveis)}")
        logger.info(f"Usuários autorizados: {len(self.usuarios_autorizados)}")

    def _carregar_tabela(self):
        """Carrega a planilha Excel com tratamento de erro robusto"""
        try:
            if not os.path.exists(self.excel_file):
                logger.error(f"ERRO: O arquivo '{self.excel_file}' não foi encontrado.")
                return pd.DataFrame(columns=["Modelo", "Servico", "Variacao", "PrecoVista", "PrecoCartao"])

            tabela = pd.read_excel(self.excel_file)
            
            # Limpa nomes das colunas (remove espaços e converte para minúsculas para comparar)
            tabela.columns = [str(col).strip() for col in tabela.columns]
            
            # Mapeamento flexível de colunas
            col_map = {
                "Modelo": ["Modelo", "modelo", "MODELO", "Aparelho"],
                "Servico": ["Servico", "Serviço", "servico", "serviço", "SERVICO"],
                "Variacao": ["Variacao", "Variação", "variacao", "variação", "TipoAro", "Tipo"],
                "PrecoVista": ["PrecoVista", "Preço à Vista", "Preço Vista", "Preco Vista", "A Vista"],
                "PrecoCartao": ["PrecoCartao", "Preço no Cartão", "Preço Cartão", "Preco Cartao", "Cartão"]
            }

            # Tenta renomear as colunas encontradas para o padrão esperado
            for padrao, variantes in col_map.items():
                for variante in variantes:
                    if variante in tabela.columns:
                        tabela.rename(columns={variante: padrao}, inplace=True)
                        break

            # Verifica se as colunas essenciais existem
            colunas_obrigatorias = ["Modelo", "Servico", "PrecoVista", "PrecoCartao"]
            for col in colunas_obrigatorias:
                if col not in tabela.columns:
                    logger.error(f"ERRO: Coluna '{col}' não encontrada na planilha!")
                    return pd.DataFrame(columns=["Modelo", "Servico", "Variacao", "PrecoVista", "PrecoCartao"])

            # Padroniza os dados
            tabela["Modelo"] = tabela["Modelo"].astype(str).str.lower().str.strip()
            tabela["Servico"] = tabela["Servico"].astype(str).str.lower().str.strip()
            if "Variacao" in tabela.columns:
                tabela["Variacao"] = tabela["Variacao"].astype(str).str.lower().str.strip()
            else:
                tabela["Variacao"] = "padrão"

            return tabela
        except Exception as e:
            logger.error(f"ERRO CRÍTICO ao carregar a tabela: {e}")
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
            logger.error(f"ERRO ao carregar whitelist: {e}")
            return []

    def _criar_whitelist_exemplo(self):
        """Cria um arquivo de exemplo de whitelist"""
        exemplo = {
            "usuarios_autorizados": [{"id": 123456789, "nome": "Exemplo", "descricao": "Dono"}],
            "comentario": "Adicione seu ID aqui."
        }
        with open(self.whitelist_file, 'w') as f:
            json.dump(exemplo, f, indent=2, ensure_ascii=False)

    def usuario_autorizado(self, user_id):
        ids_autorizados = [u["id"] for u in self.usuarios_autorizados]
        return user_id in ids_autorizados

    def buscar_preco(self, modelo, servico, variacao=None):
        filtro = (self.tabela["Modelo"] == modelo) & (self.tabela["Servico"] == servico)
        if variacao and "Variacao" in self.tabela.columns:
            filtro = filtro & (self.tabela["Variacao"] == variacao.lower().strip())
        
        resultado = self.tabela[filtro]
        if not resultado.empty:
            row = resultado.iloc[0]
            preco_v = row["PrecoVista"]
            preco_c = row["PrecoCartao"]
            v_str = f" ({variacao})" if variacao and variacao != "padrão" else ""
            return (
                f"✅ {servico.title()} do {modelo.title()}{v_str}:\n"
                f"💵 À vista: R$ {preco_v:.2f}\n"
                f"💳 Cartão: R$ {preco_c:.2f}"
            )
        return f"❌ Não encontrei preço para {modelo.title()} e {servico.title()}."

    def interpretar_texto(self, texto):
        texto = texto.lower()
        modelo_enc = None
        servico_enc = None

        modelos_ord = sorted(self.modelos_disponiveis, key=len, reverse=True)
        for m in modelos_ord:
            if m in texto:
                modelo_enc = m
                break
        
        if modelo_enc:
            servicos_m = self.tabela[self.tabela["Modelo"] == modelo_enc]["Servico"].unique().tolist()
            for s in servicos_m:
                if s in texto:
                    servico_enc = s
                    break
        else:
            for s in self.servicos_disponiveis:
                if s in texto:
                    servico_enc = s
                    break

        return modelo_enc, servico_enc

    def obter_variacoes(self, modelo, servico):
        if "Variacao" not in self.tabela.columns:
            return None
        vars = self.tabela[(self.tabela["Modelo"] == modelo) & (self.tabela["Servico"] == servico)]["Variacao"].unique().tolist()
        return vars if len(vars) > 1 else None

    async def apagar_mensagens(self, context: ContextTypes.DEFAULT_TYPE):
        job = context.job
        try:
            for msg_id in job.data:
                await context.bot.delete_message(chat_id=job.chat_id, message_id=msg_id)
        except:
            pass

    def agendar_limpeza(self, context: ContextTypes.DEFAULT_TYPE, chat_id, message_ids):
        if not isinstance(message_ids, list): message_ids = [message_ids]
        ids = [m for m in message_ids if m is not None]
        if ids:
            context.job_queue.run_once(self.apagar_mensagens, when=15, data=ids, chat_id=chat_id)

    async def responder_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text: return
        
        user_id = update.effective_user.id
        if not self.usuario_autorizado(user_id):
            logger.warning(f"Acesso negado: {user_id}")
            await update.message.reply_text(f"❌ Acesso negado. Seu ID: `{user_id}`")
            return

        modelo, servico = self.interpretar_texto(update.message.text)

        if modelo and servico:
            vars = self.obter_variacoes(modelo, servico)
            if vars:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{modelo}|{servico}|{v}|{update.message.message_id}")] for v in vars]
                await update.message.reply_text(f"Qual tipo de {servico} você precisa?", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                resp = self.buscar_preco(modelo, servico)
                sent = await update.message.reply_text(resp)
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent.message_id])
        elif modelo:
            servicos_m = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_m:
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"{modelo}|{s}|initial|{update.message.message_id}")] for s in servicos_m]
                await update.message.reply_text(f"Qual serviço você precisa para o {modelo.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id
        if not self.usuario_autorizado(user_id):
            await query.answer("❌ Sem acesso.", show_alert=True)
            return

        await query.answer()
        data = query.data.split('|')
        if len(data) >= 4:
            mod, serv, extra, u_msg_id = data[0], data[1], data[2], int(data[3])
            if extra == "initial":
                vars = self.obter_variacoes(mod, serv)
                if vars:
                    keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"{mod}|{serv}|{v}|{u_msg_id}")] for v in vars]
                    await query.edit_message_text(text=f"Qual tipo de {serv} você precisa?", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    resp = self.buscar_preco(mod, serv)
                    await query.edit_message_text(text=resp)
                    self.agendar_limpeza(context, query.message.chat_id, [u_msg_id, query.message.message_id])
            else:
                resp = self.buscar_preco(mod, serv, extra)
                await query.edit_message_text(text=resp)
                self.agendar_limpeza(context, query.message.chat_id, [u_msg_id, query.message.message_id])

    def run(self):
        # Solução para o erro do Python 3.13 e JobQueue
        application = ApplicationBuilder().token(self.token).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.responder_message))
        application.add_handler(CallbackQueryHandler(self.button_handler))
        
        logger.info("Bot rodando... 🚀")
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("ERRO: TOKEN não definido.")
        exit(1)
    bot = BudgetBot(TOKEN)
    bot.run()
