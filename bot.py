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
        self.ids_autorizados_fixos = [1129149570] 
        self.usuarios_autorizados_arquivo = self._carregar_whitelist()
        
        # Inicializa listas vazias se a tabela falhar
        if self.tabela is not None and not self.tabela.empty:
            # Ordena por tamanho do nome (maior primeiro) para busca exata ser mais precisa
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

    def interpretar_texto_ultra_flexivel(self, texto):
        """Busca ultra flexível que prioriza nomes longos mas aceita qualquer parte do nome"""
        texto = texto.lower().strip()
        
        # 1. Identifica o serviço se estiver presente no texto
        servico_enc = None
        palavras_servico = ["tela", "bateria", "conector", "vidro", "tampa", "câmera", "camera"]
        for p in palavras_servico:
            if p in texto:
                servico_enc = p
                break

        # 2. Limpa o texto para focar no modelo (remove o serviço do texto de busca)
        texto_busca_modelo = texto
        if servico_enc:
            texto_busca_modelo = texto_busca_modelo.replace(servico_enc, "").strip()

        # 3. Busca modelos que contêm o texto digitado
        # Ex: Se digitar "G22", vai encontrar "Moto G22"
        modelos_encontrados = [m for m in self.modelos_disponiveis if texto_busca_modelo in m]
        
        # 4. Se encontrou apenas um modelo, retorna ele
        if len(modelos_encontrados) == 1:
            return modelos_encontrados[0], servico_enc, []
        
        # 5. Se encontrou vários, retorna a lista para sugestão
        if len(modelos_encontrados) > 1:
            return None, servico_enc, modelos_encontrados
        
        # 6. Caso não tenha encontrado nada com o texto completo, tenta por palavras individuais (se houver mais de uma)
        palavras = texto_busca_modelo.split()
        if len(palavras) > 1:
            # Busca modelos que contêm TODAS as palavras digitadas (em qualquer ordem)
            modelos_multi = []
            for m in self.modelos_disponiveis:
                if all(palavra in m for palavra in palavras):
                    modelos_multi.append(m)
            
            if len(modelos_multi) == 1:
                return modelos_multi[0], servico_enc, []
            elif len(modelos_multi) > 1:
                return None, servico_enc, modelos_multi

        return None, servico_enc, []

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
        modelo, servico, sugestoes = self.interpretar_texto_ultra_flexivel(texto)

        # Caso 1: Modelo e Serviço encontrados
        if modelo and servico:
            vars = self.obter_variacoes(modelo, servico)
            if vars:
                keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"V|{modelo}|{servico}|{v}|{update.message.message_id}")] for v in vars]
                await update.message.reply_text(f"Qual tipo de {servico} você precisa para o {modelo.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                resp = self.buscar_preco(modelo, servico)
                sent = await update.message.reply_text(resp)
                self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent.message_id])
        
        # Caso 2: Modelo encontrado mas serviço não
        elif modelo:
            servicos_m = self.tabela[self.tabela["Modelo"] == modelo]["Servico"].unique().tolist()
            if servicos_m:
                keyboard = [[InlineKeyboardButton(s.title(), callback_data=f"S|{modelo}|{s}|initial|{update.message.message_id}")] for s in servicos_m]
                await update.message.reply_text(f"Qual serviço você precisa para o {modelo.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))

        # Caso 3: Vários modelos sugeridos por palavra-chave
        elif sugestoes:
            # Limita a 12 sugestões para não poluir o chat
            sugestoes = sorted(sugestoes)[:12]
            keyboard = [[InlineKeyboardButton(m.title(), callback_data=f"M|{m}|{servico if servico else 'none'}|initial|{update.message.message_id}")] for m in sugestoes]
            await update.message.reply_text(f"Encontrei esses modelos com sua busca. Qual você quis dizer?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Caso 4: Nada encontrado
        else:
            sent = await update.message.reply_text("❌ Não encontrei esse modelo. Tente digitar de outra forma (ex: apenas 'G22' ou 'Spark 10').")
            self.agendar_limpeza(context, update.effective_chat.id, [update.message.message_id, sent.message_id])

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id
        if not self.usuario_autorizado(user_id):
            await query.answer("❌ Sem acesso.", show_alert=True)
            return

        await query.answer()
        data = query.data.split('|')
        tipo, mod, serv, extra, u_msg_id = data[0], data[1], data[2], data[3], int(data[4])
        
        if tipo == "M": # Seleção de Modelo sugerido
            if serv != "none":
                vars = self.obter_variacoes(mod, serv)
                if vars:
                    keyboard = [[InlineKeyboardButton(v.title(), callback_data=f"V|{mod}|{serv}|{v}|{u_msg_id}")] for v in vars]
                    await query.edit_message_text(text=f"Qual tipo de {serv} você precisa para o {mod.title()}?", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    resp = self.buscar_preco(mod, serv)
                    await query.edit_message_text(text=resp)
                    self.agendar_limpeza(context, query.message.chat_id, [u_msg_id, query.message.message_id])
            else:
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
        logger.info("Bot rodando com Busca Ultra Flexível v7! 🚀")
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("ERRO: TOKEN não definido.")
        exit(1)
    bot = BudgetBot(TOKEN)
    bot.run()
