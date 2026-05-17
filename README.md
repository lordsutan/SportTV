# 🏀 SportKu

Automatic IPTV M3U playlist generator for sports channels. Scrapes public sources, downloads logos, and produces a clean playlist updated daily via GitHub Actions.

## 📁 Project Structure

```
SportKu/
├── sportku.py              # Main script
├── config.yaml             # Configuration
├── requirements.txt        # Python dependencies
├── output/
│   └── sportku.m3u         # Generated playlist
├── logos/                   # Downloaded channel logos
├── stats.json              # Playlist statistics
├── logs/                   # Execution logs
└── .github/workflows/
    └── update-playlist.yml # Daily auto-update
```

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
git clone https://github.com/lordsutan/SportKu.git
cd SportKu
pip install -r requirements.txt
```

### Configuration

Edit `config.yaml` to set your GitHub repo name and source URL:

```yaml
github:
  repo: "yourusername/SportKu"

source:
  url: "https://iptv-org.github.io/iptv/categories/sports.m3u"
  timeout: 30
  max_retries: 3
```

## 🛠️ CLI Commands

```bash
# Run the full pipeline (fetch, parse, download logos, write playlist)
python sportku.py run

# Validate your config file
python sportku.py validate

# Test the scraper without writing files
python sportku.py test-scraper

# Analyze current playlist stats
python sportku.py analyze

# Clean old log files (keeps last 7 by default)
python sportku.py clean-logs
python sportku.py clean-logs --keep 3
```

## 🔄 GitHub Actions (Auto-Update)

The playlist updates automatically every day at **00:00 UTC** via GitHub Actions.

### Setup

1. Push this repo to GitHub
2. Go to **Settings → Actions → General**
3. Under "Workflow permissions", select **Read and write permissions**
4. The workflow will run daily and commit updated files

You can also trigger it manually from the **Actions** tab → **Update SportKu Playlist** → **Run workflow**.

## 📺 Using the Playlist

Once the repo is public and the playlist is generated, use the raw GitHub URL:

```
https://raw.githubusercontent.com/lordsutan/SportKu/main/output/sportku.m3u
```

### VLC Media Player

1. Open VLC
2. **Media → Open Network Stream** (Ctrl+N)
3. Paste the raw M3U URL
4. Click **Play**

### IPTV Apps (Android/iOS/Smart TV)

1. Open your IPTV app (IPTV Smarters, TiviMate, OTT Navigator, etc.)
2. Add a new playlist → **M3U URL**
3. Paste the raw M3U URL
4. Save and refresh

### Kodi

1. Install **PVR IPTV Simple Client** add-on
2. Go to **Settings → PVR & Live TV → General → Enable**
3. Configure the add-on → Set M3U URL to the raw link
4. Restart Kodi

## 📊 Stats

After running, check `stats.json` for:

- Total channels count
- Logo coverage percentage
- Channel groups/categories
- Last update timestamp

## 🧪 Local Testing

```bash
# 1. Validate config
python sportku.py validate

# 2. Test scraper connectivity
python sportku.py test-scraper

# 3. Full run
python sportku.py run

# 4. Check results
python sportku.py analyze
```

## 📝 Logging

Logs are stored in `logs/` with automatic rotation. Configure log level in `config.yaml`:

```yaml
logging:
  level: "INFO"       # DEBUG for verbose output
  max_log_files: 7    # auto-cleanup old logs
```

## License

MIT
