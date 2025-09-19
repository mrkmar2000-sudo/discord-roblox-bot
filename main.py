import os
import discord
import aiohttp
import asyncio
import json
import random
import string
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- Load Environment Variables ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
ROBLOX_COOKIE = os.getenv("ROBLOX_COOKIE")
WEBHOOK_URL = os.getenv("RANKING_WEBHOOK")
GROUP_ID = int(os.getenv("GROUP_ID", "15008550"))
ALLOWED_ROLE_IDS = [int(rid) for rid in os.getenv("ALLOWED_ROLE_IDS", "1332732346272841822, 1332732347333869620").split(",")]

# --- Persistent Files ---
RANK_BINDS_FILE = "rank_binds.json"
if os.path.exists(RANK_BINDS_FILE):
    with open(RANK_BINDS_FILE, "r") as f:
        rank_binds = json.load(f)
else:
    rank_binds = {}  # {"255": [role_id1, role_id2]}

VERIFIED_USERS_FILE = "verified_users.json"
if os.path.exists(VERIFIED_USERS_FILE):
    with open(VERIFIED_USERS_FILE, "r") as f:
        verified_users = json.load(f)
else:
    verified_users = {}

async def save_rank_binds():
    with open(RANK_BINDS_FILE, "w") as f:
        json.dump(rank_binds, f, indent=2)

async def save_verified_users():
    with open(VERIFIED_USERS_FILE, "w") as f:
        json.dump(verified_users, f, indent=2)

# --- Discord Setup ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

group_roles_cache = {}
bot_highest_rank = None

# --- Helper Functions ---
async def fetch_group_roles():
    global group_roles_cache
    url = f"https://groups.roblox.com/v1/groups/{GROUP_ID}/roles"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    group_roles_cache = {
                        role["name"].lower(): {"id": role["id"], "rank": role["rank"]}
                        for role in data["roles"]
                    }
                    print(f"✅ Loaded {len(group_roles_cache)} roles from group {GROUP_ID}")
                else:
                    print(f"❌ Failed to fetch group roles (Status: {resp.status}) - Check if GROUP_ID {GROUP_ID} is correct")
    except Exception as e:
        print(f"❌ Error fetching group roles: {e}")

async def test_roblox_authentication():
    """Test if Roblox authentication is working"""
    if not ROBLOX_COOKIE:
        print("❌ ROBLOX_COOKIE not found in environment variables")
        return False
    
    url = "https://users.roblox.com/v1/users/authenticated"
    headers = {"Cookie": f".ROBLOSECURITY={ROBLOX_COOKIE}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = data.get("name", "Unknown")
                    user_id = data.get("id", "Unknown")
                    print(f"✅ Successfully logged into Roblox as: {username} (ID: {user_id})")
                    return True
                else:
                    print(f"❌ Roblox authentication failed (Status: {resp.status})")
                    return False
    except Exception as e:
        print(f"❌ Error testing Roblox authentication: {e}")
        return False

async def fetch_bot_rank():
    global bot_highest_rank
    # First get the authenticated user's ID
    try:
        url = "https://users.roblox.com/v1/users/authenticated"
        headers = {"Cookie": f".ROBLOSECURITY={ROBLOX_COOKIE}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print("❌ Could not get authenticated user info")
                    return
                user_data = await resp.json()
                bot_user_id = user_data["id"]
                
            # Now get the user's groups using their ID
            url = f"https://groups.roblox.com/v2/users/{bot_user_id}/groups/roles"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for group in data.get("data", []):
                        if group["group"]["id"] == GROUP_ID:
                            bot_highest_rank = group["role"]["rank"]
                            rank_name = group["role"]["name"]
                            group_name = group["group"]["name"]
                            print(f"✅ Found bot's rank in group '{group_name}': {rank_name} (Rank {bot_highest_rank})")
                            break
                    if bot_highest_rank is None:
                        print(f"❌ Bot is not in group {GROUP_ID}")
                else:
                    error_text = await resp.text()
                    print(f"❌ Failed to fetch bot's group roles (Status: {resp.status})")
                    print(f"   Response: {error_text[:200]}...")
    except Exception as e:
        print(f"❌ Error fetching bot rank: {e}")

async def change_rank(user_id: int, new_role_id: int):
    url = f"https://groups.roblox.com/v1/groups/{GROUP_ID}/users/{user_id}"
    headers = {"Cookie": f".ROBLOSECURITY={ROBLOX_COOKIE}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json={"roleId": new_role_id}, headers=headers) as resp:
            return resp.status == 200

async def get_user_group_role(user_id: int):
    url = f"https://groups.roblox.com/v2/users/{user_id}/groups/roles"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for group in data["data"]:
                    if group["group"]["id"] == GROUP_ID:
                        return group["role"]["rank"], group["role"]["name"]
    return None, None

async def fetch_roblox_bio(user_id: int):
    url = f"https://users.roblox.com/v1/users/{user_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("description", "")
    return ""

async def send_webhook_log(embed: discord.Embed):
    if WEBHOOK_URL:
        async with aiohttp.ClientSession() as session:
            await session.post(WEBHOOK_URL, json={"embeds": [embed.to_dict()]})

def is_staff(user: discord.Member) -> bool:
    return any(role.id in ALLOWED_ROLE_IDS for role in user.roles)

def get_assignable_roles():
    if bot_highest_rank is None:
        return group_roles_cache
    return {name: info for name, info in group_roles_cache.items() if info["rank"] < bot_highest_rank}

# --- Events ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("🔄 Testing Roblox authentication...")
    auth_success = await test_roblox_authentication()
    if auth_success:
        print("🔄 Fetching group information...")
        await fetch_group_roles()
        await fetch_bot_rank()
    else:
        print("⚠️ Roblox authentication failed - some commands may not work")
    try:
        await bot.tree.sync()
        print("✅ Synced slash commands.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

# --- Verify Commands ---
@bot.tree.command(name="verify", description="Verify your Roblox account.")
@app_commands.describe(username="Your Roblox username")
async def verify(interaction: discord.Interaction, username: str):
    await interaction.response.defer(ephemeral=True)
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": True}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                await interaction.followup.send("❌ API request failed.")
                return
            data = await resp.json()
            if not data.get("data") or len(data["data"]) == 0:
                await interaction.followup.send("❌ User not found.")
                return
            roblox_id = data["data"][0]["id"]
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            verified_users[str(interaction.user.id)] = {"roblox_id": roblox_id, "pending_code": code}
            await save_verified_users()
            await interaction.followup.send(f"🔗 Please put `{code}` in your Roblox bio, then run `/verifyconfirm`.")

@bot.tree.command(name="verifyconfirm", description="Confirm your Roblox verification.")
async def verifyconfirm(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    record = verified_users.get(str(interaction.user.id))
    if not record or "pending_code" not in record:
        await interaction.followup.send("❌ No pending verification found.")
        return
    bio = await fetch_roblox_bio(record["roblox_id"])
    if record["pending_code"] in bio:
        record.pop("pending_code")
        verified_users[str(interaction.user.id)] = record
        await save_verified_users()
        await interaction.followup.send("✅ Successfully verified!")
    else:
        await interaction.followup.send("❌ Code not found in bio. Please try again.")

# --- Rankbinds Command (Multi-role + Autocomplete) ---
@bot.tree.command(name="rankbinds", description="Manage Roblox rank → Discord role bindings.")
@app_commands.describe(action="Choose add/remove/list", rank="Roblox rank number", role="Discord role")
async def rankbinds(interaction: discord.Interaction, action: str, rank: int | None = None, role: discord.Role | None = None):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    if action == "list":
        if not rank_binds:
            await interaction.followup.send("📋 No rank binds have been set.")
            return
        embed = discord.Embed(title="📋 Current Rank Binds", color=0x3498db)
        for r, roles in rank_binds.items():
            mentions = ", ".join([f"<@&{rid}>" for rid in roles])
            embed.add_field(name=f"Rank {r}", value=mentions, inline=False)
        await interaction.followup.send(embed=embed)

    elif action == "add":
        if rank is None or role is None:
            await interaction.followup.send("❌ Provide both rank and role.")
            return
        roles_for_rank = rank_binds.get(str(rank), [])
        if role.id not in roles_for_rank:
            roles_for_rank.append(role.id)
            rank_binds[str(rank)] = roles_for_rank
            await save_rank_binds()
            await interaction.followup.send(f"✅ Added {role.mention} to rank {rank}.")
        else:
            await interaction.followup.send(f"⚠️ {role.mention} is already bound to rank {rank}.")

    elif action == "remove":
        if rank is None:
            await interaction.followup.send("❌ Provide a rank.")
            return
        if str(rank) not in rank_binds:
            await interaction.followup.send(f"❌ No bind found for rank {rank}.")
            return
        if role:
            if role.id in rank_binds[str(rank)]:
                rank_binds[str(rank)].remove(role.id)
                if not rank_binds[str(rank)]:
                    del rank_binds[str(rank)]
                await save_rank_binds()
                await interaction.followup.send(f"🗑️ Removed {role.mention} from rank {rank}.")
            else:
                await interaction.followup.send(f"⚠️ {role.mention} is not bound to rank {rank}.")
        else:
            removed_roles = rank_binds.pop(str(rank))
            await save_rank_binds()
            await interaction.followup.send(f"🗑️ Removed all roles from rank {rank}.")

@rankbinds.autocomplete("rank")
async def rankbinds_autocomplete(interaction: discord.Interaction, current: str):
    if not group_roles_cache:
        await fetch_group_roles()
    results = []
    for role in group_roles_cache.values():
        if current in str(role["rank"]):
            results.append(app_commands.Choice(name=f"{role['rank']} – {role['id']}", value=role["rank"]))
    return results[:25]

# --- Sync Roles Command ---
@bot.tree.command(name="syncroles", description="Sync your Discord roles with your Roblox group rank.")
async def syncroles(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    record = verified_users.get(str(interaction.user.id))
    if not record or record.get("pending_code"):
        await interaction.followup.send("❌ You must verify first using `/verify`.")
        return

    rank_number, rank_name = await get_user_group_role(record["roblox_id"])
    if not rank_number:
        await interaction.followup.send("❌ You are not in the Roblox group.")
        return

    added_roles, removed_roles = [], []
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.followup.send("❌ This command can only be used in a server.")
        return
        
    for r_rank, discord_roles in rank_binds.items():
        for discord_role_id in discord_roles:
            discord_role = interaction.guild.get_role(discord_role_id)
            if not discord_role:
                continue
            if int(r_rank) == rank_number:
                if discord_role not in interaction.user.roles:
                    await interaction.user.add_roles(discord_role)
                    added_roles.append(discord_role.name)
            else:
                if discord_role in interaction.user.roles:
                    await interaction.user.remove_roles(discord_role)
                    removed_roles.append(discord_role.name)

    msg = f"✅ Synced roles for **{rank_name}**\n"
    if added_roles:
        msg += f"➕ Added: {', '.join(added_roles)}\n"
    if removed_roles:
        msg += f"➖ Removed: {', '.join(removed_roles)}"
    await interaction.followup.send(msg or "✅ No changes needed.")

# --- Simulation Command with User Option + Logging ---
@bot.tree.command(name="simulatebind", description="Preview what roles would be assigned for a specific rank.")
@app_commands.describe(rank="Roblox rank number", user="Optional Discord user to simulate adds/removals")
async def simulatebind(interaction: discord.Interaction, rank: int, user: discord.Member | None = None):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    if not interaction.guild:
        await interaction.followup.send("❌ This command can only be used in a server.")
        return

    roles_for_rank = rank_binds.get(str(rank))
    if not roles_for_rank:
        await interaction.followup.send(f"ℹ️ No roles bound to rank **{rank}**.")
        return

    role_mentions = [f"<@&{role_id}>" for role_id in roles_for_rank]
    embed = discord.Embed(title=f"🔍 Simulation for Rank {rank}", color=0x2ecc71)
    embed.add_field(name="Bound Roles", value=", ".join(role_mentions), inline=False)

    if user:
        added, removed = [], []
        for role_id in roles_for_rank:
            discord_role = interaction.guild.get_role(role_id)
            if discord_role and discord_role not in user.roles:
                added.append(discord_role.mention)

        for other_rank, other_roles in rank_binds.items():
            if other_rank == str(rank):
                continue
            for role_id in other_roles:
                discord_role = interaction.guild.get_role(role_id)
                if discord_role and discord_role in user.roles:
                    removed.append(discord_role.mention)

        if added or removed:
            embed.add_field(name="Changes", value="\n".join([
                f"➕ Would Add: {', '.join(added)}" if added else "",
                f"➖ Would Remove: {', '.join(removed)}" if removed else ""
            ]), inline=False)
        else:
            embed.add_field(name="Changes", value="✅ No changes would be made.", inline=False)

    await interaction.followup.send(embed=embed)
    await send_webhook_log(embed)

@simulatebind.autocomplete("rank")
async def simulatebind_rank_autocomplete(interaction: discord.Interaction, current: str):
    if not group_roles_cache:
        await fetch_group_roles()
    results = []
    for role in group_roles_cache.values():
        if current in str(role["rank"]):
            results.append(app_commands.Choice(name=f"{role['rank']} – {role['id']}", value=role["rank"]))
    return results[:25]

from discord import Embed

@bot.tree.command(name="staffguide", description="Send the Roblox Rank Bot Staff Guide.")
async def staffguide(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    embed = Embed(
        title="📖 Roblox Rank Bot – Quick Staff Guide",
        description="💡 *Pin this message so staff can always find it easily!*",
        color=0x5865F2  # Discord blurple
    )

    embed.add_field(
        name="🔑 Staff-Only Commands",
        value=(
            "**1️⃣ Verify a User**\n"
            "Users must link their Roblox account before you can rank them:\n"
            "```/verify roblox_username:<username>\n"
            "/verifyconfirm code:<code>```"
        ),
        inline=False
    )

    embed.add_field(
        name="2️⃣ Rank a User",
        value=(
            "Updates their Roblox group rank **and** Discord roles:\n"
            "```/rank user:@DiscordUser rank:<roblox_rank_number>```\n"
            "✅ The bot will:\n"
            "• Change their **Roblox group rank**\n"
            "• Update their **Discord roles**\n"
            "• Log everything in the **ranking webhook channel**"
        ),
        inline=False
    )

    embed.add_field(
        name="3️⃣ Manage Rank Binds",
        value=(
            "Link or unlink Discord roles to Roblox ranks:\n"
            "```/rankbinds add rank:<roblox_rank_number> role:@Role\n"
            "/rankbinds remove rank:<roblox_rank_number> role:@Role\n"
            "/rankbinds list```\n"
            "💡 You can bind **multiple roles** to a single Roblox rank."
        ),
        inline=False
    )

    embed.add_field(
        name="4️⃣ Force Sync Roles",
        value=(
            "Re-check a user’s Roblox rank and update their roles:\n"
            "```/syncroles user:@DiscordUser```"
        ),
        inline=False
    )

    embed.add_field(
        name="5️⃣ Simulate Rank Binds",
        value=(
            "Preview what roles a rank would give — no changes applied:\n"
            "```/simulatebind rank:<roblox_rank_number>```\n"
            "Or for a specific user:\n"
            "```/simulatebind rank:<roblox_rank_number> user:@DiscordUser```\n"
            "Shows which roles would be **added** or **removed**."
        ),
        inline=False
    )

    embed.add_field(
        name="📌 Best Practices",
        value=(
            "✅ **Verify users first** before ranking\n"
            "🔍 **Use `/simulatebind`** to avoid mistakes\n"
            "🛠 **Keep rank binds updated** so Discord stays in sync\n"
            "🔒 **Never share your Roblox cookie** — it stays safe in `.env`"
        ),
        inline=False
    )

    await interaction.response.send_message(embed=embed)


# --- Entry Point ---
if __name__ == "__main__":
    bot.run(TOKEN)

