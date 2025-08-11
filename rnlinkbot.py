import asyncio, logging, re, requests
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes, InlineQueryHandler
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, MessageEntity
from urllib.parse import unquote, urljoin, urlparse, parse_qs
from uuid import uuid4

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a xhsfeedbot, please send me a xhs link!")

def get_redirected_url(url: str) -> str:
    return unquote(requests.get(url).url.split('redirectPath=')[-1])

def get_clean_url(url: str) -> str:
    return urljoin(url, urlparse(url).path)

async def xhslink_expander(update: Update, context: ContextTypes.DEFAULT_TYPE):
    urls = re.findall(r"(https?://\S+)", update.message.text)
    if len(urls) > 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=get_clean_url(get_redirected_url(urls[0])))
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"No xhslink found in {update.message.text}")

async def inline_xhslink_expander(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return
    urls = re.findall(r"(https?://\S+)", query)
    if len(urls) == 0:
        return
    redirectPath = get_redirected_url(urls[0])
    parsed_url = urlparse(redirectPath)
    xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
    clean = get_clean_url(redirectPath)
    results = []
    results.append(
        InlineQueryResultArticle(
            id=str(uuid4()),
            title=f'clean url only',
            input_message_content=InputTextMessageContent(clean)
        )
    )
    results.append(
        InlineQueryResultArticle(
            id=str(uuid4()),
            title=f'clean url and with xsec_token',
            input_message_content=InputTextMessageContent(f"clean url = {clean}\nwith xsec_token = {urls[0]}?{xsec_token}")
        )
    )
    await context.bot.answer_inline_query(update.inline_query.id, results)

if __name__ == "__main__":
    application = ApplicationBuilder().token("Bot::Token").build()
    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    xhslink_expander_handler = MessageHandler(
        filters.TEXT & (
            filters.Entity(MessageEntity.URL) |
            filters.Entity(MessageEntity.TEXT_LINK)
        ),
        xhslink_expander
    )
    application.add_handler(xhslink_expander_handler)

    inline_xhslink_expander_handler = InlineQueryHandler(inline_xhslink_expander)
    application.add_handler(inline_xhslink_expander_handler)

    application.run_polling()
