#!/usr/bin/env python3
"""Translate location names to Chinese using ExifTool's GeoLang database."""
from __future__ import print_function
from __future__ import division

import os
import re

__geo_lang_cache = None

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


def _find_geolang_file():
    """Find ExifTool's zh_cn.pm GeoLang file."""
    candidates = []

    # ExifTool installed location (Windows)
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


def translate_location(english_name, region=None, country_code=None):
    """Translate a single English location name to Chinese.

    Tries ExifTool GeoLang database first (simple key, then compound key),
    then falls back to built-in province/country mapping.
    Returns the original name if no translation found.
    """
    if not english_name or not isinstance(english_name, str):
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

    # 3. Fallback to built-in province/country mapping
    return _PROVINCE_COUNTRY.get(english_name, english_name)


def translate_location_dict(location_dict):
    """Translate all string values in a location dict from English to Chinese.

    Expects keys like 'city', 'state', 'country'.  Values that are not strings
    or that have no mapping are left unchanged.
    """
    if not location_dict:
        return location_dict

    city = location_dict.get('city', '')
    state = location_dict.get('state', '')
    country_code = location_dict.get('country_code', '')
    subregion = location_dict.get('subregion', '')

    result = {}
    for key, value in location_dict.items():
        if isinstance(value, str):
            if key == 'city':
                # Use subregion for compound key lookup if available
                region_for_lookup = subregion if subregion else state
                result[key] = translate_location(value, region_for_lookup, country_code)
            elif key == 'default':
                region_for_lookup = subregion if subregion else state
                result[key] = translate_location(value, region_for_lookup, country_code)
            else:
                result[key] = translate_location(value)
        else:
            result[key] = value
    return result
