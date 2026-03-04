#!/usr/bin/env python3
"""
Republic AI — Mining Leaderboard Discord Bot
=============================================
Tracks on-chain compute jobs and ranks miners
in the #mining-leaderboard channel.

Setup:
1. pip install discord.py requests
2. Set DISCORD_TOKEN and CHANNEL_ID below
3. python3 republic_mining_bot.py
"""

import os
import json
import time
import logging
import asyncio
import requests
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone

# ═══════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_TOKEN_HERE")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # #mining-leaderboard channel ID

RPC_URL = os.getenv("RPC_URL", "http://localhost:26657")
REST_URL = os.getenv("REST_URL", "http://localhost:1317")

# ═══════════════════════════════════
# BOT SETUP
# ═══════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

last_block = 0
last_message_id = None
cached_validators = {}
cache_time = 0


# ═══════════════════════════════════
# DATA FETCHERS
# ═══════════════════════════════════

def api_get(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"API error {url}: {e}")
        return None


def get_current_block():
    data = api_get(f"{RPC_URL}/status")
    if data:
        return int(data.get("result", {}).get("sync_info", {}).get("latest_block_height", "0"))
    return 0


def get_all_jobs():
    """Fetch all compute jobs from chain"""
    data = api_get(f"{REST_URL}/republic/computevalidation/jobs")
    if data:
        return data.get("jobs", [])

    # Fallback: try CLI-style REST endpoint
    data = api_get(f"{REST_URL}/republic.computevalidation.Query/ListJob")
    if data:
        return data.get("jobs", [])

    # Fallback: gRPC gateway
    data = api_get(f"{REST_URL}/cosmos/computevalidation/v1/jobs")
    if data:
        return data.get("jobs", [])

    return []


def get_validator_moniker(operator_address):
    """Get validator moniker from operator address"""
    global cached_validators, cache_time

    if time.time() - cache_time > 300:
        cached_validators = {}
        cache_time = time.time()
        for status in ["BOND_STATUS_BONDED", "BOND_STATUS_UNBONDING", "BOND_STATUS_UNBONDED"]:
            data = api_get(f"{REST_URL}/cosmos/staking/v1beta1/validators?status={status}&pagination.limit=300")
            if data:
                for v in data.get("validators", []):
                    op = v.get("operator_address", "")
                    moniker = v.get("description", {}).get("moniker", "")
                    cached_validators[op] = moniker

    return cached_validators.get(operator_address, operator_address[:20] + "...")


def build_leaderboard():
    """Build mining leaderboard from compute jobs"""
    jobs = get_all_jobs()
    block = get_current_block()

    if not jobs:
        return None, block

    # Count jobs per validator
    job_counts = {}
    completed_counts = {}
    for job in jobs:
        validator = job.get("target_validator", "")
        status = job.get("status", "")

        if validator not in job_counts:
            job_counts[validator] = 0
            completed_counts[validator] = 0

        job_counts[validator] += 1
        if status in ["Completed", "Verified"]:
            completed_counts[validator] += 1

    # Sort by total jobs (descending)
    sorted_miners = sorted(job_counts.items(), key=lambda x: -x[1])

    return sorted_miners, block


def format_leaderboard_embed(sorted_miners, block):
    """Create a beautiful Discord embed for the leaderboard"""
    embed = discord.Embed(
        title="⛏️  Republic AI — Mining Leaderboard",
        color=0x00D4AA,
        timestamp=datetime.now(timezone.utc),
    )

    embed.set_footer(text=f"📦 Block: {block:,}  |  ⛏️ Total Jobs: {sum(c for _, c in sorted_miners)}")

    if not sorted_miners:
        embed.description = "No compute jobs found yet."
        return embed

    # Build leaderboard text
    medals = ["🥇", "🥈", "🥉"]
    lines = []

    for i, (validator, count) in enumerate(sorted_miners[:25], 1):
        moniker = get_validator_moniker(validator)

        if i <= 3:
            icon = medals[i - 1]
        elif i <= 10:
            icon = "🔷"
        else:
            icon = "▫️"

        # Progress bar
        max_jobs = sorted_miners[0][1] if sorted_miners else 1
        bar_len = int((count / max_jobs) * 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)

        lines.append(f"{icon} **#{i}** {moniker}\n╰ `{bar}` **{count}** jobs")

    embed.description = "\n".join(lines)

    if len(sorted_miners) > 25:
        embed.description += f"\n\n*... +{len(sorted_miners) - 25} more miners*"

    return embed


def format_miner_embed(validator, jobs_list, rank, total_miners, block):
    """Create embed for individual miner info"""
    moniker = get_validator_moniker(validator)

    total_jobs = len(jobs_list)
    completed = sum(1 for j in jobs_list if j.get("status") in ["Completed", "Verified"])
    pending = sum(1 for j in jobs_list if j.get("status") == "PendingExecution")

    embed = discord.Embed(
        title=f"⛏️  Miner: {moniker}",
        color=0x00D4AA,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="🏆 Rank", value=f"#{rank} / {total_miners}", inline=True)
    embed.add_field(name="⛏️ Total Jobs", value=str(total_jobs), inline=True)
    embed.add_field(name="✅ Completed", value=str(completed), inline=True)
    embed.add_field(name="⏳ Pending", value=str(pending), inline=True)
    embed.add_field(name="📋 Address", value=f"`{validator}`", inline=False)
    embed.set_footer(text=f"📦 Block: {block:,}")

    return embed


# ═══════════════════════════════════
# DISCORD EVENTS & COMMANDS
# ═══════════════════════════════════

@bot.event
async def on_ready():
    logging.info(f"Bot connected as {bot.user}")
    if not update_leaderboard.is_running():
        update_leaderboard.start()


@bot.command(name="leaderboard", aliases=["lb", "ranking"])
async def cmd_leaderboard(ctx):
    """Show the current mining leaderboard"""
    sorted_miners, block = build_leaderboard()
    if sorted_miners is None:
        await ctx.send("❌ Could not fetch compute jobs. Is the node running?")
        return
    embed = format_leaderboard_embed(sorted_miners, block)
    await ctx.send(embed=embed)


@bot.command(name="miner")
async def cmd_miner(ctx, query: str = None):
    """Show info for a specific miner. Usage: !miner <name or address>"""
    if not query:
        await ctx.send("Usage: `!miner <validator name or address>`")
        return

    jobs = get_all_jobs()
    block = get_current_block()

    if not jobs:
        await ctx.send("❌ Could not fetch compute jobs.")
        return

    # Count jobs per validator
    job_map = {}
    for job in jobs:
        v = job.get("target_validator", "")
        if v not in job_map:
            job_map[v] = []
        job_map[v].append(job)

    # Sort for ranking
    sorted_miners = sorted(job_map.items(), key=lambda x: -len(x[1]))

    # Find validator
    query_lower = query.lower()
    found = None
    found_rank = 0

    for i, (validator, validator_jobs) in enumerate(sorted_miners, 1):
        moniker = get_validator_moniker(validator)
        if query_lower in moniker.lower() or query_lower in validator.lower():
            found = validator
            found_rank = i
            break

    if not found:
        await ctx.send(f"❌ Miner `{query}` not found.")
        return

    embed = format_miner_embed(found, job_map[found], found_rank, len(sorted_miners), block)
    await ctx.send(embed=embed)


@bot.command(name="stats")
async def cmd_stats(ctx):
    """Show network mining stats"""
    jobs = get_all_jobs()
    block = get_current_block()

    if not jobs:
        await ctx.send("❌ Could not fetch compute jobs.")
        return

    total = len(jobs)
    completed = sum(1 for j in jobs if j.get("status") in ["Completed", "Verified"])
    pending = sum(1 for j in jobs if j.get("status") == "PendingExecution")
    miners = len(set(j.get("target_validator", "") for j in jobs))
    creators = len(set(j.get("creator", "") for j in jobs))

    embed = discord.Embed(
        title="📊  Republic AI — Mining Stats",
        color=0x00D4AA,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="⛏️ Total Jobs", value=str(total), inline=True)
    embed.add_field(name="✅ Completed", value=str(completed), inline=True)
    embed.add_field(name="⏳ Pending", value=str(pending), inline=True)
    embed.add_field(name="👷 Miners", value=str(miners), inline=True)
    embed.add_field(name="📤 Job Creators", value=str(creators), inline=True)
    embed.add_field(name="📦 Block", value=f"{block:,}", inline=True)
    embed.set_footer(text="Republic AI Testnet")

    await ctx.send(embed=embed)


@bot.command(name="help_mining")
async def cmd_help_mining(ctx):
    """Show bot commands"""
    embed = discord.Embed(
        title="⛏️  Republic Mining Leaderboard — Help",
        color=0x00D4AA,
    )

    embed.description = (
        "**Commands:**\n\n"
        "`!leaderboard` — Show mining leaderboard\n"
        "`!lb` — Short for leaderboard\n"
        "`!miner <name>` — Show specific miner info\n"
        "`!stats` — Network mining statistics\n"
        "`!help_mining` — Show this message\n\n"
        "**Auto-update:**\n"
        "The leaderboard updates automatically every new block "
        "in the designated channel."
    )

    await ctx.send(embed=embed)


# ═══════════════════════════════════
# AUTO-UPDATE LEADERBOARD EVERY BLOCK
# ═══════════════════════════════════

@tasks.loop(seconds=6)
async def update_leaderboard():
    """Check for new blocks and update leaderboard"""
    global last_block, last_message_id

    if CHANNEL_ID == 0:
        return

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    current_block = get_current_block()

    if current_block <= last_block:
        return

    last_block = current_block

    sorted_miners, block = build_leaderboard()
    if sorted_miners is None:
        return

    embed = format_leaderboard_embed(sorted_miners, block)

    try:
        # Edit existing message instead of spamming
        if last_message_id:
            try:
                msg = await channel.fetch_message(last_message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                last_message_id = None

        # Send new message
        msg = await channel.send(embed=embed)
        last_message_id = msg.id

    except Exception as e:
        logging.error(f"Error updating leaderboard: {e}")


@update_leaderboard.before_loop
async def before_update():
    await bot.wait_until_ready()


# ═══════════════════════════════════
# MAIN
# ═══════════════════════════════════

def main():
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    if DISCORD_TOKEN == "YOUR_DISCORD_TOKEN_HERE":
        print("=" * 50)
        print("  Republic Mining Leaderboard Bot")
        print("=" * 50)
        print()
        print("  Setup:")
        print("  1. Set DISCORD_TOKEN env variable or edit this file")
        print("  2. Set CHANNEL_ID for #mining-leaderboard")
        print("  3. pip install discord.py requests")
        print("  4. python3 republic_mining_bot.py")
        print()
        print("  Environment variables:")
        print("    DISCORD_TOKEN  - Discord bot token")
        print("    CHANNEL_ID     - Channel ID for auto-updates")
        print("    RPC_URL        - Node RPC (default: http://localhost:26657)")
        print("    REST_URL       - Node REST (default: http://localhost:1317)")
        print()
        print("=" * 50)
        return

    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
