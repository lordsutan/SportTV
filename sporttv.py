#!/usr/bin/env python3
"""
SportTV - Automatic IPTV M3U Playlist Generator for Sports Channels
"""

import os
import re
import sys
import json
import time
import logging
import hashlib
import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config(path: str = "config.yaml") -> dict:
    """Load and validate configuration from YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    _validate_config(config)
    return config


def _validate_config(config: dict):
    """Validate required config keys exist."""
    required_keys = {
        "source": ["url", "timeout", "max_retries", "retry_delay"],
        "output": ["playlist", "logos_dir", "stats_file"],
        "logging": ["level", "file"],
    }
    for section, keys in required_keys.items():
        if section not in config:
            raise ValueError(f"Missing config section: '{section}'")
        for key in keys:
            if key not in config[section]:
                raise ValueError(f"Missing config key: '{section}.{key}'")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(config: dict) -> logging.Logger:
    """Configure logging with file and console handlers."""
    log_cfg = config["logging"]
    log_file = Path(log_cfg["file"])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Rotate: rename existing log with timestamp
    if log_file.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file.rename(log_file.parent / f"sporttv_{ts}.log")

    logger = logging.getLogger("sporttv")
    logger.setLevel(getattr(logging, log_cfg["level"].upper(), logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

def fetch_playlist(config: dict, logger: logging.Logger) -> str:
    """Fetch raw M3U playlist content with retries."""
    src = config["source"]
    url = src["url"]
    timeout = src["timeout"]
    max_retries = src["max_retries"]
    retry_delay = src["retry_delay"]

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Fetching playlist (attempt {attempt}/{max_retries}): {url}")
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            logger.info(f"Successfully fetched playlist ({len(resp.text)} bytes)")
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logger.error("All retry attempts exhausted.")
                raise RuntimeError(
                    f"Failed to fetch playlist after {max_retries} attempts: {e}"
                ) from e


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_m3u(raw: str, logger: logging.Logger) -> list[dict]:
    """Parse M3U content into a list of channel dicts."""
    channels = []
    lines = raw.strip().splitlines()

    if not lines or not lines[0].startswith("#EXTM3U"):
        raise ValueError("Invalid M3U file: missing #EXTM3U header")

    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            info = _parse_extinf(line)
            # Next non-empty, non-comment line is the URL
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
                i += 1
            if i < len(lines):
                info["url"] = lines[i].strip()
                channels.append(info)
        i += 1

    logger.info(f"Parsed {len(channels)} channels from playlist")
    return channels


def _parse_extinf(line: str) -> dict:
    """Extract metadata from an #EXTINF line."""
    channel = {"name": "", "logo": "", "group": "", "language": ""}

    # Extract tvg-logo
    logo_match = re.search(r'tvg-logo="([^"]*)"', line)
    if logo_match:
        channel["logo"] = logo_match.group(1)

    # Extract group-title
    group_match = re.search(r'group-title="([^"]*)"', line)
    if group_match:
        channel["group"] = group_match.group(1)

    # Extract tvg-language
    lang_match = re.search(r'tvg-language="([^"]*)"', line)
    if lang_match:
        channel["language"] = lang_match.group(1)

    # Extract channel name (after the last comma)
    name_match = re.search(r",(.+)$", line)
    if name_match:
        channel["name"] = name_match.group(1).strip()

    return channel


# ---------------------------------------------------------------------------
# Logo Downloader
# ---------------------------------------------------------------------------

def download_logos(channels: list[dict], config: dict, logger: logging.Logger) -> int:
    """Download channel logos to local folder. Returns count of successful downloads."""
    logos_dir = Path(config["output"]["logos_dir"])
    logos_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    total_with_logo = sum(1 for ch in channels if ch.get("logo"))

    for ch in channels:
        logo_url = ch.get("logo", "")
        if not logo_url:
            continue

        # Generate a safe filename from URL hash
        ext = _get_extension(logo_url)
        filename = hashlib.md5(logo_url.encode()).hexdigest() + ext
        filepath = logos_dir / filename

        if filepath.exists():
            ch["local_logo"] = str(filepath)
            downloaded += 1
            continue

        try:
            resp = requests.get(logo_url, timeout=10)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            ch["local_logo"] = str(filepath)
            downloaded += 1
        except requests.RequestException as e:
            logger.debug(f"Failed to download logo for '{ch['name']}': {e}")
            ch["local_logo"] = ""

    logger.info(f"Logos downloaded: {downloaded}/{total_with_logo}")
    return downloaded


def _get_extension(url: str) -> str:
    """Extract file extension from URL."""
    path = url.split("?")[0]
    if "." in path.split("/")[-1]:
        return "." + path.split("/")[-1].rsplit(".", 1)[-1][:4]
    return ".png"


# ---------------------------------------------------------------------------
# Playlist Writer
# ---------------------------------------------------------------------------

def write_playlist(channels: list[dict], config: dict, logger: logging.Logger):
    """Write clean M3U playlist file."""
    output_path = Path(config["output"]["playlist"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["#EXTM3U"]
    for ch in channels:
        attrs = []
        if ch.get("logo"):
            attrs.append(f'tvg-logo="{ch["logo"]}"')
        if ch.get("group"):
            attrs.append(f'group-title="{ch["group"]}"')
        if ch.get("language"):
            attrs.append(f'tvg-language="{ch["language"]}"')

        attr_str = " ".join(attrs)
        lines.append(f'#EXTINF:-1 {attr_str},{ch["name"]}')
        lines.append(ch["url"])

    content = "\n".join(lines) + "\n"
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Playlist written: {output_path} ({len(channels)} channels)")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def write_stats(channels: list[dict], logos_downloaded: int, config: dict, logger: logging.Logger):
    """Write stats.json report."""
    total = len(channels)
    with_logo = sum(1 for ch in channels if ch.get("logo"))
    groups = sorted(set(ch.get("group", "Unknown") for ch in channels))

    stats = {
        "total_channels": total,
        "channels_with_logo_url": with_logo,
        "logos_downloaded": logos_downloaded,
        "logo_coverage_percent": round((logos_downloaded / with_logo * 100) if with_logo else 0, 1),
        "groups": groups,
        "group_count": len(groups),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    stats_path = Path(config["output"]["stats_file"])
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Stats written: {stats_path}")
    return stats


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def run(config_path: str = "config.yaml"):
    """Run the full SportTV pipeline."""
    config = load_config(config_path)
    logger = setup_logging(config)

    logger.info("=" * 60)
    logger.info("SportTV - IPTV Sports Playlist Generator")
    logger.info("=" * 60)

    try:
        # 1. Fetch
        raw = fetch_playlist(config, logger)

        # 2. Parse
        channels = parse_m3u(raw, logger)
        if not channels:
            logger.warning("No channels found in playlist source!")
            return

        # 3. Download logos
        logos_downloaded = download_logos(channels, config, logger)

        # 4. Write playlist
        write_playlist(channels, config, logger)

        # 5. Write stats
        stats = write_stats(channels, logos_downloaded, config, logger)

        logger.info("-" * 60)
        logger.info(f"Done! {stats['total_channels']} channels, "
                    f"{stats['logo_coverage_percent']}% logo coverage")
        logger.info("-" * 60)

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli():
    """Command-line interface for SportTV."""
    parser = argparse.ArgumentParser(
        prog="sporttv",
        description="SportTV - IPTV Sports Playlist Generator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run
    run_parser = subparsers.add_parser("run", help="Run the full pipeline")
    run_parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")

    # validate
    val_parser = subparsers.add_parser("validate", help="Validate config file")
    val_parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")

    # test-scraper
    test_parser = subparsers.add_parser("test-scraper", help="Test the scraper (fetch only)")
    test_parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze current stats.json")
    analyze_parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")

    # clean-logs
    clean_parser = subparsers.add_parser("clean-logs", help="Remove old log files")
    clean_parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    clean_parser.add_argument("-k", "--keep", type=int, default=None, help="Number of logs to keep")

    args = parser.parse_args()

    if args.command == "run":
        run(args.config)

    elif args.command == "validate":
        cmd_validate(args.config)

    elif args.command == "test-scraper":
        cmd_test_scraper(args.config)

    elif args.command == "analyze":
        cmd_analyze(args.config)

    elif args.command == "clean-logs":
        cmd_clean_logs(args.config, args.keep)

    else:
        parser.print_help()


def cmd_validate(config_path: str):
    """Validate the config file."""
    try:
        config = load_config(config_path)
        print(f"[OK] Config '{config_path}' is valid.")
        print(f"     Source: {config['source']['url']}")
        print(f"     Output: {config['output']['playlist']}")
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


def cmd_test_scraper(config_path: str):
    """Test the scraper by fetching and parsing without writing files."""
    config = load_config(config_path)
    logger = setup_logging(config)
    try:
        raw = fetch_playlist(config, logger)
        channels = parse_m3u(raw, logger)
        print(f"\n[OK] Scraper test passed!")
        print(f"     Channels found: {len(channels)}")
        if channels:
            print(f"     First channel: {channels[0]['name']}")
            print(f"     Last channel:  {channels[-1]['name']}")
    except Exception as e:
        print(f"\n[ERROR] Scraper test failed: {e}")
        sys.exit(1)


def cmd_analyze(config_path: str):
    """Analyze the current stats.json."""
    config = load_config(config_path)
    stats_path = Path(config["output"]["stats_file"])
    if not stats_path.exists():
        print(f"[ERROR] Stats file not found: {stats_path}")
        print("        Run 'sporttv run' first to generate stats.")
        sys.exit(1)

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    print("=" * 50)
    print("  SportTV Playlist Analysis")
    print("=" * 50)
    print(f"  Total channels:    {stats['total_channels']}")
    print(f"  Logo coverage:     {stats['logo_coverage_percent']}%")
    print(f"  Logos downloaded:  {stats['logos_downloaded']}")
    print(f"  Groups:            {stats['group_count']}")
    print(f"  Last updated:      {stats['last_updated']}")
    print("-" * 50)
    print("  Groups:")
    for g in stats.get("groups", []):
        print(f"    - {g}")
    print("=" * 50)


def cmd_clean_logs(config_path: str, keep: int = None):
    """Remove old log files, keeping the most recent N."""
    config = load_config(config_path)
    log_dir = Path(config["logging"]["file"]).parent
    max_keep = keep if keep is not None else config["logging"].get("max_log_files", 7)

    if not log_dir.exists():
        print("[INFO] No logs directory found.")
        return

    log_files = sorted(log_dir.glob("sporttv_*.log"), key=lambda f: f.stat().st_mtime)
    to_remove = log_files[:-max_keep] if len(log_files) > max_keep else []

    if not to_remove:
        print(f"[INFO] Nothing to clean. {len(log_files)} log(s) found, keeping {max_keep}.")
        return

    for f in to_remove:
        f.unlink()
        print(f"  Removed: {f.name}")

    print(f"[OK] Cleaned {len(to_remove)} old log(s). Kept {max_keep}.")


if __name__ == "__main__":
    cli()
