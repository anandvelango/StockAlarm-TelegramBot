import os
import logging
import httpx
import asyncio
import textwrap
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackContext, JobQueue, filters

# get stock price
async def get_price(client, url):
    response = await client.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "lxml")
    try:
        afterhours_price = float(soup.find("fin-streamer", class_="C($primaryColor) Fz(24px) Fw(b)").text.strip("$"))
        close_price = float(soup.find("fin-streamer", class_="Fw(b) Fz(36px) Mb(-4px) D(ib)").text.strip("$"))
        price_change = soup.find("fin-streamer", class_="Fw(500) Pstart(8px) Fz(24px)").findChild().text
        percentage_change = soup.find_all("fin-streamer", class_="Fw(500) Pstart(8px) Fz(24px)")[1].findChild().text

        return {"afterhours_price": afterhours_price, "close_price": close_price, "price_change": f"{price_change} {percentage_change}", "url": url}
    except AttributeError:
        logging.info(f"User CMD Input - Couldn't get the stock: {url}")

# get watchlist stock prices function
async def get_watchlist_prices(watchlist):
    async with httpx.AsyncClient() as client:
        reqs = [get_price(client, f"https://finance.yahoo.com/quote/{ticker}") for ticker in watchlist]
        prices = await asyncio.gather(*reqs)

    return prices

# telegram command - initialise the bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user
    chat_id = update.effective_chat.id
    logging.info(f"User Input - {username.first_name} {username.last_name} ({chat_id}): '/start'")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Welcome to Anand's Stock Bot. Type /help for more info")
    user_data = {
        update.effective_chat.id: {
            "watchlist": [],
            "upper_limits": [],
            "lower_limits": []
        }
    }
    users.update(user_data)

# telegram command - help menu
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user
    chat_id = update.effective_chat.id
    logging.info(f"User Input - {username.first_name} {username.last_name} ({chat_id}): '/help'")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="""
    Commands:
    • /help - help menu
    • /check_watchlist - get the current prices of the stocks in your watchlist
    • /check_price <ticker> - get the price of any stock - usage e.g. (/check_price tsla)        
    • /add_to_watchlist <ticker> <upper limit> <lower limit> - add ticker, upper and lower limit - usage e.g. (/add_to_watchlist tsla 280 210)
    • /remove_from_watchlist <ticker> - remove ticker, upper and lower limit from the watchlist - usage e.g. (/remove_from_watchlist tsla)
    """)

# telegram command - get price of any stock
async def check_price(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    username = update.effective_user
    chat_id = update.effective_chat.id
    ticker = "".join(context.args)
    logging.info(f"User Input - {username.first_name} {username.last_name} ({chat_id}): '/check_price {ticker}'")
    async with httpx.AsyncClient() as client:   
        price = await get_price(client, f"https://finance.yahoo.com/quote/{ticker}")
    if price == None:
        await context.bot.send_message(chat_id=chat_id, text=f"{ticker} : Not a valid ticker")
    else:
        close_price = price["close_price"]
        price_change  = price["price_change"]
        url = price["url"]
        message = textwrap.dedent(f"""
        {ticker}
        =========
        Price: ${close_price}
        Day change: {price_change}
        More info at:
        {url}
        """)
        await context.bot.send_message(chat_id=chat_id, text=message)

# telegram command - add stock, upper & lower limit to watchlist
async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args
    
    try: 
        async with httpx.AsyncClient() as client:
            price = await get_price(client, f"https://finance.yahoo.com/quote/{args[0]}")
        if price == None:
            await context.bot.send_message(chat_id=chat_id, text=f"Not a valid ticker: {args[0]}")
        else:
            for user in users: 
                if user == chat_id:
                    users[user]["watchlist"].append(args[0])
                    users[user]["upper_limits"].append(int(args[1]))
                    users[user]["lower_limits"].append(int(args[2]))

            await context.bot.send_message(
                chat_id=chat_id,
                text=textwrap.dedent(f"""
                Added:
                - Ticker: {args[0]}
                - Upper limit: {args[1]}
                - Lower limit: {args[2]}
                """)
            )
            
        logging.info(f"User Input - {username.first_name} {username.last_name} ({chat_id}): /add_to_watchlist {args[0]} {args[1]} {args[2]}")
    except (AttributeError, IndexError):
        await context.bot.send_message(chat_id=chat_id, text=f"Error in adding to watchlist: {args[0]}")

# telegram command - check the stock prices in the watchlist
async def check_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user
    chat_id = update.effective_chat.id
    logging.info(f"User Input - {username.first_name} {username.last_name} ({chat_id}): '/check_watchlist'")
    watchlist = users[chat_id]["watchlist"]
    if chat_id in users and watchlist:
        prices = await get_watchlist_prices(watchlist)
        for i, ticker in enumerate(watchlist): 
            close_price = prices[i]["close_price"]
            price_change  = prices[i]["price_change"]
            url = prices[i]["url"]
            message = textwrap.dedent(f"""
            {ticker}
            =========
            Price: ${close_price}
            Day change: {price_change}
            More info at:
            {url}
            """)

            await context.bot.send_message(chat_id=chat_id, text=message)
    else:
        await context.bot.send_message(chat_id=chat_id, text="Watchlist is empty. Check /help on how to start adding stocks to watchlist.")

# telegram command - remove stock from watchlist
async def remove_from_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user
    chat_id = update.effective_chat.id
    ticker = "".join(context.args)

    try:
        for user in users:
            if user == chat_id:
                index = users[user]["watchlist"].index(ticker)
                users[user]["watchlist"].remove(ticker)
                users[user]["upper_limits"].pop(index)
                users[user]["lower_limits"].pop(index)
        
        logging.info(f"User Input - {username.first_name} {username.last_name} ({chat_id}): '/remove_from_watchlist {ticker}'")
        await context.bot.send_message(chat_id=chat_id, text=f"Removed {ticker} from watchlist")
    except ValueError:
        await context.bot.send_message(chat_id=chat_id, text=f"Unable to remove: {ticker} not found in watchlist")

# telegram notify user when price exceeds lower/upper limit
async def notify_price(context: CallbackContext):            
    for chat_id, user_data in users.items():
        if user_data.get("watchlist"):
            prices = await get_watchlist_prices(user_data["watchlist"])
            for i, ticker in enumerate(user_data["watchlist"]):
                price = prices[i]["close_price"]
                if price >= user_data["upper_limits"][i]:
                    await context.bot.send_message(chat_id=chat_id, text=f"[!] YOU MAY WANT TO SELL | {ticker} is at {price} | MORE INFO AT: https://finance.yahoo.com/quote/{ticker}")
                    logging.info(f"[!] YOU MAY WANT TO SELL | {ticker} is at {price} | MORE INFO AT: https://finance.yahoo.com/quote/{ticker}")
                
                if price <= user_data["lower_limits"][i]:
                    await context.bot.send_message(chat_id=chat_id, text=f"[!] YOU MAY WANT TO BUY | {ticker} is at {price} | MORE INFO AT: https://finance.yahoo.com/quote/{ticker}")
                    logging.info(f"[!] YOU MAY WANT TO BUY | {ticker} is at {price} | MORE INFO AT: https://finance.yahoo.com/quote/{ticker}")      

# telegram log user messages & input
async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user
    chat_id = update.effective_chat.id
    logging.info(f"User Input - {username.first_name} {username.last_name} ({chat_id}): '{update.message.text}'")

if __name__ == "__main__":
    logging.basicConfig(format="[%(asctime)s] %(message)s", datefmt="%d-%b-%y %H:%M:%S", level=logging.INFO)

    TOKEN = os.environ.get("B_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    headers = {"user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"}
    users = {}

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("check_watchlist", check_watchlist))
    app.add_handler(CommandHandler("check_price", check_price))
    app.add_handler(CommandHandler("add_to_watchlist", add_to_watchlist))
    app.add_handler(CommandHandler("remove_from_watchlist", remove_from_watchlist))
    app.add_handler(MessageHandler(filters.TEXT, log_message))

    jq: JobQueue = app.job_queue
    jq.run_repeating(notify_price, interval=10, first=0)    
    
    logging.info("Initialising bot...\n")
    app.run_polling()