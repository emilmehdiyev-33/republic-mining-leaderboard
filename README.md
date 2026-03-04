# Republic AI — Mining Leaderboard Bot

Discord bot that tracks on-chain compute jobs and ranks miners in real-time on the Republic AI testnet.

## Features

- Mining Leaderboard — Ranks miners by total compute jobs processed
- Auto-updates every new block in #mining-leaderboard channel
- Miner Lookup — Search any miner by name or address
- Network Stats — Total jobs, completed, pending, active miners
- On-Chain Data — All data from Republic AI computevalidation module
- Edits existing message to avoid spam

## Commands

- !leaderboard — Show full mining leaderboard
- !lb — Short for leaderboard
- !miner <name> — Show specific miner info
- !stats — Network mining statistics
- !help_mining — Show all commands

## Data Source

The bot queries the Republic AI computevalidation module:
- computevalidation/list-job — All compute jobs
- staking/validators — Validator monikers
- tendermint/status — Current block height

## License

MIT
