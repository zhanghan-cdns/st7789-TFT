"""农历（阴历）换算

自带 1900-2100 年 LUNAR_INFO 数据表，纯算法实现公历→农历转换，
不依赖任何第三方库。对外主要提供 lunar_date_str()。
数据表与算法为业界通用版本（每个年份用一个整数编码闰月与各月大小）。
"""
from datetime import date

# 1900-2100 年农历编码：低 4 位=闰月(0 表示无)，0x10000 位=闰月大小，
# 其余 12 位（0x8000..0x10）=正常 1~12 月每月大(30)/小(29)。
LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,  # 1900-1909
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,  # 1910-1919
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,  # 1920-1929
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,  # 1930-1939
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,  # 1940-1949
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,  # 1950-1959
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,  # 1960-1969
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b5a0, 0x195a6,  # 1970-1979
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,  # 1980-1989
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,  # 1990-1999
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,  # 2000-2009
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,  # 2010-2019
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,  # 2020-2029
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,  # 2030-2039
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,  # 2040-2049
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,  # 2050-2059
    0x0a2e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,  # 2060-2069
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,  # 2070-2079
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,  # 2080-2089
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,  # 2090-2099
    0x0d520,                                                                                   # 2100
]

_GAN = '甲乙丙丁戊己庚辛壬癸'
_ZHI = '子丑寅卯辰巳午未申酉戌亥'
_ZODIAC = '鼠牛虎兔龙蛇马羊猴鸡狗猪'
_MONTHS = '正二三四五六七八九十冬腊'
_DAY_N = '日一二三四五六七八九十'


def _leap_month(y):
    """返回该农历年的闰月（1~12），0 表示无闰月"""
    return LUNAR_INFO[y - 1900] & 0xf


def _leap_days(y):
    """闰月天数（无闰月返回 0）"""
    if _leap_month(y):
        return 30 if (LUNAR_INFO[y - 1900] & 0x10000) else 29
    return 0


def _month_days(y, m):
    """农历某年第 m 个普通月的天数（30 大 / 29 小）"""
    return 30 if (LUNAR_INFO[y - 1900] & (0x10000 >> m)) else 29


def _lunar_year_days(y):
    """农历某年总天数（含闰月）"""
    days = 348  # 12 * 29
    bit = 0x8000
    while bit > 0x8:
        if LUNAR_INFO[y - 1900] & bit:
            days += 1
        bit >>= 1
    return days + _leap_days(y)


def solar_to_lunar(y, m, d):
    """公历 (y, m, d) → 农历，返回 (年, 月, 日, 是否闰月)。

    基准：1900-01-31 为农历 1900 年正月初一。
    """
    offset = (date(y, m, d) - date(1900, 1, 31)).days
    temp = 0
    i = 1900
    while i < 2101 and offset > 0:
        temp = _lunar_year_days(i)
        offset -= temp
        i += 1
    if offset < 0:
        offset += temp
        i -= 1
    lunar_year = i

    leap = _leap_month(lunar_year)
    is_leap = False
    i = 1
    temp = 0
    while i < 13 and offset > 0:
        if leap > 0 and i == (leap + 1) and not is_leap:
            i -= 1
            is_leap = True
            temp = _leap_days(lunar_year)
        else:
            temp = _month_days(lunar_year, i)
        if is_leap and i == (leap + 1):
            is_leap = False
        offset -= temp
        i += 1
    # 闰月边界修正
    if offset == 0 and leap > 0 and i == leap + 1:
        if is_leap:
            is_leap = False
        else:
            is_leap = True
            i -= 1
    if offset < 0:
        offset += temp
        i -= 1
    return lunar_year, i, offset + 1, is_leap


def _gan_zhi(y):
    """农历年干支，如 1984→甲子"""
    return _GAN[(y - 4) % 10] + _ZHI[(y - 4) % 12]


def _zodiac(y):
    """生肖"""
    return _ZODIAC[(y - 4) % 12]


def _month_name(m, is_leap):
    return ('闰' if is_leap else '') + _MONTHS[m - 1] + '月'


def _day_name(d):
    if d <= 10:
        return '初' + _DAY_N[d]
    if d < 20:
        return '十' + _DAY_N[d - 10]
    if d == 20:
        return '二十'
    if d < 30:
        return '廿' + _DAY_N[d - 20]
    return '三十'


def lunar_date_str(y, m, d):
    """公历日期 → 农历显示串，如 "丙午马年 正月初一" """
    ly, lm, ld, is_leap = solar_to_lunar(y, m, d)
    return f"{_gan_zhi(ly)}{_zodiac(ly)}年 {_month_name(lm, is_leap)}{_day_name(ld)}"
