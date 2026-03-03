import requests
import argparse
import signal
import os
import sys
import time
import subprocess
import logging
import shutil
import random
import json
import codecs
import re
from urllib.parse import urljoin, urlparse

def print_header():
    header_text = """
\033[96m██╗██████╗ ████████╗██╗   ██╗     ██████╗██╗  ██╗███████╗ ██████╗██╗  ██╗███████╗██████╗   
██║██╔══██╗╚══██╔══╝██║   ██║    ██╔════╝██║  ██║██╔════╝██╔════╝██║ ██╔╝██╔════╝██╔══██╗  
██║██████╔╝   ██║   ██║   ██║    ██║     ███████║█████╗  ██║     █████╔╝ █████╗  ██████╔╝  
██║██╔═══╝    ██║   ╚██╗ ██╔╝    ██║     ██╔══██║██╔══╝  ██║     ██╔═██╗ ██╔══╝  ██╔══██╗  
██║██║        ██║    ╚████╔╝     ╚██████╗██║  ██║███████╗╚██████╗██║  ██╗███████╗██║  ██║  
╚═╝╚═╝        ╚═╝     ╚═══╝       ╚═════╝╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝  
\033[0m    
""" 
    print(header_text)
    print("\033[93mWelcome to the IPTV Stream Checker!\n\033[0m")
    print("\033[93mUse -h for help on how to use this tool.\033[0m")

def setup_logging(verbose_level):
    if verbose_level == 1:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    elif verbose_level >= 2:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

def handle_sigint(signum, frame):
    logging.info("Interrupt received, stopping...")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

def get_video_bitrate(url):
    """
    Measure approximate video bitrate by sampling the stream for 10 seconds.
    """
    command = [
        'ffmpeg',
        '-v',
        'debug',
        '-user_agent',
        'VLC/3.0.14',
        '-i',
        url,
        '-t',
        '10',
        '-f',
        'null',
        '-'
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20
        )
        output = result.stderr.decode(errors='ignore')
        total_bytes = 0
        for line in output.splitlines():
            if "Statistics:" in line and "bytes read" in line:
                parts = line.split("bytes read")
                try:
                    size_str = parts[0].strip().split()[-1]
                    total_bytes = int(size_str)
                    break
                except (IndexError, ValueError):
                    continue
        if total_bytes <= 0:
            return "N/A"
        bitrate_kbps = (total_bytes * 8) / 1000 / 10
        return f"{round(bitrate_kbps)} kbps"
    except FileNotFoundError:
        logging.warning("ffmpeg not found when attempting to measure video bitrate.")
        return "Unknown"
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout when trying to get video bitrate for {url}")
        return "Unknown"
    except Exception as exc:
        logging.error(f"Error when attempting to retrieve video bitrate: {exc}")
        return "N/A"

def check_ffmpeg_availability():
    """Check whether ffmpeg and ffprobe are available in the system PATH."""
    tool_status = {}

    for tool in ['ffmpeg', 'ffprobe']:
        available = False
        try:
            result = subprocess.run(
                [tool, '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            if result.returncode == 0:
                logging.debug(f"{tool} is available")
                available = True
            else:
                logging.error(f"{tool} is installed but not working properly")
        except FileNotFoundError:
            logging.error(f"{tool} is not found in system PATH. Please install {tool} to use this tool.")
        except subprocess.TimeoutExpired:
            logging.error(f"{tool} check timed out")
        except Exception as e:
            logging.exception(f"Unexpected error checking {tool}: {e}")
        tool_status[tool] = available

    return tool_status

def test_with_proxy(url, proxy, timeout, retries=3):
    """
    Test stream access through a specific proxy
    """
    headers = {
        'User-Agent': 'VLC/3.0.14 LibVLC/3.0.14'
    }
    proxies = {'http': proxy, 'https': proxy}
    stream_extensions = ('.ts', '.m2ts', '.m4s', '.mp4', '.aac', '.m3u8')

    for attempt in range(max(1, retries)):
        try:
            with requests.get(url, stream=True, timeout=(5, timeout), headers=headers, proxies=proxies) as resp:
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get('Content-Type', '')
                lowered_type = content_type.lower()
                stream_path = urlparse(resp.url).path.lower()
                if (
                    lowered_type.startswith('video/')
                    or lowered_type.startswith('audio/')
                    or 'application/vnd.apple.mpegurl' in lowered_type
                    or 'application/x-mpegurl' in lowered_type
                    or 'application/octet-stream' in lowered_type
                    or 'application/mp4' in lowered_type
                    or stream_path.endswith(stream_extensions)
                ):
                    # Read some data to verify stream
                    for chunk in resp.iter_content(1024 * 500):  # 500KB
                        if chunk:
                            return True
        except requests.RequestException as e:
            logging.debug(f"Proxy test failed with {proxy} (attempt {attempt + 1}/{max(1, retries)}): {str(e)}")

        if attempt + 1 < max(1, retries):
            time.sleep(0.5 * (attempt + 1))

    return False

def load_proxy_list(proxy_file):
    """
    Load proxy list from file. Supports formats:
    - ip:port
    - protocol://ip:port
    - JSON format with proxy objects (supports both 'protocol' and 'protocols' fields)
    """
    proxies = []
    try:
        with open(proxy_file, 'r') as f:
            content = f.read().strip()
            
            # Try JSON format first
            try:
                proxy_data = json.loads(content)
                if isinstance(proxy_data, list):
                    for proxy in proxy_data:
                        if isinstance(proxy, dict):
                            ip = proxy.get('ip')
                            port = proxy.get('port')
                            
                            if ip and port:
                                # Check for protocols array (new format)
                                if 'protocols' in proxy and isinstance(proxy['protocols'], list):
                                    for protocol in proxy['protocols']:
                                        proxies.append(f"{protocol}://{ip}:{port}")
                                # Fall back to single protocol (legacy format)
                                elif 'protocol' in proxy:
                                    protocol = proxy.get('protocol', 'http')
                                    proxies.append(f"{protocol}://{ip}:{port}")
                                # Default to http if no protocol specified
                                else:
                                    proxies.append(f"http://{ip}:{port}")
                        elif isinstance(proxy, str):
                            proxies.append(proxy)
                return proxies
            except json.JSONDecodeError:
                pass
            
            # Plain text format
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '://' not in line:
                        # Assume HTTP if no protocol specified
                        line = f'http://{line}'
                    proxies.append(line)
                    
    except FileNotFoundError:
        logging.error(f"Proxy file not found: {proxy_file}")
    except Exception as e:
        logging.error(f"Error loading proxy file: {str(e)}")
    
    return proxies

def check_channel_status(url, timeout, retries=6, extended_timeout=None, proxy_list=None, test_geoblock=False, ffmpeg_available=True):
    headers = {
        'User-Agent': 'VLC/3.0.14 LibVLC/3.0.14'
    }
    min_data_threshold = 1024 * 500  # 500KB minimum threshold for direct streams
    playlist_segment_threshold = 1024 * 128  # Smaller threshold for HLS media segments
    max_playlist_depth = 4
    initial_timeout = 5
    retryable_http_statuses = {408, 425, 429, 500, 502, 503, 504}
    geoblock_statuses = {403, 451, 426}
    secondary_geoblock_statuses = {401, 423, 451}

    def is_playlist(content_type, target_url):
        lowered_type = content_type.lower()
        lowered_url = target_url.lower()
        lowered_path = urlparse(lowered_url).path
        return (
            'application/vnd.apple.mpegurl' in lowered_type
            or 'application/x-mpegurl' in lowered_type
            or lowered_path.endswith('.m3u8')
        )

    def is_direct_stream(content_type, target_url):
        lowered_type = content_type.lower()
        lowered_path = urlparse(target_url).path.lower()
        stream_extensions = ('.ts', '.m2ts', '.m4s', '.mp4', '.aac')
        return (
            lowered_type.startswith('video/')
            or lowered_type.startswith('audio/')
            or 'application/octet-stream' in lowered_type
            or 'application/mp4' in lowered_type
            or lowered_path.endswith(stream_extensions)
        )

    def extract_next_url(base_url, playlist_body):
        def parse_tag_attributes(tag_line):
            attributes = {}
            _, _, payload = tag_line.partition(':')
            if not payload:
                return attributes

            index = 0
            payload_length = len(payload)
            while index < payload_length:
                while index < payload_length and payload[index] in ' \t,':
                    index += 1
                if index >= payload_length:
                    break

                key_start = index
                while index < payload_length and payload[index] not in '=,':
                    index += 1
                key = payload[key_start:index].strip().upper()
                if not key:
                    index += 1
                    continue
                if index >= payload_length or payload[index] != '=':
                    while index < payload_length and payload[index] != ',':
                        index += 1
                    continue

                index += 1
                if index < payload_length and payload[index] == '"':
                    index += 1
                    value_chars = []
                    while index < payload_length:
                        char = payload[index]
                        if char == '\\' and index + 1 < payload_length:
                            value_chars.append(payload[index + 1])
                            index += 2
                            continue
                        if char == '"':
                            index += 1
                            break
                        value_chars.append(char)
                        index += 1
                    value = ''.join(value_chars)
                else:
                    value_start = index
                    while index < payload_length and payload[index] != ',':
                        index += 1
                    value = payload[value_start:index].strip()

                attributes[key] = value
                if index < payload_length and payload[index] == ',':
                    index += 1

            return attributes

        def parse_resolution_pixels(resolution_value):
            if not resolution_value:
                return 0
            match = re.match(r'^\s*(\d+)\s*x\s*(\d+)\s*$', resolution_value, flags=re.IGNORECASE)
            if not match:
                return 0
            width = int(match.group(1))
            height = int(match.group(2))
            if width <= 0 or height <= 0:
                return 0
            return width * height

        def parse_int(value):
            if not value:
                return 0
            try:
                parsed = int(value.strip())
                return parsed if parsed > 0 else 0
            except (TypeError, ValueError):
                return 0

        saw_stream_inf = False
        pending_variant_attrs = None
        best_variant_url = None
        best_variant_score = None
        fallback_url = None

        for raw_line in playlist_body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith('#'):
                if line.upper().startswith('#EXT-X-STREAM-INF'):
                    saw_stream_inf = True
                    pending_variant_attrs = parse_tag_attributes(line)
                continue

            resolved_url = urljoin(base_url, line)
            if not saw_stream_inf:
                return resolved_url

            if pending_variant_attrs is not None:
                resolution_pixels = parse_resolution_pixels(pending_variant_attrs.get('RESOLUTION'))
                average_bandwidth = parse_int(pending_variant_attrs.get('AVERAGE-BANDWIDTH'))
                bandwidth = parse_int(pending_variant_attrs.get('BANDWIDTH'))
                quality_score = (
                    1 if resolution_pixels else 0,
                    resolution_pixels,
                    average_bandwidth,
                    bandwidth
                )
                if best_variant_score is None or quality_score > best_variant_score:
                    best_variant_score = quality_score
                    best_variant_url = resolved_url
                pending_variant_attrs = None
            elif fallback_url is None:
                fallback_url = resolved_url

        if best_variant_url:
            return best_variant_url
        return fallback_url

    def read_stream(response, min_bytes):
        bytes_read = 0
        for chunk in response.iter_content(1024 * 128):  # 128KB chunks
            if not chunk:
                continue
            bytes_read += len(chunk)
            if bytes_read >= min_bytes:
                logging.debug(f"Data received: {bytes_read} bytes")
                return 'Alive', response.url

        logging.debug(f"Data received: {bytes_read} bytes")
        if min_bytes >= min_data_threshold:
            fallback_threshold = min_bytes
        else:
            fallback_threshold = max(32768, min_bytes // 2)  # Allow smaller segments to pass
        if bytes_read >= fallback_threshold:
            return 'Alive', response.url
        return 'Dead', None

    def verify(target_url, current_timeout, depth, visited):
        if depth > max_playlist_depth:
            logging.debug("Maximum playlist nesting depth reached")
            return 'Dead', None

        normalized_url = target_url.split('#')[0]
        if normalized_url in visited:
            logging.debug(f"Detected playlist loop at {target_url}")
            return 'Dead', None
        visited.add(normalized_url)

        playlist_text = None
        final_url = target_url

        try:
            with requests.get(
                target_url,
                stream=True,
                timeout=(initial_timeout, current_timeout),
                headers=headers
            ) as resp:
                if resp.status_code in retryable_http_statuses:
                    logging.debug(f"Retryable HTTP status {resp.status_code} for {target_url}, retrying...")
                    return 'Retry', None
                if resp.status_code in geoblock_statuses:
                    logging.debug(f"Potential geoblock detected: HTTP {resp.status_code}")
                    return 'Geoblocked', None
                if resp.status_code != 200:
                    logging.debug(f"HTTP status code not OK: {resp.status_code}")
                    if resp.status_code in secondary_geoblock_statuses:
                        return 'Geoblocked', None
                    return 'Dead', None

                content_type = resp.headers.get('Content-Type', '')
                logging.debug(f"Content-Type: {content_type}")

                final_url = resp.url
                if is_playlist(content_type, final_url):
                    playlist_text = resp.text
                elif is_direct_stream(content_type, final_url):
                    min_bytes = min_data_threshold if depth == 0 else playlist_segment_threshold
                    return read_stream(resp, min_bytes)
                else:
                    if content_type.lower().startswith('text/'):
                        logging.debug(f"Content-Type not recognized as stream: {content_type}")
                        return 'Dead', None
                    logging.debug(f"Unrecognized Content-Type '{content_type}'. Attempting fallback stream read.")
                    min_bytes = min_data_threshold if depth == 0 else playlist_segment_threshold
                    return read_stream(resp, min_bytes)
        except requests.ConnectionError as exc:
            logging.warning(f"Connection error occurred for {target_url}: {exc}")
            return 'Retry', None
        except requests.Timeout as exc:
            logging.warning(f"Timeout occurred for {target_url}: {exc}")
            return 'Retry', None
        except requests.RequestException as e:
            logging.error(f"Request failed: {str(e)}")
            return 'Dead', None

        if not playlist_text:
            logging.debug("Playlist response was empty")
            return 'Dead', None

        next_url = extract_next_url(final_url, playlist_text)
        if not next_url:
            logging.debug("No media segments found in playlist")
            return 'Dead', None

        logging.debug(f"Following playlist entry: {next_url}")
        return verify(next_url, current_timeout, depth + 1, visited)

    def attempt_check(current_timeout):
        for attempt in range(retries):
            visited = set()
            status, stream_url = verify(url, current_timeout, 0, visited)
            if status == 'Retry':
                logging.debug(f"Retrying stream check for {url} ({attempt + 1}/{retries})")
                if attempt + 1 < max(1, retries):
                    time.sleep(min(2 + attempt, 5))
                continue
            return status, stream_url
        logging.error("Maximum retries exceeded for checking channel status")
        return 'Dead', None

    # First attempt with the initial timeout
    status, stream_url = attempt_check(timeout)

    # If the channel is detected as dead and extended_timeout is specified, retry with extended timeout
    if status == 'Dead' and extended_timeout:
        logging.info(f"Channel initially detected as dead. Retrying with an extended timeout of {extended_timeout} seconds.")
        status, stream_url = attempt_check(extended_timeout)
    
    # If geoblocked and proxy testing is enabled, test with proxies
    if status == 'Geoblocked' and test_geoblock and proxy_list:
        logging.info(f"Testing geoblocked stream with {len(proxy_list)} proxies...")
        for proxy in random.sample(proxy_list, min(3, len(proxy_list))):  # Test up to 3 random proxies
            if test_with_proxy(url, proxy, timeout):
                logging.info(f"Stream accessible via proxy {proxy} - confirming geoblock")
                return 'Geoblocked (Confirmed)', None
        logging.info("Stream not accessible via tested proxies")
        return 'Geoblocked (Unconfirmed)', None

    # Final Verification using ffmpeg/ffprobe for streams marked alive
    if status == 'Alive' and ffmpeg_available:
        verification_url = stream_url or url
        try:
            command = [
                'ffmpeg', '-user_agent', headers['User-Agent'], '-i', verification_url, '-t', '5', '-f', 'null', '-'
            ]
            ffmpeg_result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            if ffmpeg_result.returncode != 0:
                logging.warning(f"ffmpeg failed to read stream ({verification_url}); continuing with HTTP validation result")
        except FileNotFoundError:
            logging.warning(f"ffmpeg not found for stream verification, skipping ffmpeg check")
            # Keep status as 'Alive' since we already verified via HTTP
        except subprocess.TimeoutExpired:
            logging.warning(f"Timeout when trying to verify stream with ffmpeg for {verification_url}; continuing with HTTP validation result")
        except Exception as e:
            logging.warning(f"Error verifying stream with ffmpeg ({verification_url}): {str(e)}; continuing with HTTP validation result")

    return status, stream_url

def capture_frame(url, output_path, file_name):
    command = [
        'ffmpeg', '-y', '-i', url, '-ss', '00:00:02', '-frames:v', '1',
        os.path.join(output_path, f"{file_name}.png")
    ]
    try:
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        logging.debug(f"Screenshot saved for {file_name}")
        return True
    except FileNotFoundError:
        logging.error(f"ffmpeg not found. Please install ffmpeg to capture screenshots.")
        return False
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout when trying to capture frame for {file_name}")
        return False
    except Exception as e:
        logging.error(f"Error capturing frame for {file_name}: {str(e)}")
        return False

def get_detailed_stream_info(url, profile_bitrate=False):
    command = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 
        'stream=codec_name,width,height,r_frame_rate', '-of', 'default=noprint_wrappers=1', url
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        output = result.stdout.decode()
        codec_name = None
        width = height = None
        fps = None
        for line in output.splitlines():
            if line.startswith("codec_name="):
                codec_name = line.split('=')[1].upper()
            elif line.startswith("width="):
                width = int(line.split('=')[1])
            elif line.startswith("height="):
                height = int(line.split('=')[1])
            elif line.startswith("r_frame_rate="):
                fps_data = line.split('=')[1]
                if not fps_data:
                    continue
                try:
                    if '/' in fps_data:
                        numerator_str, denominator_str = fps_data.split('/', 1)
                        numerator = float(numerator_str)
                        denominator = float(denominator_str)
                        if denominator > 0:
                            fps = round(numerator / denominator)
                    else:
                        fps = round(float(fps_data))
                except ValueError:
                    logging.debug(f"Unable to parse frame rate '{fps_data}' for {url}")

        # Determine resolution string with FPS
        resolution = "Unknown"
        if width and height:
            if width >= 3840 and height >= 2160:
                resolution = "4K"
            elif width >= 1920 and height >= 1080:
                resolution = "1080p"
            elif width >= 1280 and height >= 720:
                resolution = "720p"
            else:
                resolution = "SD"

        video_bitrate = get_video_bitrate(url) if profile_bitrate else "N/A"

        return codec_name or "Unknown", video_bitrate, resolution, fps
    except FileNotFoundError:
        logging.error(f"ffprobe not found. Please install ffprobe to get stream info.")
        return "Unknown", "Unknown", "Unknown", None
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout when trying to get stream info for {url}")
        return "Unknown", "Unknown", "Unknown", None
    except Exception as e:
        logging.error(f"Error getting stream info: {str(e)}")
        return "Unknown", "Unknown", "Unknown", None

def format_stream_info(codec_name, video_bitrate, resolution, fps):
    if resolution != "Unknown" and fps:
        resolution_display = f"{resolution}{fps}"
    else:
        resolution_display = resolution

    components = []
    if resolution_display != "Unknown":
        components.append(resolution_display)
    if codec_name and codec_name != "Unknown":
        components.append(codec_name)

    base_info = " ".join(components) if components else "Unknown"
    if video_bitrate and isinstance(video_bitrate, str) and video_bitrate not in ("Unknown", "N/A"):
        return f"{base_info} ({video_bitrate})"
    return base_info

def get_audio_bitrate(url):
    command = [
        'ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
        'stream=codec_name,bit_rate', '-of', 'default=noprint_wrappers=1', url
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        output = result.stdout.decode()
        audio_bitrate = None
        codec_name = None
        for line in output.splitlines():
            if line.startswith("bit_rate="):
                bitrate_value = line.split('=')[1]
                if bitrate_value.isdigit():
                    audio_bitrate = int(bitrate_value) // 1000  # Convert to kbps
                else:
                    audio_bitrate = 'N/A'
            elif line.startswith("codec_name="):
                codec_name = line.split('=')[1].upper()

        return f"{audio_bitrate} kbps {codec_name}" if codec_name and audio_bitrate else "Unknown"
    except FileNotFoundError:
        logging.error(f"ffprobe not found. Please install ffprobe to get audio bitrate.")
        return "Unknown"
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout when trying to get audio bitrate for {url}")
        return "Unknown"
    except Exception as e:
        logging.error(f"Error getting audio bitrate: {str(e)}")
        return "Unknown"

def check_label_mismatch(channel_name, resolution):
    channel_name_lower = channel_name.lower()

    mismatches = []

    # Compare resolution ignoring the framerate part
    if "4k" in channel_name_lower or "uhd" in channel_name_lower:
        if resolution != "4K":
            mismatches.append(f"\033[91mExpected 4K, got {resolution}\033[0m")
    elif "1080p" in channel_name_lower or "fhd" in channel_name_lower:
        if resolution != "1080p":
            mismatches.append(f"\033[91mExpected 1080p, got {resolution}\033[0m")
    elif "hd" in channel_name_lower:
        if resolution not in ["1080p", "720p"]:
            mismatches.append(f"\033[91mExpected 720p or 1080p, got {resolution}\033[0m")
    elif resolution == "4K":
        mismatches.append(f"\033[91m4K channel not labeled as such\033[0m")

    return mismatches

def get_channel_name(extinf_line):
    if extinf_line.startswith('#EXTINF') and ',' in extinf_line:
        return extinf_line.split(',', 1)[1].strip()
    return "Unknown Channel"

def get_group_name(extinf_line):
    if "group-title=" in extinf_line:
        segment = extinf_line.split("group-title=", 1)[1]
        segment = segment.replace("\"", "")
        if "," in segment:
            return segment.split(",", 1)[0]
        return segment
    return "Unknown Group"

def get_channel_id(url):
    if not url:
        return "Unknown"
    segment = url.rsplit('/', 1)[-1]
    if segment:
        return segment.replace('.ts', '')
    return "Unknown"

def get_channel_stream_entry(lines, extinf_index):
    """
    Return (stream_url, metadata_lines, end_index) for a channel entry starting at #EXTINF.
    metadata_lines includes intermediary comment/blank lines between #EXTINF and the stream URL.
    """
    metadata_lines = []
    j = extinf_index + 1
    while j < len(lines):
        candidate = lines[j].strip()
        if candidate.startswith('#EXTINF'):
            return None, metadata_lines, j - 1
        if not candidate or candidate.startswith('#'):
            metadata_lines.append(candidate)
            j += 1
            continue
        return candidate, metadata_lines, j
    return None, metadata_lines, len(lines) - 1

def is_line_needed(line, group_title, pattern):
    if not line.startswith('#EXTINF'):
        return False
    if group_title:
        group_name = get_group_name(line).strip().lower()
        if group_name != group_title.strip().lower():
            return False
    if pattern:
        channel_name = get_channel_name(line)
        if not pattern.search(channel_name):
            return False
    return True

def compile_channel_pattern(channel_search):
    if not channel_search:
        return None
    try:
        return re.compile(channel_search, flags=re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Invalid channel search regex '{channel_search}': {exc}") from exc

def load_processed_channels(log_file):
    processed_channels = set()
    last_index = 0
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.rstrip('\n').split(' - ', 1)
                if len(parts) > 1:
                    index_source = parts[0].strip()
                    if index_source:
                        index_tokens = index_source.split()
                        if index_tokens:
                            index_part = index_tokens[0]
                            if index_part.isdigit():
                                last_index = max(last_index, int(index_part))
                    processed_channels.add(parts[1].strip())
    return processed_channels, last_index

def write_log_entry(log_file, entry):
    with open(log_file, 'a', encoding='utf-8', errors='replace') as f:
        f.write(entry + "\n")

def file_log_entry(f_output, playlist_file, current_channel, total_channels, group_name, channel_name, channel_id, status, codec_name, video_bitrate, resolution, fps, audio_info):
    if f_output is None:
        return
    safe_group = group_name.replace('"', '""') if group_name else ""
    safe_channel = channel_name.replace('"', '""') if channel_name else ""
    codec_field = codec_name if codec_name else "Unknown"
    bitrate_field = video_bitrate.replace("kbps", "").strip() if isinstance(video_bitrate, str) else video_bitrate
    if not bitrate_field:
        bitrate_field = "Unknown"
    fps_field = fps if fps is not None else ""
    audio_field = audio_info.replace('"', '""') if audio_info else "Unknown"
    channel_id_field = channel_id if channel_id else "Unknown"
    f_output.write(
        f"{playlist_file},{current_channel},{total_channels},{status},\"{safe_group}\",\"{safe_channel}\",{channel_id_field},{codec_field},{bitrate_field},{resolution},{fps_field},{audio_field}\n"
    )

def console_log_entry(playlist_file, current_channel, total_channels, channel_name, status, video_info, audio_info, max_name_length, use_padding):
    # Set colors and symbols based on status
    if status == 'Alive':
        color = "\033[92m"  # Green
        status_symbol = '✓'
    elif 'Geoblocked' in status:
        color = "\033[93m"  # Yellow
        status_symbol = '🔒'  # Lock emoji
    else:  # Dead
        color = "\033[91m"  # Red
        status_symbol = '✕'
    
    if use_padding:
        name_padding = ' ' * (max_name_length - len(channel_name) + 3)  # +3 for additional spaces
    else:
        name_padding = ''
    
    if status == 'Alive':
        prefix = f"{playlist_file}| " if playlist_file else ""
        print(f"{color}{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{name_padding} | Video: {video_info} - Audio: {audio_info}\033[0m")
        logging.info(f"{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{name_padding} | Video: {video_info} - Audio: {audio_info}")
    elif 'Geoblocked' in status:
        geoblock_info = f" [{status}]" if 'Confirmed' in status or 'Unconfirmed' in status else " [Geoblocked]"
        if use_padding:
            prefix = f"{playlist_file}| " if playlist_file else ""
            print(f"{color}{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{name_padding} |{geoblock_info}\033[0m")
            logging.info(f"{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{name_padding} |{geoblock_info}")
        else:
            prefix = f"{playlist_file}| " if playlist_file else ""
            print(f"{color}{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{geoblock_info}\033[0m")
            logging.info(f"{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{geoblock_info}")
    else:  # Dead
        if use_padding:
            prefix = f"{playlist_file}| " if playlist_file else ""
            print(f"{color}{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{name_padding} |\033[0m")
            logging.info(f"{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}{name_padding} |")
        else:
            prefix = f"{playlist_file}| " if playlist_file else ""
            print(f"{color}{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}\033[0m")
            logging.info(f"{prefix}{current_channel}/{total_channels} {status_symbol} {channel_name}")

def parse_m3u8_files(playlists, group_title, timeout, extended_timeout, split=False, rename=False, skip_screenshots=False, output_file=None, channel_search=None, channel_pattern=None, proxy_list=None, test_geoblock=False, profile_bitrate=False, ffmpeg_available=True, ffprobe_available=True):
    if not playlists:
        logging.error("No playlists to process.")
        return

    group_suffix = group_title.replace('|', '').replace(' ', '') if group_title else 'AllGroups'
    if channel_pattern is not None:
        pattern = channel_pattern
    else:
        try:
            pattern = compile_channel_pattern(channel_search)
        except ValueError as exc:
            logging.error(str(exc))
            return
    console_width = shutil.get_terminal_size((80, 20)).columns

    low_framerate_channels = []
    mislabeled_channels = []
    geoblocked_summary = {}

    f_output = None
    if output_file:
        output_dir = os.path.dirname(output_file)
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as exc:
                logging.error(f"Failed to create output directory '{output_dir}': {exc}")
                output_file = None
        if output_file:
            try:
                f_output = codecs.open(output_file, "w", "utf-8-sig")
                f_output.write("Playlist,Channel Number,Total Channels in Playlist,Channel Status,Group Name,Channel Name,Channel ID,Codec,Bit Rate (kbps),Resolution,Frame Rate,Audio\n")
            except OSError as exc:
                logging.error(f"Unable to open output file '{output_file}': {exc}")
                f_output = None

    for file_path in playlists:
        playlist_file = os.path.basename(file_path)
        base_playlist_name = os.path.splitext(playlist_file)[0]
        playlist_dir = os.path.dirname(file_path) or '.'
        logging.info(f"Loading channels from {file_path} with group '{group_title}' and search '{channel_search if channel_search else 'None'}'...")

        output_folder = None
        if not skip_screenshots:
            output_folder = os.path.join(playlist_dir, f"{base_playlist_name}_{group_suffix}_screenshots")
            try:
                os.makedirs(output_folder, exist_ok=True)
            except OSError as exc:
                logging.error(f"Failed to create output folder '{output_folder}': {exc}")
                output_folder = None

        log_file = os.path.join(playlist_dir, f"{base_playlist_name}_{group_suffix}_checklog.txt")
        processed_channels, last_index = load_processed_channels(log_file)
        current_channel = last_index
        working_channels = []
        dead_channels = []
        geoblocked_channels = []

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = [line.strip() for line in file.readlines()]
        except FileNotFoundError:
            logging.error(f"M3U file not found: {file_path}. Please check the path and try again.")
            continue
        except PermissionError:
            logging.error(f"Permission denied: Cannot read M3U file '{file_path}'")
            continue
        except Exception as exc:
            logging.error(f"Failed to read M3U file '{file_path}': {exc}")
            continue

        channels = [line for line in lines if is_line_needed(line, group_title, pattern)]
        total_channels = len(channels)
        logging.info(f"{playlist_file}: Total channels matching selection: {total_channels}\n")

        max_name_length = 0
        for channel_line in channels:
            channel_name = get_channel_name(channel_line)
            max_name_length = max(max_name_length, len(channel_name))

        max_line_length = max_name_length + len("1/5 ✓ | Video: 1080p50 H264 - Audio: 160 kbps AAC") + 3
        use_padding = max_line_length <= console_width

        renamed_lines = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if is_line_needed(line, group_title, pattern):
                channel_name = get_channel_name(line)
                stream_line, channel_metadata_lines, channel_end_index = get_channel_stream_entry(lines, i)
                if stream_line:
                    identifier = f"{channel_name} {stream_line}"
                    if identifier not in processed_channels:
                        current_channel += 1
                        status, stream_url = check_channel_status(
                            stream_line,
                            timeout,
                            extended_timeout=extended_timeout,
                            proxy_list=proxy_list,
                            test_geoblock=test_geoblock,
                            ffmpeg_available=ffmpeg_available
                        )
                        video_info = "Unknown"
                        audio_info = "Unknown"
                        codec_name = "Unknown"
                        video_bitrate = "Unknown"
                        resolution = "Unknown"
                        fps = None
                        channel_id = get_channel_id(stream_line)
                        group_value = get_group_name(line)

                        if status == 'Alive':
                            target_url = stream_url or stream_line
                            if ffprobe_available:
                                codec_name, video_bitrate, resolution, fps = get_detailed_stream_info(
                                    target_url,
                                    profile_bitrate=profile_bitrate and ffmpeg_available
                                )
                                video_info = format_stream_info(codec_name, video_bitrate, resolution, fps)
                                audio_info = get_audio_bitrate(target_url)
                                mismatches = check_label_mismatch(channel_name, resolution)
                                if fps is not None and fps <= 30:
                                    low_framerate_channels.append(f"{playlist_file}: {current_channel}/{total_channels} {channel_name} - \033[91m{fps}fps\033[0m")
                                if mismatches:
                                    mislabeled_channels.append(f"{playlist_file}: {current_channel}/{total_channels} {channel_name} - {', '.join(mismatches)}")
                            if not skip_screenshots and output_folder and ffmpeg_available:
                                file_name = f"{current_channel}-{channel_name.replace('/', '-')}"
                                capture_frame(target_url, output_folder, file_name)

                            if rename:
                                renamed_channel_name = f"{channel_name} ({video_info} | Audio: {audio_info})"
                                extinf_parts = line.split(',', 1)
                                if len(extinf_parts) > 1:
                                    extinf_parts[1] = renamed_channel_name
                                    line = ','.join(extinf_parts)

                            if split:
                                working_channels.append([line, *channel_metadata_lines, stream_line])
                        elif 'Geoblocked' in status:
                            if split:
                                geoblocked_channels.append([line, *channel_metadata_lines, stream_line])
                            geoblocked_summary[playlist_file] = geoblocked_summary.get(playlist_file, 0) + 1
                        else:
                            if split:
                                dead_channels.append([line, *channel_metadata_lines, stream_line])

                        console_log_entry(playlist_file, current_channel, total_channels, channel_name, status, video_info, audio_info, max_name_length, use_padding)
                        processed_channels.add(identifier)
                        write_log_entry(log_file, f"{current_channel} - {identifier}")
                        file_log_entry(f_output, playlist_file, current_channel, total_channels, group_value, channel_name, channel_id, status, codec_name, video_bitrate, resolution, fps, audio_info)
                    else:
                        logging.debug(f"Skipping previously processed channel: {channel_name}")

                    renamed_lines.append(line)
                    renamed_lines.extend(channel_metadata_lines)
                    renamed_lines.append(stream_line)
                else:
                    logging.warning(f"No stream URL found for channel '{channel_name}' in {playlist_file}")
                    renamed_lines.append(line)
                    renamed_lines.extend(channel_metadata_lines)
                i = max(i, channel_end_index)
            else:
                renamed_lines.append(line)
            i += 1

        if split:
            working_playlist_path = os.path.join(playlist_dir, f"{base_playlist_name}_working.m3u8")
            dead_playlist_path = os.path.join(playlist_dir, f"{base_playlist_name}_dead.m3u8")
            geoblocked_playlist_path = os.path.join(playlist_dir, f"{base_playlist_name}_geoblocked.m3u8")

            if working_channels:
                with open(working_playlist_path, 'w', encoding='utf-8') as working_file:
                    working_file.write("#EXTM3U\n")
                    for entry in working_channels:
                        for entry_line in entry:
                            working_file.write(entry_line + "\n")
                logging.info(f"Working channels playlist saved to {working_playlist_path}")

            if dead_channels:
                with open(dead_playlist_path, 'w', encoding='utf-8') as dead_file:
                    dead_file.write("#EXTM3U\n")
                    for entry in dead_channels:
                        for entry_line in entry:
                            dead_file.write(entry_line + "\n")
                logging.info(f"Dead channels playlist saved to {dead_playlist_path}")

            if geoblocked_channels:
                with open(geoblocked_playlist_path, 'w', encoding='utf-8') as geoblocked_file:
                    geoblocked_file.write("#EXTM3U\n")
                    for entry in geoblocked_channels:
                        for entry_line in entry:
                            geoblocked_file.write(entry_line + "\n")
                logging.info(f"Geoblocked channels playlist saved to {geoblocked_playlist_path}")
        if rename:
            renamed_playlist_path = os.path.join(playlist_dir, f"{base_playlist_name}_renamed.m3u8")
            with open(renamed_playlist_path, 'w', encoding='utf-8') as renamed_file:
                has_header = any(entry.upper().startswith("#EXTM3U") for entry in renamed_lines if entry)
                if not has_header:
                    renamed_file.write("#EXTM3U\n")
                for line in renamed_lines:
                    renamed_file.write(line + "\n")
            logging.info(f"Renamed playlist saved to {renamed_playlist_path}")

    if f_output:
        f_output.close()

    if low_framerate_channels:
        print("\n\033[93mLow Framerate Channels:\033[0m")
        for entry in low_framerate_channels:
            print(entry)
        logging.info("Low Framerate Channels Detected:")
        for entry in low_framerate_channels:
            logging.info(entry)

    if mislabeled_channels:
        print("\n\033[93mMislabeled Channels:\033[0m")
        for entry in mislabeled_channels:
            print(entry)
        logging.info("Mislabeled Channels Detected:")
        for entry in mislabeled_channels:
            logging.info(entry)

    if geoblocked_summary:
        print("\n\033[93mGeoblocked Channels Summary:\033[0m")
        for playlist_file, count in geoblocked_summary.items():
            print(f"{playlist_file}: {count} channels detected")
            logging.info(f"{playlist_file}: {count} geoblocked channels detected")

def main():
    print_header()

    parser = argparse.ArgumentParser(description="Check the status of channels in an IPTV M3U8 playlist and capture frames of live channels.")
    parser.add_argument("playlist", type=str, help="Path to the M3U8 playlist file")
    parser.add_argument("-group", "-g", type=str, default=None, help="Specific group title to check within the playlist")
    parser.add_argument("-timeout", "-t", type=float, default=10.0, help="Timeout in seconds for checking channel status")
    parser.add_argument("-v", action="count", default=0, help="Increase output verbosity (-v for info, -vv for debug)")
    parser.add_argument("-extended", "-e", type=int, nargs='?', const=10, default=None, help="Enable extended timeout check for dead channels. Default is 10 seconds if used without specifying time.")
    parser.add_argument("-split", "-s", action="store_true", help="Create separate playlists for working, dead, and geoblocked channels")
    parser.add_argument("-rename", "-r", action="store_true", help="Rename alive channels to include video and audio info")
    parser.add_argument("-proxy-list", "-p", type=str, default=None, help="Path to proxy list file for geoblock testing")
    parser.add_argument("-test-geoblock", "-tg", action="store_true", help="Test geoblocked streams with proxies to confirm geoblocking")
    parser.add_argument("-output", "-o", type=str, default=None, help="Write channel details to CSV at the provided path")
    parser.add_argument("-channel_search", "-c", type=str, default=None, help="Regex used to filter channels by name (case-insensitive)")
    parser.add_argument("-skip_screenshots", action="store_true", help="Skip capturing screenshots for alive channels")
    parser.add_argument("--profile-bitrate", "-b", action="store_true", help="Profile average video bitrate (slower, uses a 10-second ffmpeg sample)")

    args = parser.parse_args()

    try:
        channel_pattern = compile_channel_pattern(args.channel_search)
    except ValueError as exc:
        parser.error(str(exc))

    setup_logging(args.v)

    # Check for ffmpeg and ffprobe availability
    tool_status = check_ffmpeg_availability()
    ffmpeg_available = tool_status.get('ffmpeg', False)
    ffprobe_available = tool_status.get('ffprobe', False)
    if not (ffmpeg_available and ffprobe_available):
        logging.warning("ffmpeg and/or ffprobe not found. Some features will be disabled.")
        print("\033[93mWarning: ffmpeg and/or ffprobe not found. Screenshot capture and media info detection will be disabled.\033[0m")
    if args.profile_bitrate and not ffmpeg_available:
        logging.error("Disabling args.profile_bitrate because ffmpeg_available is False.")
        print("\033[93mWarning: args.profile_bitrate disabled because ffmpeg_available is False.\033[0m")
        args.profile_bitrate = False

    # Load proxy list if provided
    proxy_list = None
    if args.proxy_list:
        proxy_path = os.path.expanduser(args.proxy_list)
        proxy_list = load_proxy_list(proxy_path)
        if proxy_list:
            logging.info(f"Loaded {len(proxy_list)} proxies from {proxy_path}")
        else:
            logging.warning(f"No valid proxies loaded from {proxy_path}")
            if args.test_geoblock:
                logging.error("Cannot test geoblocks without valid proxies. Disabling geoblock testing.")
                args.test_geoblock = False

    playlist_input = os.path.expanduser(args.playlist)
    playlists = []
    if os.path.isdir(playlist_input):
        for entry in sorted(os.listdir(playlist_input)):
            full_path = os.path.join(playlist_input, entry)
            if os.path.isfile(full_path) and entry.lower().endswith((".m3u", ".m3u8")):
                playlists.append(full_path)
    else:
        if os.path.isfile(playlist_input):
            playlists.append(playlist_input)
        else:
            logging.error(f"Playlist path not found: {playlist_input}")
            return

    if not playlists:
        logging.error("No playlist files found to process.")
        return

    for playlist in playlists:
        logging.info(f"Will process playlist: {playlist}")

    output_file = os.path.expanduser(args.output) if args.output else None

    parse_m3u8_files(
        playlists,
        args.group,
        args.timeout,
        extended_timeout=args.extended,
        split=args.split,
        rename=args.rename,
        skip_screenshots=args.skip_screenshots,
        output_file=output_file,
        channel_search=args.channel_search,
        channel_pattern=channel_pattern,
        proxy_list=proxy_list,
        test_geoblock=args.test_geoblock,
        profile_bitrate=args.profile_bitrate,
        ffmpeg_available=ffmpeg_available,
        ffprobe_available=ffprobe_available
    )

if __name__ == "__main__":
    main()
    
