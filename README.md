# IPTV Stream Checker

![IPTV Stream Checker](https://img.shields.io/badge/IPTV%20Checker-v1.0-blue.svg) ![Python](https://img.shields.io/badge/Python-3.6%2B-brightgreen.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Overview

IPTV Stream Checker is a command-line tool designed to check the status of channels in an IPTV M3U8 playlist. It verifies if the streams are alive, captures screenshots, provides detailed information about video and audio streams, and identifies any potential issues like low framerates or mislabeled channels.

<img width="794" alt="screenshot" src="https://github.com/user-attachments/assets/ffa84de1-f644-44b5-9d7d-92e32652a2be">

## Features

- **Check Stream Status:** Verify if IPTV streams are alive or dead.
- **Split Playlist:** Split into separate playlists for working and dead channels.
- **Capture Screenshots:** Capture screenshots from live streams.
- **Group Filter:** Option to check specific groups within the M3U8 playlist.
- **Detailed Stream Info:** Retrieve and display video codec, resolution, framerate, and audio bitrate.
- **Low Framerate Detection:** Identifies and lists channels with framerates at 30fps or below.
- **Mislabeled Channel Detection:** Detects channels with resolutions that do not match their labels (e.g., "1080p" labeled as "4K").
- **Geoblock Detection:** Automatically detects geoblocked streams using HTTP status codes (403, 451, etc.).
- **Proxy Testing:** Tests geoblocked streams through proxy servers to confirm geographic restrictions.
- **Custom User-Agent:** Uses `IPTVChecker 1.0` as the user agent for HTTP requests.

## Installation

### Prerequisites

- **Python 3.6+**
- **ffmpeg** and **ffprobe**: Required for capturing screenshots and retrieving stream information.
- **Optional**: Proxy servers for geoblock testing (HTTP/SOCKS5 supported).

### Clone the Repository

```bash
git clone https://github.com/NewsGuyTor/IPTVChecker.git
cd IPTVChecker
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Basic Command

```bash
python IPTV_checker.py /path/to/your/playlist.m3u8
```

### Options

- **`-group` or `-g`**: Specify a group title to check within the playlist.
- **`-timeout` or `-t`**: Set a timeout in seconds for checking the channel status.
- **`-extended` or `-e [seconds]`**: Enable an extended timeout check for channels detected as dead. If specified without a value, defaults to 10 seconds. This option allows you to retry dead channels with a longer timeout.
- **`-split` or `-s`**: Create separate playlists for working, dead, and geoblocked channels.
- **`-rename` or `-r`**: Rename alive channels to include video and audio information in the playlist.
- **`-proxy-list` or `-p`**: Path to proxy list file for geoblock testing.
- **`-test-geoblock` or `-tg`**: Test geoblocked streams with proxies to confirm geoblocking.
- **`-v`**: Increase output verbosity to `INFO` level.
- **`-vv`**: Increase output verbosity to `DEBUG` level.

### Examples

1. **Standard Check with Default Settings**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8
   ```

2. **Check a Specific Group**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -group "SPORT HD"
   ```

3. **Check with Extended Timeout**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -extended 30
   ```

4. **Split Playlist into Working and Dead Channels**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -split
   ```

5. **Rename Working Channels with Video and Audio Info**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -rename
   ```

6. **Split Playlist and Rename Working Channels**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -split -rename
   ```

7. **Enable Debug Mode for Detailed Output**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -vv
   ```

8. **Test Geoblocked Streams with Proxies**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -proxy-list proxies.txt -test-geoblock
   ```

9. **Split Playlist Including Geoblocked Channels**:
   ```bash
   python IPTV_checker.py /path/to/your/playlist.m3u8 -split -proxy-list proxies.txt -test-geoblock
   ```
   
### Output Format

The script will output the status of each channel in the following format:

```bash
1/5 ✓ Channel Name | Video: 1080p60 H264 - Audio: 159 kbps AAC
2/5 🔒 Geoblocked Channel | [Geoblocked (Confirmed)]
3/5 ✕ Dead Channel |
```

### Low Framerate Channels

After processing, the script lists any channels with framerates of 30fps or below:

```bash
Low Framerate Channels:
1/5 EGGBALL TV HD - 25fps
```

### Mislabeled Channels

The script also detects channels with incorrect labels:

```bash
Mislabeled Channels:
3/5 Sports5 FHD - Expected 1080p, got 4K
```

### Geoblocked Channels

The script detects and reports geoblocked channels:

```bash
Geoblocked Channels Summary: 12 channels detected
```

When proxy testing is enabled, the tool will attempt to confirm geoblocks by testing through proxy servers.

## Proxy Configuration

### Proxy List Format

Create a text file with one proxy per line:

```
# HTTP proxies
http://proxy1.example.com:8080
http://username:password@proxy2.example.com:3128

# SOCKS5 proxies
socks5://proxy3.example.com:1080

# Simple format (defaults to HTTP)
192.168.1.100:8080
```

### JSON Format (Advanced)

```json
[
  {
    "protocol": "http",
    "ip": "proxy1.example.com",
    "port": 8080
  },
  {
    "protocol": "socks5",
    "ip": "proxy2.example.com",
    "port": 1080
  }
]
```

### Geoblock Detection

The tool automatically detects geoblocked content by monitoring HTTP status codes:
- **403 Forbidden**: Most common geoblock indicator
- **451 Unavailable for Legal Reasons**: Official legal restriction code
- **426 Upgrade Required**: Sometimes used for region restrictions
- **401 Unauthorized**: May indicate access restrictions
- **423 Locked**: Resource locked due to restrictions

When proxy testing is enabled (`-test-geoblock`), the tool will:
1. Detect potentially geoblocked streams
2. Test up to 3 random proxies from your list
3. Confirm or deny geoblock status based on proxy accessibility
4. Generate separate playlist files for geoblocked content

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an issue if you have any ideas or feedback.
