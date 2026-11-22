DAVIDUSHKA GO deployment starter
1) Create a public or private GitHub repository.
2) Upload bot.py, requirements.txt and Procfile.
3) In Railway connect the GitHub repository as a service.
4) Railway service -> Variables: BOT_TOKEN (from BotFather), ADMIN_ID=1805645783.
5) Deploy. Open Telegram bot and test /start and /neworder.
Admin commands: /assign ORDER_ID COURIER_TELEGRAM_ID; /cancel ORDER_ID.
Courier must start the bot before dispatcher can send messages to them.
This starter uses SQLite; add a persistent volume before relying on long-term order history.
