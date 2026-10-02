#!/usr/bin/env python3
"""Translate location names to Chinese using ExifTool's GeoLang database."""
from __future__ import print_function
from __future__ import division

import logging
import os
import re

import requests

__geo_lang_cache = None

# In-memory cache and API endpoint for the generic machine-translation
# fallback. "None" means the lookup previously failed (or returned no
# Chinese text) so we won't retry that name again this run.
_mymemory_cache = {}
_MYMEMORY_API = 'https://api.mymemory.translated.net/get'
_MYMEMORY_TIMEOUT = 5

log = logging.getLogger(__name__)

# Fallback for provinces/regions/countries not in GeoLang (city-level only)
_PROVINCE_COUNTRY = {
    'Zhejiang': '浙江', 'Jiangsu': '江苏', 'Guangdong': '广东',
    'Shandong': '山东', 'Sichuan': '四川', 'Hubei': '湖北',
    'Hunan': '湖南', 'Hebei': '河北', 'Henan': '河南',
    'Fujian': '福建', 'Anhui': '安徽', 'Jiangxi': '江西',
    'Shanxi': '山西', 'Shaanxi': '陕西', 'Liaoning': '辽宁',
    'Jilin': '吉林', 'Heilongjiang': '黑龙江', 'Yunnan': '云南',
    'Guizhou': '贵州', 'Gansu': '甘肃', 'Qinghai': '青海',
    'Hainan': '海南', 'Taiwan': '台湾', 'Guangxi': '广西',
    'Neimenggu': '内蒙古', 'Xinjiang': '新疆', 'Xizang': '西藏',
    'Ningxia': '宁夏', 'Beijing': '北京', 'Shanghai': '上海',
    'Tianjin': '天津', 'Chongqing': '重庆', 'Hong Kong': '香港',
    'Macau': '澳门',
    'China': '中国', 'Japan': '日本', 'Korea': '韩国',
    'United States': '美国', 'Canada': '加拿大', 'Australia': '澳大利亚',
    'United Kingdom': '英国', 'France': '法国', 'Germany': '德国',
    'Italy': '意大利', 'Spain': '西班牙', 'Thailand': '泰国',
    'Vietnam': '越南', 'Singapore': '新加坡', 'Malaysia': '马来西亚',
    'Indonesia': '印度尼西亚', 'Philippines': '菲律宾', 'India': '印度',
    'Russia': '俄罗斯', 'New Zealand': '新西兰',
}

# Supplementary city/place translations for names missing from ExifTool's
# GeoLang database (which is incomplete for county-level cities). Add more
# entries here (or in a config file) as needed; keys are the English name
# exactly as ExifTool returns in GeolocationCity.
_CITY_EXTRA = {
    'Cixi': '慈溪',
    'Yuyao': '余姚',
    'Ningbo': '宁波',
    'Ningbo Shi': '宁波市',
    'Hangzhou': '杭州',
    'Shangyu': '上虞',
    'Shengzhou': '嵊州',
    'Zhuji': '诸暨',
    'Fenghua': '奉化',
    'Xiangshan': '象山',
    'Ninghai': '宁海',
    'Yinzhou': '鄞州',
    'Haishu': '海曙',
    'Jiangbei': '江北',
    'Zhenhai': '镇海',
    'Beilun': '北仑',
    'Wenzhou': '温州',
    'Shaoxing': '绍兴',
    'Jinhua': '金华',
    'Taizhou': '台州',
    'Jiaxing': '嘉兴',
    'Huzhou': '湖州',
    'Quzhou': '衢州',
    'Zhoushan': '舟山',
    'Lishui': '丽水',
}


def _find_geolang_file():
    """Find a zh_cn.pm GeoLang translation file.

    A copy of the official ExifTool Chinese place-name database ships with
    Elodie (elodie/geolocations/zh_cn.pm), so we look there first - this
    works offline, without requiring the user to install ExifTool's optional
    Geolocation extension, and also resolves correctly inside a PyInstaller
    frozen build (sys._MEIPASS). We then fall back to an ExifTool installation
    that has the alternate Geolocation database installed.
    """
    candidates = []

    # 1. The copy bundled with Elodie: <elodie_package_dir>/geolocations/zh_cn.pm
    #    In a frozen (PyInstaller) build __file__ lives under _MEIPASS/elodie/,
    #    so this path is also correct there.
    bundled_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'geolocations', 'zh_cn.pm')
    candidates.append(bundled_file)

    # 2. ExifTool installed location (Windows)
    local_app = os.path.expandvars(r'%LOCALAPPDATA%\Programs\ExifTool')
    candidates.append(os.path.join(local_app, 'exiftool_files', 'lib',
                                   'Image', 'ExifTool', 'GeoLang', 'zh_cn.pm'))
    candidates.append(os.path.join(local_app, 'Geolocation500', 'zh_cn.pm'))

    # Also check the Geolocation500 in ExifTool dir alongside Geolocation.dat
    candidates.append(os.path.join(local_app, 'exiftool_files', 'lib',
                                   'Image', 'ExifTool', 'zh_cn.pm'))

    # System-wide ExifTool (Linux / macOS)
    for prefix in ['/usr/local', '/usr', '/opt/homebrew']:
        candidates.append(os.path.join(prefix, 'lib', 'perl5', 'Image',
                                       'ExifTool', 'GeoLang', 'zh_cn.pm'))

    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _load_geolang():
    """Parse zh_cn.pm and return a dict {English: Chinese}."""
    global __geo_lang_cache
    if __geo_lang_cache is not None:
        return __geo_lang_cache

    geolang_path = _find_geolang_file()
    if geolang_path is None:
        __geo_lang_cache = {}
        return __geo_lang_cache

    translate = {}
    try:
        with open(geolang_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                # Match lines like:  'EnglishName' => '中文名',
                m = re.match(r"\s*'(.+?)'\s*=>\s*'(.+?)'", line)
                if m:
                    eng, chn = m.group(1), m.group(2)
                    # Only keep entries that contain CJK characters (Chinese)
                    if any('\u4e00' <= c <= '\u9fff' for c in chn):
                        translate[eng] = chn
    except Exception:
        pass

    __geo_lang_cache = translate
    return __geo_lang_cache


def _translate_via_mymemory(text):
    """Machine-translate a single place name to Chinese via MyMemory.

    Used only as a final fallback when the bundled databases have no entry,
    so obscure/county-level names like "Haining" still get a Chinese folder
    name. Results are cached per name for the current process. All failures
    (network, timeouts, non-Chinese responses) return None so the caller can
    silently keep the English name - this must never block an import.
    """
    if not text or not isinstance(text, str):
        return None
    # Skip already-Chinese text and bare labels with no Latin letters, so we
    # never waste a rate-limited API call on something we can't improve.
    if _has_cjk(text):
        return None
    if not any(c.isalpha() for c in text):
        return None

    cached = _mymemory_cache.get(text, False)
    if cached is not False:
        return cached

    try:
        resp = requests.get(
            _MYMEMORY_API,
            params={'q': text, 'langpair': 'en|zh-CN'},
            timeout=_MYMEMORY_TIMEOUT,
        )
        resp.raise_for_status()
        translated = resp.json().get('responseData', {}).get('translatedText', '')
        if translated and isinstance(translated, str):
            translated = translated.strip()
            # Only accept responses we can actually use (contain Chinese).
            if any('\u4e00' <= c <= '\u9fff' for c in translated):
                _mymemory_cache[text] = translated
                return translated
    except (requests.exceptions.RequestException, ValueError) as e:
        log.debug('MyMemory translation failed for %r: %s', text, e)

    _mymemory_cache[text] = None
    return None


def _has_cjk(text):
    """Return True if the string contains Chinese (CJK) characters."""
    return any('\u4e00' <= c <= '\u9fff' for c in text)


def translate_location(english_name, region=None, country_code=None):
    """Translate a single English location name to Chinese.

    Tries ExifTool GeoLang database first (simple key, then compound key),
    then falls back to built-in province/country mapping.
    Returns the original name if no translation found.

    Idempotent: a name that is already Chinese (or has no Latin letters) is
    returned unchanged, so re-processing cached Chinese entries never triggers
    a redundant dictionary lookup or a network call.
    """
    if not english_name or not isinstance(english_name, str):
        return english_name

    # Already Chinese - nothing to do. Also keeps translation idempotent so
    # cached Chinese results (see geolocation.place_name) are cheap no-ops.
    if _has_cjk(english_name):
        return english_name

    geo_lang = _load_geolang()

    # 1. Simple lookup (most city names)
    result = geo_lang.get(english_name)
    if result:
        return result

    # 2. Compound key lookup: "CNZhejiang,Ningbo Shi,Linshan"
    #    This handles ambiguous city names like Linshan, Anhua, etc.
    if region and country_code:
        compound_key = f"{country_code}{region},{english_name}"
        result = geo_lang.get(compound_key)
        if result:
            return result

    # 3. Supplementary city translations for names missing from GeoLang.
    result = _CITY_EXTRA.get(english_name)
    if result:
        return result

    # 4. Fallback to built-in province/country mapping
    result = _PROVINCE_COUNTRY.get(english_name)
    if result:
        return result

    # 5. Generic machine-translation fallback for anything still missing
    #    (county-level cities, obscure place names, etc).
    return _translate_via_mymemory(english_name) or english_name


def translate_location_dict(location_dict):
    """Translate all string values in a location dict from English to Chinese.

    Expects keys like 'city', 'state', 'country'.  Values that are not strings
    or that have no mapping are left unchanged.
    """
    if not location_dict:
        return location_dict

    state = location_dict.get('state', '')
    country_code = location_dict.get('country_code', '')
    subregion = location_dict.get('subregion', '')

    result = {}
    for key, value in location_dict.items():
        if key == 'city':
            # Compound key in GeoLang uses the province/state level
            # (e.g. "CNZhejiang,Ningbo Shi,Cixi") so pass state first.
            region_for_lookup = state if state else subregion
            result[key] = translate_location(value, region_for_lookup, country_code)
        elif key == 'default':
            region_for_lookup = state if state else subregion
            result[key] = translate_location(value, region_for_lookup, country_code)
        elif key in ('state', 'country', 'subregion', 'town'):
            # 'town' is used by the MapQuest path; translate it the same way so
            # both reverse-geocoding sources produce Chinese consistently.
            result[key] = translate_location(value)
        else:
            # Leave non-place-name keys (country_code, timezone, etc.) as-is;
            # sending them to the translator would just waste an API call.
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Reverse geocoding providers that return Chinese names directly
# ---------------------------------------------------------------------------

# Rough bounding box for mainland China. Used to decide whether to call the
# Amap API (which only covers China) or fall back to Nominatim for the rest
# of the world. The box is intentionally generous so border-area photos are
# still routed to Amap.
_CHINA_BBOX = {
    'min_lat': 18.0, 'max_lat': 54.0,
    'min_lon': 73.0, 'max_lon': 135.5,
}

_amap_cache = {}
_nominatim_cache = {}


def _in_china(lat, lon):
    """Return True if the coordinate falls within the China bounding box."""
    return (
        _CHINA_BBOX['min_lat'] <= lat <= _CHINA_BBOX['max_lat']
        and _CHINA_BBOX['min_lon'] <= lon <= _CHINA_BBOX['max_lon']
    )


def amap_place_name(lat, lon, api_key):
    """Reverse-geocode via Amap and return a Chinese location dict.

    Returns a dict with keys: city, state, country, district, town, default.
    All values are Chinese strings. Returns None on failure so the caller can
    fall back to the next provider.
    """
    if not api_key:
        return None

    cache_key = f'{lat:.2f},{lon:.2f}'
    if cache_key in _amap_cache:
        return dict(_amap_cache[cache_key])

    try:
        resp = requests.get(
            'https://restapi.amap.com/v3/geocode/regeo',
            params={
                'location': f'{lon},{lat}',
                'key': api_key,
                'extensions': 'base',
                'output': 'JSON',
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get('status') != '1' or not data.get('regeocode'):
            return None

        addr = data['regeocode'].get('addressComponent', {})

        city = addr.get('city') or ''
        if isinstance(city, list):
            city = ''
        province = addr.get('province') or ''
        if isinstance(province, list):
            province = ''
        district = addr.get('district') or ''
        if isinstance(district, list):
            district = ''
        town = addr.get('township') or ''
        if isinstance(town, list):
            town = ''

        if not any([city, province, district]):
            return None

        result = {
            'city': city or district or province,
            'state': province,
            'country': '中国',
            'default': city or district or province,
        }
        if district:
            result['district'] = district
        if town:
            result['town'] = town

        _amap_cache[cache_key] = result
        return dict(result)

    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        log.debug('Amap reverse geocoding failed for (%s, %s): %s', lat, lon, e)
        return None


def nominatim_place_name(lat, lon):
    """Reverse-geocode via Nominatim (OpenStreetMap) with Chinese locale.

    Returns a dict with keys: city, state, country, default.
    All values are Chinese strings. Returns None on failure.
    """
    cache_key = f'{lat:.2f},{lon:.2f}'
    if cache_key in _nominatim_cache:
        cached = _nominatim_cache[cache_key]
        return dict(cached) if cached else None

    try:
        resp = requests.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={
                'lat': lat,
                'lon': lon,
                'format': 'json',
                'accept-language': 'zh-CN',
                'zoom': 10,
            },
            headers={'User-Agent': 'Elodie/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        addr = data.get('address', {})
        if not addr:
            _nominatim_cache[cache_key] = None
            return None

        city = (
            addr.get('city')
            or addr.get('town')
            or addr.get('county')
            or addr.get('municipality')
            or ''
        )
        state = addr.get('state') or ''
        country = addr.get('country') or ''

        if not any([city, state, country]):
            _nominatim_cache[cache_key] = None
            return None

        result = {
            'city': city or state or country,
            'state': state,
            'country': country,
            'default': city or state or country,
        }

        _nominatim_cache[cache_key] = result
        return dict(result)

    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        log.debug('Nominatim reverse geocoding failed for (%s, %s): %s', lat, lon, e)
        _nominatim_cache[cache_key] = None
        return None


def reverse_geocode_to_chinese(lat, lon, amap_key=None):
    """Get Chinese place name from coordinates using the best provider.

    Routes to Amap for China, Nominatim for the rest of the world.
    Returns a location dict or None if all providers fail.
    """
    if _in_china(lat, lon):
        result = amap_place_name(lat, lon, amap_key)
        if result:
            return result

    result = nominatim_place_name(lat, lon)
    if result:
        return result

    if not _in_china(lat, lon):
        result = amap_place_name(lat, lon, amap_key)
        if result:
            return result

    return None
