Republic AI — Mining Leaderboard Discord Bot
A real-time Discord bot that tracks on-chain compute jobs, ranks miners, monitors validators, and provides full network insights for the Republic AI blockchain.
Features
Mining Leaderboard — Ranks all miners by total compute jobs processed. The leaderboard auto-updates in a designated channel every new block. The bot edits the same message instead of spamming, keeping the channel clean.
Validator Tracking — Displays all 100 active validators ranked by stake. Each validator can be looked up individually by name, operator address, or wallet address. Shows status, rank, stake, commission rate, earned commission, rewards, compute jobs, and more.
Network Overview — Real-time network stats including block height, block time, total staked, active/unbonding/jailed validator counts, total compute jobs, and active miners.
Alert System — Users can set personal alerts for any validator. If a validator gets jailed or starts unbonding, the bot sends a DM notification. Alerts also notify when a validator recovers back to active status.
Compute Job Stats — Detailed mining statistics including total jobs, completed, validating, pending, number of active miners, and unique job creators.
Commands
Mining
!leaderboard — Show mining leaderboard ranked by compute jobs
!lb — Same, shorter
!miner <n> — Show specific miner info (rank, jobs, completed, pending)
!m <n> — Same, shorter
!stats — Mining statistics overview
Validators
!validators — Top 100 validator ranking by stake
!ranking — Same
!top100 — Same
!validator <n> — Detailed validator info (search by name, operator address, or wallet address)
!v <n> — Same, shorter
Network
!network — Full network overview (block, staked, validators, mining)
!net — Same, shorter
Alerts
!alert <n> — Set jail/unbond alert for a validator
!alert — View your active alerts
!alert clear — Remove all alerts
Help
!help_bot — Show all available commands
!cmds — Same
Data Sources
Validators — Republic AI public REST API (rest.republicai.io)
Compute Jobs — Local node CLI (republicd query computevalidation list-job)
Block Height — Local node RPC (localhost:26657)
Commission and Rewards — Republic AI public REST API
Setup
Requirements
Python 3.10+
Republic AI node running locally (for compute job queries)
discord.py and requests Python packages
Installation
pip install discord.py requests
Configuration
Set the following environment variables:
DISCORD_TOKEN=your_discord_bot_token
CHANNEL_ID=mining_leaderboard_channel_id
RPC_URL=http://localhost:26657
NODE_URL=tcp://localhost:26657
Run
python3 republic_mining_bot.py
How It Works
The bot polls the blockchain every 6 seconds for new blocks. When a new block is detected, it fetches fresh compute job data from the local node and updates the mining leaderboard embed in the designated Discord channel. It edits the existing message rather than sending new ones, keeping the channel clean.
Validator data is fetched from the Republic AI public REST API and cached for 30 seconds. Compute jobs are fetched from the local node using the republicd CLI and cached for 20 seconds.
The alert system checks validator statuses every 5 minutes. If a monitored validator changes status (active to jailed, active to unbonding, or back to active), the bot sends a DM to all users who set an alert for that validator.
License
MIT
