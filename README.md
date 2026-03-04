⛏️ Republic AI — Mining Leaderboard Bot
Discord bot that tracks on-chain compute jobs and ranks miners in real-time on the Republic AI testnet.
⚡ Features
Feature
Description
⛏️ Mining Leaderboard
Ranks miners by total compute jobs processed. Auto-updates every new block.
🔍 Miner Lookup
Search any miner by name or address. Shows jobs, rank, completed/pending status.
📊 Network Stats
Total jobs, completed, pending, active miners, job creators.
🔄 Real-Time Updates
Leaderboard auto-refreshes in #mining-leaderboard channel every block. Edits existing message to avoid spam.
📡 On-Chain Data
All data pulled directly from the Republic AI computevalidation module.
🚀 Commands
Command
Description
!leaderboard
Show full mining leaderboard
!lb
Short for leaderboard
!miner <name>
Show specific miner info
!stats
Network mining statistics
!help_mining
Show all commands
🛠 Setup
Requirements
Python 3.10+
Republic AI node (RPC + REST endpoints)
Installation
pip install discord.py requests
Configuration
Set environment variables:
export DISCORD_TOKEN="your_discord_bot_token"
export CHANNEL_ID="mining_leaderboard_channel_id"
export RPC_URL="http://localhost:26657"
export REST_URL="http://localhost:1317"
Run
python3 republic_mining_bot.py
Systemd Service (Optional)
cat > /etc/systemd/system/republic-mining-bot.service << EOF
[Unit]
Description=Republic Mining Leaderboard Bot
After=network.target

[Service]
Type=simple
Environment=DISCORD_TOKEN=your_token_here
Environment=CHANNEL_ID=your_channel_id
Environment=RPC_URL=http://localhost:26657
Environment=REST_URL=http://localhost:1317
ExecStart=/usr/bin/python3 /path/to/republic_mining_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable republic-mining-bot
systemctl start republic-mining-bot
📡 Data Source
The bot queries the Republic AI computevalidation module:
Endpoint
Description
computevalidation/list-job
All compute jobs with target validator, status, fees
staking/validators
Validator monikers and metadata
tendermint/status
Current block height
📝 License
MIT
