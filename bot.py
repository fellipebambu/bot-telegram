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
    filters,
    Defaults
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
        
        # --- CONFIGURAÇÃO DE SEGURANÇA (WHITELIST) ---
        # Adicione aqui os IDs dos usuários autorizados (o seu ID já está incluído)
        self.ids_autorizados_fixos = [1129149570] 
        self.usuarios_autorizados_arquivo = self._carregar_whitelist()
        
        # Inicializa listas vazias se a tabela falhar
        if self.tabela is not None and not self.tabela.empty:
            self.modelos_disponiveis = sorted(self.tabela["Modelo"].unique().tolist(), key=len, reverse=True)
            self.servicos_disponiveis = self.tabela["Servico"].unique().tolist()
        else:
            self.modelos_disponiveis = []
            self.servicos_disponiveis = []
            
        logger.info(f"Bot inicializado. Modelos: {len(self.modelos_disponiveis)}, Serviços: {len(self.servicos_disponiveis)}")

    def _carregar_tabela(self):
        """Carrega a planilha Excel com tratamento de erro robusto"""
        try:
            if not os.path.exists(self.excel_file):
                logger.error(f"ERRO: O arquivo '{self.excel_file}' não foi encontrado.")
                return pd.DataFrame(columns=["Modelo", "Servico", "Variacao", "PrecoVista", "PrecoCartao"])

            tabela = pd.read_excel(self.excel_file)
            tabela.columns = [str(col).strip() for col in tabela.columns]
            
            col_map = {
                "Modelo": ["Modelo", "modelo", "MODELO", "Aparelho"],
                "Servico": ["Servico", "Serviço", "servico", "serviço", "SERVICO"],
                "Variacao": ["Variacao", "Variação", "variacao", "variação", "TipoAro", "Tipo"],
                "PrecoVista": ["PrecoVista", "Preço à Vista", "Preço Vista", "Preco Vista", "A Vista"],
                "PrecoCartao": ["PrecoCartao", "Preço no Cartão", "Preço Cartão", "Preco Cartao", "Cartão"]
            }

            for padrao, variantes in col_map.items():
                for variante in variantes:
                    if variante in tabela.columns:
                        tabela.rename(columns={variante: padrao}, inplace=True)
                        break

            colunas_obrigatorias = ["Modelo", "Servico", "PrecoVista", "PrecoCartao"]
            for col in colunas_obrigatorias:
                if col not in tabela.columns:
                    logger.error(f"ERRO: Coluna '{col}' não encontrada na planilha!")
                    return pd.DataFrame(columns=["Modelo", "Servico", "Variacao", "PrecoVista", "PrecoCartao"])

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
        """Carrega a lista de usuários autorizados do arquivo JSON (opcional)"""
        try:
            if os.path.exists(self.whitelist_file):
                with open(self.whitelist_file, 'r') as f:
                    dados = json.load(f)
                    return dados.get("usuarios_autorizados", [])
            return []
        except Exception as e:
            logger.error(f"ERRO ao carregar whitelist: {e}")
            return []

    def usuario_autorizado(self, user_id):
        ids_arquivo = [u["id"] for u in self.usuarios_autorizados_arquivo]
        return user_id in self.ids_autorizados_fixos or user_id in ids_arquivo

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

    def interpretar_texto_avancado(self, texto):
        """Nova lógica de interpretação que suporta buscas parciais"""
        texto = texto.lower().strip()
        
        # 1. Tenta encontrar modelo e serviço exatos (ou o modelo maior primeiro)
        modelo_enc = None
        servico_enc = None

        for m in self.modelos_disponiveis:
            if m in texto:
                modelo_enc = m
                break
        
        if modelo_enc:
            servicos_m = self.tabela[self.tabela["Modelo"] == modelo_enc]["Servico"].unique().tolist()
            for s in servicos_m:
                if s in texto:
                    servico_enc = s
                    break
            return modelo_enc, servico_enc, []

        # 2. Se não encontrou modelo exato, busca por palavras-chave
        # Remove palavras comuns de serviço para focar no modelo
        palavras_servico = ["tela", "bateria", "conector", "vidro", "tampa", "câmera", "camera"]
        texto_modelo = texto
        for p in palavras_servico:
            texto_modelo = texto_modelo.replace(p, "").strip()
            if p in texto:
                servico_enc = p

        # Busca modelos que contêm o texto digitado
        modelos_sugeridos = [m for m in self.modelos_disponiveis if texto_modelo in m]
        
        # Se encontrou apenas um modelo por palavra-chave, assume que é ele
        if len(modelos_sugeridos) == 1:
            return modelos_sugeridos[0], servico_enc, []
        
        # Se encontrou vários, retorna a lista para sugestão
        return None, servico_enc, modelos_sugeridos

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
            await update.message.reply_text(f"❌ Acesso negado. Seu ID: `{user_id}`")
            return

        texto = update.message.text
        modelo, servico, sugestoes = self.interpretar_texto_avancado(texto)

        # Caso 1: Modelo e Serviço encontrados (ou modelo único sugerido)
        if modelo and servico:
            vars = self.obter_variacoes(modelo, servico)
            if vars:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"V|{modelo}|{servico}|{v}|{update.message.message_id}")] for v in vars]
                await update.message.reply_text(f"Qual tipo de {servico} você precisa para o {modelo.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                resp = self.buscar_preco(modelo, servico)
                sent = await update.message.reply_text(resp)
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent.message_id])
        
        # Caso 2: Modelo encontrado mas serviço não (ou modelo único sugerido)
        elif modelo:
            servicos_m = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_m:
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"S|{modelo}|{s}|initial|{update.message.message_id}")] for s in servicos_m]
                await update.message.reply_text(f"Qual serviço você precisa para o {modelo.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))

        # Caso 3: Vários modelos sugeridos por palavra-chave
        elif sugestoes:
            # Limita a 10 sugestões para não poluir o chat
            sugestoes = sugestoes[:10]
            keyboard = [[InlineKeyboardButton(m.title(), callback_data=f"M|{m}|{servico if servico else 'none'}|initial|{update.message.message_id}")] for m in sugestoes]
            await update.message.reply_text(f"Encontrei esses modelos. Qual você quis dizer?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Caso 4: Nada encontrado
        else:
            sent = await update.message.reply_text("❌ Não consegui encontrar esse modelo ou serviço. Tente digitar de outra forma (ex: 'tela tecno spark').")
            self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent.message_id])

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id
        if not self.usuario_autorizado(user_id):
            await query.answer("❌ Sem acesso.", show_alert=True)
            return

        await query.answer()
        data = query.data.split('|')
        # Formato: TIPO | MOD | SERV | EXTRA | USER_MSG_ID
        tipo, mod, serv, extra, u_msg_id = data[0], data[1], data[2], data[3], int(data[4])
        
        if tipo == "M": # Seleção de Modelo sugerido
            if serv != "none":
                # Já temos o serviço, agora verifica variações
                vars = self.obter_variacoes(mod, serv)
                if vars:
                    keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"V|{mod}|{serv}|{v}|{u_msg_id}")] for v in vars]
                    await query.edit_message_text(text=f"Qual tipo de {serv} você precisa para o {mod.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    resp = self.buscar_preco(mod, serv)
                    await query.edit_message_text(text=resp)
                    self.agendar_limpeza(context, query.message.chat_id, [u_msg_id, query.message.message_id])
            else:
                # Não temos o serviço, pergunta agora
                servicos_m = self.tabela[self.tabela["Modelo"] == mod]["Servico"].unique().tolist()
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"S|{mod}|{s}|initial|{u_msg_id}")] for s in servicos_m]
                await query.edit_message_text(text=f"Qual serviço você precisa para o {mod.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))

        elif tipo == "S": # Seleção de Serviço
            vars = self.obter_variacoes(mod, serv)
            if vars:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"V|{mod}|{serv}|{v}|{u_msg_id}")] for v in vars]
                await query.edit_message_text(text=f"Qual tipo de {serv} você precisa para o {mod.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                resp = self.buscar_preco(mod, serv)
                await query.edit_message_text(text=resp)
                self.agendar_limpeza(context, query.message.chat_id, [u_msg_id, query.message.message_id])

        elif tipo == "V": # Seleção de Variação (Aro/Qualidade)
            resp = self.buscar_preco(mod, serv, extra)
            await query.edit_message_text(text=resp)
            self.agendar_limpeza(context, query.message.chat_id, [u_msg_id, query.message.message_id])

    def run(self):
        application = ApplicationBuilder().token(self.token).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.responder_message))
        application.add_handler(CallbackQueryHandler(self.button_handler))
        logger.info("Bot rodando com Busca Inteligente v6! 🚀")
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("ERRO: TOKEN não definido.")
        exit(1)
    bot = BudgetBot(TOKEN)
    bot.run()
