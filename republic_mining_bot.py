#!/usr/bin/env python3
"""
Republic AI — Discord Bot (Final v7)
REST API for validators + CLI for compute jobs
"""

import os, json, time, logging, subprocess
import requests, discord
from discord.ext import commands, tasks
from datetime import datetime, timezone

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_TOKEN_HERE")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
REST = "https://rest.republicai.io"
RPC = "https://rpc.republicai.io"
LOCAL_RPC = os.getenv("RPC_URL", "http://localhost:26657")
NODE_URL = os.getenv("NODE_URL", "tcp://localhost:26657")
REPUBLICD = "/usr/local/bin/republicd"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

last_block = 0
last_message_id = None
user_alerts = {}
prev_statuses = {}

_val_cache = []
_val_time = 0
_job_cache = []
_job_time = 0


# ═══════════════════════════════════════════════
# CORE
# ═══════════════════════════════════════════════

def api(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"API: {e}")
        return None


def cli(args):
    try:
        r = subprocess.run(
            [REPUBLICD] + args + ["--node", NODE_URL, "--output", "json"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "HOME": "/root"}
        )
        if r.returncode == 0 and r.stdout:
            return json.loads(r.stdout)
    except Exception as e:
        logging.error(f"CLI: {e}")
    return None


def block_height():
    d = api(f"{RPC}/status")
    if d:
        return int(d.get("result", {}).get("sync_info", {}).get("latest_block_height", "0"))
    return 0


def block_time_str():
    d = api(f"{RPC}/status")
    if d:
        bt = d.get("result", {}).get("sync_info", {}).get("latest_block_time", "")
        try:
            dt = datetime.fromisoformat(bt.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            return bt
    return "N/A"


def get_vals():
    global _val_cache, _val_time
    if time.time() - _val_time < 30 and _val_cache:
        return _val_cache
    vals = []
    for s in ["BOND_STATUS_BONDED", "BOND_STATUS_UNBONDING", "BOND_STATUS_UNBONDED"]:
        d = api(f"{REST}/cosmos/staking/v1beta1/validators?status={s}&pagination.limit=300")
        if d:
            vals.extend(d.get("validators", []))
    vals.sort(key=lambda v: int(v.get("tokens", "0")), reverse=True)
    _val_cache = vals
    _val_time = time.time()
    return vals


def get_jobs():
    global _job_cache, _job_time
    if time.time() - _job_time < 20 and _job_cache:
        return _job_cache
    d = cli(["query", "computevalidation", "list-job"])
    if d:
        _job_cache = d.get("jobs", [])
        _job_time = time.time()
    return _job_cache


def ftok(s):
    try:
        r = int(s.split(".")[0]) / 1e18
        if r >= 1000: return f"{r:,.0f} RAI"
        if r >= 1: return f"{r:,.2f} RAI"
        return f"{r:,.6f} RAI"
    except:
        return "0 RAI"


def fpct(s):
    try: return f"{float(s)*100:.1f}%"
    except: return "0%"


def moniker(op):
    for v in get_vals():
        if v.get("operator_address", "") == op:
            return v.get("description", {}).get("moniker", "Unknown")
    return op[:16] + "..."


def status_emoji(v):
    if v.get("jailed"): return "🔴 JAILED"
    s = v.get("status", "")
    if "BONDED" in s and "UN" not in s: return "🟢 ACTIVE"
    if "UNBONDING" in s: return "🟡 UNBONDING"
    return "🔴 INACTIVE"


def status_color(v):
    if v.get("jailed"): return 0xE74C3C
    s = v.get("status", "")
    if "BONDED" in s and "UN" not in s: return 0x2ECC71
    if "UNBONDING" in s: return 0xF1C40F
    return 0xE74C3C


def status_bar(v):
    if v.get("jailed"): return "🟥🟥🟥🟥🟥🟥🟥🟥🟥🟥"
    s = v.get("status", "")
    if "BONDED" in s and "UN" not in s: return "🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩"
    if "UNBONDING" in s: return "🟨🟨🟨🟨🟨🟨🟨🟨⬜⬜"
    return "🟥🟥🟥🟥⬜⬜⬜⬜⬜⬜"


def status_dot(v):
    if v.get("jailed"): return "🔴"
    s = v.get("status", "")
    if "BONDED" in s and "UN" not in s: return "🟢"
    if "UNBONDING" in s: return "🟡"
    return "🔴"


def find_val(q):
    vals = get_vals()
    ql = q.lower().strip()
    for v in vals:
        if v.get("operator_address", "").lower() == ql:
            return v
    for v in vals:
        if v.get("description", {}).get("moniker", "").lower() == ql:
            return v
    for v in vals:
        if ql in v.get("description", {}).get("moniker", "").lower():
            return v
    if ql.startswith("rai1"):
        for v in vals:
            if ql in str(v).lower():
                return v
        d = api(f"{REST}/cosmos/staking/v1beta1/delegations/{ql}")
        if d:
            dels = d.get("delegation_responses", [])
            if dels:
                op = dels[0].get("delegation", {}).get("validator_address", "")
                if op:
                    for v in vals:
                        if v.get("operator_address") == op:
                            return v
    return None


def val_rank(v):
    vals = get_vals()
    bonded = [x for x in vals if "BONDED" in x.get("status", "") and "UN" not in x.get("status", "")]
    bonded.sort(key=lambda x: int(x.get("tokens", "0")), reverse=True)
    op = v.get("operator_address", "")
    for i, x in enumerate(bonded, 1):
        if x.get("operator_address") == op:
            return i, len(bonded)
    return 0, len(bonded)


def get_commission(op):
    d = api(f"{REST}/cosmos/distribution/v1beta1/validators/{op}/commission")
    if d:
        c = d.get("commission", {}).get("commission", [])
        if c:
            return ftok(c[0].get("amount", "0"))
    return "0 RAI"


def get_rewards(op):
    d = api(f"{REST}/cosmos/distribution/v1beta1/validators/{op}/outstanding_rewards")
    if d:
        r = d.get("rewards", {}).get("rewards", [])
        if r:
            return ftok(r[0].get("amount", "0"))
    return "0 RAI"


# ═══════════════════════════════════════════════
# EMBEDS
# ═══════════════════════════════════════════════

def mining_lb_embed():
    jobs = get_jobs()
    blk = block_height()
    if not jobs:
        return discord.Embed(title="⛏️ Mining Leaderboard", description="No jobs found.", color=0x00D4AA)

    counts = {}
    for j in jobs:
        v = j.get("target_validator", "")
        counts[v] = counts.get(v, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: -x[1])
    total = sum(c for _, c in ranked)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for i, (addr, cnt) in enumerate(ranked[:25], 1):
        name = moniker(addr)
        ic = medals.get(i, "🔷" if i <= 10 else "▫️")
        mx = ranked[0][1]
        bl = int((cnt / mx) * 10)
        bar = "█" * bl + "░" * (10 - bl)
        lines.append(f"{ic} **#{i}** {name}\n╰ `{bar}` **{cnt}** jobs")

    desc = "\n".join(lines)
    if len(ranked) > 25:
        desc += f"\n\n*+{len(ranked)-25} more miners*"

    e = discord.Embed(title="⛏️  Republic AI — Mining Leaderboard", description=desc, color=0x00D4AA, timestamp=datetime.now(timezone.utc))
    e.set_footer(text=f"📦 Block {blk:,}  •  ⛏️ {total} jobs  •  👷 {len(ranked)} miners")
    return e


def miner_info_embed(addr, jlist, rank, total):
    name = moniker(addr)
    blk = block_height()
    done = sum(1 for j in jlist if j.get("status") in ["Completed", "Verified"])
    pend = sum(1 for j in jlist if j.get("status") == "PendingExecution")
    pval = sum(1 for j in jlist if j.get("status") == "PendingValidation")
    colors = {1: 0xFFD700, 2: 0xC0C0C0, 3: 0xCD7F32}

    e = discord.Embed(title=f"⛏️  {name}", color=colors.get(rank, 0x00D4AA), timestamp=datetime.now(timezone.utc))
    e.add_field(name="🏆 Rank", value=f"**#{rank}** / {total}", inline=True)
    e.add_field(name="⛏️ Jobs", value=f"**{len(jlist)}**", inline=True)
    e.add_field(name="✅ Done", value=str(done), inline=True)
    e.add_field(name="🔍 Validating", value=str(pval), inline=True)
    e.add_field(name="⏳ Pending", value=str(pend), inline=True)
    e.add_field(name="📋 Address", value=f"`{addr}`", inline=False)
    e.set_footer(text=f"📦 Block {blk:,}")
    return e


def stats_embed():
    jobs = get_jobs()
    blk = block_height()
    vals = get_vals()
    bonded = len([v for v in vals if "BONDED" in v.get("status", "") and "UN" not in v.get("status", "")])

    if not jobs:
        return discord.Embed(title="📊 Stats", description="No jobs.", color=0x00D4AA)

    e = discord.Embed(title="📊  Republic AI — Mining Stats", color=0x00D4AA, timestamp=datetime.now(timezone.utc))
    e.add_field(name="⛏️ Total Jobs", value=f"**{len(jobs)}**", inline=True)
    e.add_field(name="✅ Completed", value=str(sum(1 for j in jobs if j.get("status") in ["Completed", "Verified"])), inline=True)
    e.add_field(name="🔍 Validating", value=str(sum(1 for j in jobs if j.get("status") == "PendingValidation")), inline=True)
    e.add_field(name="⏳ Pending", value=str(sum(1 for j in jobs if j.get("status") == "PendingExecution")), inline=True)
    e.add_field(name="👷 Miners", value=str(len(set(j.get("target_validator", "") for j in jobs))), inline=True)
    e.add_field(name="👥 Validators", value=str(bonded), inline=True)
    e.set_footer(text=f"📦 Block {blk:,}")
    return e


def val_ranking_embeds():
    vals = get_vals()
    blk = block_height()
    bonded = [v for v in vals if "BONDED" in v.get("status", "") and "UN" not in v.get("status", "")]
    bonded.sort(key=lambda v: int(v.get("tokens", "0")), reverse=True)

    if not bonded:
        return [discord.Embed(title="🏛 Ranking", description="No validators.", color=0x3498DB)]

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    embeds = []

    for start in range(0, min(len(bonded), 100), 25):
        end = min(start + 25, len(bonded), 100)
        lines = []
        for i in range(start, end):
            idx = i + 1
            v = bonded[i]
            m = v.get("description", {}).get("moniker", "Unknown")
            tok = ftok(v.get("tokens", "0"))
            j = " 🔒" if v.get("jailed") else ""
            ic = medals.get(idx, "🔷" if idx <= 10 else ("🔹" if idx <= 25 else ("▪️" if idx <= 50 else "•")))
            if len(m) > 14:
                m = m[:13] + ".."
            lines.append(f"{ic} **#{idx}** {m}{j} — {tok}")

        if start == 0:
            e = discord.Embed(
                title="🏛  Republic AI — Top 100 Validators",
                description="\n".join(lines), color=0x3498DB,
                timestamp=datetime.now(timezone.utc),
            )
            e.set_footer(text=f"📦 Block {blk:,}  •  👥 {len(bonded)} active validators")
        else:
            e = discord.Embed(description="\n".join(lines), color=0x3498DB)
        embeds.append(e)

    return embeds


def val_info_embed(v):
    blk = block_height()
    m = v.get("description", {}).get("moniker", "Unknown")
    op = v.get("operator_address", "")
    tok = v.get("tokens", "0")
    rate = v.get("commission", {}).get("commission_rates", {}).get("rate", "0")
    web = v.get("description", {}).get("website", "")
    details = v.get("description", {}).get("details", "")
    rank, total = val_rank(v)
    rank_text = f"**#{rank}** / {total}" if rank > 0 else "Not in active set"

    comm = get_commission(op)
    rew = get_rewards(op)

    jobs = get_jobs()
    jc = sum(1 for j in jobs if j.get("target_validator") == op)

    e = discord.Embed(title=f"🏛  {m}", color=status_color(v), timestamp=datetime.now(timezone.utc))
    e.description = status_bar(v)
    e.add_field(name="📊 Status", value=status_emoji(v), inline=True)
    e.add_field(name="🏆 Rank", value=rank_text, inline=True)
    e.add_field(name="🔒 Jailed", value="🔴 Yes" if v.get("jailed") else "🟢 No", inline=True)
    e.add_field(name="💰 Stake", value=f"**{ftok(tok)}**", inline=True)
    e.add_field(name="💸 Commission Rate", value=fpct(rate), inline=True)
    e.add_field(name="🎁 Commission Earned", value=comm, inline=True)
    e.add_field(name="💎 Rewards", value=rew, inline=True)
    e.add_field(name="⛏️ Compute Jobs", value=str(jc), inline=True)
    e.add_field(name="📋 Operator", value=f"`{op}`", inline=False)
    if web:
        e.add_field(name="🌐 Website", value=web, inline=True)
    if details and len(details) < 200:
        e.add_field(name="📝 Details", value=details, inline=False)
    e.set_footer(text=f"📦 Block {blk:,}")
    return e


def network_embed():
    blk = block_height()
    bt = block_time_str()
    vals = get_vals()
    jobs = get_jobs()

    bonded = len([v for v in vals if "BONDED" in v.get("status", "") and "UN" not in v.get("status", "")])
    unbonding = len([v for v in vals if "UNBONDING" in v.get("status", "")])
    jailed = len([v for v in vals if v.get("jailed")])
    total_staked = sum(int(v.get("tokens", "0")) for v in vals if "BONDED" in v.get("status", "") and "UN" not in v.get("status", ""))

    e = discord.Embed(title="🌐  Republic AI — Network Overview", color=0x3498DB, timestamp=datetime.now(timezone.utc))
    e.add_field(name="📦 Block", value=f"**{blk:,}**", inline=True)
    e.add_field(name="⏰ Time", value=bt, inline=True)
    e.add_field(name="💰 Total Staked", value=ftok(str(total_staked)), inline=True)
    e.add_field(name="\u200b", value="**🏛 Validators**", inline=False)
    e.add_field(name="🟢 Active", value=f"**{bonded}**", inline=True)
    e.add_field(name="🟡 Unbonding", value=str(unbonding), inline=True)
    e.add_field(name="🔒 Jailed", value=str(jailed), inline=True)
    e.add_field(name="📊 Total", value=str(len(vals)), inline=True)
    e.add_field(name="\u200b", value="**⛏️ Mining**", inline=False)
    e.add_field(name="⛏️ Jobs", value=f"**{len(jobs)}**", inline=True)
    e.add_field(name="👷 Miners", value=str(len(set(j.get("target_validator", "") for j in jobs))), inline=True)
    e.set_footer(text="Republic AI Testnet")
    return e


# ═══════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════

@bot.event
async def on_ready():
    logging.info(f"Bot online: {bot.user}")
    jobs = get_jobs()
    vals = get_vals()
    logging.info(f"Ready: {len(jobs)} jobs, {len(vals)} validators")
    if not auto_update.is_running():
        auto_update.start()
    if not alert_checker.is_running():
        alert_checker.start()


@bot.command(name="leaderboard", aliases=["lb"])
async def cmd_lb(ctx):
    await ctx.send(embed=mining_lb_embed())

@bot.command(name="miner", aliases=["m"])
async def cmd_miner(ctx, *, query: str = None):
    if not query:
        await ctx.send("Usage: `!miner <name or address>`")
        return
    jobs = get_jobs()
    if not jobs:
        await ctx.send("❌ No jobs found.")
        return
    jmap = {}
    for j in jobs:
        v = j.get("target_validator", "")
        jmap.setdefault(v, []).append(j)
    ranked = sorted(jmap.items(), key=lambda x: -len(x[1]))
    q = query.lower()
    for i, (addr, jlist) in enumerate(ranked, 1):
        name = moniker(addr)
        if q in name.lower() or q in addr.lower():
            await ctx.send(embed=miner_info_embed(addr, jlist, i, len(ranked)))
            return
    await ctx.send(f"❌ Miner `{query}` not found.")

@bot.command(name="stats")
async def cmd_stats(ctx):
    await ctx.send(embed=stats_embed())

@bot.command(name="validators", aliases=["ranking", "top100"])
async def cmd_vals(ctx):
    embeds = val_ranking_embeds()
    for e in embeds:
        await ctx.send(embed=e)

@bot.command(name="validator", aliases=["v", "val"])
async def cmd_val(ctx, *, query: str = None):
    if not query:
        await ctx.send("Usage: `!validator <name, raivaloper1..., or rai1...>`")
        return
    v = find_val(query)
    if not v:
        await ctx.send(f"❌ Validator `{query}` not found.\nTry: name, operator address, or wallet address.")
        return
    await ctx.send(embed=val_info_embed(v))

@bot.command(name="network", aliases=["net", "chain"])
async def cmd_net(ctx):
    await ctx.send(embed=network_embed())

@bot.command(name="alert")
async def cmd_alert(ctx, *, name: str = None):
    uid = ctx.author.id
    if not name:
        alerts = user_alerts.get(uid, [])
        if alerts:
            e = discord.Embed(title="🔔 Your Alerts", color=0xF39C12)
            e.description = "\n".join(f"• {a}" for a in alerts)
            e.description += "\n\n`!alert <n>` — Add\n`!alert clear` — Remove all"
        else:
            e = discord.Embed(title="🔕 No Alerts", description="`!alert <validator>` — Set alert", color=0x95A5A6)
        await ctx.send(embed=e)
        return
    if name.lower() == "clear":
        user_alerts[uid] = []
        await ctx.send("🔕 All alerts removed.")
        return
    v = find_val(name)
    if v:
        mn = v.get("description", {}).get("moniker", name)
        if uid not in user_alerts:
            user_alerts[uid] = []
        if mn not in user_alerts[uid]:
            user_alerts[uid].append(mn)
        e = discord.Embed(title="🔔 Alert Set!", color=0x2ECC71)
        e.description = f"Validator: **{mn}**\n\nYou'll be notified if jailed 🔒 or unbonding 🟡"
        await ctx.send(embed=e)
    else:
        await ctx.send(f"❌ Validator `{name}` not found.")

@bot.command(name="help_bot", aliases=["commands", "cmds"])
async def cmd_help(ctx):
    e = discord.Embed(title="⚡  Republic AI Bot — Commands", color=0x00D4AA, timestamp=datetime.now(timezone.utc))
    e.add_field(name="⛏️ Mining", value=(
        "`!leaderboard` / `!lb` — Mining leaderboard\n"
        "`!miner <n>` / `!m <n>` — Miner info\n"
        "`!stats` — Mining statistics"
    ), inline=False)
    e.add_field(name="🏛 Validators", value=(
        "`!validators` / `!ranking` / `!top100` — Top 100\n"
        "`!validator <n>` / `!v <n>` — Validator info\n"
        "Search by: name, operator addr, wallet addr"
    ), inline=False)
    e.add_field(name="🌐 Network", value="`!network` / `!net` — Network overview", inline=False)
    e.add_field(name="🔔 Alerts", value=(
        "`!alert <n>` — Set jail/unbond alert\n"
        "`!alert` — View alerts\n"
        "`!alert clear` — Remove all"
    ), inline=False)
    e.set_footer(text="Auto-updates mining leaderboard every block  •  Alerts check every 5 min")
    await ctx.send(embed=e)


# ═══════════════════════════════════════════════
# AUTO UPDATE + ALERTS
# ═══════════════════════════════════════════════

@tasks.loop(seconds=6)
async def auto_update():
    global last_block, last_message_id, _job_time
    if CHANNEL_ID == 0:
        return
    ch = bot.get_channel(CHANNEL_ID)
    if not ch:
        return
    blk = block_height()
    if blk <= last_block:
        return
    last_block = blk
    _job_time = 0

    embed = mining_lb_embed()
    try:
        if last_message_id:
            try:
                msg = await ch.fetch_message(last_message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                last_message_id = None
        msg = await ch.send(embed=embed)
        last_message_id = msg.id
    except Exception as e:
        logging.error(f"Auto: {e}")

@auto_update.before_loop
async def before_auto():
    await bot.wait_until_ready()

@tasks.loop(minutes=5)
async def alert_checker():
    global prev_statuses, _val_time
    _val_time = 0
    vals = get_vals()
    for v in vals:
        mn = v.get("description", {}).get("moniker", "")
        j = v.get("jailed", False)
        s = v.get("status", "")
        current = "jailed" if j else ("unbonding" if "UNBONDING" in s else "active")
        prev = prev_statuses.get(mn, "")
        if prev and prev != current:
            for uid, names in user_alerts.items():
                if mn in names:
                    user = bot.get_user(uid)
                    if user:
                        try:
                            if current == "jailed":
                                e = discord.Embed(title="🚨 JAIL ALERT", color=0xE74C3C)
                                e.description = f"**{mn}** is **JAILED!** 🔒\n⚡ Action needed!"
                            elif current == "unbonding":
                                e = discord.Embed(title="⚠️ UNBOND ALERT", color=0xF39C12)
                                e.description = f"**{mn}** is **UNBONDING!** 🟡"
                            elif current == "active":
                                e = discord.Embed(title="✅ RECOVERED", color=0x2ECC71)
                                e.description = f"**{mn}** is back **ACTIVE!** 🟢"
                            else:
                                continue
                            await user.send(embed=e)
                        except:
                            pass
        prev_statuses[mn] = current

@alert_checker.before_loop
async def before_alert():
    await bot.wait_until_ready()


def main():
    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
    if DISCORD_TOKEN == "YOUR_DISCORD_TOKEN_HERE":
        print("Set DISCORD_TOKEN!")
        return
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
