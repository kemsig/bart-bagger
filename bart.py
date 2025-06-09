from bs4 import BeautifulSoup
import argparse
import discord
from discord.ext import tasks
import cloudscraper

# ——— Configuration ———
DEFAULT_DISCORD_TOKEN = "yourtoken" # replace with your bot token
DEFAULT_CHANNEL_ID   = 696969696969 # replace with your channel ID
DEFAULT_URL          = "https://us.jellycat.com/bartholomew-bear-junior/" # replace with your product URL
CHECK_INTERVAL       = 12     # seconds between stock checks 
SPAM_INTERVAL        = 6      # seconds between pings once in stock
STATUS_INTERVAL_HRS  = 3      # hours between automatic status reports


# ——— Bot Setup ———
intents = discord.Intents.default()
intents.messages = True
client = discord.Client(intents=intents)
# create an app_commands tree for slash commands
tree = discord.app_commands.CommandTree(client)

# Flags and counters
_spamming = False
request_count = 0     # number of times we’ve checked the website
issue_count   = 0     # number of unexpected errors

# cloudscraper to handle JS-based protections
scraper = cloudscraper.create_scraper(
    browser={'custom': 'StockCheckerBot/1.0'}
)

def check_stock_in_wrapper(url: str) -> bool:
    global request_count, issue_count
    request_count += 1

    # ←— core logic untouched
    r = scraper.get(url)
    if r.status_code != 200:
        print(f"⚠️ Unexpected status code {r.status_code}", flush=True)
        issue_count += 1
        return False

    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.find("div", id="add-to-cart-wrapper")
    if not container:
        print("⚠️ Could not find 'add-to-cart-wrapper' div.", flush=True)
        issue_count += 1
        return False

    inner_html = str(container).lower()
    if "form-action-addtocart" in inner_html and "out of stock" in inner_html:
        print("❌ Out of stock.", flush=True)
        return False
    elif "form-action-addtocart" in inner_html or "add to bag" in inner_html:
        print("✅ Item likely IN STOCK!", flush=True)
        return True
    elif "coming soon" in inner_html:
        print("❌ Still Coming Soon.", flush=True)
        return False
    else:
        print("❓ Unknown stock status.", flush=True)
        issue_count += 1
        return False


@tasks.loop(seconds=CHECK_INTERVAL)
async def stock_check_loop():
    global _spamming
    channel = client.get_channel(stock_check_loop.channel_id)
    if channel is None:
        print(f"⚠️ Channel {stock_check_loop.channel_id} not found.", flush=True)
        global issue_count
        issue_count += 1
        return

    print(f"Checking stock for {stock_check_loop.url}", flush=True)
    if not _spamming and check_stock_in_wrapper(stock_check_loop.url):
        _spamming = True
        print("🔔 Starting spam routine!", flush=True)
        spam_ping_loop.start(channel)

@tasks.loop(seconds=SPAM_INTERVAL)
async def spam_ping_loop(channel: discord.TextChannel):
    global issue_count
    try:
        await channel.send(f"{stock_check_loop.url} is now in stock! @everyone")
    except Exception as e:
        print(f"Error sending spam: {e}", flush=True)
        issue_count += 1

@tasks.loop(hours=STATUS_INTERVAL_HRS)
async def status_report_loop():
    channel = client.get_channel(status_report_loop.channel_id)
    if channel:
        status_msg = (
            f"**Status Report**\n"
            f"• URL checks: {request_count}\n"
            f"• Spamming active: {_spamming}\n"
            f"• Total issues encountered: {issue_count}"
        )
        await channel.send(status_msg)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})", flush=True)
    # start our loops
    stock_check_loop.start()
    status_report_loop.start()
    # register slash commands with Discord
    await tree.sync()
    print("Slash commands synced.", flush=True)


# ——— Slash Commands ———
@tree.command(name="stop", description="Shut down the bot (owner only).")
async def stop(interaction: discord.Interaction):

    await interaction.response.send_message("🛑 Bot is shutting down…")
    await client.close()

@tree.command(name="status", description="Get a status report right now.")
async def status(interaction: discord.Interaction):
    status_msg = (
        f"**Status Report**\n"
        f"• URL checks: {request_count}\n"
        f"• Spamming active: {_spamming}\n"
        f"• Total issues encountered: {issue_count}"
    )
    await interaction.response.send_message(status_msg)


def main():
    parser = argparse.ArgumentParser("Stock Checker + Discord Notifier")
    parser.add_argument("--token",      default=DEFAULT_DISCORD_TOKEN)
    parser.add_argument("--channel_id", type=int, default=DEFAULT_CHANNEL_ID)
    parser.add_argument("--url",        default=DEFAULT_URL)
    parser.add_argument("--check-interval", type=int, default=CHECK_INTERVAL, help="Seconds between stock checks")
    args = parser.parse_args()

    # stash args onto our loops
    stock_check_loop.url           = args.url
    stock_check_loop.channel_id    = args.channel_id
    status_report_loop.channel_id  = args.channel_id
    stock_check_loop.change_interval(seconds=args.check_interval)

    client.run(args.token)

if __name__ == "__main__":
    main()
