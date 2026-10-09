# -*- coding: utf-8 -*-
"""
版本说明：基于V13阈值参数优化版 + V15逻辑修复增强版 合并而成
赛事五引擎分析器 (V29 信心区间回测校准版 - 弃单点0.01/肉眼挑点, 改回测+约登指数自动定三档)
V29新增：信心/干扰信号阈值不再单点硬切(0.01/肉眼挑最稳区间)，改为对录入历史赛果跑回测，
         用约登指数+ROC/AUC在滚动时间序列交叉验证下确定"稳定输出正确方向"的信心区间，
         输出三档(放弃区/降仓区/正常区)，两档阈值写入CONFIG可配，避免0.01一刀切脆弱性。
核心特性：
1. 融合了V10的“双重错题本匹配算法”（概率+数学指标容差）。
2. 融合了V9的“完美让分逻辑”与“全量回测功能”。
3. [V15修复] 修复了__file__不可用导致数据无法自动保存的问题（三层兜底机制）。
4. [V15修复] 简化错题本去重逻辑（精确匹配替代相似度匹配，避免定位失败）。
5. [V15新增] 引擎性能自适应权重系统（根据历史表现自动调整引擎权重）。
6. [V15新增] 系统信心指数评估 + 引擎分歧检测 + 建议放弃机制。
7. [V15新增] 重复编号自动检测与修复。
8. [V13阈值优化] 引擎A阈值(1.7/2.6/2.9)、冷门风险阈值(0.12)、引擎E临界值(2.8)等经回测优化。
9. [V24新增] 冷门预测独立模块：单独设立差距阈值 0.01，仅当预测结果与实际赛果(赛事胜平负概率最大值方向)不同且两者概率差距<=0.01时才进行冷门预测。
9. V13新增：概率区间赛果映射引擎(F)、比分引擎动态重构、加权投票决策升级
10. [V15+指纹集成] 数据指纹比分分析引擎：基于让分面板+身价对比+平均概率指向三维指纹匹配历史比分库
11. [V16新增] 零球/一球数据指纹识别系统：基于赛事数据指纹分析结果，自动识别0球(0:0)和1球(1:0/0:1)指纹特征，支持概率区间+引擎结论+共振类型多维匹配
12. [逻辑梳理] 理顺代码逻辑：优化函数注释、简化重复检测流程、增强关键逻辑说明
13. [V17阈值优化] 0球/1球指纹识别阈值从60/55提升至90，减少误报，提高参考价值；阈值定义为可配置常量
14. [V18新增] 胶着数据面板分级响应机制(降仓替代放弃) | 比分-方向一致性校验引擎 | 引擎F高风险信心扣减 | 0球指纹强弱过滤 | 错题本时间加权
15. [V21新增] 错题本偏差检测机制 - 自动检测错题本自身方向偏差并降低历史预警权重
16. [V21修复] 冷门Override全面弱化 - 移除自动翻转结论逻辑，改为信心扣减+提示
 17. [V21修复] 冷门阈值全面上调 - COLD_RATIO_THRESHOLD 0.6->0.75, COLD_RISK_BOOST_THRESHOLD 0.10->0.18->0.25
18. [V27修复] 移植V25分级决策链并修复V26"全是观望"过度保守:
   a) 硬否决改为"强信号加权分"机制: 信心不足只降仓不单独否决, 数据面板仅预警不计入否决, 需多个独立强风险(反向背离/引擎F高风险/多信号叠加)凑够高阈值才观望;
   b) 取消"六引擎全票一致反而扣信心"的反直觉逻辑, 全票一致且无干扰信号=方向信号最强维持满信心;
   c) 引擎相关性去膨胀改为仅作降仓参考(缩放系数可配), 不再在否决判定前重复乘算;
   d) 保留V26有价值的运行时修复: 步骤8~12缩进错位、相似度虚报、冷门"最大概率=实际赛果"错误代理。
"""

import sys
import os
import math
import re
from collections import Counter
# ==========================================
# 安全获取脚本路径，防止 __file__ 不可用导致保存失败
# ==========================================
_SCRIPT_PATH = None
try:
    _SCRIPT_PATH = os.path.abspath(__file__)
except (NameError, AttributeError):
    try:
        import inspect
        _SCRIPT_PATH = os.path.abspath(inspect.getfile(sys.modules[__name__]))
    except Exception:
        try:
            _SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            _SCRIPT_PATH = os.path.abspath(".")


# ==========================================
# 1. 错题本数据库 
# 说明：请在此处粘贴你的历史数据。
ERROR_BOOK = [
    {"handicap": 1, "jc_win": 2.42, "jc_draw": 2.95, "jc_lose": 2.65, "rq_win": 5.75, "rq_draw": 3.9, "rq_lose": 1.43, "avg_win": 2.55, "avg_draw": 3.06, "avg_lose": 2.71, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.21, "jc_draw": 5.5, "jc_lose": 8.25, "rq_win": 1.72, "rq_draw": 4.0, "rq_lose": 3.36, "avg_win": 1.3, "avg_draw": 5.36, "avg_lose": 7.43, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.34, "jc_draw": 4.55, "jc_lose": 6.15, "rq_win": 2.13, "rq_draw": 3.45, "rq_lose": 2.7, "avg_win": 1.44, "avg_draw": 4.44, "avg_lose": 6.02, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.3, "jc_lose": 3.5, "rq_win": 3.75, "rq_draw": 3.52, "rq_lose": 1.73, "avg_win": 1.86, "avg_draw": 3.55, "avg_lose": 3.76, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 2.92, "jc_lose": 3.35, "rq_win": 4.6, "rq_draw": 3.5, "rq_lose": 1.6, "avg_win": 2.33, "avg_draw": 3.12, "avg_lose": 2.96, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 4.05, "jc_lose": 1.58, "rq_win": 2.08, "rq_draw": 3.7, "rq_lose": 3.64, "avg_win": 3.97, "avg_draw": 3.86, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.35, "jc_lose": 3.85, "rq_win": 3.5, "rq_draw": 3.4, "rq_lose": 1.82, "avg_win": 2.0, "avg_draw": 3.49, "avg_lose": 3.33, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 7.45, "jc_lose": 11.83, "rq_win": 2.04, "rq_draw": 4.35, "rq_lose": 2.45, "avg_win": 1.18, "avg_draw": 7.0, "avg_lose": 11.0, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.15, "jc_lose": 2.2, "rq_win": 1.5, "rq_draw": 3.9, "rq_lose": 4.85, "avg_win": 2.32, "avg_draw": 3.39, "avg_lose": 2.73, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.74, "jc_draw": 3.2, "jc_lose": 4.15, "rq_win": 3.55, "rq_draw": 3.3, "rq_lose": 1.84, "avg_win": 1.65, "avg_draw": 3.45, "avg_lose": 5.03, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.26, "jc_lose": 4.2, "rq_win": 3.4, "rq_draw": 3.3, "rq_lose": 1.88, "avg_win": 1.69, "avg_draw": 3.49, "avg_lose": 4.67, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.48, "jc_lose": 5.7, "rq_win": 2.13, "rq_draw": 3.75, "rq_lose": 2.55, "avg_win": 1.62, "avg_draw": 4.21, "avg_lose": 4.3, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 2.85, "jc_lose": 2.86, "rq_win": 5.5, "rq_draw": 3.8, "rq_lose": 1.46, "avg_win": 2.34, "avg_draw": 3.18, "avg_lose": 2.91, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.4, "jc_draw": 3.0, "jc_lose": 2.65, "rq_win": 5.6, "rq_draw": 3.9, "rq_lose": 1.44, "avg_win": 2.59, "avg_draw": 3.22, "avg_lose": 2.57, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.77, "jc_draw": 3.25, "jc_lose": 2.17, "rq_win": 1.51, "rq_draw": 3.8, "rq_lose": 4.9, "avg_win": 2.84, "avg_draw": 3.59, "avg_lose": 2.24, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.45, "jc_lose": 1.78, "rq_win": 1.81, "rq_draw": 3.48, "rq_lose": 3.45, "avg_win": 4.06, "avg_draw": 3.53, "avg_lose": 1.81, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.6, "jc_draw": 3.45, "jc_lose": 4.65, "rq_win": 2.99, "rq_draw": 3.25, "rq_lose": 2.05, "avg_win": 1.69, "avg_draw": 3.55, "avg_lose": 4.68, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.72, "jc_draw": 3.15, "jc_lose": 2.25, "rq_win": 1.49, "rq_draw": 3.75, "rq_lose": 5.22, "avg_win": 2.91, "avg_draw": 3.18, "avg_lose": 2.34, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.81, "jc_draw": 3.5, "jc_lose": 3.45, "rq_win": 3.5, "rq_draw": 3.6, "rq_lose": 1.77, "avg_win": 2.18, "avg_draw": 3.33, "avg_lose": 2.92, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 3.65, "jc_lose": 3.02, "rq_win": 3.95, "rq_draw": 3.95, "rq_lose": 1.61, "avg_win": 2.02, "avg_draw": 3.5, "avg_lose": 2.88, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 6.05, "jc_draw": 4.7, "jc_lose": 1.33, "rq_win": 2.7, "rq_draw": 3.7, "rq_lose": 2.05, "avg_win": 5.43, "avg_draw": 4.33, "avg_lose": 1.48, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.66, "jc_draw": 3.5, "jc_lose": 4.15, "rq_win": 3.1, "rq_draw": 3.45, "rq_lose": 1.94, "avg_win": 1.77, "avg_draw": 3.56, "avg_lose": 4.21, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.9, "jc_lose": 3.52, "rq_win": 3.0, "rq_draw": 3.75, "rq_lose": 1.89, "avg_win": 1.63, "avg_draw": 4.15, "avg_lose": 4.28, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 2.16, "jc_draw": 3.65, "jc_lose": 2.55, "rq_win": 4.3, "rq_draw": 4.12, "rq_lose": 1.53, "avg_win": 2.01, "avg_draw": 3.83, "avg_lose": 3.06, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.26, "jc_draw": 4.8, "jc_lose": 8.0, "rq_win": 1.92, "rq_draw": 3.5, "rq_lose": 3.1, "avg_win": 1.45, "avg_draw": 4.21, "avg_lose": 6.39, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.32, "jc_lose": 2.68, "rq_win": 4.6, "rq_draw": 3.95, "rq_lose": 1.52, "avg_win": 2.42, "avg_draw": 3.4, "avg_lose": 2.66, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.5, "jc_lose": 3.0, "rq_win": 3.95, "rq_draw": 3.75, "rq_lose": 1.64, "avg_win": 2.16, "avg_draw": 3.48, "avg_lose": 2.94, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 5.0, "jc_draw": 4.1, "jc_lose": 1.46, "rq_win": 2.35, "rq_draw": 3.4, "rq_lose": 2.45, "avg_win": 4.74, "avg_draw": 3.85, "avg_lose": 1.61, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 4.3, "jc_draw": 3.8, "jc_lose": 1.58, "rq_win": 2.05, "rq_draw": 3.45, "rq_lose": 2.85, "avg_win": 4.57, "avg_draw": 3.72, "avg_lose": 1.67, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.49, "jc_draw": 4.05, "jc_lose": 4.75, "rq_win": 2.46, "rq_draw": 3.55, "rq_lose": 2.27, "avg_win": 1.51, "avg_draw": 4.21, "avg_lose": 5.56, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 3.15, "jc_draw": 3.65, "jc_lose": 1.86, "rq_win": 1.74, "rq_draw": 3.72, "rq_lose": 3.5, "avg_win": 2.95, "avg_draw": 3.52, "avg_lose": 2.1, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.65, "jc_lose": 4.5, "rq_win": 2.88, "rq_draw": 3.3, "rq_lose": 2.09, "avg_win": 1.73, "avg_draw": 3.59, "avg_lose": 4.39, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.35, "jc_draw": 4.05, "jc_lose": 7.05, "rq_win": 2.28, "rq_draw": 3.2, "rq_lose": 2.65, "avg_win": 1.54, "avg_draw": 3.74, "avg_lose": 6.01, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.15, "jc_lose": 3.7, "rq_win": 3.85, "rq_draw": 3.45, "rq_lose": 1.73, "avg_win": 2.38, "avg_draw": 3.09, "avg_lose": 2.88, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.0, "jc_lose": 6.05, "rq_win": 2.41, "rq_draw": 3.25, "rq_lose": 2.46, "avg_win": 1.7, "avg_draw": 3.79, "avg_lose": 4.36, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.82, "jc_draw": 3.4, "jc_lose": 3.5, "rq_win": 3.65, "rq_draw": 3.52, "rq_lose": 1.75, "avg_win": 1.78, "avg_draw": 3.52, "avg_lose": 4.13, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 6.4, "jc_draw": 4.4, "jc_lose": 1.34, "rq_win": 2.73, "rq_draw": 3.4, "rq_lose": 2.13, "avg_win": 5.87, "avg_draw": 4.0, "avg_lose": 1.5, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.35, "jc_lose": 3.2, "rq_win": 3.9, "rq_draw": 3.62, "rq_lose": 1.68, "avg_win": 2.18, "avg_draw": 3.39, "avg_lose": 3.05, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "正常", "match_context": "Z=2.2900; Y=1.3200; X=1.6400; cold_risk=12.4%; dev_level=一致", "match_id": "#626"},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.96, "jc_lose": 4.1, "rq_win": 2.78, "rq_draw": 3.55, "rq_lose": 2.05, "avg_win": 1.67, "avg_draw": 4.02, "avg_lose": 4.32, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.84, "jc_draw": 3.12, "jc_lose": 3.77, "rq_win": 3.95, "rq_draw": 3.25, "rq_lose": 1.76, "avg_win": 1.87, "avg_draw": 3.29, "avg_lose": 4.14, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 4.25, "jc_lose": 1.37, "rq_win": 2.59, "rq_draw": 3.3, "rq_lose": 2.27, "avg_win": 6.08, "avg_draw": 4.04, "avg_lose": 1.5, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.97, "jc_draw": 3.82, "jc_lose": 2.78, "rq_win": 3.62, "rq_draw": 4.05, "rq_lose": 1.65, "avg_win": 1.52, "avg_draw": 4.61, "avg_lose": 4.94, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.56, "jc_draw": 3.6, "jc_lose": 4.75, "rq_win": 2.82, "rq_draw": 3.35, "rq_lose": 2.1, "avg_win": 1.61, "avg_draw": 3.6, "avg_lose": 5.46, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.65, "jc_lose": 2.01, "rq_win": 1.63, "rq_draw": 3.9, "rq_lose": 3.85, "avg_win": 2.94, "avg_draw": 3.74, "avg_lose": 2.1, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.75, "jc_draw": 3.26, "jc_lose": 1.8, "rq_win": 1.78, "rq_draw": 3.45, "rq_lose": 3.6, "avg_win": 4.25, "avg_draw": 3.42, "avg_lose": 1.79, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.86, "jc_draw": 2.9, "jc_lose": 2.3, "rq_win": 1.48, "rq_draw": 3.7, "rq_lose": 5.45, "avg_win": 2.76, "avg_draw": 2.94, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.15, "jc_lose": 4.46, "rq_win": 3.45, "rq_draw": 3.2, "rq_lose": 1.9, "avg_win": 1.86, "avg_draw": 3.33, "avg_lose": 4.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.01, "jc_draw": 3.15, "jc_lose": 3.18, "rq_win": 4.15, "rq_draw": 3.65, "rq_lose": 1.63, "avg_win": 2.09, "avg_draw": 3.23, "avg_lose": 3.36, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.3, "jc_lose": 3.25, "rq_win": 3.85, "rq_draw": 3.65, "rq_lose": 1.68, "avg_win": 2.25, "avg_draw": 3.44, "avg_lose": 2.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.86, "jc_draw": 3.2, "jc_lose": 3.6, "rq_win": 3.9, "rq_draw": 3.45, "rq_lose": 1.72, "avg_win": 2.24, "avg_draw": 3.23, "avg_lose": 3.02, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.43, "jc_draw": 4.1, "jc_lose": 5.4, "rq_win": 2.4, "rq_draw": 3.45, "rq_lose": 2.38, "avg_win": 1.92, "avg_draw": 3.52, "avg_lose": 3.64, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.91, "jc_draw": 3.15, "jc_lose": 3.47, "rq_win": 4.1, "rq_draw": 3.45, "rq_lose": 1.68, "avg_win": 2.05, "avg_draw": 3.25, "avg_lose": 3.45, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.01, "jc_draw": 3.2, "jc_lose": 3.13, "rq_win": 4.2, "rq_draw": 3.65, "rq_lose": 1.62, "avg_win": 2.02, "avg_draw": 3.34, "avg_lose": 3.45, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 3.8, "jc_draw": 3.05, "jc_lose": 1.86, "rq_win": 1.72, "rq_draw": 3.3, "rq_lose": 4.08, "avg_win": 3.4, "avg_draw": 3.05, "avg_lose": 2.15, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 5.25, "jc_draw": 4.1, "jc_lose": 1.44, "rq_win": 2.4, "rq_draw": 3.5, "rq_lose": 2.35, "avg_win": 4.78, "avg_draw": 4.1, "avg_lose": 1.57, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.44, "jc_draw": 3.4, "jc_lose": 2.35, "rq_win": 1.45, "rq_draw": 4.25, "rq_lose": 4.9, "avg_win": 2.38, "avg_draw": 3.43, "avg_lose": 2.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 2.75, "jc_lose": 3.7, "rq_win": 4.6, "rq_draw": 3.45, "rq_lose": 1.61, "avg_win": 2.23, "avg_draw": 3.03, "avg_lose": 3.66, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 5.15, "jc_draw": 4.0, "jc_lose": 1.46, "rq_win": 2.34, "rq_draw": 3.5, "rq_lose": 2.4, "avg_win": 4.89, "avg_draw": 4.09, "avg_lose": 1.56, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 5.8, "jc_lose": 10.5, "rq_win": 2.75, "rq_draw": 3.88, "rq_lose": 1.97, "avg_win": 1.29, "avg_draw": 5.28, "avg_lose": 8.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 4.56, "jc_draw": 4.1, "jc_lose": 1.5, "rq_win": 2.25, "rq_draw": 3.55, "rq_lose": 2.48, "avg_win": 4.58, "avg_draw": 3.95, "avg_lose": 1.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.45, "jc_draw": 3.65, "jc_lose": 1.77, "rq_win": 1.8, "rq_draw": 3.65, "rq_lose": 3.35, "avg_win": 3.1, "avg_draw": 3.55, "avg_lose": 2.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.5, "jc_lose": 5.3, "rq_win": 2.88, "rq_draw": 3.15, "rq_lose": 2.15, "avg_win": 1.58, "avg_draw": 3.67, "avg_lose": 5.52, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 5.15, "jc_draw": 3.45, "jc_lose": 1.55, "rq_win": 2.12, "rq_draw": 3.2, "rq_lose": 2.9, "avg_win": 4.66, "avg_draw": 3.44, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.76, "jc_draw": 3.75, "jc_lose": 3.4, "rq_win": 3.2, "rq_draw": 3.8, "rq_lose": 1.81, "avg_win": 2.3, "avg_draw": 3.31, "avg_lose": 3.24, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 6.25, "jc_lose": 9.3, "rq_win": 2.56, "rq_draw": 4.0, "rq_lose": 2.05, "avg_win": 1.28, "avg_draw": 5.54, "avg_lose": 8.34, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.75, "jc_lose": 2.86, "rq_win": 3.75, "rq_draw": 3.95, "rq_lose": 1.64, "avg_win": 1.99, "avg_draw": 3.7, "avg_lose": 3.17, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.62, "jc_draw": 3.35, "jc_lose": 2.23, "rq_win": 1.5, "rq_draw": 4.1, "rq_lose": 4.6, "avg_win": 3.16, "avg_draw": 3.58, "avg_lose": 2.02, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.19, "jc_draw": 3.3, "jc_lose": 2.71, "rq_win": 4.6, "rq_draw": 3.95, "rq_lose": 1.52, "avg_win": 1.92, "avg_draw": 3.53, "avg_lose": 3.41, "shenjia": "主身 = 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.55, "jc_lose": 2.13, "rq_win": 1.54, "rq_draw": 4.0, "rq_lose": 4.4, "avg_win": 2.92, "avg_draw": 3.57, "avg_lose": 2.13, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.66, "jc_draw": 3.45, "jc_lose": 2.16, "rq_win": 1.52, "rq_draw": 3.95, "rq_lose": 4.6, "avg_win": 2.78, "avg_draw": 3.49, "avg_lose": 2.27, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.59, "jc_draw": 3.85, "jc_lose": 4.15, "rq_win": 2.84, "rq_draw": 3.45, "rq_lose": 2.05, "avg_win": 1.72, "avg_draw": 3.75, "avg_lose": 4.18, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 3.25, "jc_lose": 2.55, "rq_win": 5.2, "rq_draw": 4.05, "rq_lose": 1.45, "avg_win": 2.49, "avg_draw": 3.35, "avg_lose": 2.62, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.7, "jc_lose": 3.4, "rq_win": 3.2, "rq_draw": 3.7, "rq_lose": 1.83, "avg_win": 1.82, "avg_draw": 4.03, "avg_lose": 3.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 3.45, "jc_draw": 3.35, "jc_lose": 1.85, "rq_win": 1.72, "rq_draw": 3.55, "rq_lose": 3.75, "avg_win": 3.36, "avg_draw": 3.32, "avg_lose": 2.05, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.25, "jc_draw": 3.02, "jc_lose": 2.04, "rq_win": 1.59, "rq_draw": 3.55, "rq_lose": 4.6, "avg_win": 3.18, "avg_draw": 3.16, "avg_lose": 2.14, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.9, "jc_draw": 2.83, "jc_lose": 2.32, "rq_win": 1.46, "rq_draw": 3.65, "rq_lose": 5.85, "avg_win": 2.95, "avg_draw": 2.96, "avg_lose": 2.39, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.65, "jc_draw": 3.35, "jc_lose": 4.45, "rq_win": 3.25, "rq_draw": 3.25, "rq_lose": 1.95, "avg_win": 1.79, "avg_draw": 3.35, "avg_lose": 4.17, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 3.15, "jc_lose": 2.75, "rq_win": 5.05, "rq_draw": 3.85, "rq_lose": 1.49, "avg_win": 2.32, "avg_draw": 3.21, "avg_lose": 2.82, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.45, "jc_lose": 2.47, "rq_win": 4.92, "rq_draw": 4.15, "rq_lose": 1.46, "avg_win": 2.65, "avg_draw": 3.45, "avg_lose": 2.39, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 6.6, "jc_draw": 5.25, "jc_lose": 1.27, "rq_win": 3.0, "rq_draw": 3.9, "rq_lose": 1.86, "avg_win": 6.67, "avg_draw": 4.63, "avg_lose": 1.37, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 3.8, "jc_lose": 5.3, "rq_win": 2.55, "rq_draw": 3.35, "rq_lose": 2.28, "avg_win": 1.81, "avg_draw": 3.51, "avg_lose": 4.06, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.9, "jc_draw": 3.32, "jc_lose": 1.75, "rq_win": 1.83, "rq_draw": 3.35, "rq_lose": 3.52, "avg_win": 3.68, "avg_draw": 3.33, "avg_lose": 1.95, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 3.2, "jc_lose": 3.1, "rq_win": 4.6, "rq_draw": 3.45, "rq_lose": 1.61, "avg_win": 2.64, "avg_draw": 3.28, "avg_lose": 2.59, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.32, "jc_draw": 3.12, "jc_lose": 2.65, "rq_win": 5.25, "rq_draw": 3.95, "rq_lose": 1.46, "avg_win": 2.3, "avg_draw": 3.25, "avg_lose": 2.97, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 3.15, "jc_draw": 3.1, "jc_lose": 2.05, "rq_win": 1.6, "rq_draw": 3.6, "rq_lose": 4.45, "avg_win": 3.3, "avg_draw": 3.3, "avg_lose": 2.07, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 3.65, "jc_draw": 3.7, "jc_lose": 1.71, "rq_win": 1.9, "rq_draw": 3.5, "rq_lose": 3.15, "avg_win": 3.81, "avg_draw": 3.3, "avg_lose": 2.0, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 4.0, "jc_lose": 4.15, "rq_win": 2.64, "rq_draw": 3.65, "rq_lose": 2.1, "avg_win": 1.8, "avg_draw": 3.88, "avg_lose": 3.77, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.45, "jc_lose": 3.52, "rq_win": 3.46, "rq_draw": 3.55, "rq_lose": 1.79, "avg_win": 1.99, "avg_draw": 3.37, "avg_lose": 3.7, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.73, "jc_draw": 3.15, "jc_lose": 4.3, "rq_win": 3.55, "rq_draw": 3.25, "rq_lose": 1.85, "avg_win": 2.07, "avg_draw": 3.3, "avg_lose": 3.33, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.18, "jc_lose": 2.33, "rq_win": 1.46, "rq_draw": 4.0, "rq_lose": 5.15, "avg_win": 3.23, "avg_draw": 3.17, "avg_lose": 2.21, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 3.9, "jc_lose": 7.0, "rq_win": 2.35, "rq_draw": 3.15, "rq_lose": 2.59, "avg_win": 1.57, "avg_draw": 3.56, "avg_lose": 5.7, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.8, "jc_lose": 3.7, "rq_win": 3.0, "rq_draw": 3.7, "rq_lose": 1.9, "avg_win": 1.61, "avg_draw": 4.13, "avg_lose": 4.43, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 4.4, "jc_lose": 4.5, "rq_win": 2.32, "rq_draw": 3.85, "rq_lose": 2.28, "avg_win": 1.74, "avg_draw": 3.94, "avg_lose": 4.07, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.78, "jc_lose": 3.53, "rq_win": 3.08, "rq_draw": 3.75, "rq_lose": 1.86, "avg_win": 1.72, "avg_draw": 3.98, "avg_lose": 4.04, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.65, "jc_lose": 2.9, "rq_win": 3.8, "rq_draw": 3.95, "rq_lose": 1.63, "avg_win": 2.17, "avg_draw": 3.66, "avg_lose": 2.92, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 2.11, "jc_draw": 3.5, "jc_lose": 2.71, "rq_win": 4.02, "rq_draw": 4.1, "rq_lose": 1.57, "avg_win": 2.14, "avg_draw": 3.75, "avg_lose": 2.91, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.34, "jc_draw": 4.6, "jc_lose": 6.05, "rq_win": 2.08, "rq_draw": 3.65, "rq_lose": 2.67, "avg_win": 1.39, "avg_draw": 4.6, "avg_lose": 6.68, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.4, "jc_lose": 3.6, "rq_win": 3.62, "rq_draw": 3.4, "rq_lose": 1.79, "avg_win": 1.76, "avg_draw": 3.69, "avg_lose": 4.09, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.35, "jc_lose": 2.85, "rq_win": 4.25, "rq_draw": 3.85, "rq_lose": 1.58, "avg_win": 2.05, "avg_draw": 3.57, "avg_lose": 3.16, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.6, "jc_lose": 1.95, "rq_win": 1.65, "rq_draw": 3.75, "rq_lose": 3.9, "avg_win": 2.57, "avg_draw": 3.25, "avg_lose": 2.56, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 2, "jc_win": 1.2, "jc_draw": 5.5, "jc_lose": 11.0, "rq_win": 2.15, "rq_draw": 3.9, "rq_lose": 2.45, "avg_win": 1.2, "avg_draw": 5.87, "avg_lose": 12.45, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.15, "jc_lose": 4.35, "rq_win": 3.62, "rq_draw": 3.15, "rq_lose": 1.87, "avg_win": 1.88, "avg_draw": 3.25, "avg_lose": 4.19, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 4.25, "jc_lose": 4.7, "rq_win": 2.43, "rq_draw": 3.65, "rq_lose": 2.25, "avg_win": 1.72, "avg_draw": 4.0, "avg_lose": 3.98, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 2, "jc_win": 1.17, "jc_draw": 6.1, "jc_lose": 9.0, "rq_win": 2.45, "rq_draw": 4.2, "rq_lose": 2.07, "avg_win": 1.3, "avg_draw": 5.35, "avg_lose": 7.46, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.6, "jc_draw": 3.58, "jc_lose": 4.45, "rq_win": 2.88, "rq_draw": 3.45, "rq_lose": 2.03, "avg_win": 1.58, "avg_draw": 4.33, "avg_lose": 4.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.19, "jc_draw": 5.1, "jc_lose": 11.0, "rq_win": 1.8, "rq_draw": 3.4, "rq_lose": 3.58, "avg_win": 1.29, "avg_draw": 4.87, "avg_lose": 9.81, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.74, "jc_draw": 3.05, "jc_lose": 4.4, "rq_win": 3.65, "rq_draw": 3.15, "rq_lose": 1.86, "avg_win": 1.9, "avg_draw": 3.06, "avg_lose": 4.42, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.4, "jc_lose": 5.8, "rq_win": 2.15, "rq_draw": 3.55, "rq_lose": 2.61, "avg_win": 1.63, "avg_draw": 4.1, "avg_lose": 4.54, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 4.8, "jc_lose": 1.32, "rq_win": 2.78, "rq_draw": 3.55, "rq_lose": 2.05, "avg_win": 7.08, "avg_draw": 4.2, "avg_lose": 1.43, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 3.3, "jc_lose": 2.17, "rq_win": 1.54, "rq_draw": 3.75, "rq_lose": 4.7, "avg_win": 2.79, "avg_draw": 3.05, "avg_lose": 2.57, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.54, "jc_draw": 3.9, "jc_lose": 4.5, "rq_win": 2.7, "rq_draw": 3.35, "rq_lose": 2.17, "avg_win": 1.53, "avg_draw": 3.97, "avg_lose": 5.6, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 4.45, "jc_draw": 4.2, "jc_lose": 1.5, "rq_win": 2.25, "rq_draw": 3.6, "rq_lose": 2.46, "avg_win": 4.69, "avg_draw": 4.15, "avg_lose": 1.57, "shenjia": "未输入", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 3.65, "jc_lose": 2.4, "rq_win": 4.7, "rq_draw": 4.15, "rq_lose": 1.48, "avg_win": 2.53, "avg_draw": 3.78, "avg_lose": 2.36, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": -1, "jc_win": 2.82, "jc_draw": 3.1, "jc_lose": 2.21, "rq_win": 1.51, "rq_draw": 3.8, "rq_lose": 4.9, "avg_win": 2.78, "avg_draw": 3.27, "avg_lose": 2.38, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 2.01, "jc_draw": 3.3, "jc_lose": 3.05, "rq_win": 4.15, "rq_draw": 3.65, "rq_lose": 1.63, "avg_win": 1.75, "avg_draw": 3.57, "avg_lose": 4.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 3.96, "jc_draw": 3.0, "jc_lose": 1.84, "rq_win": 1.74, "rq_draw": 3.3, "rq_lose": 4.0, "avg_win": 3.3, "avg_draw": 3.04, "avg_lose": 2.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.86, "jc_draw": 3.45, "jc_lose": 3.32, "rq_win": 3.6, "rq_draw": 3.7, "rq_lose": 1.72, "avg_win": 1.85, "avg_draw": 3.5, "avg_lose": 3.83, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.88, "jc_draw": 3.7, "jc_lose": 1.96, "rq_win": 1.66, "rq_draw": 3.9, "rq_lose": 3.7, "avg_win": 2.84, "avg_draw": 3.62, "avg_lose": 2.11, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 3.35, "jc_draw": 3.35, "jc_lose": 1.88, "rq_win": 1.71, "rq_draw": 3.55, "rq_lose": 3.8, "avg_win": 3.78, "avg_draw": 3.48, "avg_lose": 1.91, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.15, "jc_lose": 2.3, "rq_win": 1.47, "rq_draw": 3.95, "rq_lose": 5.1, "avg_win": 2.72, "avg_draw": 3.21, "avg_lose": 2.48, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 2.85, "jc_draw": 3.15, "jc_lose": 2.17, "rq_win": 1.52, "rq_draw": 3.7, "rq_lose": 5.0, "avg_win": 2.82, "avg_draw": 3.19, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 4.05, "jc_lose": 1.58, "rq_win": 2.08, "rq_draw": 3.7, "rq_lose": 2.64, "avg_win": 3.97, "avg_draw": 3.86, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.85, "jc_lose": 1.64, "rq_win": 1.95, "rq_draw": 3.65, "rq_lose": 2.92, "avg_win": 3.65, "avg_draw": 3.68, "avg_lose": 1.82, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 3.9, "jc_draw": 3.05, "jc_lose": 1.84, "rq_win": 1.75, "rq_draw": 3.25, "rq_lose": 4.0, "avg_win": 4.69, "avg_draw": 3.44, "avg_lose": 1.76, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 1.54, "jc_draw": 3.8, "jc_lose": 4.6, "rq_win": 2.66, "rq_draw": 3.5, "rq_lose": 2.14, "avg_win": 1.66, "avg_draw": 3.72, "avg_lose": 4.42, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.23, "jc_lose": 2.6, "rq_win": 5.1, "rq_draw": 4.1, "rq_lose": 1.45, "avg_win": 2.23, "avg_draw": 3.26, "avg_lose": 3.05, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 2.43, "jc_draw": 3.18, "jc_lose": 2.48, "rq_win": 5.57, "rq_draw": 4.15, "rq_lose": 1.41, "avg_win": 2.56, "avg_draw": 3.22, "avg_lose": 2.56, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.4, "jc_lose": 3.95, "rq_win": 3.25, "rq_draw": 3.45, "rq_lose": 1.88, "avg_win": 1.7, "avg_draw": 3.69, "avg_lose": 4.47, "shenjia": "未输入", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.62, "jc_draw": 3.62, "jc_lose": 4.2, "rq_win": 3.0, "rq_draw": 3.45, "rq_lose": 1.98, "avg_win": 2.05, "avg_draw": 3.44, "avg_lose": 3.23, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 2.43, "jc_draw": 3.65, "jc_lose": 2.25, "rq_win": 1.48, "rq_draw": 4.25, "rq_lose": 4.6, "avg_win": 3.35, "avg_draw": 3.63, "avg_lose": 1.93, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.4, "jc_lose": 3.4, "rq_win": 3.57, "rq_draw": 3.7, "rq_lose": 1.73, "avg_win": 2.05, "avg_draw": 3.65, "avg_lose": 3.18, "shenjia": "未输入", "real_result": "胜", "real_score": "4:2"},
    {"handicap": 1, "jc_win": 2.17, "jc_draw": 3.45, "jc_lose": 2.65, "rq_win": 4.4, "rq_draw": 4.1, "rq_lose": 1.52, "avg_win": 2.37, "avg_draw": 3.53, "avg_lose": 2.72, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.5, "jc_lose": 3.6, "rq_win": 3.35, "rq_draw": 3.6, "rq_lose": 1.81, "avg_win": 1.83, "avg_draw": 3.63, "avg_lose": 3.76, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 4.25, "jc_lose": 4.35, "rq_win": 2.5, "rq_draw": 3.65, "rq_lose": 2.2, "avg_win": 1.63, "avg_draw": 4.26, "avg_lose": 4.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.97, "jc_draw": 3.2, "jc_lose": 3.25, "rq_win": 4.2, "rq_draw": 3.6, "rq_lose": 1.63, "avg_win": 2.09, "avg_draw": 3.38, "avg_lose": 3.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.56, "jc_draw": 3.6, "jc_lose": 4.75, "rq_win": 2.9, "rq_draw": 3.3, "rq_lose": 2.08, "avg_win": 1.7, "avg_draw": 3.69, "avg_lose": 4.4, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "3:3"},
    {"handicap": 1, "jc_win": 1.35, "jc_draw": 4.3, "jc_lose": 6.4, "rq_win": 2.19, "rq_draw": 3.45, "rq_lose": 2.62, "avg_win": 1.59, "avg_draw": 3.98, "avg_lose": 4.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 2, "jc_win": 1.14, "jc_draw": 6.0, "jc_lose": 11.8, "rq_win": 2.62, "rq_draw": 4.0, "rq_lose": 2.01, "avg_win": 1.2, "avg_draw": 6.78, "avg_lose": 11.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.35, "jc_lose": 3.77, "rq_win": 3.55, "rq_draw": 3.4, "rq_lose": 1.81, "avg_win": 1.7, "avg_draw": 3.57, "avg_lose": 4.59, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.13, "jc_draw": 3.12, "jc_lose": 2.95, "rq_win": 4.9, "rq_draw": 3.7, "rq_lose": 1.53, "avg_win": 2.26, "avg_draw": 3.14, "avg_lose": 3.07, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 2.53, "jc_draw": 3.04, "jc_lose": 2.47, "rq_win": 1.4, "rq_draw": 4.0, "rq_lose": 6.05, "avg_win": 2.68, "avg_draw": 2.94, "avg_lose": 2.57, "shenjia": "未输入", "real_result": "负", "real_score": "0:4"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.35, "jc_lose": 1.81, "rq_win": 1.77, "rq_draw": 3.5, "rq_lose": 3.6, "avg_win": 3.75, "avg_draw": 3.42, "avg_lose": 1.9, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": 1, "jc_win": 1.86, "jc_draw": 3.35, "jc_lose": 3.42, "rq_win": 3.75, "rq_draw": 3.55, "rq_lose": 1.72, "avg_win": 1.85, "avg_draw": 3.46, "avg_lose": 3.89, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:2"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.02, "jc_lose": 1.86, "rq_win": 1.72, "rq_draw": 3.35, "rq_lose": 4.0, "avg_win": 4.45, "avg_draw": 3.18, "avg_lose": 1.82, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.45, "jc_lose": 2.77, "rq_win": 4.32, "rq_draw": 3.95, "rq_lose": 1.55, "avg_win": 2.19, "avg_draw": 3.4, "avg_lose": 3.04, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 3.16, "jc_lose": 3.2, "rq_win": 4.15, "rq_draw": 3.7, "rq_lose": 1.62, "avg_win": 2.21, "avg_draw": 3.19, "avg_lose": 3.05, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.38, "jc_lose": 2.02, "rq_win": 1.62, "rq_draw": 3.8, "rq_lose": 4.02, "avg_win": 3.07, "avg_draw": 3.6, "avg_lose": 2.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:3"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.25, "jc_lose": 3.48, "rq_win": 3.72, "rq_draw": 3.55, "rq_lose": 1.73, "avg_win": 2.0, "avg_draw": 3.4, "avg_lose": 3.41, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.45, "jc_lose": 2.2, "rq_win": 1.51, "rq_draw": 4.0, "rq_lose": 4.6, "avg_win": 2.69, "avg_draw": 3.42, "avg_lose": 2.33, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 4.18, "jc_draw": 3.95, "jc_lose": 1.57, "rq_win": 2.08, "rq_draw": 3.7, "rq_lose": 2.65, "avg_win": 4.73, "avg_draw": 4.24, "avg_lose": 1.57, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": 1, "jc_win": 1.91, "jc_draw": 3.1, "jc_lose": 3.55, "rq_win": 4.1, "rq_draw": 3.45, "rq_lose": 1.68, "avg_win": 2.17, "avg_draw": 3.22, "avg_lose": 3.3, "shenjia": "未输入", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 5.35, "jc_draw": 4.5, "jc_lose": 1.39, "rq_win": 2.52, "rq_draw": 3.75, "rq_lose": 2.15, "avg_win": 4.5, "avg_draw": 3.97, "avg_lose": 1.6, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.55, "jc_lose": 3.25, "rq_win": 3.45, "rq_draw": 3.75, "rq_lose": 1.75, "avg_win": 1.79, "avg_draw": 3.81, "avg_lose": 3.83, "shenjia": "未输入", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 2.12, "jc_draw": 3.2, "jc_lose": 2.9, "rq_win": 4.4, "rq_draw": 3.9, "rq_lose": 1.55, "avg_win": 2.46, "avg_draw": 3.14, "avg_lose": 2.75, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.63, "jc_draw": 3.45, "jc_lose": 2.18, "rq_win": 1.51, "rq_draw": 4.0, "rq_lose": 4.6, "avg_win": 2.31, "avg_draw": 3.61, "avg_lose": 2.66, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 2.95, "jc_lose": 2.22, "rq_win": 1.5, "rq_draw": 3.65, "rq_lose": 5.3, "avg_win": 3.13, "avg_draw": 3.23, "avg_lose": 2.25, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 2.6, "jc_lose": 3.38, "rq_win": 5.8, "rq_draw": 3.5, "rq_lose": 1.49, "avg_win": 2.3, "avg_draw": 2.87, "avg_lose": 3.39, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.36, "jc_draw": 4.4, "jc_lose": 6.0, "rq_win": 2.15, "rq_draw": 3.55, "rq_lose": 2.62, "avg_win": 1.44, "avg_draw": 4.47, "avg_lose": 5.86, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 5.05, "jc_draw": 4.6, "jc_lose": 1.4, "rq_win": 2.45, "rq_draw": 3.95, "rq_lose": 2.14, "avg_win": 4.54, "avg_draw": 4.34, "avg_lose": 1.56, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 3.95, "jc_lose": 4.2, "rq_win": 2.68, "rq_draw": 3.7, "rq_lose": 2.06, "avg_win": 1.83, "avg_draw": 3.83, "avg_lose": 3.64, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 2.9, "jc_lose": 3.05, "rq_win": 5.2, "rq_draw": 3.65, "rq_lose": 1.51, "avg_win": 2.3, "avg_draw": 3.13, "avg_lose": 3.09, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 9.2, "jc_draw": 4.85, "jc_lose": 1.23, "rq_win": 3.25, "rq_draw": 3.55, "rq_lose": 1.85, "avg_win": 8.7, "avg_draw": 5.42, "avg_lose": 1.3, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 2.8, "jc_lose": 2.54, "rq_win": 1.38, "rq_draw": 4.1, "rq_lose": 6.2, "avg_win": 2.65, "avg_draw": 3.07, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.99, "jc_draw": 3.05, "jc_lose": 3.35, "rq_win": 4.3, "rq_draw": 3.5, "rq_lose": 1.64, "avg_win": 1.94, "avg_draw": 3.18, "avg_lose": 3.91, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -1, "jc_win": 3.06, "jc_draw": 3.0, "jc_lose": 2.13, "rq_win": 1.54, "rq_draw": 3.6, "rq_lose": 4.95, "avg_win": 3.09, "avg_draw": 3.13, "avg_lose": 2.26, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.72, "jc_lose": 4.05, "rq_win": 2.9, "rq_draw": 3.6, "rq_lose": 1.99, "avg_win": 1.68, "avg_draw": 3.92, "avg_lose": 4.29, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 3.8, "jc_lose": 5.7, "rq_win": 2.48, "rq_draw": 3.3, "rq_lose": 2.37, "avg_win": 1.57, "avg_draw": 3.78, "avg_lose": 5.29, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.16, "jc_draw": 2.95, "jc_lose": 3.05, "rq_win": 5.0, "rq_draw": 3.65, "rq_lose": 1.53, "avg_win": 2.27, "avg_draw": 3.13, "avg_lose": 3.15, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.4, "jc_draw": 2.95, "jc_lose": 2.68, "rq_win": 5.8, "rq_draw": 3.95, "rq_lose": 1.42, "avg_win": 2.32, "avg_draw": 3.07, "avg_lose": 2.98, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.5, "jc_draw": 3.4, "jc_lose": 2.3, "rq_win": 1.46, "rq_draw": 4.1, "rq_lose": 5.0, "avg_win": 2.69, "avg_draw": 3.67, "avg_lose": 2.28, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": -1, "jc_win": 4.35, "jc_draw": 3.42, "jc_lose": 1.65, "rq_win": 1.95, "rq_draw": 3.35, "rq_lose": 3.15, "avg_win": 4.56, "avg_draw": 3.52, "avg_lose": 1.7, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 2.97, "jc_lose": 3.05, "rq_win": 4.85, "rq_draw": 3.65, "rq_lose": 1.54, "avg_win": 2.03, "avg_draw": 3.24, "avg_lose": 3.44, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.75, "jc_lose": 4.02, "rq_win": 2.92, "rq_draw": 3.55, "rq_lose": 1.98, "avg_win": 1.71, "avg_draw": 3.81, "avg_lose": 4.12, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 2.67, "jc_draw": 3.28, "jc_lose": 2.22, "rq_win": 1.51, "rq_draw": 3.95, "rq_lose": 4.7, "avg_win": 2.77, "avg_draw": 3.28, "avg_lose": 2.35, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.5, "jc_lose": 5.65, "rq_win": 2.15, "rq_draw": 3.68, "rq_lose": 2.55, "avg_win": 1.46, "avg_draw": 4.59, "avg_lose": 5.73, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 6.2, "jc_lose": 10.2, "rq_win": 2.49, "rq_draw": 4.05, "rq_lose": 2.08, "avg_win": 1.25, "avg_draw": 5.97, "avg_lose": 8.9, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 1.28, "jc_draw": 5.1, "jc_lose": 6.6, "rq_win": 1.87, "rq_draw": 3.9, "rq_lose": 2.96, "avg_win": 1.4, "avg_draw": 4.93, "avg_lose": 6.1, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 2.45, "jc_draw": 3.75, "jc_lose": 2.2, "rq_win": 1.52, "rq_draw": 4.25, "rq_lose": 4.25, "avg_win": 2.51, "avg_draw": 3.66, "avg_lose": 2.4, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "5:5"},
    {"handicap": 1, "jc_win": 2.37, "jc_draw": 3.17, "jc_lose": 2.55, "rq_win": 5.4, "rq_draw": 4.0, "rq_lose": 1.44, "avg_win": 2.16, "avg_draw": 3.58, "avg_lose": 3.11, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.15, "jc_lose": 2.2, "rq_win": 1.52, "rq_draw": 3.85, "rq_lose": 4.75, "avg_win": 3.32, "avg_draw": 3.45, "avg_lose": 2.03, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.23, "jc_lose": 2.62, "rq_win": 5.2, "rq_draw": 3.9, "rq_lose": 1.47, "avg_win": 2.48, "avg_draw": 3.33, "avg_lose": 2.79, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -1, "jc_win": 4.22, "jc_draw": 3.85, "jc_lose": 1.58, "rq_win": 2.05, "rq_draw": 3.55, "rq_lose": 2.78, "avg_win": 4.2, "avg_draw": 3.86, "avg_lose": 1.71, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 3.45, "jc_lose": 2.75, "rq_win": 4.25, "rq_draw": 3.9, "rq_lose": 1.57, "avg_win": 2.14, "avg_draw": 3.57, "avg_lose": 2.99, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.7, "jc_lose": 6.1, "rq_win": 2.0, "rq_draw": 3.8, "rq_lose": 2.74, "avg_win": 1.53, "avg_draw": 4.31, "avg_lose": 5.15, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 2.98, "jc_draw": 3.38, "jc_lose": 2.01, "rq_win": 1.62, "rq_draw": 3.82, "rq_lose": 4.0, "avg_win": 2.8, "avg_draw": 3.36, "avg_lose": 2.29, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 3.2, "jc_draw": 3.45, "jc_lose": 1.9, "rq_win": 1.69, "rq_draw": 3.7, "rq_lose": 3.75, "avg_win": 3.46, "avg_draw": 3.33, "avg_lose": 2.04, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.6, "jc_lose": 3.0, "rq_win": 3.8, "rq_draw": 3.8, "rq_lose": 1.66, "avg_win": 2.19, "avg_draw": 3.42, "avg_lose": 2.95, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.5, "jc_lose": 5.65, "rq_win": 2.13, "rq_draw": 3.75, "rq_lose": 2.54, "avg_win": 1.51, "avg_draw": 4.27, "avg_lose": 5.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 3.45, "jc_lose": 2.75, "rq_win": 4.3, "rq_draw": 3.85, "rq_lose": 1.57, "avg_win": 1.65, "avg_draw": 3.95, "avg_lose": 4.49, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 1.59, "jc_draw": 3.46, "jc_lose": 4.75, "rq_win": 3.05, "rq_draw": 3.2, "rq_lose": 2.05, "avg_win": 1.88, "avg_draw": 3.47, "avg_lose": 3.89, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 2.24, "jc_draw": 3.35, "jc_lose": 2.6, "rq_win": 4.5, "rq_draw": 4.15, "rq_lose": 1.5, "avg_win": 2.29, "avg_draw": 3.53, "avg_lose": 2.74, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.21, "jc_draw": 6.0, "jc_lose": 8.05, "rq_win": 1.71, "rq_draw": 4.0, "rq_lose": 3.4, "avg_win": 1.23, "avg_draw": 6.0, "avg_lose": 9.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 2.27, "jc_draw": 3.3, "jc_lose": 2.59, "rq_win": 4.8, "rq_draw": 4.15, "rq_lose": 1.47, "avg_win": 2.37, "avg_draw": 3.39, "avg_lose": 2.63, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.1, "jc_lose": 3.05, "rq_win": 4.6, "rq_draw": 3.6, "rq_lose": 1.58, "avg_win": 2.39, "avg_draw": 3.14, "avg_lose": 2.89, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 1.55, "jc_draw": 3.65, "jc_lose": 4.75, "rq_win": 2.81, "rq_draw": 3.25, "rq_lose": 2.15, "avg_win": 1.94, "avg_draw": 3.4, "avg_lose": 3.47, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "冷门预警", "match_context": "Z=2.8600; Y=1.2200; X=1.0900; cold_risk=26.3%; dev_level=显著偏离", "match_id": "#618"},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.7, "jc_lose": 3.6, "rq_win": 3.1, "rq_draw": 3.6, "rq_lose": 1.89, "avg_win": 1.95, "avg_draw": 3.4, "avg_lose": 3.62, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.7, "jc_lose": 3.8, "rq_win": 3.1, "rq_draw": 3.45, "rq_lose": 1.94, "avg_win": 1.85, "avg_draw": 3.53, "avg_lose": 3.88, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": -1, "jc_win": 3.7, "jc_draw": 3.27, "jc_lose": 1.81, "rq_win": 1.77, "rq_draw": 3.45, "rq_lose": 3.65, "avg_win": 3.63, "avg_draw": 3.33, "avg_lose": 2.0, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.5, "jc_lose": 4.35, "rq_win": 3.12, "rq_draw": 3.25, "rq_lose": 2.0, "avg_win": 1.82, "avg_draw": 3.58, "avg_lose": 3.97, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 3.72, "jc_draw": 3.15, "jc_lose": 1.84, "rq_win": 1.75, "rq_draw": 3.4, "rq_lose": 3.8, "avg_win": 3.72, "avg_draw": 3.32, "avg_lose": 1.97, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4"},
    {"handicap": 1, "jc_win": 1.55, "jc_draw": 3.78, "jc_lose": 4.55, "rq_win": 2.75, "rq_draw": 3.43, "rq_lose": 2.11, "avg_win": 1.73, "avg_draw": 3.78, "avg_lose": 4.27, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.12, "jc_lose": 2.4, "rq_win": 1.43, "rq_draw": 4.05, "rq_lose": 5.45, "avg_win": 2.58, "avg_draw": 2.96, "avg_lose": 2.74, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 2.08, "jc_draw": 3.02, "jc_lose": 3.15, "rq_win": 4.6, "rq_draw": 3.6, "rq_lose": 1.58, "avg_win": 2.11, "avg_draw": 3.24, "avg_lose": 3.29, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.39, "jc_draw": 4.3, "jc_lose": 5.7, "rq_win": 2.26, "rq_draw": 3.4, "rq_lose": 2.55, "avg_win": 1.55, "avg_draw": 3.94, "avg_lose": 5.09, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 2.95, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.7, "rq_lose": 4.9, "avg_win": 2.87, "avg_draw": 3.12, "avg_lose": 2.44, "shenjia": "未输入", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.7, "jc_lose": 4.2, "rq_win": 2.86, "rq_draw": 3.55, "rq_lose": 2.01, "avg_win": 1.72, "avg_draw": 3.73, "avg_lose": 4.16, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 2.36, "jc_draw": 2.65, "jc_lose": 3.05, "rq_win": 5.65, "rq_draw": 3.8, "rq_lose": 1.45, "avg_win": 2.64, "avg_draw": 2.85, "avg_lose": 2.8, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 2.63, "jc_draw": 3.0, "jc_lose": 2.41, "rq_win": 1.43, "rq_draw": 3.95, "rq_lose": 5.65, "avg_win": 2.51, "avg_draw": 3.05, "avg_lose": 2.7, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.2, "jc_draw": 5.1, "jc_lose": 10.0, "rq_win": 1.74, "rq_draw": 3.6, "rq_lose": 3.61, "avg_win": 1.24, "avg_draw": 5.56, "avg_lose": 11.4, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.7, "jc_lose": 4.45, "rq_win": 2.76, "rq_draw": 3.5, "rq_lose": 2.08, "avg_win": 1.59, "avg_draw": 3.9, "avg_lose": 5.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.35, "jc_draw": 3.5, "jc_lose": 2.4, "rq_win": 4.85, "rq_draw": 4.3, "rq_lose": 1.45, "avg_win": 2.56, "avg_draw": 3.71, "avg_lose": 2.44, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": -1, "jc_win": 3.11, "jc_draw": 2.9, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.55, "rq_lose": 5.15, "avg_win": 2.99, "avg_draw": 2.97, "avg_lose": 2.44, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "3:3"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 3.9, "jc_lose": 6.3, "rq_win": 2.36, "rq_draw": 3.25, "rq_lose": 2.51, "avg_win": 1.42, "avg_draw": 4.29, "avg_lose": 7.1, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -1, "jc_win": 2.81, "jc_draw": 3.5, "jc_lose": 2.05, "rq_win": 1.58, "rq_draw": 3.95, "rq_lose": 4.12, "avg_win": 2.94, "avg_draw": 3.63, "avg_lose": 2.1, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.55, "jc_lose": 3.85, "rq_win": 3.12, "rq_draw": 3.5, "rq_lose": 1.91, "avg_win": 1.7, "avg_draw": 3.66, "avg_lose": 4.37, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 4.35, "jc_lose": 4.55, "rq_win": 2.43, "rq_draw": 3.65, "rq_lose": 2.25, "avg_win": 1.66, "avg_draw": 4.05, "avg_lose": 4.15, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "3:3"},
    {"handicap": 1, "jc_win": 1.76, "jc_draw": 3.8, "jc_lose": 3.35, "rq_win": 3.22, "rq_draw": 3.8, "rq_lose": 1.8, "avg_win": 1.68, "avg_draw": 3.97, "avg_lose": 4.11, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": -1, "jc_win": 3.46, "jc_draw": 3.55, "jc_lose": 1.79, "rq_win": 1.78, "rq_draw": 3.65, "rq_lose": 3.4, "avg_win": 3.43, "avg_draw": 3.59, "avg_lose": 1.93, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:6"},
    {"handicap": 1, "jc_win": 1.38, "jc_draw": 4.5, "jc_lose": 5.5, "rq_win": 2.13, "rq_draw": 3.68, "rq_lose": 2.58, "avg_win": 1.34, "avg_draw": 4.79, "avg_lose": 7.05, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "6:0"},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 3.7, "jc_lose": 5.45, "rq_win": 2.63, "rq_draw": 3.2, "rq_lose": 2.3, "avg_win": 1.83, "avg_draw": 3.26, "avg_lose": 4.21, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.25, "jc_lose": 3.5, "rq_win": 3.82, "rq_draw": 3.45, "rq_lose": 1.73, "avg_win": 1.88, "avg_draw": 3.64, "avg_lose": 3.6, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.15, "jc_lose": 8.75, "rq_win": 1.77, "rq_draw": 3.7, "rq_lose": 3.4, "avg_win": 1.49, "avg_draw": 4.23, "avg_lose": 5.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.47, "jc_lose": 3.02, "rq_win": 3.95, "rq_draw": 3.65, "rq_lose": 1.66, "avg_win": 2.07, "avg_draw": 3.54, "avg_lose": 3.08, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.25, "jc_draw": 3.5, "jc_lose": 2.52, "rq_win": 4.5, "rq_draw": 4.2, "rq_lose": 1.5, "avg_win": 2.25, "avg_draw": 3.71, "avg_lose": 2.65, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 5.05, "jc_draw": 3.05, "jc_lose": 1.66, "rq_win": 1.95, "rq_draw": 3.2, "rq_lose": 3.3, "avg_win": 4.35, "avg_draw": 3.26, "avg_lose": 1.84, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 2.7, "jc_draw": 3.6, "jc_lose": 2.08, "rq_win": 1.57, "rq_draw": 4.0, "rq_lose": 4.12, "avg_win": 2.72, "avg_draw": 3.78, "avg_lose": 2.21, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 2.57, "jc_draw": 3.4, "jc_lose": 2.24, "rq_win": 1.48, "rq_draw": 4.05, "rq_lose": 4.83, "avg_win": 2.67, "avg_draw": 3.64, "avg_lose": 2.29, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 3.35, "jc_draw": 3.25, "jc_lose": 1.91, "rq_win": 1.68, "rq_draw": 3.6, "rq_lose": 3.9, "avg_win": 2.55, "avg_draw": 3.23, "avg_lose": 2.66, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": -1, "jc_win": 4.15, "jc_draw": 3.85, "jc_lose": 1.59, "rq_win": 2.04, "rq_draw": 3.55, "rq_lose": 2.8, "avg_win": 3.09, "avg_draw": 3.63, "avg_lose": 2.12, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.77, "jc_lose": 4.75, "rq_win": 2.65, "rq_draw": 3.47, "rq_lose": 2.16, "avg_win": 1.63, "avg_draw": 4.14, "avg_lose": 4.47, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.15, "jc_lose": 5.75, "rq_win": 2.31, "rq_draw": 3.45, "rq_lose": 2.46, "avg_win": 1.69, "avg_draw": 3.82, "avg_lose": 4.47, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "7:0"},
    {"handicap": -2, "jc_win": 10.0, "jc_draw": 5.72, "jc_lose": 1.17, "rq_win": 1.98, "rq_draw": 3.95, "rq_lose": 2.7, "avg_win": 10.9, "avg_draw": 6.11, "avg_lose": 1.22, "shenjia": "未输入", "real_result": "负", "real_score": "0:3"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.77, "jc_lose": 4.15, "rq_win": 2.96, "rq_draw": 3.4, "rq_lose": 2.01, "avg_win": 1.97, "avg_draw": 3.51, "avg_lose": 3.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 7.36, "jc_lose": 15.37, "rq_win": 2.18, "rq_draw": 4.0, "rq_lose": 2.38, "avg_win": 1.15, "avg_draw": 7.0, "avg_lose": 13.0, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.1, "jc_lose": 6.45, "rq_win": 2.32, "rq_draw": 3.22, "rq_lose": 2.58, "avg_win": 1.64, "avg_draw": 3.73, "avg_lose": 4.88, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:2"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.05, "jc_lose": 6.55, "rq_win": 2.33, "rq_draw": 3.25, "rq_lose": 2.55, "avg_win": 1.49, "avg_draw": 4.05, "avg_lose": 6.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -2, "jc_win": 10.0, "jc_draw": 6.0, "jc_lose": 1.16, "rq_win": 2.08, "rq_draw": 3.92, "rq_lose": 2.54, "avg_win": 10.16, "avg_draw": 6.36, "avg_lose": 1.21, "shenjia": "未输入", "real_result": "负", "real_score": "0:4"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.25, "jc_lose": 2.6, "rq_win": 4.85, "rq_draw": 4.05, "rq_lose": 1.48, "avg_win": 2.43, "avg_draw": 3.34, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.95, "jc_lose": 3.5, "rq_win": 3.0, "rq_draw": 3.8, "rq_lose": 1.88, "avg_win": 1.68, "avg_draw": 4.18, "avg_lose": 3.98, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 4.3, "jc_lose": 4.82, "rq_win": 2.34, "rq_draw": 3.75, "rq_lose": 2.3, "avg_win": 2.26, "avg_draw": 3.65, "avg_lose": 2.74, "shenjia": "未输入", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.27, "jc_draw": 3.15, "jc_lose": 2.7, "rq_win": 5.15, "rq_draw": 3.85, "rq_lose": 1.48, "avg_win": 2.49, "avg_draw": 3.25, "avg_lose": 2.67, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.74, "jc_draw": 3.85, "jc_lose": 3.4, "rq_win": 3.05, "rq_draw": 3.8, "rq_lose": 1.86, "avg_win": 1.93, "avg_draw": 3.71, "avg_lose": 3.25, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2"},
    {"handicap": 1, "jc_win": 1.65, "jc_draw": 3.75, "jc_lose": 3.9, "rq_win": 2.95, "rq_draw": 3.6, "rq_lose": 1.95, "avg_win": 1.7, "avg_draw": 4.15, "avg_lose": 4.12, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:0"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 3.26, "jc_lose": 3.1, "rq_win": 4.2, "rq_draw": 3.65, "rq_lose": 1.62, "avg_win": 2.14, "avg_draw": 3.24, "avg_lose": 3.33, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 3.3, "jc_lose": 3.02, "rq_win": 4.2, "rq_draw": 3.7, "rq_lose": 1.61, "avg_win": 2.18, "avg_draw": 3.35, "avg_lose": 3.0, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 2.96, "jc_lose": 2.91, "rq_win": 5.31, "rq_draw": 3.7, "rq_lose": 1.49, "avg_win": 2.41, "avg_draw": 3.16, "avg_lose": 2.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 3.3, "jc_lose": 3.0, "rq_win": 4.1, "rq_draw": 3.8, "rq_lose": 1.61, "avg_win": 2.06, "avg_draw": 3.44, "avg_lose": 3.23, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 3.9, "jc_draw": 3.45, "jc_lose": 1.72, "rq_win": 1.87, "rq_draw": 3.48, "rq_lose": 3.25, "avg_win": 3.84, "avg_draw": 3.35, "avg_lose": 1.86, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:7"},
    {"handicap": -1, "jc_win": 8.9, "jc_draw": 5.1, "jc_lose": 1.22, "rq_win": 3.32, "rq_draw": 3.8, "rq_lose": 1.77, "avg_win": 6.61, "avg_draw": 4.5, "avg_lose": 1.43, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.18, "jc_lose": 2.65, "rq_win": 4.95, "rq_draw": 4.05, "rq_lose": 1.47, "avg_win": 1.81, "avg_draw": 3.64, "avg_lose": 4.17, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.83, "jc_draw": 3.52, "jc_lose": 3.35, "rq_win": 3.55, "rq_draw": 3.65, "rq_lose": 1.75, "avg_win": 2.19, "avg_draw": 3.41, "avg_lose": 2.98, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.06, "jc_draw": 3.1, "jc_lose": 3.12, "rq_win": 4.5, "rq_draw": 3.65, "rq_lose": 1.58, "avg_win": 2.06, "avg_draw": 3.51, "avg_lose": 3.43, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.15, "jc_lose": 3.0, "rq_win": 4.6, "rq_draw": 3.7, "rq_lose": 1.56, "avg_win": 2.19, "avg_draw": 3.46, "avg_lose": 3.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 3.05, "jc_lose": 2.7, "rq_win": 5.4, "rq_draw": 3.95, "rq_lose": 1.45, "avg_win": 2.67, "avg_draw": 3.3, "avg_lose": 2.56, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.4, "jc_draw": 3.12, "jc_lose": 2.55, "rq_win": 5.4, "rq_draw": 4.1, "rq_lose": 1.43, "avg_win": 2.47, "avg_draw": 3.56, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 4.75, "jc_draw": 4.2, "jc_lose": 1.47, "rq_win": 2.3, "rq_draw": 3.65, "rq_lose": 2.38, "avg_win": 4.09, "avg_draw": 4.01, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.25, "jc_lose": 3.75, "rq_win": 3.7, "rq_draw": 3.4, "rq_lose": 1.78, "avg_win": 2.07, "avg_draw": 3.26, "avg_lose": 3.51, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 1.6, "jc_draw": 3.2, "jc_lose": 5.25, "rq_win": 3.15, "rq_draw": 3.15, "rq_lose": 2.03, "avg_win": 1.6, "avg_draw": 3.72, "avg_lose": 5.58, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.45, "jc_lose": 6.55, "rq_win": 2.1, "rq_draw": 3.5, "rq_lose": 2.72, "avg_win": 1.52, "avg_draw": 4.25, "avg_lose": 5.69, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.35, "jc_lose": 2.66, "rq_win": 4.6, "rq_draw": 4.0, "rq_lose": 1.51, "avg_win": 2.55, "avg_draw": 3.57, "avg_lose": 2.57, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 4.65, "jc_draw": 3.45, "jc_lose": 1.6, "rq_win": 2.01, "rq_draw": 3.25, "rq_lose": 3.1, "avg_win": 4.4, "avg_draw": 3.4, "avg_lose": 1.8, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.35, "jc_draw": 2.95, "jc_lose": 2.75, "rq_win": 5.5, "rq_draw": 3.9, "rq_lose": 1.45, "avg_win": 2.34, "avg_draw": 3.15, "avg_lose": 3.01, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 4.28, "jc_lose": 1.55, "rq_win": 2.13, "rq_draw": 3.8, "rq_lose": 2.52, "avg_win": 4.32, "avg_draw": 4.46, "avg_lose": 1.64, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": -1, "jc_win": 4.45, "jc_draw": 3.2, "jc_lose": 1.69, "rq_win": 1.9, "rq_draw": 3.25, "rq_lose": 3.4, "avg_win": 5.62, "avg_draw": 3.7, "avg_lose": 1.59, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 2.8, "jc_lose": 3.0, "rq_win": 5.7, "rq_draw": 3.65, "rq_lose": 1.47, "avg_win": 2.38, "avg_draw": 3.07, "avg_lose": 2.99, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.94, "jc_draw": 3.25, "jc_lose": 3.27, "rq_win": 3.95, "rq_draw": 3.6, "rq_lose": 1.67, "avg_win": 2.2, "avg_draw": 3.45, "avg_lose": 3.06, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.61, "jc_draw": 3.25, "jc_lose": 2.28, "rq_win": 1.48, "rq_draw": 4.05, "rq_lose": 4.85, "avg_win": 3.62, "avg_draw": 3.61, "avg_lose": 1.93, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 6.3, "jc_draw": 4.45, "jc_lose": 1.34, "rq_win": 2.7, "rq_draw": 3.45, "rq_lose": 2.13, "avg_win": 4.94, "avg_draw": 3.98, "avg_lose": 1.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.39, "jc_draw": 4.35, "jc_lose": 5.55, "rq_win": 2.16, "rq_draw": 3.65, "rq_lose": 2.55, "avg_win": 1.48, "avg_draw": 4.53, "avg_lose": 5.63, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:0"},
    {"handicap": 1, "jc_win": 2.45, "jc_draw": 3.0, "jc_lose": 2.58, "rq_win": 5.9, "rq_draw": 4.0, "rq_lose": 1.41, "avg_win": 2.66, "avg_draw": 3.06, "avg_lose": 2.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.69, "jc_lose": 3.48, "rq_win": 3.1, "rq_draw": 3.8, "rq_lose": 1.84, "avg_win": 1.57, "avg_draw": 4.17, "avg_lose": 4.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.3, "jc_lose": 3.7, "rq_win": 3.6, "rq_draw": 3.45, "rq_lose": 1.78, "avg_win": 1.73, "avg_draw": 3.45, "avg_lose": 4.57, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.1, "jc_lose": 2.37, "rq_win": 1.43, "rq_draw": 4.15, "rq_lose": 5.3, "avg_win": 2.78, "avg_draw": 3.3, "avg_lose": 2.43, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.3, "jc_lose": 2.13, "rq_win": 1.54, "rq_draw": 3.95, "rq_lose": 4.4, "avg_win": 2.49, "avg_draw": 3.22, "avg_lose": 2.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.35, "jc_lose": 2.28, "rq_win": 1.48, "rq_draw": 4.15, "rq_lose": 4.7, "avg_win": 3.53, "avg_draw": 3.67, "avg_lose": 1.9, "shenjia": "未输入", "real_result": "负", "real_score": "4:6", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8900; Y=1.4400; X=2.6000; cold_risk=11.1%; dev_level=轻微偏离", "match_id": "#638"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.4, "jc_lose": 5.32, "rq_win": 2.26, "rq_draw": 3.55, "rq_lose": 2.47, "avg_win": 1.59, "avg_draw": 4.02, "avg_lose": 4.61, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 1.24, "jc_draw": 5.42, "jc_lose": 7.2, "rq_win": 1.77, "rq_draw": 4.05, "rq_lose": 3.15, "avg_win": 1.42, "avg_draw": 4.83, "avg_lose": 6.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:1"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.8, "jc_lose": 5.9, "rq_win": 2.0, "rq_draw": 3.8, "rq_lose": 2.74, "avg_win": 1.44, "avg_draw": 4.95, "avg_lose": 5.72, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 3.4, "jc_lose": 1.58, "rq_win": 2.08, "rq_draw": 3.2, "rq_lose": 2.98, "avg_win": 5.35, "avg_draw": 3.82, "avg_lose": 1.61, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.6, "jc_lose": 1.69, "rq_win": 1.89, "rq_draw": 3.6, "rq_lose": 3.1, "avg_win": 4.34, "avg_draw": 3.93, "avg_lose": 1.64, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:4"},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 3.6, "jc_lose": 4.65, "rq_win": 2.9, "rq_draw": 3.3, "rq_lose": 2.08, "avg_win": 1.79, "avg_draw": 3.63, "avg_lose": 4.15, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 1.3, "jc_draw": 4.75, "jc_lose": 6.7, "rq_win": 2.0, "rq_draw": 3.6, "rq_lose": 2.85, "avg_win": 1.48, "avg_draw": 4.35, "avg_lose": 5.53, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -2, "jc_win": 10.5, "jc_draw": 6.4, "jc_lose": 1.14, "rq_win": 2.09, "rq_draw": 4.15, "rq_lose": 2.44, "avg_win": 5.66, "avg_draw": 4.41, "avg_lose": 1.48, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:5"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.5, "jc_lose": 1.77, "rq_win": 1.83, "rq_draw": 3.65, "rq_lose": 3.25, "avg_win": 4.02, "avg_draw": 3.73, "avg_lose": 1.8, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 3.35, "jc_draw": 3.77, "jc_lose": 1.77, "rq_win": 1.82, "rq_draw": 3.9, "rq_lose": 3.1, "avg_win": 2.86, "avg_draw": 3.81, "avg_lose": 2.18, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 7.0, "jc_draw": 4.5, "jc_lose": 1.31, "rq_win": 2.82, "rq_draw": 3.45, "rq_lose": 2.06, "avg_win": 7.03, "avg_draw": 4.32, "avg_lose": 1.42, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.92, "jc_draw": 3.05, "jc_lose": 3.57, "rq_win": 4.3, "rq_draw": 3.4, "rq_lose": 1.66, "avg_win": 2.38, "avg_draw": 3.15, "avg_lose": 2.97, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 2.48, "jc_draw": 2.83, "jc_lose": 2.68, "rq_win": 6.5, "rq_draw": 3.85, "rq_lose": 1.4, "avg_win": 2.84, "avg_draw": 2.95, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 2.88, "jc_lose": 3.8, "rq_win": 4.2, "rq_draw": 3.4, "rq_lose": 1.68, "avg_win": 1.88, "avg_draw": 2.99, "avg_lose": 4.7, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 4.67, "jc_draw": 3.65, "jc_lose": 1.56, "rq_win": 2.07, "rq_draw": 3.32, "rq_lose": 2.9, "avg_win": 4.13, "avg_draw": 3.53, "avg_lose": 1.83, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.43, "jc_draw": 4.0, "jc_lose": 5.55, "rq_win": 2.42, "rq_draw": 3.35, "rq_lose": 2.4, "avg_win": 1.52, "avg_draw": 4.08, "avg_lose": 5.82, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 8.25, "jc_draw": 5.3, "jc_lose": 1.22, "rq_win": 3.35, "rq_draw": 3.9, "rq_lose": 1.74, "avg_win": 7.72, "avg_draw": 5.32, "avg_lose": 1.32, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:5"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 5.7, "jc_lose": 11.8, "rq_win": 2.75, "rq_draw": 3.95, "rq_lose": 1.95, "avg_win": 1.19, "avg_draw": 6.49, "avg_lose": 13.33, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.69, "jc_draw": 3.45, "jc_lose": 4.05, "rq_win": 3.3, "rq_draw": 3.3, "rq_lose": 1.91, "avg_win": 2.01, "avg_draw": 3.3, "avg_lose": 3.52, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.08, "jc_draw": 2.98, "jc_lose": 3.2, "rq_win": 4.75, "rq_draw": 3.55, "rq_lose": 1.57, "avg_win": 2.05, "avg_draw": 3.15, "avg_lose": 3.66, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 5.2, "jc_draw": 4.5, "jc_lose": 1.4, "rq_win": 2.47, "rq_draw": 3.77, "rq_lose": 2.18, "avg_win": 4.58, "avg_draw": 4.13, "avg_lose": 1.61, "shenjia": "未输入", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 2.7, "jc_draw": 3.65, "jc_lose": 2.07, "rq_win": 1.56, "rq_draw": 4.1, "rq_lose": 4.1, "avg_win": 2.54, "avg_draw": 3.59, "avg_lose": 2.37, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": 1, "jc_win": 1.62, "jc_draw": 3.36, "jc_lose": 4.66, "rq_win": 3.1, "rq_draw": 3.26, "rq_lose": 2.0, "avg_win": 1.7, "avg_draw": 3.68, "avg_lose": 4.59, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.3, "jc_lose": 6.0, "rq_win": 2.19, "rq_draw": 3.5, "rq_lose": 2.58, "avg_win": 1.39, "avg_draw": 4.96, "avg_lose": 5.99, "shenjia": "未输入", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.52, "jc_draw": 3.6, "jc_lose": 5.15, "rq_win": 2.64, "rq_draw": 3.35, "rq_lose": 2.21, "avg_win": 1.56, "avg_draw": 3.77, "avg_lose": 5.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0"},
    {"handicap": -1, "jc_win": 3.55, "jc_draw": 3.52, "jc_lose": 1.78, "rq_win": 1.8, "rq_draw": 3.65, "rq_lose": 3.35, "avg_win": 3.06, "avg_draw": 3.59, "avg_lose": 2.15, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.4, "jc_lose": 5.5, "rq_win": 2.9, "rq_draw": 3.13, "rq_lose": 2.15, "avg_win": 1.68, "avg_draw": 3.53, "avg_lose": 5.02, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 2.8, "jc_lose": 2.92, "rq_win": 5.5, "rq_draw": 3.8, "rq_lose": 1.46, "avg_win": 2.45, "avg_draw": 3.02, "avg_lose": 2.94, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.17, "jc_draw": 3.0, "jc_lose": 2.98, "rq_win": 4.9, "rq_draw": 3.7, "rq_lose": 1.53, "avg_win": 2.02, "avg_draw": 3.28, "avg_lose": 3.42, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": -1, "jc_win": 2.92, "jc_draw": 3.15, "jc_lose": 2.13, "rq_win": 1.55, "rq_draw": 3.8, "rq_lose": 4.55, "avg_win": 3.34, "avg_draw": 3.36, "avg_lose": 2.03, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 2.24, "jc_draw": 2.98, "jc_lose": 2.88, "rq_win": 5.35, "rq_draw": 3.7, "rq_lose": 1.49, "avg_win": 2.6, "avg_draw": 3.02, "avg_lose": 2.71, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 3.65, "jc_lose": 4.6, "rq_win": 2.8, "rq_draw": 3.4, "rq_lose": 2.09, "avg_win": 1.42, "avg_draw": 4.44, "avg_lose": 6.81, "shenjia": "未输入", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 2.8, "jc_lose": 3.62, "rq_win": 4.7, "rq_draw": 3.4, "rq_lose": 1.61, "avg_win": 2.04, "avg_draw": 3.03, "avg_lose": 3.75, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 3.5, "jc_lose": 2.88, "rq_win": 3.95, "rq_draw": 3.95, "rq_lose": 1.61, "avg_win": 2.02, "avg_draw": 3.65, "avg_lose": 3.02, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -2, "jc_win": 9.75, "jc_draw": 6.35, "jc_lose": 1.15, "rq_win": 2.1, "rq_draw": 4.05, "rq_lose": 2.47, "avg_win": 7.95, "avg_draw": 6.21, "avg_lose": 1.27, "shenjia": "未输入", "real_result": "负", "real_score": "2:3"},
    {"handicap": -1, "jc_win": 2.64, "jc_draw": 3.0, "jc_lose": 2.4, "rq_win": 1.42, "rq_draw": 4.15, "rq_lose": 5.45, "avg_win": 2.76, "avg_draw": 3.26, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.7, "jc_lose": 3.3, "rq_win": 3.25, "rq_draw": 3.75, "rq_lose": 1.8, "avg_win": 2.62, "avg_draw": 3.05, "avg_lose": 2.81, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 4.5, "jc_lose": 4.7, "rq_win": 2.24, "rq_draw": 3.75, "rq_lose": 2.4, "avg_win": 1.63, "avg_draw": 4.27, "avg_lose": 4.52, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 2.13, "jc_draw": 3.15, "jc_lose": 2.92, "rq_win": 4.45, "rq_draw": 3.92, "rq_lose": 1.54, "avg_win": 2.11, "avg_draw": 3.43, "avg_lose": 3.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.55, "jc_lose": 1.7, "rq_win": 1.9, "rq_draw": 3.58, "rq_lose": 3.1, "avg_win": 3.61, "avg_draw": 3.58, "avg_lose": 1.9, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:6"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.05, "jc_lose": 2.45, "rq_win": 1.41, "rq_draw": 4.1, "rq_lose": 5.75, "avg_win": 2.61, "avg_draw": 3.24, "avg_lose": 2.59, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.64, "jc_draw": 3.0, "jc_lose": 2.4, "rq_win": 1.42, "rq_draw": 4.15, "rq_lose": 5.45, "avg_win": 2.76, "avg_draw": 3.26, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.4500; X=2.2100; cold_risk=23.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.3, "jc_lose": 2.88, "rq_win": 4.4, "rq_draw": 3.8, "rq_lose": 1.57, "avg_win": 2.29, "avg_draw": 3.41, "avg_lose": 2.78, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.1400; Y=1.3500; X=1.8600; cold_risk=10.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.0, "jc_draw": 3.0, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.75, "rq_lose": 4.8, "avg_win": 3.11, "avg_draw": 3.11, "avg_lose": 2.31, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "平局共振", "match_context": "Z=1.5000; Y=1.5000; X=2.5900; cold_risk=18.0%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.14, "jc_draw": 6.2, "jc_lose": 11.0, "rq_win": 2.6, "rq_draw": 4.0, "rq_lose": 2.02, "avg_win": 1.28, "avg_draw": 5.43, "avg_lose": 8.46, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.7900; Y=1.0700; X=0.6900; cold_risk=10.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.27, "jc_draw": 4.85, "jc_lose": 7.35, "rq_win": 1.9, "rq_draw": 3.65, "rq_lose": 3.05, "avg_win": 1.46, "avg_draw": 4.49, "avg_lose": 5.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.2700; Y=1.1200; X=0.8500; cold_risk=15.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.42, "jc_draw": 3.8, "jc_lose": 6.25, "rq_win": 2.48, "rq_draw": 3.15, "rq_lose": 2.45, "avg_win": 1.56, "avg_draw": 3.68, "avg_lose": 6.18, "shenjia": "未输入", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.1400; Y=1.1700; X=0.8200; cold_risk=12.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.2, "jc_lose": 2.77, "rq_win": 4.7, "rq_draw": 3.9, "rq_lose": 1.52, "avg_win": 2.63, "avg_draw": 3.03, "avg_lose": 2.78, "shenjia": "未输入", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.0000; Y=1.3800; X=1.9100; cold_risk=8.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.35, "jc_lose": 2.53, "rq_win": 4.8, "rq_draw": 4.1, "rq_lose": 1.48, "avg_win": 2.61, "avg_draw": 3.37, "avg_lose": 2.53, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=2.0300; Y=1.3900; X=2.2400; cold_risk=8.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.35, "jc_lose": 3.4, "rq_win": 3.7, "rq_draw": 3.6, "rq_lose": 1.72, "avg_win": 1.93, "avg_draw": 3.43, "avg_lose": 3.75, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.3000; X=1.5200; cold_risk=13.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.55, "jc_draw": 4.0, "jc_lose": 1.43, "rq_win": 2.4, "rq_draw": 3.5, "rq_lose": 2.34, "avg_win": 5.54, "avg_draw": 4.1, "avg_lose": 1.52, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.2200; Y=1.6900; X=6.7800; cold_risk=16.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.4, "jc_lose": 8.1, "rq_win": 1.72, "rq_draw": 4.05, "rq_lose": 3.32, "avg_win": 1.41, "avg_draw": 4.69, "avg_lose": 6.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.8600; Y=1.1000; X=0.8400; cold_risk=14.3%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 3.7, "jc_lose": 5.8, "rq_win": 2.6, "rq_draw": 3.15, "rq_lose": 2.35, "avg_win": 1.47, "avg_draw": 3.96, "avg_lose": 6.36, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.0100; Y=1.1900; X=0.8700; cold_risk=14.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 3.7, "jc_lose": 5.9, "rq_win": 2.57, "rq_draw": 3.2, "rq_lose": 2.34, "avg_win": 1.7, "avg_draw": 3.52, "avg_lose": 4.65, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.0200; Y=1.1800; X=0.8600; cold_risk=19.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.65, "jc_lose": 2.92, "rq_win": 3.75, "rq_draw": 3.8, "rq_lose": 1.67, "avg_win": 2.36, "avg_draw": 3.47, "avg_lose": 2.79, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.4700; Y=1.3200; X=1.9800; cold_risk=6.3%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.2, "jc_lose": 3.55, "rq_win": 3.85, "rq_draw": 3.43, "rq_lose": 1.73, "avg_win": 1.91, "avg_draw": 3.45, "avg_lose": 3.84, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.2300; Y=1.3000; X=1.3900; cold_risk=11.3%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 5.8, "jc_lose": 10.5, "rq_win": 2.69, "rq_draw": 3.88, "rq_lose": 2.0, "avg_win": 1.26, "avg_draw": 5.43, "avg_lose": 11.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.3700; Y=1.0700; X=0.6800; cold_risk=8.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 4.7, "jc_lose": 1.33, "rq_win": 2.71, "rq_draw": 3.65, "rq_lose": 2.06, "avg_win": 6.85, "avg_draw": 4.8, "avg_lose": 1.38, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3200; Y=1.7200; X=9.2200; cold_risk=13.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.83, "jc_draw": 3.15, "jc_lose": 2.18, "rq_win": 1.53, "rq_draw": 3.9, "rq_lose": 4.55, "avg_win": 2.84, "avg_draw": 3.5, "avg_lose": 2.32, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6400; Y=1.4800; X=2.6500; cold_risk=22.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.28, "jc_draw": 4.6, "jc_lose": 7.65, "rq_win": 1.97, "rq_draw": 3.5, "rq_lose": 2.98, "avg_win": 1.38, "avg_draw": 4.54, "avg_lose": 7.64, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.0400; Y=1.1200; X=0.7800; cold_risk=12.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.78, "jc_draw": 3.1, "jc_lose": 4.1, "rq_win": 3.7, "rq_draw": 3.3, "rq_lose": 1.8, "avg_win": 2.01, "avg_draw": 3.4, "avg_lose": 3.69, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.2300; Y=1.2800; X=1.1300; cold_risk=25.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.3, "jc_lose": 8.3, "rq_win": 1.75, "rq_draw": 3.85, "rq_lose": 3.35, "avg_win": 1.44, "avg_draw": 4.55, "avg_lose": 5.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.7700; Y=1.1000; X=0.8000; cold_risk=15.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.51, "jc_draw": 3.35, "jc_lose": 2.31, "rq_win": 1.46, "rq_draw": 4.1, "rq_lose": 5.0, "avg_win": 2.79, "avg_draw": 3.51, "avg_lose": 2.26, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "3:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9100; Y=1.4300; X=2.5500; cold_risk=21.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 3.9, "jc_lose": 4.75, "rq_win": 2.6, "rq_draw": 3.45, "rq_lose": 2.2, "avg_win": 1.51, "avg_draw": 4.14, "avg_lose": 5.39, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.1100; Y=1.2000; X=1.1500; cold_risk=17.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.35, "jc_lose": 3.15, "rq_win": 4.02, "rq_draw": 3.65, "rq_lose": 1.65, "avg_win": 2.5, "avg_draw": 3.35, "avg_lose": 2.76, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.2700; Y=1.3200; X=1.6700; cold_risk=7.7%; dev_level=轻微偏离"},
    {"handicap": -2, "jc_win": 9.0, "jc_draw": 5.85, "jc_lose": 1.18, "rq_win": 1.96, "rq_draw": 4.1, "rq_lose": 2.67, "avg_win": 8.58, "avg_draw": 5.94, "avg_lose": 1.26, "shenjia": "未输入", "real_result": "负", "real_score": "1:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1700; Y=1.8000; X=16.5000; cold_risk=3.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.3, "jc_lose": 4.7, "rq_win": 3.2, "rq_draw": 3.2, "rq_lose": 1.99, "avg_win": 1.67, "avg_draw": 3.64, "avg_lose": 4.82, "shenjia": "未输入", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.5100; Y=1.2400; X=1.0100; cold_risk=11.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 4.25, "jc_lose": 4.8, "rq_win": 2.31, "rq_draw": 3.7, "rq_lose": 2.35, "avg_win": 1.45, "avg_draw": 4.74, "avg_lose": 5.86, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.4600; Y=1.1900; X=1.2200; cold_risk=15.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 3.43, "jc_lose": 1.96, "rq_win": 1.66, "rq_draw": 3.85, "rq_lose": 3.75, "avg_win": 3.0, "avg_draw": 3.62, "avg_lose": 2.06, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6900; Y=1.5100; X=3.3300; cold_risk=20.4%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.17, "jc_draw": 6.5, "jc_lose": 8.25, "rq_win": 2.29, "rq_draw": 4.4, "rq_lose": 2.15, "avg_win": 1.23, "avg_draw": 6.9, "avg_lose": 9.6, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=5.9900; Y=1.0800; X=0.9800; cold_risk=9.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.3, "jc_draw": 4.4, "jc_lose": 7.5, "rq_win": 2.01, "rq_draw": 3.45, "rq_lose": 2.93, "avg_win": 1.3, "avg_draw": 5.15, "avg_lose": 9.88, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.8300; Y=1.1300; X=0.7600; cold_risk=9.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.4, "jc_draw": 3.9, "jc_lose": 1.55, "rq_win": 2.09, "rq_draw": 3.55, "rq_lose": 2.72, "avg_win": 4.09, "avg_draw": 3.89, "avg_lose": 1.79, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4400; Y=1.6300; X=5.5900; cold_risk=23.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.9, "jc_draw": 4.0, "jc_lose": 1.48, "rq_win": 2.26, "rq_draw": 3.5, "rq_lose": 2.5, "avg_win": 5.14, "avg_draw": 4.12, "avg_lose": 1.59, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3600; Y=1.6600; X=6.2900; cold_risk=18.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.07, "jc_lose": 2.72, "rq_win": 5.25, "rq_draw": 3.8, "rq_lose": 1.48, "avg_win": 2.42, "avg_draw": 3.32, "avg_lose": 2.8, "shenjia": "未输入", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8600; Y=1.3900; X=1.8900; cold_risk=11.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 8.75, "jc_draw": 5.3, "jc_lose": 1.21, "rq_win": 3.4, "rq_draw": 3.8, "rq_lose": 1.75, "avg_win": 8.62, "avg_draw": 5.92, "avg_lose": 1.27, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.0900; Y=1.7900; X=13.7200; cold_risk=10.8%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.9, "jc_draw": 3.25, "jc_lose": 2.1, "rq_win": 1.56, "rq_draw": 3.8, "rq_lose": 4.45, "avg_win": 2.76, "avg_draw": 3.52, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6700; Y=1.4900; X=2.8700; cold_risk=23.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.95, "jc_draw": 3.28, "jc_lose": 1.75, "rq_win": 1.84, "rq_draw": 3.3, "rq_lose": 3.55, "avg_win": 3.73, "avg_draw": 3.1, "avg_lose": 2.03, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3300; Y=1.6000; X=3.8900; cold_risk=24.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.5, "jc_draw": 3.25, "jc_lose": 1.87, "rq_win": 1.72, "rq_draw": 3.48, "rq_lose": 3.85, "avg_win": 3.25, "avg_draw": 3.23, "avg_lose": 2.15, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4400; Y=1.5600; X=3.4500; cold_risk=28.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.35, "jc_lose": 3.45, "rq_win": 3.61, "rq_draw": 3.6, "rq_lose": 1.74, "avg_win": 2.33, "avg_draw": 3.29, "avg_lose": 2.76, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3500; Y=1.3000; X=1.4900; cold_risk=2.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 3.28, "jc_lose": 3.08, "rq_win": 4.2, "rq_draw": 3.7, "rq_lose": 1.61, "avg_win": 1.81, "avg_draw": 3.56, "avg_lose": 3.78, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.1900; Y=1.3300; X=1.6900; cold_risk=14.1%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.25, "jc_draw": 3.71, "jc_lose": 1.81, "rq_win": 1.78, "rq_draw": 3.8, "rq_lose": 3.28, "avg_win": 4.11, "avg_draw": 3.67, "avg_lose": 1.74, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7500; Y=1.5300; X=4.0400; cold_risk=11.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.4, "jc_lose": 5.8, "rq_win": 2.2, "rq_draw": 3.55, "rq_lose": 2.55, "avg_win": 1.43, "avg_draw": 4.57, "avg_lose": 6.46, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.7100; Y=1.1600; X=1.0100; cold_risk=14.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 3.82, "jc_lose": 5.35, "rq_win": 2.5, "rq_draw": 3.35, "rq_lose": 2.32, "avg_win": 1.38, "avg_draw": 4.83, "avg_lose": 7.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.0900; Y=1.1900; X=0.9800; cold_risk=12.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 3.88, "jc_lose": 5.65, "rq_win": 2.5, "rq_draw": 3.3, "rq_lose": 2.35, "avg_win": 1.59, "avg_draw": 3.78, "avg_lose": 5.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.1800; Y=1.1800; X=0.9400; cold_risk=17.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.6, "jc_draw": 4.07, "jc_lose": 1.5, "rq_win": 2.24, "rq_draw": 3.65, "rq_lose": 2.45, "avg_win": 6.2, "avg_draw": 4.91, "avg_lose": 1.43, "shenjia": "未输入", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.4500; Y=1.6400; X=6.1900; cold_risk=4.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.43, "jc_draw": 4.3, "jc_lose": 5.05, "rq_win": 2.31, "rq_draw": 3.7, "rq_lose": 2.35, "avg_win": 1.48, "avg_draw": 4.57, "avg_lose": 5.92, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.5400; Y=1.1800; X=1.1600; cold_risk=15.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.34, "jc_draw": 3.4, "jc_lose": 2.45, "rq_win": 5.0, "rq_draw": 4.25, "rq_lose": 1.44, "avg_win": 2.51, "avg_draw": 3.58, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "3:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.0400; Y=1.4000; X=2.3700; cold_risk=17.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 3.57, "jc_lose": 2.06, "rq_win": 1.57, "rq_draw": 4.0, "rq_lose": 4.12, "avg_win": 3.28, "avg_draw": 3.72, "avg_lose": 2.02, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9000; Y=1.4700; X=3.1800; cold_risk=16.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.5, "jc_draw": 3.93, "jc_lose": 4.8, "rq_win": 2.6, "rq_draw": 3.4, "rq_lose": 2.22, "avg_win": 1.59, "avg_draw": 4.06, "avg_lose": 4.95, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.1400; Y=1.2000; X=1.1400; cold_risk=18.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.46, "jc_lose": 4.4, "rq_win": 3.0, "rq_draw": 3.45, "rq_lose": 1.98, "avg_win": 1.91, "avg_draw": 3.62, "avg_lose": 3.71, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.6300; Y=1.2400; X=1.1400; cold_risk=25.2%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.35, "jc_lose": 3.38, "rq_win": 3.6, "rq_draw": 3.7, "rq_lose": 1.72, "avg_win": 1.77, "avg_draw": 3.86, "avg_lose": 4.16, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.3000; X=1.5300; cold_risk=11.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.2, "jc_lose": 2.1, "rq_win": 1.56, "rq_draw": 3.8, "rq_lose": 4.45, "avg_win": 2.57, "avg_draw": 3.45, "avg_lose": 2.54, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6200; Y=1.4900; X=2.8300; cold_risk=25.2%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.02, "jc_draw": 3.48, "jc_lose": 1.96, "rq_win": 1.65, "rq_draw": 3.8, "rq_lose": 3.85, "avg_win": 2.86, "avg_draw": 3.66, "avg_lose": 2.29, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "正常", "match_context": "Z=1.7300; Y=1.5000; X=3.3700; cold_risk=16.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.06, "jc_draw": 3.48, "jc_lose": 2.8, "rq_win": 4.0, "rq_draw": 4.05, "rq_lose": 1.58, "avg_win": 2.09, "avg_draw": 3.66, "avg_lose": 3.17, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.2700; Y=1.3500; X=2.0100; cold_risk=11.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.24, "jc_draw": 5.05, "jc_lose": 8.0, "rq_win": 1.8, "rq_draw": 3.75, "rq_lose": 3.25, "avg_win": 1.32, "avg_draw": 5.37, "avg_lose": 8.57, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.5100; Y=1.1100; X=0.8000; cold_risk=11.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.82, "jc_draw": 2.95, "jc_lose": 2.3, "rq_win": 1.48, "rq_draw": 3.7, "rq_lose": 5.45, "avg_win": 3.06, "avg_draw": 3.16, "avg_lose": 2.4, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5400; Y=1.4800; X=2.3200; cold_risk=20.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.5, "jc_draw": 3.8, "jc_lose": 5.0, "rq_win": 2.7, "rq_draw": 3.3, "rq_lose": 2.2, "avg_win": 1.52, "avg_draw": 4.26, "avg_lose": 5.77, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.0400; Y=1.2000; X=1.0600; cold_risk=16.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.08, "jc_draw": 3.1, "jc_lose": 3.08, "rq_win": 4.6, "rq_draw": 3.65, "rq_lose": 1.57, "avg_win": 2.34, "avg_draw": 3.33, "avg_lose": 2.96, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.0100; Y=1.3500; X=1.6200; cold_risk=21.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.26, "jc_draw": 5.2, "jc_lose": 7.0, "rq_win": 1.85, "rq_draw": 3.8, "rq_lose": 3.07, "avg_win": 1.49, "avg_draw": 4.54, "avg_lose": 5.45, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.6000; Y=1.1200; X=0.9500; cold_risk=17.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.83, "jc_draw": 3.3, "jc_lose": 3.6, "rq_win": 3.65, "rq_draw": 3.55, "rq_lose": 1.75, "avg_win": 1.79, "avg_draw": 3.65, "avg_lose": 4.22, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.2900; X=1.3900; cold_risk=22.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 9.2, "jc_draw": 5.0, "jc_lose": 1.22, "rq_win": 3.3, "rq_draw": 3.55, "rq_lose": 1.84, "avg_win": 8.28, "avg_draw": 5.09, "avg_lose": 1.33, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=0.9800; Y=1.8000; X=12.6600; cold_risk=11.3%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.12, "jc_draw": 6.25, "jc_lose": 13.0, "rq_win": 2.6, "rq_draw": 3.85, "rq_lose": 2.06, "avg_win": 1.22, "avg_draw": 6.14, "avg_lose": 12.09, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.9000; Y=1.0600; X=0.5800; cold_risk=7.8%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.55, "jc_draw": 3.3, "jc_lose": 1.84, "rq_win": 1.74, "rq_draw": 3.5, "rq_lose": 3.75, "avg_win": 2.85, "avg_draw": 3.33, "avg_lose": 2.37, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4500; Y=1.5600; X=3.5800; cold_risk=32.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.36, "jc_draw": 3.5, "jc_lose": 1.83, "rq_win": 1.74, "rq_draw": 3.7, "rq_lose": 3.52, "avg_win": 3.31, "avg_draw": 3.6, "avg_lose": 2.01, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6100; Y=1.5400; X=3.7900; cold_risk=16.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.12, "jc_draw": 4.3, "jc_lose": 1.53, "rq_win": 2.14, "rq_draw": 3.9, "rq_lose": 2.47, "avg_win": 4.17, "avg_draw": 4.27, "avg_lose": 1.66, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:6", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.6800; Y=1.6100; X=6.2100; cold_risk=11.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.5, "jc_draw": 3.3, "jc_lose": 1.85, "rq_win": 1.73, "rq_draw": 3.5, "rq_lose": 3.78, "avg_win": 3.16, "avg_draw": 3.25, "avg_lose": 2.13, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4700; Y=1.5600; X=3.5600; cold_risk=28.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.0, "jc_lose": 2.19, "rq_win": 1.5, "rq_draw": 3.7, "rq_lose": 5.2, "avg_win": 2.78, "avg_draw": 3.09, "avg_lose": 2.44, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5200; Y=1.4900; X=2.5300; cold_risk=22.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.85, "jc_draw": 4.4, "jc_lose": 1.44, "rq_win": 2.38, "rq_draw": 3.65, "rq_lose": 2.3, "avg_win": 4.99, "avg_draw": 4.5, "avg_lose": 1.51, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.5000; Y=1.6600; X=7.1900; cold_risk=18.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.24, "jc_draw": 5.35, "jc_lose": 7.4, "rq_win": 1.75, "rq_draw": 4.1, "rq_lose": 3.18, "avg_win": 1.31, "avg_draw": 5.4, "avg_lose": 7.26, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.7800; Y=1.1100; X=0.9200; cold_risk=12.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.05, "jc_lose": 2.74, "rq_win": 5.1, "rq_draw": 3.95, "rq_lose": 1.47, "avg_win": 2.79, "avg_draw": 3.37, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.8500; Y=1.3900; X=1.8700; cold_risk=13.5%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.2, "jc_lose": 2.62, "rq_win": 4.9, "rq_draw": 4.25, "rq_lose": 1.45, "avg_win": 2.61, "avg_draw": 3.53, "avg_lose": 2.48, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.9400; Y=1.3900; X=2.0600; cold_risk=17.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.98, "jc_draw": 3.15, "jc_lose": 3.26, "rq_win": 4.15, "rq_draw": 3.55, "rq_lose": 1.65, "avg_win": 2.17, "avg_draw": 3.45, "avg_lose": 3.22, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1100; Y=1.3300; X=1.5200; cold_risk=13.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.5, "jc_lose": 3.67, "rq_win": 3.35, "rq_draw": 3.55, "rq_lose": 1.82, "avg_win": 1.9, "avg_draw": 3.57, "avg_lose": 3.83, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.5500; Y=1.2700; X=1.4300; cold_risk=24.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 4.4, "jc_lose": 1.43, "rq_win": 2.38, "rq_draw": 3.8, "rq_lose": 2.25, "avg_win": 3.63, "avg_draw": 3.74, "avg_lose": 1.85, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.4800; Y=1.6600; X=7.3100; cold_risk=25.4%; dev_level=显著偏离"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 6.5, "jc_lose": 9.5, "rq_win": 2.47, "rq_draw": 4.2, "rq_lose": 2.06, "avg_win": 1.19, "avg_draw": 6.4, "avg_lose": 10.47, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=6.0500; Y=1.0700; X=0.8400; cold_risk=16.9%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 7.21, "jc_lose": 14.51, "rq_win": 1.75, "rq_draw": 4.28, "rq_lose": 3.1, "avg_win": 1.18, "avg_draw": 7.0, "avg_lose": 15.0, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=6.6800; Y=1.0700; X=0.5700; cold_risk=6.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.26, "jc_draw": 5.0, "jc_lose": 7.35, "rq_win": 1.88, "rq_draw": 3.7, "rq_lose": 3.06, "avg_win": 1.39, "avg_draw": 4.67, "avg_lose": 7.3, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.4200; Y=1.1200; X=0.8700; cold_risk=12.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.4, "jc_lose": 3.15, "rq_win": 3.9, "rq_draw": 3.75, "rq_lose": 1.65, "avg_win": 1.97, "avg_draw": 3.82, "avg_lose": 3.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3200; Y=1.3200; X=1.6900; cold_risk=18.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.22, "jc_draw": 2.97, "jc_lose": 2.92, "rq_win": 5.2, "rq_draw": 3.7, "rq_lose": 1.5, "avg_win": 2.33, "avg_draw": 3.08, "avg_lose": 3.17, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8400; Y=1.3800; X=1.6800; cold_risk=19.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.45, "jc_draw": 2.85, "jc_lose": 2.7, "rq_win": 6.1, "rq_draw": 3.9, "rq_lose": 1.41, "avg_win": 2.66, "avg_draw": 3.12, "avg_lose": 2.68, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.4200; X=1.8100; cold_risk=24.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 8.05, "jc_draw": 5.2, "jc_lose": 1.23, "rq_win": 3.22, "rq_draw": 3.9, "rq_lose": 1.78, "avg_win": 5.93, "avg_draw": 4.49, "avg_lose": 1.46, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.1500; Y=1.7800; X=12.7300; cold_risk=15.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.91, "jc_draw": 2.95, "jc_lose": 3.75, "rq_win": 4.2, "rq_draw": 3.35, "rq_lose": 1.69, "avg_win": 1.9, "avg_draw": 3.3, "avg_lose": 4.21, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.0300; Y=1.3100; X=1.2100; cold_risk=22.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 8.0, "jc_draw": 4.6, "jc_lose": 1.27, "rq_win": 2.97, "rq_draw": 3.45, "rq_lose": 1.99, "avg_win": 6.03, "avg_draw": 3.85, "avg_lose": 1.54, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.0200; Y=1.7800; X=10.3700; cold_risk=15.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 3.5, "jc_lose": 2.65, "rq_win": 4.35, "rq_draw": 4.0, "rq_lose": 1.54, "avg_win": 2.32, "avg_draw": 3.75, "avg_lose": 2.71, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2200; Y=1.3700; X=2.1700; cold_risk=16.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.28, "jc_draw": 4.7, "jc_lose": 7.5, "rq_win": 1.96, "rq_draw": 3.5, "rq_lose": 3.0, "avg_win": 1.43, "avg_draw": 4.35, "avg_lose": 6.48, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.1200; Y=1.1200; X=0.8100; cold_risk=14.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.1, "jc_lose": 2.85, "rq_win": 4.9, "rq_draw": 3.8, "rq_lose": 1.51, "avg_win": 2.31, "avg_draw": 3.31, "avg_lose": 3.01, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9400; Y=1.3800; X=1.7900; cold_risk=20.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.05, "jc_lose": 3.55, "rq_win": 4.25, "rq_draw": 3.45, "rq_lose": 1.66, "avg_win": 1.91, "avg_draw": 3.26, "avg_lose": 3.99, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0800; Y=1.3200; X=1.3300; cold_risk=23.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 3.2, "jc_lose": 2.85, "rq_win": 4.6, "rq_draw": 3.75, "rq_lose": 1.55, "avg_win": 2.14, "avg_draw": 3.27, "avg_lose": 3.15, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.0300; Y=1.3700; X=1.8400; cold_risk=12.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.9, "jc_draw": 3.5, "jc_lose": 3.15, "rq_win": 3.7, "rq_draw": 3.7, "rq_lose": 1.7, "avg_win": 1.91, "avg_draw": 3.62, "avg_lose": 3.45, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4100; Y=1.3100; X=1.7300; cold_risk=15.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 7.0, "jc_draw": 3.9, "jc_lose": 1.37, "rq_win": 2.6, "rq_draw": 3.2, "rq_lose": 2.32, "avg_win": 5.16, "avg_draw": 3.44, "avg_lose": 1.71, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=0.9700; Y=1.7500; X=7.3600; cold_risk=18.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 4.22, "jc_lose": 5.05, "rq_win": 2.32, "rq_draw": 3.55, "rq_lose": 2.4, "avg_win": 1.58, "avg_draw": 3.99, "avg_lose": 4.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4600; Y=1.1800; X=1.1500; cold_risk=19.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.8, "jc_lose": 3.6, "rq_win": 3.06, "rq_draw": 3.7, "rq_lose": 1.88, "avg_win": 1.69, "avg_draw": 3.99, "avg_lose": 3.99, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.8100; Y=1.2600; X=1.5700; cold_risk=16.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 2.7, "jc_lose": 4.08, "rq_win": 4.65, "rq_draw": 3.25, "rq_lose": 1.65, "avg_win": 2.09, "avg_draw": 3.17, "avg_lose": 3.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8300; Y=1.3200; X=1.0200; cold_risk=26.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.16, "jc_draw": 3.4, "jc_lose": 1.68, "rq_win": 1.91, "rq_draw": 3.35, "rq_lose": 3.25, "avg_win": 3.81, "avg_draw": 3.38, "avg_lose": 1.89, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3200; Y=1.6100; X=4.3100; cold_risk=24.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.35, "jc_draw": 3.75, "jc_lose": 1.48, "rq_win": 2.28, "rq_draw": 3.35, "rq_lose": 2.55, "avg_win": 4.09, "avg_draw": 3.61, "avg_lose": 1.83, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1800; Y=1.6900; X=5.9700; cold_risk=22.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.55, "jc_draw": 3.65, "jc_lose": 4.75, "rq_win": 2.82, "rq_draw": 3.35, "rq_lose": 2.1, "avg_win": 1.69, "avg_draw": 3.69, "avg_lose": 4.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8600; Y=1.2200; X=1.0900; cold_risk=19.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 4.05, "jc_lose": 4.4, "rq_win": 2.55, "rq_draw": 3.6, "rq_lose": 2.18, "avg_win": 1.65, "avg_draw": 4.07, "avg_lose": 4.25, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.2000; Y=1.2100; X=1.3000; cold_risk=21.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.35, "jc_lose": 3.65, "rq_win": 3.45, "rq_draw": 3.52, "rq_lose": 1.8, "avg_win": 2.1, "avg_draw": 3.51, "avg_lose": 3.24, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3900; Y=1.2900; X=1.3900; cold_risk=7.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.78, "jc_draw": 3.5, "jc_lose": 3.55, "rq_win": 3.38, "rq_draw": 3.6, "rq_lose": 1.8, "avg_win": 1.79, "avg_draw": 3.71, "avg_lose": 4.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.5200; Y=1.2800; X=1.4900; cold_risk=22.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.99, "jc_draw": 3.14, "jc_lose": 3.25, "rq_win": 4.1, "rq_draw": 3.68, "rq_lose": 1.63, "avg_win": 2.6, "avg_draw": 3.31, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1000; Y=1.3300; X=1.5300; cold_risk=5.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 3.2, "jc_lose": 3.05, "rq_win": 4.2, "rq_draw": 3.75, "rq_lose": 1.6, "avg_win": 2.55, "avg_draw": 3.5, "avg_lose": 2.55, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1000; Y=1.3400; X=1.6800; cold_risk=6.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.46, "jc_draw": 3.16, "jc_lose": 2.46, "rq_win": 5.5, "rq_draw": 4.2, "rq_lose": 1.41, "avg_win": 2.57, "avg_draw": 3.36, "avg_lose": 2.55, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.8300; Y=1.4200; X=2.2300; cold_risk=26.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 3.85, "jc_lose": 4.85, "rq_win": 2.6, "rq_draw": 3.45, "rq_lose": 2.2, "avg_win": 1.49, "avg_draw": 4.25, "avg_lose": 6.39, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0700; Y=1.2000; X=1.1100; cold_risk=14.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 3.2, "jc_lose": 2.65, "rq_win": 4.9, "rq_draw": 4.0, "rq_lose": 1.48, "avg_win": 2.3, "avg_draw": 3.47, "avg_lose": 2.87, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.9500; Y=1.3900; X=2.0300; cold_risk=22.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.85, "jc_draw": 3.36, "jc_lose": 2.08, "rq_win": 1.57, "rq_draw": 3.95, "rq_lose": 4.2, "avg_win": 2.6, "avg_draw": 3.44, "avg_lose": 2.53, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7500; Y=1.4800; X=2.9900; cold_risk=24.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.28, "jc_lose": 3.95, "rq_win": 3.45, "rq_draw": 3.35, "rq_lose": 1.85, "avg_win": 1.94, "avg_draw": 3.3, "avg_lose": 3.89, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3900; Y=1.2700; X=1.2400; cold_risk=23.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.58, "jc_draw": 3.09, "jc_lose": 2.39, "rq_win": 1.42, "rq_draw": 4.0, "rq_lose": 5.7, "avg_win": 3.39, "avg_draw": 3.61, "avg_lose": 1.94, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7300; Y=1.4400; X=2.2800; cold_risk=14.1%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 3.08, "jc_draw": 3.4, "jc_lose": 1.96, "rq_win": 1.65, "rq_draw": 3.7, "rq_lose": 3.95, "avg_win": 2.91, "avg_draw": 3.46, "avg_lose": 2.25, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6700; Y=1.5100; X=3.3100; cold_risk=21.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.8, "jc_draw": 3.25, "jc_lose": 1.79, "rq_win": 1.78, "rq_draw": 3.4, "rq_lose": 3.65, "avg_win": 3.52, "avg_draw": 3.26, "avg_lose": 2.05, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3500; Y=1.5800; X=3.7200; cold_risk=26.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.6, "jc_lose": 3.75, "rq_win": 3.22, "rq_draw": 3.5, "rq_lose": 1.88, "avg_win": 1.85, "avg_draw": 3.57, "avg_lose": 3.92, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.6600; Y=1.2600; X=1.4300; cold_risk=11.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.76, "jc_draw": 3.4, "jc_lose": 3.75, "rq_win": 3.35, "rq_draw": 3.5, "rq_lose": 1.84, "avg_win": 1.88, "avg_draw": 3.45, "avg_lose": 3.88, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4600; Y=1.2800; X=1.3600; cold_risk=23.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.99, "jc_draw": 3.15, "jc_lose": 3.25, "rq_win": 4.08, "rq_draw": 3.65, "rq_lose": 1.64, "avg_win": 1.87, "avg_draw": 3.53, "avg_lose": 3.93, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1100; Y=1.3300; X=1.5300; cold_risk=13.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 3.19, "jc_lose": 2.85, "rq_win": 4.5, "rq_draw": 3.88, "rq_lose": 1.54, "avg_win": 1.91, "avg_draw": 3.53, "avg_lose": 3.83, "shenjia": "未输入", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0300; Y=1.3700; X=1.8300; cold_risk=4.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.32, "jc_lose": 4.1, "rq_win": 3.2, "rq_draw": 3.45, "rq_lose": 1.9, "avg_win": 1.71, "avg_draw": 3.63, "avg_lose": 4.8, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4500; Y=1.2600; X=1.2000; cold_risk=19.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.5, "jc_lose": 3.3, "rq_win": 3.4, "rq_draw": 3.8, "rq_lose": 1.75, "avg_win": 1.89, "avg_draw": 3.59, "avg_lose": 3.81, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4600; Y=1.3000; X=1.6300; cold_risk=13.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.32, "jc_lose": 2.22, "rq_win": 1.5, "rq_draw": 4.15, "rq_lose": 4.5, "avg_win": 2.11, "avg_draw": 3.53, "avg_lose": 3.2, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.8200; Y=1.4500; X=2.6800; cold_risk=20.1%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.05, "jc_lose": 2.36, "rq_win": 1.45, "rq_draw": 3.95, "rq_lose": 5.35, "avg_win": 2.59, "avg_draw": 3.1, "avg_lose": 2.62, "shenjia": "未输入", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6700; Y=1.4500; X=2.3000; cold_risk=13.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.64, "jc_draw": 3.75, "jc_lose": 3.95, "rq_win": 3.0, "rq_draw": 3.42, "rq_lose": 1.99, "avg_win": 1.95, "avg_draw": 3.49, "avg_lose": 3.43, "shenjia": "未输入", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8400; Y=1.2400; X=1.3800; cold_risk=12.4%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.8, "jc_lose": 1.7, "rq_win": 1.9, "rq_draw": 3.7, "rq_lose": 3.0, "avg_win": 2.45, "avg_draw": 3.43, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.5700; X=4.6000; cold_risk=16.9%; dev_level=极高偏离"},
    {"handicap": -1, "jc_win": 4.6, "jc_draw": 4.5, "jc_lose": 1.45, "rq_win": 2.37, "rq_draw": 3.6, "rq_lose": 2.33, "avg_win": 5.38, "avg_draw": 4.28, "avg_lose": 1.47, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.6100; Y=1.6400; X=7.2200; cold_risk=8.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.1, "jc_draw": 3.25, "jc_lose": 2.01, "rq_win": 1.62, "rq_draw": 3.7, "rq_lose": 4.15, "avg_win": 3.1, "avg_draw": 3.29, "avg_lose": 2.29, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5900; Y=1.5100; X=3.0700; cold_risk=20.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.88, "jc_draw": 3.35, "jc_lose": 3.35, "rq_win": 3.65, "rq_draw": 3.7, "rq_lose": 1.71, "avg_win": 2.3, "avg_draw": 3.25, "avg_lose": 3.16, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.3100; X=1.5500; cold_risk=19.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.49, "jc_draw": 4.23, "jc_lose": 4.5, "rq_win": 2.43, "rq_draw": 3.65, "rq_lose": 2.25, "avg_win": 1.54, "avg_draw": 4.03, "avg_lose": 5.74, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4000; Y=1.2000; X=1.3100; cold_risk=16.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.2, "jc_lose": 5.65, "rq_win": 2.2, "rq_draw": 3.6, "rq_lose": 2.52, "avg_win": 1.48, "avg_draw": 4.39, "avg_lose": 6.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.5000; Y=1.1700; X=1.0000; cold_risk=15.1%; dev_level=一致"},
    {"handicap": -2, "jc_win": 8.8, "jc_draw": 5.7, "jc_lose": 1.19, "rq_win": 1.91, "rq_draw": 4.25, "rq_lose": 2.7, "avg_win": 6.38, "avg_draw": 4.86, "avg_lose": 1.39, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1600; Y=1.8000; X=15.5700; cold_risk=14.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 5.7, "jc_draw": 5.1, "jc_lose": 1.32, "rq_win": 2.83, "rq_draw": 3.92, "rq_lose": 1.92, "avg_win": 6.64, "avg_draw": 4.72, "avg_lose": 1.39, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.5200; Y=1.7000; X=10.0700; cold_risk=7.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.0, "jc_draw": 3.0, "jc_lose": 2.17, "rq_win": 1.51, "rq_draw": 3.65, "rq_lose": 5.2, "avg_win": 2.89, "avg_draw": 3.07, "avg_lose": 2.42, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "平局共振", "match_context": "Z=1.5000; Y=1.5000; X=2.5600; cold_risk=15.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.82, "jc_lose": 3.68, "rq_win": 2.89, "rq_draw": 3.9, "rq_lose": 1.9, "avg_win": 1.74, "avg_draw": 4.02, "avg_lose": 3.96, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8500; Y=1.2500; X=1.5300; cold_risk=11.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.6, "jc_lose": 2.52, "rq_win": 4.25, "rq_draw": 4.25, "rq_lose": 1.52, "avg_win": 2.8, "avg_draw": 3.52, "avg_lose": 2.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "5:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=2.2500; Y=1.3800; X=2.3800; cold_risk=5.3%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.39, "jc_draw": 4.55, "jc_lose": 5.25, "rq_win": 2.16, "rq_draw": 3.75, "rq_lose": 2.5, "avg_win": 1.44, "avg_draw": 5.05, "avg_lose": 5.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.8100; Y=1.1600; X=1.1700; cold_risk=16.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.2, "jc_draw": 3.3, "jc_lose": 1.7, "rq_win": 1.9, "rq_draw": 3.25, "rq_lose": 3.4, "avg_win": 5.15, "avg_draw": 3.48, "avg_lose": 1.71, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.2700; Y=1.6200; X=4.1200; cold_risk=18.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.0, "jc_draw": 4.55, "jc_lose": 1.41, "rq_win": 2.49, "rq_draw": 3.85, "rq_lose": 2.14, "avg_win": 5.18, "avg_draw": 3.98, "avg_lose": 1.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.5200; Y=1.6700; X=7.7600; cold_risk=12.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 5.15, "jc_lose": 1.3, "rq_win": 2.9, "rq_draw": 3.95, "rq_lose": 1.88, "avg_win": 3.83, "avg_draw": 3.88, "avg_lose": 1.83, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.4500; Y=1.7200; X=10.5600; cold_risk=24.5%; dev_level=极高偏离"},
    {"handicap": 1, "jc_win": 1.23, "jc_draw": 5.25, "jc_lose": 7.95, "rq_win": 1.74, "rq_draw": 4.11, "rq_lose": 3.21, "avg_win": 1.44, "avg_draw": 4.9, "avg_lose": 6.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.7100; Y=1.1000; X=0.8400; cold_risk=15.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.05, "jc_lose": 3.45, "rq_win": 4.4, "rq_draw": 3.38, "rq_lose": 1.65, "avg_win": 2.14, "avg_draw": 3.12, "avg_lose": 3.46, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0600; Y=1.3200; X=1.3800; cold_risk=26.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.2, "jc_lose": 3.29, "rq_win": 4.1, "rq_draw": 3.55, "rq_lose": 1.66, "avg_win": 1.68, "avg_draw": 3.58, "avg_lose": 4.65, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1700; Y=1.3200; X=1.5200; cold_risk=9.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.96, "jc_draw": 3.35, "jc_lose": 2.03, "rq_win": 1.6, "rq_draw": 3.75, "rq_lose": 4.22, "avg_win": 2.92, "avg_draw": 3.36, "avg_lose": 2.24, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6900; Y=1.4900; X=3.0900; cold_risk=20.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 3.55, "jc_lose": 2.82, "rq_win": 4.0, "rq_draw": 3.95, "rq_lose": 1.6, "avg_win": 2.35, "avg_draw": 3.61, "avg_lose": 2.77, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3400; Y=1.3400; X=2.0200; cold_risk=13.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.58, "jc_lose": 1.75, "rq_win": 1.85, "rq_draw": 3.75, "rq_lose": 3.1, "avg_win": 4.29, "avg_draw": 3.71, "avg_lose": 1.77, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5600; Y=1.5700; X=4.1600; cold_risk=10.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.35, "jc_lose": 4.1, "rq_win": 3.35, "rq_draw": 3.35, "rq_lose": 1.88, "avg_win": 1.76, "avg_draw": 3.46, "avg_lose": 4.7, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4700; Y=1.2600; X=1.2000; cold_risk=19.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.66, "jc_draw": 3.8, "jc_lose": 3.8, "rq_win": 3.0, "rq_draw": 3.63, "rq_lose": 1.92, "avg_win": 1.59, "avg_draw": 4.17, "avg_lose": 5.07, "shenjia": "未输入", "real_result": "负", "real_score": "3:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8600; Y=1.2500; X=1.4700; cold_risk=5.8%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.86, "jc_draw": 3.95, "jc_lose": 1.62, "rq_win": 2.02, "rq_draw": 3.8, "rq_lose": 2.7, "avg_win": 3.18, "avg_draw": 3.8, "avg_lose": 2.04, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6300; Y=1.5900; X=5.1800; cold_risk=16.9%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.22, "jc_draw": 3.55, "jc_lose": 1.86, "rq_win": 1.73, "rq_draw": 3.76, "rq_lose": 3.5, "avg_win": 2.79, "avg_draw": 3.48, "avg_lose": 2.38, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6800; Y=1.5300; X=3.7300; cold_risk=22.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.51, "jc_draw": 3.7, "jc_lose": 2.17, "rq_win": 1.51, "rq_draw": 4.31, "rq_lose": 4.25, "avg_win": 2.56, "avg_draw": 3.84, "avg_lose": 2.4, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1100; Y=1.4300; X=3.0200; cold_risk=14.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.7, "jc_lose": 6.05, "rq_win": 2.0, "rq_draw": 3.76, "rq_lose": 2.75, "avg_win": 1.49, "avg_draw": 4.7, "avg_lose": 5.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.0300; Y=1.1400; X=1.0200; cold_risk=17.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 3.15, "jc_lose": 2.75, "rq_win": 4.95, "rq_draw": 3.9, "rq_lose": 1.49, "avg_win": 2.65, "avg_draw": 3.36, "avg_lose": 2.59, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9500; Y=1.3800; X=1.9000; cold_risk=15.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.52, "jc_draw": 3.7, "jc_lose": 5.0, "rq_win": 2.7, "rq_draw": 3.3, "rq_lose": 2.2, "avg_win": 1.66, "avg_draw": 3.9, "avg_lose": 4.91, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9400; Y=1.2100; X=1.0400; cold_risk=19.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 3.12, "jc_lose": 2.7, "rq_win": 5.25, "rq_draw": 3.95, "rq_lose": 1.46, "avg_win": 2.19, "avg_draw": 3.42, "avg_lose": 3.17, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9000; Y=1.3900; X=1.9400; cold_risk=22.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.25, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.9, "rq_lose": 4.6, "avg_win": 2.5, "avg_draw": 3.5, "avg_lose": 2.63, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7100; Y=1.4700; X=2.7500; cold_risk=26.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.45, "jc_lose": 6.55, "rq_win": 2.1, "rq_draw": 3.5, "rq_lose": 2.72, "avg_win": 1.45, "avg_draw": 4.56, "avg_lose": 6.41, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.8200; Y=1.1400; X=0.8900; cold_risk=14.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 3.75, "jc_lose": 5.65, "rq_win": 2.63, "rq_draw": 3.2, "rq_lose": 2.29, "avg_win": 1.78, "avg_draw": 3.46, "avg_lose": 4.6, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0500; Y=1.1900; X=0.9100; cold_risk=20.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.69, "jc_draw": 3.85, "jc_lose": 3.6, "rq_win": 3.04, "rq_draw": 3.65, "rq_lose": 1.9, "avg_win": 1.86, "avg_draw": 3.75, "avg_lose": 3.52, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8600; Y=1.2600; X=1.5800; cold_risk=13.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 3.35, "jc_lose": 1.72, "rq_win": 1.85, "rq_draw": 3.45, "rq_lose": 3.35, "avg_win": 4.63, "avg_draw": 3.94, "avg_lose": 1.69, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3400; Y=1.6000; X=4.0800; cold_risk=20.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.06, "jc_draw": 3.35, "jc_lose": 2.9, "rq_win": 4.2, "rq_draw": 3.9, "rq_lose": 1.58, "avg_win": 1.81, "avg_draw": 3.49, "avg_lose": 4.49, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1900; Y=1.3500; X=1.8600; cold_risk=11.0%; dev_level=轻微偏离"},
    {"handicap": -2, "jc_win": 12.0, "jc_draw": 6.0, "jc_lose": 1.14, "rq_win": 1.98, "rq_draw": 4.05, "rq_lose": 2.65, "avg_win": 9.3, "avg_draw": 5.28, "avg_lose": 1.29, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=0.9200; Y=1.8500; X=19.7800; cold_risk=10.0%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 4.6, "jc_lose": 1.41, "rq_win": 2.48, "rq_draw": 3.65, "rq_lose": 2.22, "avg_win": 4.52, "avg_draw": 4.3, "avg_lose": 1.58, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.5500; Y=1.6600; X=7.8300; cold_risk=10.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.54, "jc_draw": 3.86, "jc_lose": 2.1, "rq_win": 1.55, "rq_draw": 4.45, "rq_lose": 3.85, "avg_win": 2.5, "avg_draw": 3.92, "avg_lose": 2.4, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1800; Y=1.4400; X=3.2900; cold_risk=15.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.45, "jc_lose": 4.1, "rq_win": 3.2, "rq_draw": 3.4, "rq_lose": 1.92, "avg_win": 2.14, "avg_draw": 3.3, "avg_lose": 3.35, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.5700; Y=1.2500; X=1.2300; cold_risk=27.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.45, "jc_draw": 3.1, "jc_lose": 2.51, "rq_win": 5.5, "rq_draw": 4.1, "rq_lose": 1.42, "avg_win": 2.42, "avg_draw": 3.26, "avg_lose": 2.88, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.8000; Y=1.4200; X=2.1300; cold_risk=28.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.25, "jc_lose": 6.1, "rq_win": 2.2, "rq_draw": 3.5, "rq_lose": 2.57, "avg_win": 1.48, "avg_draw": 4.27, "avg_lose": 6.56, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.5900; Y=1.1600; X=0.9300; cold_risk=14.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.88, "jc_draw": 3.25, "jc_lose": 3.45, "rq_win": 3.85, "rq_draw": 3.48, "rq_lose": 1.72, "avg_win": 2.14, "avg_draw": 3.3, "avg_lose": 3.19, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2600; Y=1.3100; X=1.4500; cold_risk=5.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.69, "jc_draw": 3.55, "jc_lose": 3.9, "rq_win": 3.22, "rq_draw": 3.4, "rq_lose": 1.91, "avg_win": 1.83, "avg_draw": 3.5, "avg_lose": 4.05, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.6400; Y=1.2600; X=1.3400; cold_risk=22.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 3.35, "jc_lose": 1.99, "rq_win": 1.62, "rq_draw": 3.7, "rq_lose": 4.15, "avg_win": 3.23, "avg_draw": 3.37, "avg_lose": 2.11, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.5100; X=3.1900; cold_risk=18.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.98, "jc_draw": 3.1, "jc_lose": 2.12, "rq_win": 1.55, "rq_draw": 3.7, "rq_lose": 4.7, "avg_win": 3.4, "avg_draw": 3.27, "avg_lose": 2.04, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5600; Y=1.5000; X=2.7300; cold_risk=17.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 3.8, "jc_lose": 5.5, "rq_win": 2.6, "rq_draw": 3.25, "rq_lose": 2.3, "avg_win": 1.58, "avg_draw": 3.77, "avg_lose": 5.37, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0900; Y=1.1900; X=0.9500; cold_risk=17.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 3.9, "jc_lose": 5.1, "rq_win": 2.6, "rq_draw": 3.3, "rq_lose": 2.27, "avg_win": 1.72, "avg_draw": 3.67, "avg_lose": 4.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.1500; Y=1.1900; X=1.0600; cold_risk=14.1%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.62, "jc_draw": 3.0, "jc_lose": 2.42, "rq_win": 1.42, "rq_draw": 4.15, "rq_lose": 5.45, "avg_win": 2.85, "avg_draw": 3.27, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6600; Y=1.4500; X=2.1900; cold_risk=22.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.5, "jc_draw": 3.82, "jc_lose": 1.72, "rq_win": 1.85, "rq_draw": 3.95, "rq_lose": 2.98, "avg_win": 3.48, "avg_draw": 3.92, "avg_lose": 1.88, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7000; Y=1.5600; X=4.5200; cold_risk=14.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 3.4, "jc_lose": 1.97, "rq_win": 1.65, "rq_draw": 3.75, "rq_lose": 3.9, "avg_win": 2.75, "avg_draw": 3.38, "avg_lose": 2.48, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6800; Y=1.5100; X=3.2800; cold_risk=24.2%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.2, "jc_lose": 2.36, "rq_win": 1.44, "rq_draw": 3.95, "rq_lose": 5.5, "avg_win": 2.73, "avg_draw": 3.28, "avg_lose": 2.52, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8000; Y=1.4400; X=2.3800; cold_risk=24.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.17, "jc_draw": 2.9, "jc_lose": 3.1, "rq_win": 5.15, "rq_draw": 3.55, "rq_lose": 1.53, "avg_win": 1.83, "avg_draw": 3.35, "avg_lose": 4.5, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "冷门预警", "match_context": "Z=1.8300; Y=1.3700; X=1.5200; cold_risk=10.8%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 2.93, "jc_draw": 3.3, "jc_lose": 2.06, "rq_win": 1.58, "rq_draw": 3.85, "rq_lose": 4.25, "avg_win": 3.41, "avg_draw": 3.47, "avg_lose": 2.07, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:6", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6800; Y=1.4900; X=2.9900; cold_risk=16.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.52, "jc_draw": 3.3, "jc_lose": 2.33, "rq_win": 1.45, "rq_draw": 4.05, "rq_lose": 5.2, "avg_win": 2.53, "avg_draw": 3.55, "avg_lose": 2.58, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8800; Y=1.4300; X=2.4900; cold_risk=16.4%; dev_level=一致"},
    {"handicap": -2, "jc_win": 8.75, "jc_draw": 6.0, "jc_lose": 1.18, "rq_win": 1.99, "rq_draw": 4.2, "rq_lose": 2.57, "avg_win": 5.11, "avg_draw": 4.31, "avg_lose": 1.56, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "冷门预警", "match_context": "Z=1.2300; Y=1.7900; X=16.8100; cold_risk=18.3%; dev_level=极高偏离"},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.12, "jc_lose": 4.1, "rq_win": 3.75, "rq_draw": 3.22, "rq_lose": 1.81, "avg_win": 1.91, "avg_draw": 3.27, "avg_lose": 4.01, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2500; Y=1.2800; X=1.1400; cold_risk=23.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.7, "jc_lose": 7.5, "rq_win": 1.7, "rq_draw": 4.2, "rq_lose": 3.3, "avg_win": 1.53, "avg_draw": 4.3, "avg_lose": 4.99, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=5.1400; Y=1.1000; X=0.9600; cold_risk=18.4%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 1.52, "jc_draw": 3.75, "jc_lose": 4.9, "rq_win": 2.7, "rq_draw": 3.35, "rq_lose": 2.18, "avg_win": 1.65, "avg_draw": 3.85, "avg_lose": 5.09, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9800; Y=1.2100; X=1.0700; cold_risk=18.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.77, "jc_lose": 3.41, "rq_win": 3.2, "rq_draw": 3.78, "rq_lose": 1.81, "avg_win": 1.91, "avg_draw": 3.96, "avg_lose": 3.46, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7400; Y=1.2700; X=1.6700; cold_risk=14.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.88, "jc_draw": 3.25, "jc_lose": 3.45, "rq_win": 3.95, "rq_draw": 3.5, "rq_lose": 1.7, "avg_win": 1.91, "avg_draw": 3.39, "avg_lose": 4.01, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2600; Y=1.3100; X=1.4500; cold_risk=23.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 2.95, "jc_lose": 3.2, "rq_win": 4.75, "rq_draw": 3.6, "rq_lose": 1.56, "avg_win": 2.25, "avg_draw": 3.22, "avg_lose": 3.21, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.9000; Y=1.3500; X=1.4800; cold_risk=16.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.25, "jc_draw": 3.15, "jc_lose": 2.72, "rq_win": 4.95, "rq_draw": 3.9, "rq_lose": 1.49, "avg_win": 2.13, "avg_draw": 3.23, "avg_lose": 3.44, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9400; Y=1.3800; X=1.9300; cold_risk=23.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.84, "jc_draw": 3.25, "jc_lose": 3.6, "rq_win": 3.75, "rq_draw": 3.45, "rq_lose": 1.75, "avg_win": 2.25, "avg_draw": 3.23, "avg_lose": 3.18, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2900; Y=1.3000; X=1.3800; cold_risk=29.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.7, "jc_lose": 4.2, "rq_win": 2.89, "rq_draw": 3.5, "rq_lose": 2.01, "avg_win": 1.55, "avg_draw": 4.23, "avg_lose": 5.28, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8400; Y=1.2300; X=1.2700; cold_risk=17.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 2.95, "jc_lose": 3.3, "rq_win": 4.65, "rq_draw": 3.5, "rq_lose": 1.59, "avg_win": 2.26, "avg_draw": 3.21, "avg_lose": 3.21, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.9300; Y=1.3400; X=1.4300; cold_risk=16.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.1, "jc_draw": 3.22, "jc_lose": 2.02, "rq_win": 1.62, "rq_draw": 3.58, "rq_lose": 4.3, "avg_win": 3.09, "avg_draw": 3.3, "avg_lose": 2.2, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5700; Y=1.5100; X=3.0200; cold_risk=19.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.83, "jc_draw": 3.05, "jc_lose": 3.95, "rq_win": 3.95, "rq_draw": 3.3, "rq_lose": 1.75, "avg_win": 2.31, "avg_draw": 3.04, "avg_lose": 3.28, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1600; Y=1.2900; X=1.1700; cold_risk=28.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.34, "jc_draw": 2.65, "jc_lose": 3.08, "rq_win": 5.9, "rq_draw": 3.7, "rq_lose": 1.45, "avg_win": 2.51, "avg_draw": 3.0, "avg_lose": 2.97, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5900; Y=1.4000; X=1.4400; cold_risk=24.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.67, "jc_draw": 3.85, "jc_lose": 3.7, "rq_win": 2.9, "rq_draw": 3.7, "rq_lose": 1.95, "avg_win": 1.73, "avg_draw": 3.89, "avg_lose": 3.95, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8800; Y=1.2500; X=1.5300; cold_risk=11.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.3, "jc_draw": 3.85, "jc_lose": 1.57, "rq_win": 2.05, "rq_draw": 3.5, "rq_lose": 2.81, "avg_win": 3.87, "avg_draw": 3.71, "avg_lose": 1.77, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4500; Y=1.6200; X=5.4000; cold_risk=23.6%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.12, "jc_draw": 6.7, "jc_lose": 11.75, "rq_win": 2.3, "rq_draw": 4.1, "rq_lose": 2.22, "avg_win": 1.32, "avg_draw": 5.24, "avg_lose": 6.93, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=6.3200; Y=1.0600; X=0.6900; cold_risk=7.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 2.9, "jc_lose": 2.38, "rq_win": 1.43, "rq_draw": 3.8, "rq_lose": 6.0, "avg_win": 2.52, "avg_draw": 3.04, "avg_lose": 2.92, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.5500; Y=1.4700; X=2.1800; cold_risk=27.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.19, "jc_draw": 3.25, "jc_lose": 2.75, "rq_win": 4.85, "rq_draw": 3.85, "rq_lose": 1.51, "avg_win": 2.05, "avg_draw": 3.41, "avg_lose": 3.38, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0400; Y=1.3700; X=1.9500; cold_risk=17.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 3.3, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 4.0, "rq_lose": 4.45, "avg_win": 3.06, "avg_draw": 3.17, "avg_lose": 2.35, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7600; Y=1.4700; X=2.7800; cold_risk=19.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.21, "jc_draw": 3.5, "jc_lose": 1.88, "rq_win": 1.7, "rq_draw": 3.75, "rq_lose": 3.65, "avg_win": 2.93, "avg_draw": 3.38, "avg_lose": 2.19, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.6600; Y=1.5200; X=3.6200; cold_risk=8.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.65, "jc_lose": 3.85, "rq_win": 3.0, "rq_draw": 3.6, "rq_lose": 1.93, "avg_win": 1.69, "avg_draw": 3.97, "avg_lose": 4.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7200; Y=1.2500; X=1.4000; cold_risk=20.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.35, "jc_lose": 2.25, "rq_win": 1.49, "rq_draw": 4.1, "rq_lose": 4.7, "avg_win": 2.62, "avg_draw": 3.6, "avg_lose": 2.45, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8600; Y=1.4400; X=2.6400; cold_risk=24.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 4.3, "jc_lose": 4.55, "rq_win": 2.35, "rq_draw": 3.9, "rq_lose": 2.24, "avg_win": 1.4, "avg_draw": 4.74, "avg_lose": 6.44, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4700; Y=1.1900; X=1.3100; cold_risk=14.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.94, "jc_draw": 3.1, "jc_lose": 3.45, "rq_win": 4.1, "rq_draw": 3.45, "rq_lose": 1.68, "avg_win": 2.08, "avg_draw": 3.27, "avg_lose": 3.38, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1100; Y=1.3200; X=1.4000; cold_risk=6.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.8, "jc_lose": 3.4, "rq_win": 3.1, "rq_draw": 3.85, "rq_lose": 1.83, "avg_win": 1.76, "avg_draw": 3.94, "avg_lose": 3.75, "shenjia": "未输入", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7600; Y=1.2700; X=1.6800; cold_risk=9.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.67, "jc_draw": 3.6, "jc_lose": 3.95, "rq_win": 3.05, "rq_draw": 3.56, "rq_lose": 1.92, "avg_win": 1.85, "avg_draw": 3.55, "avg_lose": 3.95, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7000; Y=1.2500; X=1.3400; cold_risk=23.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.65, "jc_lose": 5.0, "rq_win": 2.82, "rq_draw": 3.25, "rq_lose": 2.15, "avg_win": 1.85, "avg_draw": 3.48, "avg_lose": 4.02, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8900; Y=1.2100; X=1.0200; cold_risk=23.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 4.2, "jc_lose": 4.95, "rq_win": 2.3, "rq_draw": 3.75, "rq_lose": 2.35, "avg_win": 1.61, "avg_draw": 4.21, "avg_lose": 4.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4300; Y=1.1800; X=1.1700; cold_risk=19.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.65, "jc_draw": 3.8, "jc_lose": 3.85, "rq_win": 2.85, "rq_draw": 3.78, "rq_lose": 1.95, "avg_win": 1.79, "avg_draw": 3.96, "avg_lose": 4.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8700; Y=1.2500; X=1.4400; cold_risk=23.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.9, "jc_draw": 3.3, "jc_lose": 3.33, "rq_win": 3.75, "rq_draw": 3.7, "rq_lose": 1.69, "avg_win": 2.27, "avg_draw": 3.48, "avg_lose": 2.96, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2800; Y=1.3100; X=1.5400; cold_risk=21.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 4.85, "jc_draw": 4.05, "jc_lose": 1.48, "rq_win": 2.26, "rq_draw": 3.65, "rq_lose": 2.42, "avg_win": 4.16, "avg_draw": 3.88, "avg_lose": 1.77, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3800; Y=1.6600; X=6.3400; cold_risk=22.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.38, "jc_draw": 3.55, "jc_lose": 8.25, "rq_win": 2.45, "rq_draw": 3.05, "rq_lose": 2.55, "avg_win": 1.52, "avg_draw": 3.48, "avg_lose": 7.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=2.9800; Y=1.1600; X=0.5700; cold_risk=15.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 2.92, "jc_lose": 2.44, "rq_win": 1.41, "rq_draw": 3.85, "rq_lose": 6.25, "avg_win": 2.45, "avg_draw": 3.08, "avg_lose": 2.79, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.6000; Y=1.4500; X=2.1200; cold_risk=27.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.51, "jc_draw": 3.35, "jc_lose": 2.31, "rq_win": 1.47, "rq_draw": 4.15, "rq_lose": 4.8, "avg_win": 3.06, "avg_draw": 3.45, "avg_lose": 2.1, "shenjia": "未输入", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9100; Y=1.4300; X=2.5500; cold_risk=6.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.75, "jc_lose": 4.35, "rq_win": 2.86, "rq_draw": 3.45, "rq_lose": 2.04, "avg_win": 1.96, "avg_draw": 3.61, "avg_lose": 3.63, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9100; Y=1.2200; X=1.2300; cold_risk=25.9%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 4.4, "jc_draw": 3.38, "jc_lose": 1.65, "rq_win": 1.98, "rq_draw": 3.35, "rq_lose": 3.07, "avg_win": 3.88, "avg_draw": 3.6, "avg_lose": 1.9, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.2500; Y=1.6300; X=4.4300; cold_risk=24.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.7, "jc_lose": 4.07, "rq_win": 2.85, "rq_draw": 3.65, "rq_lose": 1.98, "avg_win": 1.73, "avg_draw": 3.88, "avg_lose": 4.32, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8100; Y=1.2400; X=1.3200; cold_risk=21.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.85, "jc_draw": 3.15, "jc_lose": 2.17, "rq_win": 1.52, "rq_draw": 3.8, "rq_lose": 4.8, "avg_win": 2.6, "avg_draw": 3.3, "avg_lose": 2.58, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6400; Y=1.4800; X=2.6600; cold_risk=25.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 3.85, "jc_lose": 4.85, "rq_win": 2.6, "rq_draw": 3.45, "rq_lose": 2.2, "avg_win": 1.63, "avg_draw": 3.87, "avg_lose": 4.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "6:3", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0700; Y=1.2000; X=1.1100; cold_risk=19.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.2, "jc_draw": 4.95, "jc_lose": 11.0, "rq_win": 1.81, "rq_draw": 3.35, "rq_lose": 3.6, "avg_win": 1.41, "avg_draw": 3.87, "avg_lose": 8.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.5000; Y=1.0900; X=0.5600; cold_risk=14.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 2.58, "jc_lose": 4.15, "rq_win": 4.7, "rq_draw": 3.3, "rq_lose": 1.63, "avg_win": 2.45, "avg_draw": 2.91, "avg_lose": 3.01, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "正常", "match_context": "Z=1.7200; Y=1.3300; X=0.9700; cold_risk=15.0%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 4.06, "jc_lose": 2.3, "rq_win": 4.2, "rq_draw": 4.55, "rq_lose": 1.49, "avg_win": 2.13, "avg_draw": 4.06, "avg_lose": 2.75, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.5100; Y=1.3800; X=3.0000; cold_risk=13.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.03, "jc_draw": 3.35, "jc_lose": 2.0, "rq_win": 1.62, "rq_draw": 3.8, "rq_lose": 4.05, "avg_win": 2.51, "avg_draw": 3.37, "avg_lose": 2.73, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6600; Y=1.5000; X=3.1700; cold_risk=26.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.7, "jc_lose": 3.7, "rq_win": 3.0, "rq_draw": 3.75, "rq_lose": 1.89, "avg_win": 2.12, "avg_draw": 3.59, "avg_lose": 3.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7400; Y=1.2600; X=1.4800; cold_risk=11.9%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.28, "jc_lose": 2.28, "rq_win": 1.47, "rq_draw": 4.1, "rq_lose": 4.9, "avg_win": 2.74, "avg_draw": 3.4, "avg_lose": 2.46, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8200; Y=1.4400; X=2.5500; cold_risk=23.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.25, "jc_draw": 3.8, "jc_lose": 1.48, "rq_win": 2.25, "rq_draw": 3.25, "rq_lose": 2.65, "avg_win": 3.97, "avg_draw": 3.42, "avg_lose": 1.89, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "冷门预警", "match_context": "Z=1.2200; Y=1.6800; X=6.0300; cold_risk=23.5%; dev_level=显著偏离"}
]
# ==========================================
# 0. 全局配置常量
# ==========================================
# 【参数优化说明】以下参数已通过错题集567条历史数据进行回测分析优化：
# - COLD_RISK_THRESHOLD: 0.15→0.12（引擎C冷门风险阈值，回测准确率提升0.2%）
# - ENGINE_E_CRITICAL_DRAW: 新增配置项（原硬编码3.05→2.8，引擎E准确率提升0.4%）
# - SIMILARITY_THRESHOLD: 统一为CONFIG值（修复原函数内硬编码0.6与CONFIG的0.7不一致问题）
# - 引擎A阈值: 1.8→1.7, 2.5→2.6, 3.0→2.9（基于错题集回测的温和调整）
# 注意：所有引擎判断逻辑结构保持不变，仅优化阈值参数
CONFIG = {
    # 错题本匹配参数
    'TOLERANCE': 0.2,              # 概率容差
    'SIMILARITY_THRESHOLD': 0.7,   # 相似度阈值
    'METRIC_TOLERANCE': 0.15,      # 数学指标容差
    # 冷门预警参数
    'COLD_RATIO_THRESHOLD': 0.75,   # [V21修复] 冷门预警线(原0.6提升至0.75，减少误触发)
    'COLD_RISK_THRESHOLD': 0.12,       # 冷门风险阈值（12%）【基于错题集567条数据回测优化】
    # 比分预测参数
    'GOAL_MULTIPLIER': 1.35,       # [已弃用] 期望进球系数(已被动态系数替代，保留以防旧代码引用)
    # 让分分析参数
    'DEEP_ODDS_LOW': 1.7,          # 深度让分低概率阈值【已优化：原1.8→1.7】
    'DEEP_ODDS_HIGH': 2.6,         # 深度让分高概率阈值【已优化：原2.5→2.6】
    'MID_ODDS_DRAW': 2.9,          # 中度让分平概率阈值【已优化：原3.0→2.9】
    'GAP_LOW_MID': 0.4,            # [已弃用] 低概率优势差距阈值(保留以防旧代码引用)
    # 引擎权重（简单多数投票，可改为加权）
    'ENGINE_WEIGHTS': {'A': 1, 'B': 1, 'C': 1, 'D': 1, 'E': 1, 'F': 1},
    # 双维度共振参数
    'RESONANCE_DRAW_GAP': 0.15,        # 平局共振：Z/Y差值阈值，小于此值判定为势均力敌
    'RESONANCE_DEEP_HANDICAP': 1,      # 深度让分阈值：让分>=1为深度让分
    # V13 概率区间映射引擎参数
    'ZONE_MAP_WEIGHT': 1.2,
    'ZONE_CONFIDENCE_BOOST': 1.3,  # [已弃用] 区间置信度加成(保留以防旧代码引用)
    'ZONE_HIGH_RISK_THRESHOLD': 0.45,
    'ZONE_EVEN_MATCH_THRESHOLD': 0.3,
    # V13 引擎E临界参数（基于错题集回测优化）
    'ENGINE_E_CRITICAL_DRAW': 2.8,    # 引擎E平概率临界值（原硬编码3.05→2.8）
    # V15 引擎性能自适应参数
    'ENGINE_PERFORMANCE_DECAY': 0.98,  # 历史性能衰减系数(越旧权重越低)
    'MIN_ENGINE_WEIGHT': 0.3,          # 引擎最低权重(防止低准确率引擎完全失效)
    'CONFIDENCE_THRESHOLD': 0.65,      # 最低信心阈值(低于此值建议放弃)
    'MIN_AGREE_COUNT': 4,              # 最低共识票数(低于此值建议放弃)
    'MARKET_ODDS_RANGE_THRESHOLD': 0.5,      # [V18优化] 赛事概率差距阈值(原1.0→0.5)，降低误触发率
    'MARKET_ODDS_RANGE_WARN': 0.8,       # [V18新增] 胶着数据面板警告阈值(高于此值不警告，低于此值降仓)，介于0.5~1.0时触发降仓而非放弃
    'MARKET_ODDS_RANGE_SKIP': 0.3,       # [V18新增] 强制放弃阈值(低于此值才放弃)，极胶着时才放弃      # 赛事概率差距阈值，小于此值判定为概率过于接近(不能买)
    'MARKET_HANDICAP_EVEN_WARN': True,        # 是否启用胶着数据面板(平手/无让分)警告(注:赛事中心极少开平手/无让分，此检查作为补充)
    'MARKET_ODDS_RATIO_THRESHOLD': 1.3,     # 赛事概率比值阈值(最高/最低)，小于此值判定为概率比值接近
    # [V19新增] 干扰信号检测参数
    'EXTREME_ODDS_THRESHOLD': 1.60,         # [V20升级] 极端低概率阈值(赛事主胜/客胜低于此值触发干扰信号检测)
    'MEDIUM_ODDS_THRESHOLD': 1.65,          # [V20新增] 中等概率干扰信号阈值(扩展检测范围至1.40~1.65区间)
    #MEDIUM_ODDS_THRESHOLD#: 1.65,          # [V20新增] 中等概率干扰信号阈值(扩展检测范围至1.40~1.65区间) [V23重构] 已删除重复配置项
    'AVG_ODDS_RATIO_THRESHOLD': 3.0,        # 多家机构平均概率极差比值阈值(最高/最低>此值触发干扰信号预警)
    'UNANIMOUS_PENALTY': 0.10,              # 全票一致信心扣减幅度(6引擎全票一致时扣减10%)
    'COLD_RISK_BOOST': 0.12,                # [V21修复] 冷门风险额外权重加成(原0.20降至0.12，降低冷门偏向)
     'COLD_RISK_BOOST_THRESHOLD': 0.25,      # [V23优化] 冷门风险触发阈值(原0.18提升至0.25，进一步减少误触发)
     'MULTI_SIGNAL_THRESHOLD': 3,              # [V23优化] 多信号叠加阈值(信号数>=此值自动升级风控，原2提升至3)
    'SIGNAL_5VOTE_RESONANCE_PENALTY': 0.25,   # [V20新增] 5票+共振背离信心扣减幅度
    'COLD_RISK_DIRECTION_OVERRIDE': 0.12,     # [V21修复] 冷门反向Override幅度(原0.30降至0.12，改为信心扣减而非直接翻转)
    # [V23重构] 已删除重复配置项: MULTI_SIGNAL_THRESHOLD (保留上方定义)
    # [V23重构] 以下为历史遗留仓释，已清理重复项: 'SIGNAL_5VOTE_RESONANCE_PENALTY': 0.25,   # [V20新增] 5票+共振背离信心扣减幅度
    # [V23重构] 以下为历史遗留仓释，已清理重复项
    'SECONDARY_TOLERANCE': 0.35,            # 二级匹配容差(当一级匹配数为0时使用宽松容差二次搜索)
    # [V18新增] 错题本样本加权参数
    'ERROR_BOOK_RECENT_WEIGHT': 1.5,        # 近期比赛权重系数(最近10条数据)
    'ERROR_BOOK_WEIGHT_DECAY': 0.95,        # 权重衰减系数(每往前一条衰减5%)
    'ERROR_BOOK_MIN_SAMPLE': 5,             # [V21修复] 最低有效样本量(原3提升至5，减少小样本误判)
    'HISTORY_OVERRIDE_MIN_SAMPLES': 5,      # [V21新增] 历史预警触发override所需最小匹配数
    'ERROR_BOOK_BIAS_THRESHOLD': 0.70,      # [V21新增] 错题本偏差检测阈值(超过此值认为错题本自身有偏差)
    # ===== [V24新增] 冷门预测独立阈值 =====
    # 冷门定义: 预测结果与实际赛果不同, 且由输入的赛事胜平负概率(jc_win/jc_draw/jc_lose)判定
    #           '实际赛果对应最大值' = 该方向概率为三项中最大值(概率最大=最不被看好=打出即为冷门)
    'COLD_UPSET_GAP_THRESHOLD': 0.01,   # [V24] 差距阈值: 仅当 冷门方向概率 与 预测方向概率 差距 <= 0.01 时才进行冷门预测
    'COLD_UPSET_ENABLED': True,         # [V24] 冷门预测独立逻辑总开关
    # ===== [V25新增] 实际赛果输入端接入开关 =====
    # True: 冷门预测改用时录入的真实赛果(选项10/11)判定; False: 完全沿用V24的概率最大值代理逻辑
    'COLD_UPSET_USE_INPUT_RESULT': False,
    # ===== [V26新增] 硬否决 / 冷门形态 / 去相关 / 自学习开关 =====
    'VETO_SIGNAL_MIN': 2,               # [V26] 触发硬否决所需最少风控信号数
    'COLD_UPSET_PATTERN_MODE': True,    # [V26] 冷门判定改用胶着干扰信号形态, 不再用最大概率=实际赛果错误代理
    'COLD_DRAW_ODDS_MAX': 3.60,         # [V26] 平概率<=此值 视为平局高危
    # ===== [V28新增] 信心区间分析与冷门过滤配置 =====
    'CONFIDENCE_TRACKING_ENABLED': True,   # [V28] 信心区间追踪开关(自动记录每次预测)
    'CONFIDENCE_MIN_FOR_REPORT': 10,       # [V28] 生成区间报告所需最少预测数
    'COLD_PRE_FILTER_ENABLED': True,       # [V28] 冷门赛前预过滤开关
    'COLD_PRE_FILTER_SKIP': True,          # [V28] 命中冷门特征时是否直接跳过(True=跳过, False=仅警告)
    'COLD_PRE_FILTER_DRAW_MAX': 3.40,      # [V28] 平概率<=此值触发冷门预警
    'COLD_PRE_FILTER_ODDS_RANGE_MIN': 0.6, # [V28] 概率极差<=此值触发胶着预警
    'COLD_PRE_FILTER_SIGNAL_THRESHOLD': 2, # [V28] 冷门信号数>=此值触发过滤
    'COLD_FAVOR_ODDS_MIN': 1.45,        # [V26] 热门概率>=此值(且<2.0) 视为赢球失利高危
    'ENGINE_SELF_TRAINING': False,      # [V26] 单场赛后即时自学习开关(默认关)
    # ===== [V27新增] 决策链修复: 强信号加权否决 + 信心只降仓不否决 + 去相关仅参考 =====
    'DECORR_PENALTY_SCALE': 0.5,        # [V27] 去相关性对信心影响的缩放(1=完全按簇比例直乘, 0.5=减半, 越小说明越温和)
    'VETO_W_RESONANCE': 2.0,            # [V27] 反向背离(干扰信号) 否决权重
    'VETO_W_ENGINE_F': 1.0,             # [V27] 引擎F高风险(概率接近) 否决权重
    'VETO_W_MULTI': 2.0,                # [V27] 多信号叠加 否决权重
    'VETO_SCORE_THRESHOLD': 4.0,        # [V27] 加权风险分达到此值才硬否决(需多个独立强信号), 低于此值仅降仓
    'STAKE_HALF_FLOOR': 0.45,           # [V27] 信心低于此值提示极小仓, 介于其与CONFIDENCE_THRESHOLD之间提示半仓
    # ===== [V36新增] 最终执行决策层配置 =====
    'V36_ENABLED': True,                # [V36] 最终执行决策层总开关(以V27后最终信心+全局信号统一拍板执行等级)
    'EXEC_BASE_THRESHOLD': 0.60,        # [V36] 正常跟进初始执行基准(可被V29校准值ZONE_HIGH_CUT覆盖)
    # ===== [V29新增] 信心区间回测校准配置(弃单点0.01/肉眼挑点, 改约登指数+ROC/AUC自动定三档) =====
    # 设计原则: 不用单一评分的0.01差异判定冷门/放弃, 而是从录入的真实赛果里回测,
    #           用约登指数找'稳定输出正确方向'的信心区间, 输出三档(放弃/降仓/正常), 阈值可配。
    'CALIBRATION_ENABLED': True,        # [V29] 是否在信心区间报告时自动回测校准三档阈值
    'CALIB_MIN_SAMPLES': 15,            # [V29] 校准所需最少已结算样本数, 不足则沿用默认三档, 防小样本过拟合
    'CALIB_CV_FOLDS': 3,               # [V29] 时间序列滚动交叉验证折数(按录入时序切块, 防同批数据反复调参)
    'CALIB_STABILITY_TOL': 0.06,       # [V29] 各折阈值标准差>此值判定'阈值不稳定', 回归默认区间而非单点硬切
    'ZONE_DEFAULT_HIGH': 0.78,          # [V29] 默认正常区下界(信心>=此值=标准仓/正常输出), 样本不足或阈值漂移时兜底
    'ZONE_DEFAULT_MID': 0.62,           # [V29] 默认降仓区下界(此值~正常下界=降仓; <此值=放弃区)
    # 以下为校准运行后写回的生效阈值(None=未校准, 将回退到 ZONE_DEFAULT_*)
    'ZONE_HIGH_CUT': None,              # [V29] 约登指数+交叉验证得到的正常区下界(可配, 非0.01单点)
    'ZONE_MID_CUT': None,               # [V29] 约登指数+交叉验证得到的降仓/放弃分界(可配)
    'ZONE_CALIB_AUC': None,             # [V29] 信心评分对命中的整体区分能力(AUC), 接近0.5说明无区分力不宜设区间
    'ZONE_CALIB_STABLE': None,          # [V29] 阈值是否稳定(True=各折一致可用; False=漂移大, 保守用默认)
    # ===== [V30新增] 冷门模板命中分支(诚实版: 相似案例的真实低概率结果率, 而非'相似=冷门'臆断) =====
    'COLD_TEMPLATE_ENABLED': True,       # [V30] 冷门模板命中总开关
    'COLD_TEMPLATE_TOL': 0.01,           # [V30] 概率模板容差(9项概率最大偏差<=此值视为同结构; 0.01=你原直觉, 需用回测函数验证)
    'COLD_TEMPLATE_HANDI_TOL': 0.01,     # [V30] 让分数容差(与概率容差分开, 便于各自调)
    'COLD_TEMPLATE_MIN_SAMPLE': 5,       # [V30] 相似案例少于此数=样本不足, 拒绝给出风险分(防小样本过拟合)
    'COLD_TEMPLATE_RATE_MID': 0.25,      # [V30] 相似组内低概率结果率>=此值=中风险
    'COLD_TEMPLATE_RATE_HIGH': 0.40,     # [V30] 相似组内低概率结果率>=此值=高风险
    'COLD_TEMPLATE_LIFT_MIN': 0.08,      # [V30] 相似组低概率结果率相对整体基准率的最低提升, 低于此值即便率高也判'无区分力'
    'COLD_TEMPLATE_PRINT': True,         # [V30] 是否在每次分析时打印冷门模板命中提示
    # ===== [V32新增] 冷门匹配改为 Top-K 最近邻(修复0.01硬卡阈值命中不到样本的问题) =====
    'COLD_TEMPLATE_METHOD': 'knn',       # 'knn'=Top-K最近邻(推荐) | 'strict'=旧的9项全卡阈值(几乎命中不到)
    'COLD_TEMPLATE_TOPK': 30,            # [V32] 最近邻取最相似的前K场(太小的K噪声大, 太大被基准稀释)
    'COLD_TEMPLATE_PREDICT_THRESH': 0.5, # [V32] K邻真实低概率结果率>=此值, 才把本场判为'预测冷门'
    # ===== [V33新增] 收紧冷门定义(1) + 热门信心校准回测(3) =====
    'COLD_STRICT_BY_ODDS': True,       # [V34] True=低概率结果改按'胜方概率>=COLD_UPSET_MIN_ODDS 且 热门方概率<=COLD_FAV_MAX_ODDS'双条件判定(收紧); False=沿用旧'赛果方向!=热门方向'
    'COLD_UPSET_MIN_ODDS': 3.00,       # [V34] 真低概率结果双条件之一: 实际赛果(胜方)概率>=此值(冷门=低概率热门翻车); 2.50太低会把'平局/次热门赢'误算进冷门, 故默认提到3.00
    'COLD_FAV_MAX_ODDS': 2.00,          # [V34] 真低概率结果双条件之二: 该场热门方(最低概率)概率<=此值才算'有明确热门', 排除势均力敌(没有真冷门可言)的比赛; <=0则不启用此条件
    'HOT_CALIB_BINS': [0.50, 0.60, 0.70, 0.80, 0.90, 1.00],  # [V33] 热门校准分档上界(按信心区间统计实际命中率)
    # ===== [V37新增] 自动校准模块开关(独立, 默认关闭, 开启后也不自动改阈值, 仅每N场弹建议由你确认) =====
    'AUTO_CALIBRATE': False,            # [V37] 自动校准总开关(默认False=行为与V36完全一致; True=每分析满N场弹一次阈值建议, 仍需你y/n确认)
    'CALIBRATE_EVERY_N': 100,           # [V37] 每积累N场新分析触发一次校准建议(样本足则稳, 追短期波动会更糟, 默认100)
    'CALIB_MIN_BASE_RANGE': (0.55, 0.85),  # [V37] 正常线建议扫描区间下/上界
    'CALIB_MIN_HIGH_SAMPLE': 15,        # [V37] 建议切点处高信心档至少需要的样本数(防小样本乱跳)
    'CALIB_HIT_FLOOR': 0.50,            # [V37] 高信心档命中率至少达此值才给出可跟进建议
}

# [V23重构] 魔法数字常量 - 集中管理硬编码阈值，避免散落各处
# 这些值在多个函数中被引用，修改时只需改此处
MAGIC_ENGINE_A_RQ_DRAW_THRESHOLD = 2.9       # 引擎A: 让分平概率阈值 (used in engine_pure_rq)
MAGIC_ENGINE_A_RQ_LOSE_CEIL = 2.50           # 引擎A: 让分负概率上限 (used in engine_pure_rq)
MAGIC_ENGINE_A_RQ_WIN_CEIL = 2.50            # 引擎A: 让分胜概率上限 (used in engine_pure_rq)
MAGIC_ENGINE_METRICS_TOLERANCE = 0.01        # 引擎C: 最小值精确匹配容差 (used in engine_metrics)
MAGIC_HANDICAP_NORM_DENOM = 2               # 让分归一化分母 (used in find_similar_cases)



def get_score(val1, val2):
    """计算两个数值之间的相似度得分 (0~1)，使用CONFIG中的TOLERANCE参数"""
    diff = abs(val1 - val2)
    return 1 - (diff / CONFIG["TOLERANCE"]) if diff <= CONFIG["TOLERANCE"] else 0

# ==========================================
# V13 概率区间赛果映射引擎（第六引擎 Engine F）
# ==========================================

# 概率区间六段划分
ODDS_ZONES = [
    ('Z1', 1.0, 1.3, '超低概率·超级热门', 0.78, 0.12, 0.10),
    ('Z2', 1.3, 1.7, '低概率·明确看好', 0.62, 0.22, 0.16),
    ('Z3', 1.7, 2.2, '中低概率·轻度优势', 0.48, 0.28, 0.24),
    ('Z4', 2.2, 3.0, '中度让分·均势博弈', 0.35, 0.33, 0.32),
    ('Z5', 3.0, 4.5, '中高概率·弱势方', 0.25, 0.26, 0.49),
    ('Z6', 4.5, 99.0, '高概率·深度冷门', 0.18, 0.19, 0.63),
]

# 概率区间-赛果概率映射矩阵（支持模糊匹配）
ODDS_ZONE_RESULT_MAP = {
    ('Z3', 'Z5', 'Z5'): {'win': 0.49, 'draw': 0.27, 'lose': 0.25, 'sample': 109},
    ('Z2', 'Z6', 'Z5'): {'win': 0.55, 'draw': 0.23, 'lose': 0.22, 'sample': 74},
    ('Z4', 'Z4', 'Z5'): {'win': 0.36, 'draw': 0.31, 'lose': 0.32, 'sample': 74},
    ('Z5', 'Z3', 'Z5'): {'win': 0.21, 'draw': 0.3, 'lose': 0.49, 'sample': 53},
    ('Z1', 'Z6', 'Z6'): {'win': 0.78, 'draw': 0.16, 'lose': 0.05, 'sample': 37},
    ('Z2', 'Z5', 'Z5'): {'win': 0.57, 'draw': 0.23, 'lose': 0.2, 'sample': 35},
    ('Z4', 'Z3', 'Z5'): {'win': 0.32, 'draw': 0.29, 'lose': 0.39, 'sample': 31},
    ('Z3', 'Z4', 'Z5'): {'win': 0.36, 'draw': 0.28, 'lose': 0.36, 'sample': 25},
    ('Z6', 'Z2', 'Z5'): {'win': 0.17, 'draw': 0.17, 'lose': 0.67, 'sample': 24},
    ('Z4', 'Z4', 'Z4'): {'win': 0.32, 'draw': 0.32, 'lose': 0.37, 'sample': 19},
    ('Z5', 'Z2', 'Z5'): {'win': 0.32, 'draw': 0.05, 'lose': 0.63, 'sample': 19},
    ('Z6', 'Z1', 'Z6'): {'win': 0.06, 'draw': 0.06, 'lose': 0.88, 'sample': 17},
    ('Z3', 'Z5', 'Z4'): {'win': 0.31, 'draw': 0.46, 'lose': 0.23, 'sample': 13},
    ('Z2', 'Z6', 'Z6'): {'win': 0.58, 'draw': 0.25, 'lose': 0.17, 'sample': 12},
    ('Z6', 'Z2', 'Z6'): {'win': 0.25, 'draw': 0.17, 'lose': 0.58, 'sample': 12},
    ('Z4', 'Z5', 'Z4'): {'win': 0.4, 'draw': 0.4, 'lose': 0.2, 'sample': 5},
}

def get_odds_zone(odds):
    """将概率映射到Z1-Z6区间"""
    if odds <= 0: return 'Z1'
    for zone_id, low, high, label, pw, pd, pl in ODDS_ZONES:
        if low <= odds < high:
            return zone_id
    return 'Z6'

def get_zone_probability(zone_h, zone_a, zone_d):
    """在映射矩阵中查找概率三元组，支持模糊匹配相邻区间"""
    key = (zone_h, zone_a, zone_d)
    if key in ODDS_ZONE_RESULT_MAP:
        return ODDS_ZONE_RESULT_MAP[key]
    zone_ids = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6']
    def get_zone_index(z):
        return zone_ids.index(z) if z in zone_ids else 2
    weighted_sum = {'win': 0, 'draw': 0, 'lose': 0, 'sample': 0}
    for k, v in ODDS_ZONE_RESULT_MAP.items():
        kh, ka, kd = k
        dist = abs(get_zone_index(kh) - get_zone_index(zone_h)) + \
               abs(get_zone_index(ka) - get_zone_index(zone_a)) + \
               abs(get_zone_index(kd) - get_zone_index(zone_d))
        if dist <= 3:
            weight = max(0.1, 1.0 - dist * 0.3)
            weighted_sum['win'] += v['win'] * weight
            weighted_sum['draw'] += v['draw'] * weight
            weighted_sum['lose'] += v['lose'] * weight
            weighted_sum['sample'] += weight
    if weighted_sum['sample'] > 0:
        total = weighted_sum['win'] + weighted_sum['draw'] + weighted_sum['lose']
        return {
            'win': round(weighted_sum['win'] / total, 3),
            'draw': round(weighted_sum['draw'] / total, 3),
            'lose': round(weighted_sum['lose'] / total, 3),
            'sample': 'fuzzy'
        }
    return {'win': 0.33, 'draw': 0.33, 'lose': 0.34, 'sample': 0}

def engine_zone_mapping(data, shenjia_info):
    """第六引擎：概率区间赛果映射引擎"""
    jc_win, jc_draw, jc_lose = data['jc_win'], data['jc_draw'], data['jc_lose']
    handicap = data['handicap']
    zone_h = get_odds_zone(jc_win)
    zone_d = get_odds_zone(jc_draw)
    zone_a = get_odds_zone(jc_lose)
    if abs(handicap) >= 2:
        handicap_level = '深度让分'
    elif abs(handicap) >= 1:
        handicap_level = '中度让分'
    else:
        handicap_level = '浅度让分/平手'
    odds_range = max(jc_win, jc_draw, jc_lose) - min(jc_win, jc_draw, jc_lose)
    is_even_match = odds_range < CONFIG['ZONE_EVEN_MATCH_THRESHOLD']
    is_extreme = odds_range > 1.5
    prob_info = get_zone_probability(zone_h, zone_a, zone_d)
    zone_win_prob = prob_info['win']
    zone_draw_prob = prob_info['draw']
    zone_lose_prob = prob_info['lose']
    zone_direction = '平'
    zone_confidence = zone_draw_prob
    if zone_win_prob > zone_draw_prob and zone_win_prob > zone_lose_prob:
        zone_direction = '胜'
        zone_confidence = zone_win_prob
    elif zone_lose_prob > zone_draw_prob and zone_lose_prob > zone_win_prob:
        zone_direction = '负'
        zone_confidence = zone_lose_prob
    max_prob = max(zone_win_prob, zone_draw_prob, zone_lose_prob)
    min_prob = min(zone_win_prob, zone_draw_prob, zone_lose_prob)
    is_high_risk = (max_prob - min_prob) < CONFIG['ZONE_HIGH_RISK_THRESHOLD']
    reason_parts = []
    reason_parts.append("概率区间: {}/{}".format(zone_h, zone_a))
    reason_parts.append("让分深度: {}".format(handicap_level))
    reason_parts.append("主胜{:.0%}/平{:.0%}/客胜{:.0%}".format(
        zone_win_prob, zone_draw_prob, zone_lose_prob))
    if is_high_risk:
        reason_parts.append("高风险标记(概率接近)")
    if is_even_match:
        reason_parts.append("均势面标记")
    return {
        'engine': 'F-概率区间映射引擎',
        'conclusion': zone_direction,
        'reason': ' | '.join(reason_parts),
        'zone_h': zone_h, 'zone_d': zone_d, 'zone_a': zone_a,
        'zone_win_prob': zone_win_prob,
        'zone_draw_prob': zone_draw_prob,
        'zone_lose_prob': zone_lose_prob,
        'zone_confidence': zone_confidence,
        'handicap_level': handicap_level,
        'is_high_risk': is_high_risk,
        'is_even_match': is_even_match,
        'odds_range': round(odds_range, 2),
        'weight': CONFIG['ZONE_MAP_WEIGHT'],
    }

# ==========================================
# V13 比分引擎动态重构
# ==========================================

def get_dynamic_goal_multiplier(zone):
    """六档动态进球系数：随概率区间自动切换"""
    multiplier_map = {
        'Z1': 1.6, 'Z2': 1.45, 'Z3': 1.35,
        'Z4': 1.25, 'Z5': 1.10, 'Z6': 0.9,
    }
    return multiplier_map.get(zone, 1.25)

def get_handicap_correction(handicap, zone_h, zone_a):
    """让分深度修正：深度让分(>=2球)强队+0.3/弱队-0.2，均势面(=0)启用回归模式"""
    home_correction = 0
    away_correction = 0
    if abs(handicap) >= 2:
        if handicap > 0:
            home_correction = 0.3
            away_correction = -0.2
        else:
            away_correction = 0.3
            home_correction = -0.2
    elif handicap == 0:
        home_correction = -0.15
        away_correction = -0.15
    return home_correction, away_correction



# 格式示例：{'handicap': 1, 'jc_win': 2.0, ... 'real_result': '胜', 'real_score': ''},
# ==========================================
# ==========================================
# 比赛自动编号系统
# ==========================================
_MATCH_ID_COUNTER = {'next_id': 1}

def _assign_match_id():
    """分配下一个比赛编号"""
    mid = _MATCH_ID_COUNTER['next_id']
    _MATCH_ID_COUNTER['next_id'] += 1
    return '#{:03d}'.format(mid)

def _init_existing_ids():
    """为已有的错题本条目分配编号(仅首次运行)
    V14修复: 检测并修复重复编号，确保所有match_id唯一
    """
    assigned = 0
    existing_ids = set()
    
    # 第一阶段: 收集所有已有的match_id(包括重复的)
    for item in ERROR_BOOK:
        mid = item.get('match_id')
        if mid and mid in existing_ids:
            # 发现重复ID，标记为需要重新分配
            item['_need_reassign'] = True
        if mid:
            existing_ids.add(mid)
    
    # 第二阶段: 为需要重新分配的条目分配新编号
    # 找出当前最大的编号
    max_id = 0
    for item in ERROR_BOOK:
        mid = item.get('match_id')
        if mid and mid.startswith('#'):
            try:
                num = int(mid[1:])
                if num > max_id:
                    max_id = num
            except ValueError:
                pass
    
    next_id = max_id + 1
    reassign_count = 0
    
    for item in ERROR_BOOK:
        if item.pop('_need_reassign', False):
            # 重新分配唯一编号
            while '#{:03d}'.format(next_id) in existing_ids:
                next_id += 1
            item['match_id'] = '#{:03d}'.format(next_id)
            existing_ids.add(item['match_id'])
            reassign_count += 1
        elif 'match_id' not in item:
            # [Bug修复] 检查编号是否已被使用，避免冲突
            candidate = assigned + 1
            while '#{:03d}'.format(candidate) in existing_ids:
                candidate += 1
            item['match_id'] = '#{:03d}'.format(candidate)
            assigned = candidate
    # 更新计数器
    final_max = max_id
    for item in ERROR_BOOK:
        mid = item.get('match_id')
        if mid and mid.startswith('#'):
            try:
                num = int(mid[1:])
                if num > final_max:
                    final_max = num
            except ValueError:
                pass
    _MATCH_ID_COUNTER['next_id'] = final_max + 1
    
    if reassign_count > 0:
        print("[编号修复] 检测到 {} 条重复编号，已自动重新分配".format(reassign_count))


# ==========================================
# 错题本数据库 
# 说明：请在此处粘贴你的历史数据。
# ==========================================
ERROR_BOOK = [
    {"handicap": 1, "jc_win": 2.42, "jc_draw": 2.95, "jc_lose": 2.65, "rq_win": 5.75, "rq_draw": 3.9, "rq_lose": 1.43, "avg_win": 2.55, "avg_draw": 3.06, "avg_lose": 2.71, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.4, "jc_lose": 5.8, "rq_win": 2.15, "rq_draw": 3.55, "rq_lose": 2.61, "avg_win": 1.63, "avg_draw": 4.1, "avg_lose": 4.54, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.85, "jc_lose": 1.64, "rq_win": 1.95, "rq_draw": 3.65, "rq_lose": 2.92, "avg_win": 3.65, "avg_draw": 3.68, "avg_lose": 1.82, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.21, "jc_draw": 5.5, "jc_lose": 8.25, "rq_win": 1.72, "rq_draw": 4.0, "rq_lose": 3.36, "avg_win": 1.3, "avg_draw": 5.36, "avg_lose": 7.43, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.34, "jc_draw": 4.55, "jc_lose": 6.15, "rq_win": 2.13, "rq_draw": 3.45, "rq_lose": 2.7, "avg_win": 1.44, "avg_draw": 4.44, "avg_lose": 6.02, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.3, "jc_lose": 3.5, "rq_win": 3.75, "rq_draw": 3.52, "rq_lose": 1.73, "avg_win": 1.86, "avg_draw": 3.55, "avg_lose": 3.76, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 2.92, "jc_lose": 3.35, "rq_win": 4.6, "rq_draw": 3.5, "rq_lose": 1.6, "avg_win": 2.33, "avg_draw": 3.12, "avg_lose": 2.96, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 4.05, "jc_lose": 1.58, "rq_win": 2.08, "rq_draw": 3.7, "rq_lose": 3.64, "avg_win": 3.97, "avg_draw": 3.86, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.35, "jc_lose": 3.85, "rq_win": 3.5, "rq_draw": 3.4, "rq_lose": 1.82, "avg_win": 2.0, "avg_draw": 3.49, "avg_lose": 3.33, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 7.45, "jc_lose": 11.83, "rq_win": 2.04, "rq_draw": 4.35, "rq_lose": 2.45, "avg_win": 1.18, "avg_draw": 7.0, "avg_lose": 11.0, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.15, "jc_lose": 2.2, "rq_win": 1.5, "rq_draw": 3.9, "rq_lose": 4.85, "avg_win": 2.32, "avg_draw": 3.39, "avg_lose": 2.73, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.74, "jc_draw": 3.2, "jc_lose": 4.15, "rq_win": 3.55, "rq_draw": 3.3, "rq_lose": 1.84, "avg_win": 1.65, "avg_draw": 3.45, "avg_lose": 5.03, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.26, "jc_lose": 4.2, "rq_win": 3.4, "rq_draw": 3.3, "rq_lose": 1.88, "avg_win": 1.69, "avg_draw": 3.49, "avg_lose": 4.67, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.48, "jc_lose": 5.7, "rq_win": 2.13, "rq_draw": 3.75, "rq_lose": 2.55, "avg_win": 1.62, "avg_draw": 4.21, "avg_lose": 4.3, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 2.85, "jc_lose": 2.86, "rq_win": 5.5, "rq_draw": 3.8, "rq_lose": 1.46, "avg_win": 2.34, "avg_draw": 3.18, "avg_lose": 2.91, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.4, "jc_draw": 3.0, "jc_lose": 2.65, "rq_win": 5.6, "rq_draw": 3.9, "rq_lose": 1.44, "avg_win": 2.59, "avg_draw": 3.22, "avg_lose": 2.57, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.77, "jc_draw": 3.25, "jc_lose": 2.17, "rq_win": 1.51, "rq_draw": 3.8, "rq_lose": 4.9, "avg_win": 2.84, "avg_draw": 3.59, "avg_lose": 2.24, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.45, "jc_lose": 1.78, "rq_win": 1.81, "rq_draw": 3.48, "rq_lose": 3.45, "avg_win": 4.06, "avg_draw": 3.53, "avg_lose": 1.81, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.6, "jc_draw": 3.45, "jc_lose": 4.65, "rq_win": 2.99, "rq_draw": 3.25, "rq_lose": 2.05, "avg_win": 1.69, "avg_draw": 3.55, "avg_lose": 4.68, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.72, "jc_draw": 3.15, "jc_lose": 2.25, "rq_win": 1.49, "rq_draw": 3.75, "rq_lose": 5.22, "avg_win": 2.91, "avg_draw": 3.18, "avg_lose": 2.34, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.81, "jc_draw": 3.5, "jc_lose": 3.45, "rq_win": 3.5, "rq_draw": 3.6, "rq_lose": 1.77, "avg_win": 2.18, "avg_draw": 3.33, "avg_lose": 2.92, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 3.65, "jc_lose": 3.02, "rq_win": 3.95, "rq_draw": 3.95, "rq_lose": 1.61, "avg_win": 2.02, "avg_draw": 3.5, "avg_lose": 2.88, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 6.05, "jc_draw": 4.7, "jc_lose": 1.33, "rq_win": 2.7, "rq_draw": 3.7, "rq_lose": 2.05, "avg_win": 5.43, "avg_draw": 4.33, "avg_lose": 1.48, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 3.96, "jc_draw": 3.0, "jc_lose": 1.84, "rq_win": 1.74, "rq_draw": 3.3, "rq_lose": 4.0, "avg_win": 3.3, "avg_draw": 3.04, "avg_lose": 2.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.66, "jc_draw": 3.5, "jc_lose": 4.15, "rq_win": 3.1, "rq_draw": 3.45, "rq_lose": 1.94, "avg_win": 1.77, "avg_draw": 3.56, "avg_lose": 4.21, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.9, "jc_lose": 3.52, "rq_win": 3.0, "rq_draw": 3.75, "rq_lose": 1.89, "avg_win": 1.63, "avg_draw": 4.15, "avg_lose": 4.28, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 2.16, "jc_draw": 3.65, "jc_lose": 2.55, "rq_win": 4.3, "rq_draw": 4.12, "rq_lose": 1.53, "avg_win": 2.01, "avg_draw": 3.83, "avg_lose": 3.06, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.26, "jc_draw": 4.8, "jc_lose": 8.0, "rq_win": 1.92, "rq_draw": 3.5, "rq_lose": 3.1, "avg_win": 1.45, "avg_draw": 4.21, "avg_lose": 6.39, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.99, "jc_draw": 3.05, "jc_lose": 3.35, "rq_win": 4.3, "rq_draw": 3.5, "rq_lose": 1.64, "avg_win": 1.94, "avg_draw": 3.18, "avg_lose": 3.91, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.32, "jc_lose": 2.68, "rq_win": 4.6, "rq_draw": 3.95, "rq_lose": 1.52, "avg_win": 2.42, "avg_draw": 3.4, "avg_lose": 2.66, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.01, "jc_draw": 3.3, "jc_lose": 3.05, "rq_win": 4.15, "rq_draw": 3.65, "rq_lose": 1.63, "avg_win": 1.75, "avg_draw": 3.57, "avg_lose": 4.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.5, "jc_lose": 3.0, "rq_win": 3.95, "rq_draw": 3.75, "rq_lose": 1.64, "avg_win": 2.16, "avg_draw": 3.48, "avg_lose": 2.94, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 5.0, "jc_draw": 4.1, "jc_lose": 1.46, "rq_win": 2.35, "rq_draw": 3.4, "rq_lose": 2.45, "avg_win": 4.74, "avg_draw": 3.85, "avg_lose": 1.61, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 4.3, "jc_draw": 3.8, "jc_lose": 1.58, "rq_win": 2.05, "rq_draw": 3.45, "rq_lose": 2.85, "avg_win": 4.57, "avg_draw": 3.72, "avg_lose": 1.67, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.06, "jc_draw": 3.0, "jc_lose": 2.13, "rq_win": 1.54, "rq_draw": 3.6, "rq_lose": 4.95, "avg_win": 3.09, "avg_draw": 3.13, "avg_lose": 2.26, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.82, "jc_draw": 3.1, "jc_lose": 2.21, "rq_win": 1.51, "rq_draw": 3.8, "rq_lose": 4.9, "avg_win": 2.78, "avg_draw": 3.27, "avg_lose": 2.38, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.49, "jc_draw": 4.05, "jc_lose": 4.75, "rq_win": 2.46, "rq_draw": 3.55, "rq_lose": 2.27, "avg_win": 1.51, "avg_draw": 4.21, "avg_lose": 5.56, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 3.15, "jc_draw": 3.65, "jc_lose": 1.86, "rq_win": 1.74, "rq_draw": 3.72, "rq_lose": 3.5, "avg_win": 2.95, "avg_draw": 3.52, "avg_lose": 2.1, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.65, "jc_lose": 4.5, "rq_win": 2.88, "rq_draw": 3.3, "rq_lose": 2.09, "avg_win": 1.73, "avg_draw": 3.59, "avg_lose": 4.39, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.35, "jc_draw": 4.05, "jc_lose": 7.05, "rq_win": 2.28, "rq_draw": 3.2, "rq_lose": 2.65, "avg_win": 1.54, "avg_draw": 3.74, "avg_lose": 6.01, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.15, "jc_lose": 3.7, "rq_win": 3.85, "rq_draw": 3.45, "rq_lose": 1.73, "avg_win": 2.38, "avg_draw": 3.09, "avg_lose": 2.88, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.0, "jc_lose": 6.05, "rq_win": 2.41, "rq_draw": 3.25, "rq_lose": 2.46, "avg_win": 1.7, "avg_draw": 3.79, "avg_lose": 4.36, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.82, "jc_draw": 3.4, "jc_lose": 3.5, "rq_win": 3.65, "rq_draw": 3.52, "rq_lose": 1.75, "avg_win": 1.78, "avg_draw": 3.52, "avg_lose": 4.13, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 6.4, "jc_draw": 4.4, "jc_lose": 1.34, "rq_win": 2.73, "rq_draw": 3.4, "rq_lose": 2.13, "avg_win": 5.87, "avg_draw": 4.0, "avg_lose": 1.5, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.35, "jc_lose": 3.2, "rq_win": 3.9, "rq_draw": 3.62, "rq_lose": 1.68, "avg_win": 2.18, "avg_draw": 3.39, "avg_lose": 3.05, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "正常", "match_context": "Z=2.2900; Y=1.3200; X=1.6400; cold_risk=12.4%; dev_level=一致", "match_id": "#626"},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.96, "jc_lose": 4.1, "rq_win": 2.78, "rq_draw": 3.55, "rq_lose": 2.05, "avg_win": 1.67, "avg_draw": 4.02, "avg_lose": 4.32, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.84, "jc_draw": 3.12, "jc_lose": 3.77, "rq_win": 3.95, "rq_draw": 3.25, "rq_lose": 1.76, "avg_win": 1.87, "avg_draw": 3.29, "avg_lose": 4.14, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 4.25, "jc_lose": 1.37, "rq_win": 2.59, "rq_draw": 3.3, "rq_lose": 2.27, "avg_win": 6.08, "avg_draw": 4.04, "avg_lose": 1.5, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.97, "jc_draw": 3.82, "jc_lose": 2.78, "rq_win": 3.62, "rq_draw": 4.05, "rq_lose": 1.65, "avg_win": 1.52, "avg_draw": 4.61, "avg_lose": 4.94, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.56, "jc_draw": 3.6, "jc_lose": 4.75, "rq_win": 2.82, "rq_draw": 3.35, "rq_lose": 2.1, "avg_win": 1.61, "avg_draw": 3.6, "avg_lose": 5.46, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.65, "jc_lose": 2.01, "rq_win": 1.63, "rq_draw": 3.9, "rq_lose": 3.85, "avg_win": 2.94, "avg_draw": 3.74, "avg_lose": 2.1, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.75, "jc_draw": 3.26, "jc_lose": 1.8, "rq_win": 1.78, "rq_draw": 3.45, "rq_lose": 3.6, "avg_win": 4.25, "avg_draw": 3.42, "avg_lose": 1.79, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.86, "jc_draw": 2.9, "jc_lose": 2.3, "rq_win": 1.48, "rq_draw": 3.7, "rq_lose": 5.45, "avg_win": 2.76, "avg_draw": 2.94, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.15, "jc_lose": 4.46, "rq_win": 3.45, "rq_draw": 3.2, "rq_lose": 1.9, "avg_win": 1.86, "avg_draw": 3.33, "avg_lose": 4.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.01, "jc_draw": 3.15, "jc_lose": 3.18, "rq_win": 4.15, "rq_draw": 3.65, "rq_lose": 1.63, "avg_win": 2.09, "avg_draw": 3.23, "avg_lose": 3.36, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.3, "jc_lose": 3.25, "rq_win": 3.85, "rq_draw": 3.65, "rq_lose": 1.68, "avg_win": 2.25, "avg_draw": 3.44, "avg_lose": 2.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.86, "jc_draw": 3.2, "jc_lose": 3.6, "rq_win": 3.9, "rq_draw": 3.45, "rq_lose": 1.72, "avg_win": 2.24, "avg_draw": 3.23, "avg_lose": 3.02, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.43, "jc_draw": 4.1, "jc_lose": 5.4, "rq_win": 2.4, "rq_draw": 3.45, "rq_lose": 2.38, "avg_win": 1.92, "avg_draw": 3.52, "avg_lose": 3.64, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.91, "jc_draw": 3.15, "jc_lose": 3.47, "rq_win": 4.1, "rq_draw": 3.45, "rq_lose": 1.68, "avg_win": 2.05, "avg_draw": 3.25, "avg_lose": 3.45, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.01, "jc_draw": 3.2, "jc_lose": 3.13, "rq_win": 4.2, "rq_draw": 3.65, "rq_lose": 1.62, "avg_win": 2.02, "avg_draw": 3.34, "avg_lose": 3.45, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 3.8, "jc_draw": 3.05, "jc_lose": 1.86, "rq_win": 1.72, "rq_draw": 3.3, "rq_lose": 4.08, "avg_win": 3.4, "avg_draw": 3.05, "avg_lose": 2.15, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 5.25, "jc_draw": 4.1, "jc_lose": 1.44, "rq_win": 2.4, "rq_draw": 3.5, "rq_lose": 2.35, "avg_win": 4.78, "avg_draw": 4.1, "avg_lose": 1.57, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.44, "jc_draw": 3.4, "jc_lose": 2.35, "rq_win": 1.45, "rq_draw": 4.25, "rq_lose": 4.9, "avg_win": 2.38, "avg_draw": 3.43, "avg_lose": 2.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 2.75, "jc_lose": 3.7, "rq_win": 4.6, "rq_draw": 3.45, "rq_lose": 1.61, "avg_win": 2.23, "avg_draw": 3.03, "avg_lose": 3.66, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 5.15, "jc_draw": 4.0, "jc_lose": 1.46, "rq_win": 2.34, "rq_draw": 3.5, "rq_lose": 2.4, "avg_win": 4.89, "avg_draw": 4.09, "avg_lose": 1.56, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 5.8, "jc_lose": 10.5, "rq_win": 2.75, "rq_draw": 3.88, "rq_lose": 1.97, "avg_win": 1.29, "avg_draw": 5.28, "avg_lose": 8.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 4.56, "jc_draw": 4.1, "jc_lose": 1.5, "rq_win": 2.25, "rq_draw": 3.55, "rq_lose": 2.48, "avg_win": 4.58, "avg_draw": 3.95, "avg_lose": 1.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.45, "jc_draw": 3.65, "jc_lose": 1.77, "rq_win": 1.8, "rq_draw": 3.65, "rq_lose": 3.35, "avg_win": 3.1, "avg_draw": 3.55, "avg_lose": 2.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.5, "jc_lose": 5.3, "rq_win": 2.88, "rq_draw": 3.15, "rq_lose": 2.15, "avg_win": 1.58, "avg_draw": 3.67, "avg_lose": 5.52, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 5.15, "jc_draw": 3.45, "jc_lose": 1.55, "rq_win": 2.12, "rq_draw": 3.2, "rq_lose": 2.9, "avg_win": 4.66, "avg_draw": 3.44, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.76, "jc_draw": 3.75, "jc_lose": 3.4, "rq_win": 3.2, "rq_draw": 3.8, "rq_lose": 1.81, "avg_win": 2.3, "avg_draw": 3.31, "avg_lose": 3.24, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 6.25, "jc_lose": 9.3, "rq_win": 2.56, "rq_draw": 4.0, "rq_lose": 2.05, "avg_win": 1.28, "avg_draw": 5.54, "avg_lose": 8.34, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.75, "jc_lose": 2.86, "rq_win": 3.75, "rq_draw": 3.95, "rq_lose": 1.64, "avg_win": 1.99, "avg_draw": 3.7, "avg_lose": 3.17, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.62, "jc_draw": 3.35, "jc_lose": 2.23, "rq_win": 1.5, "rq_draw": 4.1, "rq_lose": 4.6, "avg_win": 3.16, "avg_draw": 3.58, "avg_lose": 2.02, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.19, "jc_draw": 3.3, "jc_lose": 2.71, "rq_win": 4.6, "rq_draw": 3.95, "rq_lose": 1.52, "avg_win": 1.92, "avg_draw": 3.53, "avg_lose": 3.41, "shenjia": "主身 = 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.55, "jc_lose": 2.13, "rq_win": 1.54, "rq_draw": 4.0, "rq_lose": 4.4, "avg_win": 2.92, "avg_draw": 3.57, "avg_lose": 2.13, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.66, "jc_draw": 3.45, "jc_lose": 2.16, "rq_win": 1.52, "rq_draw": 3.95, "rq_lose": 4.6, "avg_win": 2.78, "avg_draw": 3.49, "avg_lose": 2.27, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.59, "jc_draw": 3.85, "jc_lose": 4.15, "rq_win": 2.84, "rq_draw": 3.45, "rq_lose": 2.05, "avg_win": 1.72, "avg_draw": 3.75, "avg_lose": 4.18, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 3.25, "jc_lose": 2.55, "rq_win": 5.2, "rq_draw": 4.05, "rq_lose": 1.45, "avg_win": 2.49, "avg_draw": 3.35, "avg_lose": 2.62, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.7, "jc_lose": 3.4, "rq_win": 3.2, "rq_draw": 3.7, "rq_lose": 1.83, "avg_win": 1.82, "avg_draw": 4.03, "avg_lose": 3.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 3.45, "jc_draw": 3.35, "jc_lose": 1.85, "rq_win": 1.72, "rq_draw": 3.55, "rq_lose": 3.75, "avg_win": 3.36, "avg_draw": 3.32, "avg_lose": 2.05, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.25, "jc_draw": 3.02, "jc_lose": 2.04, "rq_win": 1.59, "rq_draw": 3.55, "rq_lose": 4.6, "avg_win": 3.18, "avg_draw": 3.16, "avg_lose": 2.14, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.9, "jc_draw": 2.83, "jc_lose": 2.32, "rq_win": 1.46, "rq_draw": 3.65, "rq_lose": 5.85, "avg_win": 2.95, "avg_draw": 2.96, "avg_lose": 2.39, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.65, "jc_draw": 3.35, "jc_lose": 4.45, "rq_win": 3.25, "rq_draw": 3.25, "rq_lose": 1.95, "avg_win": 1.79, "avg_draw": 3.35, "avg_lose": 4.17, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 3.15, "jc_lose": 2.75, "rq_win": 5.05, "rq_draw": 3.85, "rq_lose": 1.49, "avg_win": 2.32, "avg_draw": 3.21, "avg_lose": 2.82, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.45, "jc_lose": 2.47, "rq_win": 4.92, "rq_draw": 4.15, "rq_lose": 1.46, "avg_win": 2.65, "avg_draw": 3.45, "avg_lose": 2.39, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 6.6, "jc_draw": 5.25, "jc_lose": 1.27, "rq_win": 3.0, "rq_draw": 3.9, "rq_lose": 1.86, "avg_win": 6.67, "avg_draw": 4.63, "avg_lose": 1.37, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 3.8, "jc_lose": 5.3, "rq_win": 2.55, "rq_draw": 3.35, "rq_lose": 2.28, "avg_win": 1.81, "avg_draw": 3.51, "avg_lose": 4.06, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": -1, "jc_win": 3.9, "jc_draw": 3.32, "jc_lose": 1.75, "rq_win": 1.83, "rq_draw": 3.35, "rq_lose": 3.52, "avg_win": 3.68, "avg_draw": 3.33, "avg_lose": 1.95, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 3.2, "jc_lose": 3.1, "rq_win": 4.6, "rq_draw": 3.45, "rq_lose": 1.61, "avg_win": 2.64, "avg_draw": 3.28, "avg_lose": 2.59, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.15, "jc_lose": 2.3, "rq_win": 1.47, "rq_draw": 3.95, "rq_lose": 5.1, "avg_win": 2.72, "avg_draw": 3.21, "avg_lose": 2.48, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.32, "jc_draw": 3.12, "jc_lose": 2.65, "rq_win": 5.25, "rq_draw": 3.95, "rq_lose": 1.46, "avg_win": 2.3, "avg_draw": 3.25, "avg_lose": 2.97, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 3.15, "jc_draw": 3.1, "jc_lose": 2.05, "rq_win": 1.6, "rq_draw": 3.6, "rq_lose": 4.45, "avg_win": 3.3, "avg_draw": 3.3, "avg_lose": 2.07, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 3.65, "jc_draw": 3.7, "jc_lose": 1.71, "rq_win": 1.9, "rq_draw": 3.5, "rq_lose": 3.15, "avg_win": 3.81, "avg_draw": 3.3, "avg_lose": 2.0, "shenjia": "主身 < 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 4.0, "jc_lose": 4.15, "rq_win": 2.64, "rq_draw": 3.65, "rq_lose": 2.1, "avg_win": 1.8, "avg_draw": 3.88, "avg_lose": 3.77, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.45, "jc_lose": 3.52, "rq_win": 3.46, "rq_draw": 3.55, "rq_lose": 1.79, "avg_win": 1.99, "avg_draw": 3.37, "avg_lose": 3.7, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.73, "jc_draw": 3.15, "jc_lose": 4.3, "rq_win": 3.55, "rq_draw": 3.25, "rq_lose": 1.85, "avg_win": 2.07, "avg_draw": 3.3, "avg_lose": 3.33, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.18, "jc_lose": 2.33, "rq_win": 1.46, "rq_draw": 4.0, "rq_lose": 5.15, "avg_win": 3.23, "avg_draw": 3.17, "avg_lose": 2.21, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 3.9, "jc_lose": 7.0, "rq_win": 2.35, "rq_draw": 3.15, "rq_lose": 2.59, "avg_win": 1.57, "avg_draw": 3.56, "avg_lose": 5.7, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.8, "jc_lose": 3.7, "rq_win": 3.0, "rq_draw": 3.7, "rq_lose": 1.9, "avg_win": 1.61, "avg_draw": 4.13, "avg_lose": 4.43, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 4.4, "jc_lose": 4.5, "rq_win": 2.32, "rq_draw": 3.85, "rq_lose": 2.28, "avg_win": 1.74, "avg_draw": 3.94, "avg_lose": 4.07, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.78, "jc_lose": 3.53, "rq_win": 3.08, "rq_draw": 3.75, "rq_lose": 1.86, "avg_win": 1.72, "avg_draw": 3.98, "avg_lose": 4.04, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.65, "jc_lose": 2.9, "rq_win": 3.8, "rq_draw": 3.95, "rq_lose": 1.63, "avg_win": 2.17, "avg_draw": 3.66, "avg_lose": 2.92, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 2.11, "jc_draw": 3.5, "jc_lose": 2.71, "rq_win": 4.02, "rq_draw": 4.1, "rq_lose": 1.57, "avg_win": 2.14, "avg_draw": 3.75, "avg_lose": 2.91, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.34, "jc_draw": 4.6, "jc_lose": 6.05, "rq_win": 2.08, "rq_draw": 3.65, "rq_lose": 2.67, "avg_win": 1.39, "avg_draw": 4.6, "avg_lose": 6.68, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.7, "jc_lose": 3.6, "rq_win": 3.1, "rq_draw": 3.6, "rq_lose": 1.89, "avg_win": 1.95, "avg_draw": 3.4, "avg_lose": 3.62, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.4, "jc_lose": 3.6, "rq_win": 3.62, "rq_draw": 3.4, "rq_lose": 1.79, "avg_win": 1.76, "avg_draw": 3.69, "avg_lose": 4.09, "shenjia": "未输入", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.35, "jc_lose": 2.85, "rq_win": 4.25, "rq_draw": 3.85, "rq_lose": 1.58, "avg_win": 2.05, "avg_draw": 3.57, "avg_lose": 3.16, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.6, "jc_lose": 1.95, "rq_win": 1.65, "rq_draw": 3.75, "rq_lose": 3.9, "avg_win": 2.57, "avg_draw": 3.25, "avg_lose": 2.56, "shenjia": "主身 < 客身", "real_result": "平", "real_score": ""},
    {"handicap": 2, "jc_win": 1.2, "jc_draw": 5.5, "jc_lose": 11.0, "rq_win": 2.15, "rq_draw": 3.9, "rq_lose": 2.45, "avg_win": 1.2, "avg_draw": 5.87, "avg_lose": 12.45, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.15, "jc_lose": 4.35, "rq_win": 3.62, "rq_draw": 3.15, "rq_lose": 1.87, "avg_win": 1.88, "avg_draw": 3.25, "avg_lose": 4.19, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 4.25, "jc_lose": 4.7, "rq_win": 2.43, "rq_draw": 3.65, "rq_lose": 2.25, "avg_win": 1.72, "avg_draw": 4.0, "avg_lose": 3.98, "shenjia": "主身 > 客身", "real_result": "负", "real_score": ""},
    {"handicap": 2, "jc_win": 1.17, "jc_draw": 6.1, "jc_lose": 9.0, "rq_win": 2.45, "rq_draw": 4.2, "rq_lose": 2.07, "avg_win": 1.3, "avg_draw": 5.35, "avg_lose": 7.46, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.6, "jc_draw": 3.58, "jc_lose": 4.45, "rq_win": 2.88, "rq_draw": 3.45, "rq_lose": 2.03, "avg_win": 1.58, "avg_draw": 4.33, "avg_lose": 4.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": 1, "jc_win": 1.74, "jc_draw": 3.05, "jc_lose": 4.4, "rq_win": 3.65, "rq_draw": 3.15, "rq_lose": 1.86, "avg_win": 1.9, "avg_draw": 3.06, "avg_lose": 4.42, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.19, "jc_draw": 5.1, "jc_lose": 11.0, "rq_win": 1.8, "rq_draw": 3.4, "rq_lose": 3.58, "avg_win": 1.29, "avg_draw": 4.87, "avg_lose": 9.81, "shenjia": "主身 > 客身", "real_result": "平", "real_score": ""},
    {"handicap": 1, "jc_win": 1.6, "jc_draw": 3.58, "jc_lose": 4.45, "rq_win": 2.88, "rq_draw": 3.45, "rq_lose": 2.03, "avg_win": 1.58, "avg_draw": 4.33, "avg_lose": 4.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.19, "jc_draw": 5.1, "jc_lose": 11.0, "rq_win": 1.8, "rq_draw": 3.4, "rq_lose": 3.58, "avg_win": 1.29, "avg_draw": 4.87, "avg_lose": 9.81, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.74, "jc_draw": 3.05, "jc_lose": 4.4, "rq_win": 3.65, "rq_draw": 3.15, "rq_lose": 1.86, "avg_win": 1.9, "avg_draw": 3.06, "avg_lose": 4.42, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.4, "jc_lose": 5.8, "rq_win": 2.15, "rq_draw": 3.55, "rq_lose": 2.61, "avg_win": 1.63, "avg_draw": 4.1, "avg_lose": 4.54, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 4.8, "jc_lose": 1.32, "rq_win": 2.78, "rq_draw": 3.55, "rq_lose": 2.05, "avg_win": 7.08, "avg_draw": 4.2, "avg_lose": 1.43, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 3.3, "jc_lose": 2.17, "rq_win": 1.54, "rq_draw": 3.75, "rq_lose": 4.7, "avg_win": 2.79, "avg_draw": 3.05, "avg_lose": 2.57, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.54, "jc_draw": 3.9, "jc_lose": 4.5, "rq_win": 2.7, "rq_draw": 3.35, "rq_lose": 2.17, "avg_win": 1.53, "avg_draw": 3.97, "avg_lose": 5.6, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 4.45, "jc_draw": 4.2, "jc_lose": 1.5, "rq_win": 2.25, "rq_draw": 3.6, "rq_lose": 2.46, "avg_win": 4.69, "avg_draw": 4.15, "avg_lose": 1.57, "shenjia": "未输入", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 3.65, "jc_lose": 2.4, "rq_win": 4.7, "rq_draw": 4.15, "rq_lose": 1.48, "avg_win": 2.53, "avg_draw": 3.78, "avg_lose": 2.36, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": -1, "jc_win": 2.82, "jc_draw": 3.1, "jc_lose": 2.21, "rq_win": 1.51, "rq_draw": 3.8, "rq_lose": 4.9, "avg_win": 2.78, "avg_draw": 3.27, "avg_lose": 2.38, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 2.01, "jc_draw": 3.3, "jc_lose": 3.05, "rq_win": 4.15, "rq_draw": 3.65, "rq_lose": 1.63, "avg_win": 1.75, "avg_draw": 3.57, "avg_lose": 4.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 3.96, "jc_draw": 3.0, "jc_lose": 1.84, "rq_win": 1.74, "rq_draw": 3.3, "rq_lose": 4.0, "avg_win": 3.3, "avg_draw": 3.04, "avg_lose": 2.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.86, "jc_draw": 3.45, "jc_lose": 3.32, "rq_win": 3.6, "rq_draw": 3.7, "rq_lose": 1.72, "avg_win": 1.85, "avg_draw": 3.5, "avg_lose": 3.83, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": ""},
    {"handicap": -1, "jc_win": 2.88, "jc_draw": 3.7, "jc_lose": 1.96, "rq_win": 1.66, "rq_draw": 3.9, "rq_lose": 3.7, "avg_win": 2.84, "avg_draw": 3.62, "avg_lose": 2.11, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 3.35, "jc_draw": 3.35, "jc_lose": 1.88, "rq_win": 1.71, "rq_draw": 3.55, "rq_lose": 3.8, "avg_win": 3.78, "avg_draw": 3.48, "avg_lose": 1.91, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.15, "jc_lose": 2.3, "rq_win": 1.47, "rq_draw": 3.95, "rq_lose": 5.1, "avg_win": 2.72, "avg_draw": 3.21, "avg_lose": 2.48, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 2.85, "jc_draw": 3.15, "jc_lose": 2.17, "rq_win": 1.52, "rq_draw": 3.7, "rq_lose": 5.0, "avg_win": 2.82, "avg_draw": 3.19, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 4.05, "jc_lose": 1.58, "rq_win": 2.08, "rq_draw": 3.7, "rq_lose": 2.64, "avg_win": 3.97, "avg_draw": 3.86, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.85, "jc_lose": 1.64, "rq_win": 1.95, "rq_draw": 3.65, "rq_lose": 2.92, "avg_win": 3.65, "avg_draw": 3.68, "avg_lose": 1.82, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 3.9, "jc_draw": 3.05, "jc_lose": 1.84, "rq_win": 1.75, "rq_draw": 3.25, "rq_lose": 4.0, "avg_win": 4.69, "avg_draw": 3.44, "avg_lose": 1.76, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 1.54, "jc_draw": 3.8, "jc_lose": 4.6, "rq_win": 2.66, "rq_draw": 3.5, "rq_lose": 2.14, "avg_win": 1.66, "avg_draw": 3.72, "avg_lose": 4.42, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.23, "jc_lose": 2.6, "rq_win": 5.1, "rq_draw": 4.1, "rq_lose": 1.45, "avg_win": 2.23, "avg_draw": 3.26, "avg_lose": 3.05, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 2.43, "jc_draw": 3.18, "jc_lose": 2.48, "rq_win": 5.57, "rq_draw": 4.15, "rq_lose": 1.41, "avg_win": 2.56, "avg_draw": 3.22, "avg_lose": 2.56, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.4, "jc_lose": 3.95, "rq_win": 3.25, "rq_draw": 3.45, "rq_lose": 1.88, "avg_win": 1.7, "avg_draw": 3.69, "avg_lose": 4.47, "shenjia": "未输入", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.62, "jc_draw": 3.62, "jc_lose": 4.2, "rq_win": 3.0, "rq_draw": 3.45, "rq_lose": 1.98, "avg_win": 2.05, "avg_draw": 3.44, "avg_lose": 3.23, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 2.43, "jc_draw": 3.65, "jc_lose": 2.25, "rq_win": 1.48, "rq_draw": 4.25, "rq_lose": 4.6, "avg_win": 3.35, "avg_draw": 3.63, "avg_lose": 1.93, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.4, "jc_lose": 3.4, "rq_win": 3.57, "rq_draw": 3.7, "rq_lose": 1.73, "avg_win": 2.05, "avg_draw": 3.65, "avg_lose": 3.18, "shenjia": "未输入", "real_result": "胜", "real_score": "4:2"},
    {"handicap": 1, "jc_win": 2.17, "jc_draw": 3.45, "jc_lose": 2.65, "rq_win": 4.4, "rq_draw": 4.1, "rq_lose": 1.52, "avg_win": 2.37, "avg_draw": 3.53, "avg_lose": 2.72, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.5, "jc_lose": 3.6, "rq_win": 3.35, "rq_draw": 3.6, "rq_lose": 1.81, "avg_win": 1.83, "avg_draw": 3.63, "avg_lose": 3.76, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 4.25, "jc_lose": 4.35, "rq_win": 2.5, "rq_draw": 3.65, "rq_lose": 2.2, "avg_win": 1.63, "avg_draw": 4.26, "avg_lose": 4.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.97, "jc_draw": 3.2, "jc_lose": 3.25, "rq_win": 4.2, "rq_draw": 3.6, "rq_lose": 1.63, "avg_win": 2.09, "avg_draw": 3.38, "avg_lose": 3.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.56, "jc_draw": 3.6, "jc_lose": 4.75, "rq_win": 2.9, "rq_draw": 3.3, "rq_lose": 2.08, "avg_win": 1.7, "avg_draw": 3.69, "avg_lose": 4.4, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "3:3"},
    {"handicap": 1, "jc_win": 1.35, "jc_draw": 4.3, "jc_lose": 6.4, "rq_win": 2.19, "rq_draw": 3.45, "rq_lose": 2.62, "avg_win": 1.59, "avg_draw": 3.98, "avg_lose": 4.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 2, "jc_win": 1.14, "jc_draw": 6.0, "jc_lose": 11.8, "rq_win": 2.62, "rq_draw": 4.0, "rq_lose": 2.01, "avg_win": 1.2, "avg_draw": 6.78, "avg_lose": 11.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.35, "jc_lose": 3.77, "rq_win": 3.55, "rq_draw": 3.4, "rq_lose": 1.81, "avg_win": 1.7, "avg_draw": 3.57, "avg_lose": 4.59, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.13, "jc_draw": 3.12, "jc_lose": 2.95, "rq_win": 4.9, "rq_draw": 3.7, "rq_lose": 1.53, "avg_win": 2.26, "avg_draw": 3.14, "avg_lose": 3.07, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 2.53, "jc_draw": 3.04, "jc_lose": 2.47, "rq_win": 1.4, "rq_draw": 4.0, "rq_lose": 6.05, "avg_win": 2.68, "avg_draw": 2.94, "avg_lose": 2.57, "shenjia": "未输入", "real_result": "负", "real_score": "0:4"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.35, "jc_lose": 1.81, "rq_win": 1.77, "rq_draw": 3.5, "rq_lose": 3.6, "avg_win": 3.75, "avg_draw": 3.42, "avg_lose": 1.9, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": 1, "jc_win": 1.86, "jc_draw": 3.35, "jc_lose": 3.42, "rq_win": 3.75, "rq_draw": 3.55, "rq_lose": 1.72, "avg_win": 1.85, "avg_draw": 3.46, "avg_lose": 3.89, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:2"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.02, "jc_lose": 1.86, "rq_win": 1.72, "rq_draw": 3.35, "rq_lose": 4.0, "avg_win": 4.45, "avg_draw": 3.18, "avg_lose": 1.82, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.45, "jc_lose": 2.77, "rq_win": 4.32, "rq_draw": 3.95, "rq_lose": 1.55, "avg_win": 2.19, "avg_draw": 3.4, "avg_lose": 3.04, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 3.16, "jc_lose": 3.2, "rq_win": 4.15, "rq_draw": 3.7, "rq_lose": 1.62, "avg_win": 2.21, "avg_draw": 3.19, "avg_lose": 3.05, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.38, "jc_lose": 2.02, "rq_win": 1.62, "rq_draw": 3.8, "rq_lose": 4.02, "avg_win": 3.07, "avg_draw": 3.6, "avg_lose": 2.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:3"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.25, "jc_lose": 3.48, "rq_win": 3.72, "rq_draw": 3.55, "rq_lose": 1.73, "avg_win": 2.0, "avg_draw": 3.4, "avg_lose": 3.41, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.45, "jc_lose": 2.2, "rq_win": 1.51, "rq_draw": 4.0, "rq_lose": 4.6, "avg_win": 2.69, "avg_draw": 3.42, "avg_lose": 2.33, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 4.18, "jc_draw": 3.95, "jc_lose": 1.57, "rq_win": 2.08, "rq_draw": 3.7, "rq_lose": 2.65, "avg_win": 4.73, "avg_draw": 4.24, "avg_lose": 1.57, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": 1, "jc_win": 1.91, "jc_draw": 3.1, "jc_lose": 3.55, "rq_win": 4.1, "rq_draw": 3.45, "rq_lose": 1.68, "avg_win": 2.17, "avg_draw": 3.22, "avg_lose": 3.3, "shenjia": "未输入", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 5.35, "jc_draw": 4.5, "jc_lose": 1.39, "rq_win": 2.52, "rq_draw": 3.75, "rq_lose": 2.15, "avg_win": 4.5, "avg_draw": 3.97, "avg_lose": 1.6, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.55, "jc_lose": 3.25, "rq_win": 3.45, "rq_draw": 3.75, "rq_lose": 1.75, "avg_win": 1.79, "avg_draw": 3.81, "avg_lose": 3.83, "shenjia": "未输入", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 2.12, "jc_draw": 3.2, "jc_lose": 2.9, "rq_win": 4.4, "rq_draw": 3.9, "rq_lose": 1.55, "avg_win": 2.46, "avg_draw": 3.14, "avg_lose": 2.75, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.63, "jc_draw": 3.45, "jc_lose": 2.18, "rq_win": 1.51, "rq_draw": 4.0, "rq_lose": 4.6, "avg_win": 2.31, "avg_draw": 3.61, "avg_lose": 2.66, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 2.95, "jc_lose": 2.22, "rq_win": 1.5, "rq_draw": 3.65, "rq_lose": 5.3, "avg_win": 3.13, "avg_draw": 3.23, "avg_lose": 2.25, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 2.6, "jc_lose": 3.38, "rq_win": 5.8, "rq_draw": 3.5, "rq_lose": 1.49, "avg_win": 2.3, "avg_draw": 2.87, "avg_lose": 3.39, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.36, "jc_draw": 4.4, "jc_lose": 6.0, "rq_win": 2.15, "rq_draw": 3.55, "rq_lose": 2.62, "avg_win": 1.44, "avg_draw": 4.47, "avg_lose": 5.86, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 5.05, "jc_draw": 4.6, "jc_lose": 1.4, "rq_win": 2.45, "rq_draw": 3.95, "rq_lose": 2.14, "avg_win": 4.54, "avg_draw": 4.34, "avg_lose": 1.56, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 3.95, "jc_lose": 4.2, "rq_win": 2.68, "rq_draw": 3.7, "rq_lose": 2.06, "avg_win": 1.83, "avg_draw": 3.83, "avg_lose": 3.64, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 2.9, "jc_lose": 3.05, "rq_win": 5.2, "rq_draw": 3.65, "rq_lose": 1.51, "avg_win": 2.3, "avg_draw": 3.13, "avg_lose": 3.09, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 9.2, "jc_draw": 4.85, "jc_lose": 1.23, "rq_win": 3.25, "rq_draw": 3.55, "rq_lose": 1.85, "avg_win": 8.7, "avg_draw": 5.42, "avg_lose": 1.3, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 2.8, "jc_lose": 2.54, "rq_win": 1.38, "rq_draw": 4.1, "rq_lose": 6.2, "avg_win": 2.65, "avg_draw": 3.07, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.99, "jc_draw": 3.05, "jc_lose": 3.35, "rq_win": 4.3, "rq_draw": 3.5, "rq_lose": 1.64, "avg_win": 1.94, "avg_draw": 3.18, "avg_lose": 3.91, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -1, "jc_win": 3.06, "jc_draw": 3.0, "jc_lose": 2.13, "rq_win": 1.54, "rq_draw": 3.6, "rq_lose": 4.95, "avg_win": 3.09, "avg_draw": 3.13, "avg_lose": 2.26, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.72, "jc_lose": 4.05, "rq_win": 2.9, "rq_draw": 3.6, "rq_lose": 1.99, "avg_win": 1.68, "avg_draw": 3.92, "avg_lose": 4.29, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 3.8, "jc_lose": 5.7, "rq_win": 2.48, "rq_draw": 3.3, "rq_lose": 2.37, "avg_win": 1.57, "avg_draw": 3.78, "avg_lose": 5.29, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.16, "jc_draw": 2.95, "jc_lose": 3.05, "rq_win": 5.0, "rq_draw": 3.65, "rq_lose": 1.53, "avg_win": 2.27, "avg_draw": 3.13, "avg_lose": 3.15, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.4, "jc_draw": 2.95, "jc_lose": 2.68, "rq_win": 5.8, "rq_draw": 3.95, "rq_lose": 1.42, "avg_win": 2.32, "avg_draw": 3.07, "avg_lose": 2.98, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.5, "jc_draw": 3.4, "jc_lose": 2.3, "rq_win": 1.46, "rq_draw": 4.1, "rq_lose": 5.0, "avg_win": 2.69, "avg_draw": 3.67, "avg_lose": 2.28, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4"},
    {"handicap": -1, "jc_win": 4.35, "jc_draw": 3.42, "jc_lose": 1.65, "rq_win": 1.95, "rq_draw": 3.35, "rq_lose": 3.15, "avg_win": 4.56, "avg_draw": 3.52, "avg_lose": 1.7, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 2.97, "jc_lose": 3.05, "rq_win": 4.85, "rq_draw": 3.65, "rq_lose": 1.54, "avg_win": 2.03, "avg_draw": 3.24, "avg_lose": 3.44, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.75, "jc_lose": 4.02, "rq_win": 2.92, "rq_draw": 3.55, "rq_lose": 1.98, "avg_win": 1.71, "avg_draw": 3.81, "avg_lose": 4.12, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 2.67, "jc_draw": 3.28, "jc_lose": 2.22, "rq_win": 1.51, "rq_draw": 3.95, "rq_lose": 4.7, "avg_win": 2.77, "avg_draw": 3.28, "avg_lose": 2.35, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.5, "jc_lose": 5.65, "rq_win": 2.15, "rq_draw": 3.68, "rq_lose": 2.55, "avg_win": 1.46, "avg_draw": 4.59, "avg_lose": 5.73, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 6.2, "jc_lose": 10.2, "rq_win": 2.49, "rq_draw": 4.05, "rq_lose": 2.08, "avg_win": 1.25, "avg_draw": 5.97, "avg_lose": 8.9, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 1.28, "jc_draw": 5.1, "jc_lose": 6.6, "rq_win": 1.87, "rq_draw": 3.9, "rq_lose": 2.96, "avg_win": 1.4, "avg_draw": 4.93, "avg_lose": 6.1, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 2.45, "jc_draw": 3.75, "jc_lose": 2.2, "rq_win": 1.52, "rq_draw": 4.25, "rq_lose": 4.25, "avg_win": 2.51, "avg_draw": 3.66, "avg_lose": 2.4, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "5:5"},
    {"handicap": 1, "jc_win": 2.37, "jc_draw": 3.17, "jc_lose": 2.55, "rq_win": 5.4, "rq_draw": 4.0, "rq_lose": 1.44, "avg_win": 2.16, "avg_draw": 3.58, "avg_lose": 3.11, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.15, "jc_lose": 2.2, "rq_win": 1.52, "rq_draw": 3.85, "rq_lose": 4.75, "avg_win": 3.32, "avg_draw": 3.45, "avg_lose": 2.03, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.23, "jc_lose": 2.62, "rq_win": 5.2, "rq_draw": 3.9, "rq_lose": 1.47, "avg_win": 2.48, "avg_draw": 3.33, "avg_lose": 2.79, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -1, "jc_win": 4.22, "jc_draw": 3.85, "jc_lose": 1.58, "rq_win": 2.05, "rq_draw": 3.55, "rq_lose": 2.78, "avg_win": 4.2, "avg_draw": 3.86, "avg_lose": 1.71, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 3.45, "jc_lose": 2.75, "rq_win": 4.25, "rq_draw": 3.9, "rq_lose": 1.57, "avg_win": 2.14, "avg_draw": 3.57, "avg_lose": 2.99, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.7, "jc_lose": 6.1, "rq_win": 2.0, "rq_draw": 3.8, "rq_lose": 2.74, "avg_win": 1.53, "avg_draw": 4.31, "avg_lose": 5.15, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 2.98, "jc_draw": 3.38, "jc_lose": 2.01, "rq_win": 1.62, "rq_draw": 3.82, "rq_lose": 4.0, "avg_win": 2.8, "avg_draw": 3.36, "avg_lose": 2.29, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 3.2, "jc_draw": 3.45, "jc_lose": 1.9, "rq_win": 1.69, "rq_draw": 3.7, "rq_lose": 3.75, "avg_win": 3.46, "avg_draw": 3.33, "avg_lose": 2.04, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.6, "jc_lose": 3.0, "rq_win": 3.8, "rq_draw": 3.8, "rq_lose": 1.66, "avg_win": 2.19, "avg_draw": 3.42, "avg_lose": 2.95, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.5, "jc_lose": 5.65, "rq_win": 2.13, "rq_draw": 3.75, "rq_lose": 2.54, "avg_win": 1.51, "avg_draw": 4.27, "avg_lose": 5.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 3.45, "jc_lose": 2.75, "rq_win": 4.3, "rq_draw": 3.85, "rq_lose": 1.57, "avg_win": 1.65, "avg_draw": 3.95, "avg_lose": 4.49, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 1.59, "jc_draw": 3.46, "jc_lose": 4.75, "rq_win": 3.05, "rq_draw": 3.2, "rq_lose": 2.05, "avg_win": 1.88, "avg_draw": 3.47, "avg_lose": 3.89, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 2.24, "jc_draw": 3.35, "jc_lose": 2.6, "rq_win": 4.5, "rq_draw": 4.15, "rq_lose": 1.5, "avg_win": 2.29, "avg_draw": 3.53, "avg_lose": 2.74, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.21, "jc_draw": 6.0, "jc_lose": 8.05, "rq_win": 1.71, "rq_draw": 4.0, "rq_lose": 3.4, "avg_win": 1.23, "avg_draw": 6.0, "avg_lose": 9.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 2.27, "jc_draw": 3.3, "jc_lose": 2.59, "rq_win": 4.8, "rq_draw": 4.15, "rq_lose": 1.47, "avg_win": 2.37, "avg_draw": 3.39, "avg_lose": 2.63, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.1, "jc_lose": 3.05, "rq_win": 4.6, "rq_draw": 3.6, "rq_lose": 1.58, "avg_win": 2.39, "avg_draw": 3.14, "avg_lose": 2.89, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 1.55, "jc_draw": 3.65, "jc_lose": 4.75, "rq_win": 2.81, "rq_draw": 3.25, "rq_lose": 2.15, "avg_win": 1.94, "avg_draw": 3.4, "avg_lose": 3.47, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "冷门预警", "match_context": "Z=2.8600; Y=1.2200; X=1.0900; cold_risk=26.3%; dev_level=显著偏离", "match_id": "#618"},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.7, "jc_lose": 3.6, "rq_win": 3.1, "rq_draw": 3.6, "rq_lose": 1.89, "avg_win": 1.95, "avg_draw": 3.4, "avg_lose": 3.62, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.7, "jc_lose": 3.8, "rq_win": 3.1, "rq_draw": 3.45, "rq_lose": 1.94, "avg_win": 1.85, "avg_draw": 3.53, "avg_lose": 3.88, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": -1, "jc_win": 3.7, "jc_draw": 3.27, "jc_lose": 1.81, "rq_win": 1.77, "rq_draw": 3.45, "rq_lose": 3.65, "avg_win": 3.63, "avg_draw": 3.33, "avg_lose": 2.0, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.5, "jc_lose": 4.35, "rq_win": 3.12, "rq_draw": 3.25, "rq_lose": 2.0, "avg_win": 1.82, "avg_draw": 3.58, "avg_lose": 3.97, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 3.72, "jc_draw": 3.15, "jc_lose": 1.84, "rq_win": 1.75, "rq_draw": 3.4, "rq_lose": 3.8, "avg_win": 3.72, "avg_draw": 3.32, "avg_lose": 1.97, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4"},
    {"handicap": 1, "jc_win": 1.55, "jc_draw": 3.78, "jc_lose": 4.55, "rq_win": 2.75, "rq_draw": 3.43, "rq_lose": 2.11, "avg_win": 1.73, "avg_draw": 3.78, "avg_lose": 4.27, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.12, "jc_lose": 2.4, "rq_win": 1.43, "rq_draw": 4.05, "rq_lose": 5.45, "avg_win": 2.58, "avg_draw": 2.96, "avg_lose": 2.74, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 2.08, "jc_draw": 3.02, "jc_lose": 3.15, "rq_win": 4.6, "rq_draw": 3.6, "rq_lose": 1.58, "avg_win": 2.11, "avg_draw": 3.24, "avg_lose": 3.29, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.39, "jc_draw": 4.3, "jc_lose": 5.7, "rq_win": 2.26, "rq_draw": 3.4, "rq_lose": 2.55, "avg_win": 1.55, "avg_draw": 3.94, "avg_lose": 5.09, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 2.95, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.7, "rq_lose": 4.9, "avg_win": 2.87, "avg_draw": 3.12, "avg_lose": 2.44, "shenjia": "未输入", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.7, "jc_lose": 4.2, "rq_win": 2.86, "rq_draw": 3.55, "rq_lose": 2.01, "avg_win": 1.72, "avg_draw": 3.73, "avg_lose": 4.16, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 2.36, "jc_draw": 2.65, "jc_lose": 3.05, "rq_win": 5.65, "rq_draw": 3.8, "rq_lose": 1.45, "avg_win": 2.64, "avg_draw": 2.85, "avg_lose": 2.8, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": -1, "jc_win": 2.63, "jc_draw": 3.0, "jc_lose": 2.41, "rq_win": 1.43, "rq_draw": 3.95, "rq_lose": 5.65, "avg_win": 2.51, "avg_draw": 3.05, "avg_lose": 2.7, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 1.2, "jc_draw": 5.1, "jc_lose": 10.0, "rq_win": 1.74, "rq_draw": 3.6, "rq_lose": 3.61, "avg_win": 1.24, "avg_draw": 5.56, "avg_lose": 11.4, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.7, "jc_lose": 4.45, "rq_win": 2.76, "rq_draw": 3.5, "rq_lose": 2.08, "avg_win": 1.59, "avg_draw": 3.9, "avg_lose": 5.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.35, "jc_draw": 3.5, "jc_lose": 2.4, "rq_win": 4.85, "rq_draw": 4.3, "rq_lose": 1.45, "avg_win": 2.56, "avg_draw": 3.71, "avg_lose": 2.44, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": -1, "jc_win": 3.11, "jc_draw": 2.9, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.55, "rq_lose": 5.15, "avg_win": 2.99, "avg_draw": 2.97, "avg_lose": 2.44, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "3:3"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 3.9, "jc_lose": 6.3, "rq_win": 2.36, "rq_draw": 3.25, "rq_lose": 2.51, "avg_win": 1.42, "avg_draw": 4.29, "avg_lose": 7.1, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -1, "jc_win": 2.81, "jc_draw": 3.5, "jc_lose": 2.05, "rq_win": 1.58, "rq_draw": 3.95, "rq_lose": 4.12, "avg_win": 2.94, "avg_draw": 3.63, "avg_lose": 2.1, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.55, "jc_lose": 3.85, "rq_win": 3.12, "rq_draw": 3.5, "rq_lose": 1.91, "avg_win": 1.7, "avg_draw": 3.66, "avg_lose": 4.37, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 4.35, "jc_lose": 4.55, "rq_win": 2.43, "rq_draw": 3.65, "rq_lose": 2.25, "avg_win": 1.66, "avg_draw": 4.05, "avg_lose": 4.15, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "3:3"},
    {"handicap": 1, "jc_win": 1.76, "jc_draw": 3.8, "jc_lose": 3.35, "rq_win": 3.22, "rq_draw": 3.8, "rq_lose": 1.8, "avg_win": 1.68, "avg_draw": 3.97, "avg_lose": 4.11, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2"},
    {"handicap": -1, "jc_win": 3.46, "jc_draw": 3.55, "jc_lose": 1.79, "rq_win": 1.78, "rq_draw": 3.65, "rq_lose": 3.4, "avg_win": 3.43, "avg_draw": 3.59, "avg_lose": 1.93, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:6"},
    {"handicap": 1, "jc_win": 1.38, "jc_draw": 4.5, "jc_lose": 5.5, "rq_win": 2.13, "rq_draw": 3.68, "rq_lose": 2.58, "avg_win": 1.34, "avg_draw": 4.79, "avg_lose": 7.05, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "6:0"},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 3.7, "jc_lose": 5.45, "rq_win": 2.63, "rq_draw": 3.2, "rq_lose": 2.3, "avg_win": 1.83, "avg_draw": 3.26, "avg_lose": 4.21, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.25, "jc_lose": 3.5, "rq_win": 3.82, "rq_draw": 3.45, "rq_lose": 1.73, "avg_win": 1.88, "avg_draw": 3.64, "avg_lose": 3.6, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.15, "jc_lose": 8.75, "rq_win": 1.77, "rq_draw": 3.7, "rq_lose": 3.4, "avg_win": 1.49, "avg_draw": 4.23, "avg_lose": 5.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.47, "jc_lose": 3.02, "rq_win": 3.95, "rq_draw": 3.65, "rq_lose": 1.66, "avg_win": 2.07, "avg_draw": 3.54, "avg_lose": 3.08, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.25, "jc_draw": 3.5, "jc_lose": 2.52, "rq_win": 4.5, "rq_draw": 4.2, "rq_lose": 1.5, "avg_win": 2.25, "avg_draw": 3.71, "avg_lose": 2.65, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 5.05, "jc_draw": 3.05, "jc_lose": 1.66, "rq_win": 1.95, "rq_draw": 3.2, "rq_lose": 3.3, "avg_win": 4.35, "avg_draw": 3.26, "avg_lose": 1.84, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 2.7, "jc_draw": 3.6, "jc_lose": 2.08, "rq_win": 1.57, "rq_draw": 4.0, "rq_lose": 4.12, "avg_win": 2.72, "avg_draw": 3.78, "avg_lose": 2.21, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 2.57, "jc_draw": 3.4, "jc_lose": 2.24, "rq_win": 1.48, "rq_draw": 4.05, "rq_lose": 4.83, "avg_win": 2.67, "avg_draw": 3.64, "avg_lose": 2.29, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 3.35, "jc_draw": 3.25, "jc_lose": 1.91, "rq_win": 1.68, "rq_draw": 3.6, "rq_lose": 3.9, "avg_win": 2.55, "avg_draw": 3.23, "avg_lose": 2.66, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": -1, "jc_win": 4.15, "jc_draw": 3.85, "jc_lose": 1.59, "rq_win": 2.04, "rq_draw": 3.55, "rq_lose": 2.8, "avg_win": 3.09, "avg_draw": 3.63, "avg_lose": 2.12, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.77, "jc_lose": 4.75, "rq_win": 2.65, "rq_draw": 3.47, "rq_lose": 2.16, "avg_win": 1.63, "avg_draw": 4.14, "avg_lose": 4.47, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.15, "jc_lose": 5.75, "rq_win": 2.31, "rq_draw": 3.45, "rq_lose": 2.46, "avg_win": 1.69, "avg_draw": 3.82, "avg_lose": 4.47, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "7:0"},
    {"handicap": -2, "jc_win": 10.0, "jc_draw": 5.72, "jc_lose": 1.17, "rq_win": 1.98, "rq_draw": 3.95, "rq_lose": 2.7, "avg_win": 10.9, "avg_draw": 6.11, "avg_lose": 1.22, "shenjia": "未输入", "real_result": "负", "real_score": "0:3"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.77, "jc_lose": 4.15, "rq_win": 2.96, "rq_draw": 3.4, "rq_lose": 2.01, "avg_win": 1.97, "avg_draw": 3.51, "avg_lose": 3.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 7.36, "jc_lose": 15.37, "rq_win": 2.18, "rq_draw": 4.0, "rq_lose": 2.38, "avg_win": 1.15, "avg_draw": 7.0, "avg_lose": 13.0, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.1, "jc_lose": 6.45, "rq_win": 2.32, "rq_draw": 3.22, "rq_lose": 2.58, "avg_win": 1.64, "avg_draw": 3.73, "avg_lose": 4.88, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:2"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.05, "jc_lose": 6.55, "rq_win": 2.33, "rq_draw": 3.25, "rq_lose": 2.55, "avg_win": 1.49, "avg_draw": 4.05, "avg_lose": 6.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -2, "jc_win": 10.0, "jc_draw": 6.0, "jc_lose": 1.16, "rq_win": 2.08, "rq_draw": 3.92, "rq_lose": 2.54, "avg_win": 10.16, "avg_draw": 6.36, "avg_lose": 1.21, "shenjia": "未输入", "real_result": "负", "real_score": "0:4"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.25, "jc_lose": 2.6, "rq_win": 4.85, "rq_draw": 4.05, "rq_lose": 1.48, "avg_win": 2.43, "avg_draw": 3.34, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.95, "jc_lose": 3.5, "rq_win": 3.0, "rq_draw": 3.8, "rq_lose": 1.88, "avg_win": 1.68, "avg_draw": 4.18, "avg_lose": 3.98, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 4.3, "jc_lose": 4.82, "rq_win": 2.34, "rq_draw": 3.75, "rq_lose": 2.3, "avg_win": 2.26, "avg_draw": 3.65, "avg_lose": 2.74, "shenjia": "未输入", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.27, "jc_draw": 3.15, "jc_lose": 2.7, "rq_win": 5.15, "rq_draw": 3.85, "rq_lose": 1.48, "avg_win": 2.49, "avg_draw": 3.25, "avg_lose": 2.67, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.74, "jc_draw": 3.85, "jc_lose": 3.4, "rq_win": 3.05, "rq_draw": 3.8, "rq_lose": 1.86, "avg_win": 1.93, "avg_draw": 3.71, "avg_lose": 3.25, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2"},
    {"handicap": 1, "jc_win": 1.65, "jc_draw": 3.75, "jc_lose": 3.9, "rq_win": 2.95, "rq_draw": 3.6, "rq_lose": 1.95, "avg_win": 1.7, "avg_draw": 4.15, "avg_lose": 4.12, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:0"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 3.26, "jc_lose": 3.1, "rq_win": 4.2, "rq_draw": 3.65, "rq_lose": 1.62, "avg_win": 2.14, "avg_draw": 3.24, "avg_lose": 3.33, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 3.3, "jc_lose": 3.02, "rq_win": 4.2, "rq_draw": 3.7, "rq_lose": 1.61, "avg_win": 2.18, "avg_draw": 3.35, "avg_lose": 3.0, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 2.96, "jc_lose": 2.91, "rq_win": 5.31, "rq_draw": 3.7, "rq_lose": 1.49, "avg_win": 2.41, "avg_draw": 3.16, "avg_lose": 2.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 3.3, "jc_lose": 3.0, "rq_win": 4.1, "rq_draw": 3.8, "rq_lose": 1.61, "avg_win": 2.06, "avg_draw": 3.44, "avg_lose": 3.23, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 3.9, "jc_draw": 3.45, "jc_lose": 1.72, "rq_win": 1.87, "rq_draw": 3.48, "rq_lose": 3.25, "avg_win": 3.84, "avg_draw": 3.35, "avg_lose": 1.86, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:7"},
    {"handicap": -1, "jc_win": 8.9, "jc_draw": 5.1, "jc_lose": 1.22, "rq_win": 3.32, "rq_draw": 3.8, "rq_lose": 1.77, "avg_win": 6.61, "avg_draw": 4.5, "avg_lose": 1.43, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.18, "jc_lose": 2.65, "rq_win": 4.95, "rq_draw": 4.05, "rq_lose": 1.47, "avg_win": 1.81, "avg_draw": 3.64, "avg_lose": 4.17, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.83, "jc_draw": 3.52, "jc_lose": 3.35, "rq_win": 3.55, "rq_draw": 3.65, "rq_lose": 1.75, "avg_win": 2.19, "avg_draw": 3.41, "avg_lose": 2.98, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.06, "jc_draw": 3.1, "jc_lose": 3.12, "rq_win": 4.5, "rq_draw": 3.65, "rq_lose": 1.58, "avg_win": 2.06, "avg_draw": 3.51, "avg_lose": 3.43, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.15, "jc_lose": 3.0, "rq_win": 4.6, "rq_draw": 3.7, "rq_lose": 1.56, "avg_win": 2.19, "avg_draw": 3.46, "avg_lose": 3.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 3.05, "jc_lose": 2.7, "rq_win": 5.4, "rq_draw": 3.95, "rq_lose": 1.45, "avg_win": 2.67, "avg_draw": 3.3, "avg_lose": 2.56, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.4, "jc_draw": 3.12, "jc_lose": 2.55, "rq_win": 5.4, "rq_draw": 4.1, "rq_lose": 1.43, "avg_win": 2.47, "avg_draw": 3.56, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 4.75, "jc_draw": 4.2, "jc_lose": 1.47, "rq_win": 2.3, "rq_draw": 3.65, "rq_lose": 2.38, "avg_win": 4.09, "avg_draw": 4.01, "avg_lose": 1.72, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.25, "jc_lose": 3.75, "rq_win": 3.7, "rq_draw": 3.4, "rq_lose": 1.78, "avg_win": 2.07, "avg_draw": 3.26, "avg_lose": 3.51, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": 1, "jc_win": 1.6, "jc_draw": 3.2, "jc_lose": 5.25, "rq_win": 3.15, "rq_draw": 3.15, "rq_lose": 2.03, "avg_win": 1.6, "avg_draw": 3.72, "avg_lose": 5.58, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.45, "jc_lose": 6.55, "rq_win": 2.1, "rq_draw": 3.5, "rq_lose": 2.72, "avg_win": 1.52, "avg_draw": 4.25, "avg_lose": 5.69, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.35, "jc_lose": 2.66, "rq_win": 4.6, "rq_draw": 4.0, "rq_lose": 1.51, "avg_win": 2.55, "avg_draw": 3.57, "avg_lose": 2.57, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": -1, "jc_win": 4.65, "jc_draw": 3.45, "jc_lose": 1.6, "rq_win": 2.01, "rq_draw": 3.25, "rq_lose": 3.1, "avg_win": 4.4, "avg_draw": 3.4, "avg_lose": 1.8, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.35, "jc_draw": 2.95, "jc_lose": 2.75, "rq_win": 5.5, "rq_draw": 3.9, "rq_lose": 1.45, "avg_win": 2.34, "avg_draw": 3.15, "avg_lose": 3.01, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 4.28, "jc_lose": 1.55, "rq_win": 2.13, "rq_draw": 3.8, "rq_lose": 2.52, "avg_win": 4.32, "avg_draw": 4.46, "avg_lose": 1.64, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": -1, "jc_win": 4.45, "jc_draw": 3.2, "jc_lose": 1.69, "rq_win": 1.9, "rq_draw": 3.25, "rq_lose": 3.4, "avg_win": 5.62, "avg_draw": 3.7, "avg_lose": 1.59, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 2.8, "jc_lose": 3.0, "rq_win": 5.7, "rq_draw": 3.65, "rq_lose": 1.47, "avg_win": 2.38, "avg_draw": 3.07, "avg_lose": 2.99, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.94, "jc_draw": 3.25, "jc_lose": 3.27, "rq_win": 3.95, "rq_draw": 3.6, "rq_lose": 1.67, "avg_win": 2.2, "avg_draw": 3.45, "avg_lose": 3.06, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": -1, "jc_win": 2.61, "jc_draw": 3.25, "jc_lose": 2.28, "rq_win": 1.48, "rq_draw": 4.05, "rq_lose": 4.85, "avg_win": 3.62, "avg_draw": 3.61, "avg_lose": 1.93, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 6.3, "jc_draw": 4.45, "jc_lose": 1.34, "rq_win": 2.7, "rq_draw": 3.45, "rq_lose": 2.13, "avg_win": 4.94, "avg_draw": 3.98, "avg_lose": 1.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.39, "jc_draw": 4.35, "jc_lose": 5.55, "rq_win": 2.16, "rq_draw": 3.65, "rq_lose": 2.55, "avg_win": 1.48, "avg_draw": 4.53, "avg_lose": 5.63, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:0"},
    {"handicap": 1, "jc_win": 2.45, "jc_draw": 3.0, "jc_lose": 2.58, "rq_win": 5.9, "rq_draw": 4.0, "rq_lose": 1.41, "avg_win": 2.66, "avg_draw": 3.06, "avg_lose": 2.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.69, "jc_lose": 3.48, "rq_win": 3.1, "rq_draw": 3.8, "rq_lose": 1.84, "avg_win": 1.57, "avg_draw": 4.17, "avg_lose": 4.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.3, "jc_lose": 3.7, "rq_win": 3.6, "rq_draw": 3.45, "rq_lose": 1.78, "avg_win": 1.73, "avg_draw": 3.45, "avg_lose": 4.57, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.1, "jc_lose": 2.37, "rq_win": 1.43, "rq_draw": 4.15, "rq_lose": 5.3, "avg_win": 2.78, "avg_draw": 3.3, "avg_lose": 2.43, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.3, "jc_lose": 2.13, "rq_win": 1.54, "rq_draw": 3.95, "rq_lose": 4.4, "avg_win": 2.49, "avg_draw": 3.22, "avg_lose": 2.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.35, "jc_lose": 2.28, "rq_win": 1.48, "rq_draw": 4.15, "rq_lose": 4.7, "avg_win": 3.53, "avg_draw": 3.67, "avg_lose": 1.9, "shenjia": "未输入", "real_result": "负", "real_score": "4:6", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8900; Y=1.4400; X=2.6000; cold_risk=11.1%; dev_level=轻微偏离", "match_id": "#638"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.4, "jc_lose": 5.32, "rq_win": 2.26, "rq_draw": 3.55, "rq_lose": 2.47, "avg_win": 1.59, "avg_draw": 4.02, "avg_lose": 4.61, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 1.24, "jc_draw": 5.42, "jc_lose": 7.2, "rq_win": 1.77, "rq_draw": 4.05, "rq_lose": 3.15, "avg_win": 1.42, "avg_draw": 4.83, "avg_lose": 6.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:1"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.8, "jc_lose": 5.9, "rq_win": 2.0, "rq_draw": 3.8, "rq_lose": 2.74, "avg_win": 1.44, "avg_draw": 4.95, "avg_lose": 5.72, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 3.4, "jc_lose": 1.58, "rq_win": 2.08, "rq_draw": 3.2, "rq_lose": 2.98, "avg_win": 5.35, "avg_draw": 3.82, "avg_lose": 1.61, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.6, "jc_lose": 1.69, "rq_win": 1.89, "rq_draw": 3.6, "rq_lose": 3.1, "avg_win": 4.34, "avg_draw": 3.93, "avg_lose": 1.64, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:4"},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 3.6, "jc_lose": 4.65, "rq_win": 2.9, "rq_draw": 3.3, "rq_lose": 2.08, "avg_win": 1.79, "avg_draw": 3.63, "avg_lose": 4.15, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 1.3, "jc_draw": 4.75, "jc_lose": 6.7, "rq_win": 2.0, "rq_draw": 3.6, "rq_lose": 2.85, "avg_win": 1.48, "avg_draw": 4.35, "avg_lose": 5.53, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": -2, "jc_win": 10.5, "jc_draw": 6.4, "jc_lose": 1.14, "rq_win": 2.09, "rq_draw": 4.15, "rq_lose": 2.44, "avg_win": 5.66, "avg_draw": 4.41, "avg_lose": 1.48, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:5"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.5, "jc_lose": 1.77, "rq_win": 1.83, "rq_draw": 3.65, "rq_lose": 3.25, "avg_win": 4.02, "avg_draw": 3.73, "avg_lose": 1.8, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 3.35, "jc_draw": 3.77, "jc_lose": 1.77, "rq_win": 1.82, "rq_draw": 3.9, "rq_lose": 3.1, "avg_win": 2.86, "avg_draw": 3.81, "avg_lose": 2.18, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -1, "jc_win": 7.0, "jc_draw": 4.5, "jc_lose": 1.31, "rq_win": 2.82, "rq_draw": 3.45, "rq_lose": 2.06, "avg_win": 7.03, "avg_draw": 4.32, "avg_lose": 1.42, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": 1, "jc_win": 1.92, "jc_draw": 3.05, "jc_lose": 3.57, "rq_win": 4.3, "rq_draw": 3.4, "rq_lose": 1.66, "avg_win": 2.38, "avg_draw": 3.15, "avg_lose": 2.97, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": 1, "jc_win": 2.48, "jc_draw": 2.83, "jc_lose": 2.68, "rq_win": 6.5, "rq_draw": 3.85, "rq_lose": 1.4, "avg_win": 2.84, "avg_draw": 2.95, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 2.88, "jc_lose": 3.8, "rq_win": 4.2, "rq_draw": 3.4, "rq_lose": 1.68, "avg_win": 1.88, "avg_draw": 2.99, "avg_lose": 4.7, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0"},
    {"handicap": -1, "jc_win": 4.67, "jc_draw": 3.65, "jc_lose": 1.56, "rq_win": 2.07, "rq_draw": 3.32, "rq_lose": 2.9, "avg_win": 4.13, "avg_draw": 3.53, "avg_lose": 1.83, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.43, "jc_draw": 4.0, "jc_lose": 5.55, "rq_win": 2.42, "rq_draw": 3.35, "rq_lose": 2.4, "avg_win": 1.52, "avg_draw": 4.08, "avg_lose": 5.82, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1"},
    {"handicap": -1, "jc_win": 8.25, "jc_draw": 5.3, "jc_lose": 1.22, "rq_win": 3.35, "rq_draw": 3.9, "rq_lose": 1.74, "avg_win": 7.72, "avg_draw": 5.32, "avg_lose": 1.32, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:5"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 5.7, "jc_lose": 11.8, "rq_win": 2.75, "rq_draw": 3.95, "rq_lose": 1.95, "avg_win": 1.19, "avg_draw": 6.49, "avg_lose": 13.33, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 1.69, "jc_draw": 3.45, "jc_lose": 4.05, "rq_win": 3.3, "rq_draw": 3.3, "rq_lose": 1.91, "avg_win": 2.01, "avg_draw": 3.3, "avg_lose": 3.52, "shenjia": "未输入", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.08, "jc_draw": 2.98, "jc_lose": 3.2, "rq_win": 4.75, "rq_draw": 3.55, "rq_lose": 1.57, "avg_win": 2.05, "avg_draw": 3.15, "avg_lose": 3.66, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 5.2, "jc_draw": 4.5, "jc_lose": 1.4, "rq_win": 2.47, "rq_draw": 3.77, "rq_lose": 2.18, "avg_win": 4.58, "avg_draw": 4.13, "avg_lose": 1.61, "shenjia": "未输入", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 2.7, "jc_draw": 3.65, "jc_lose": 2.07, "rq_win": 1.56, "rq_draw": 4.1, "rq_lose": 4.1, "avg_win": 2.54, "avg_draw": 3.59, "avg_lose": 2.37, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:3"},
    {"handicap": 1, "jc_win": 1.62, "jc_draw": 3.36, "jc_lose": 4.66, "rq_win": 3.1, "rq_draw": 3.26, "rq_lose": 2.0, "avg_win": 1.7, "avg_draw": 3.68, "avg_lose": 4.59, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.3, "jc_lose": 6.0, "rq_win": 2.19, "rq_draw": 3.5, "rq_lose": 2.58, "avg_win": 1.39, "avg_draw": 4.96, "avg_lose": 5.99, "shenjia": "未输入", "real_result": "胜", "real_score": "3:2"},
    {"handicap": 1, "jc_win": 1.52, "jc_draw": 3.6, "jc_lose": 5.15, "rq_win": 2.64, "rq_draw": 3.35, "rq_lose": 2.21, "avg_win": 1.56, "avg_draw": 3.77, "avg_lose": 5.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0"},
    {"handicap": -1, "jc_win": 3.55, "jc_draw": 3.52, "jc_lose": 1.78, "rq_win": 1.8, "rq_draw": 3.65, "rq_lose": 3.35, "avg_win": 3.06, "avg_draw": 3.59, "avg_lose": 2.15, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.4, "jc_lose": 5.5, "rq_win": 2.9, "rq_draw": 3.13, "rq_lose": 2.15, "avg_win": 1.68, "avg_draw": 3.53, "avg_lose": 5.02, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0"},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 2.8, "jc_lose": 2.92, "rq_win": 5.5, "rq_draw": 3.8, "rq_lose": 1.46, "avg_win": 2.45, "avg_draw": 3.02, "avg_lose": 2.94, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 2.17, "jc_draw": 3.0, "jc_lose": 2.98, "rq_win": 4.9, "rq_draw": 3.7, "rq_lose": 1.53, "avg_win": 2.02, "avg_draw": 3.28, "avg_lose": 3.42, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3"},
    {"handicap": -1, "jc_win": 2.92, "jc_draw": 3.15, "jc_lose": 2.13, "rq_win": 1.55, "rq_draw": 3.8, "rq_lose": 4.55, "avg_win": 3.34, "avg_draw": 3.36, "avg_lose": 2.03, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0"},
    {"handicap": 1, "jc_win": 2.24, "jc_draw": 2.98, "jc_lose": 2.88, "rq_win": 5.35, "rq_draw": 3.7, "rq_lose": 1.49, "avg_win": 2.6, "avg_draw": 3.02, "avg_lose": 2.71, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2"},
    {"handicap": 1, "jc_win": 1.57, "jc_draw": 3.65, "jc_lose": 4.6, "rq_win": 2.8, "rq_draw": 3.4, "rq_lose": 2.09, "avg_win": 1.42, "avg_draw": 4.44, "avg_lose": 6.81, "shenjia": "未输入", "real_result": "胜", "real_score": "2:1"},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 2.8, "jc_lose": 3.62, "rq_win": 4.7, "rq_draw": 3.4, "rq_lose": 1.61, "avg_win": 2.04, "avg_draw": 3.03, "avg_lose": 3.75, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3"},
    {"handicap": 1, "jc_win": 2.02, "jc_draw": 3.5, "jc_lose": 2.88, "rq_win": 3.95, "rq_draw": 3.95, "rq_lose": 1.61, "avg_win": 2.02, "avg_draw": 3.65, "avg_lose": 3.02, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2"},
    {"handicap": -2, "jc_win": 9.75, "jc_draw": 6.35, "jc_lose": 1.15, "rq_win": 2.1, "rq_draw": 4.05, "rq_lose": 2.47, "avg_win": 7.95, "avg_draw": 6.21, "avg_lose": 1.27, "shenjia": "未输入", "real_result": "负", "real_score": "2:3"},
    {"handicap": -1, "jc_win": 2.64, "jc_draw": 3.0, "jc_lose": 2.4, "rq_win": 1.42, "rq_draw": 4.15, "rq_lose": 5.45, "avg_win": 2.76, "avg_draw": 3.26, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.7, "jc_lose": 3.3, "rq_win": 3.25, "rq_draw": 3.75, "rq_lose": 1.8, "avg_win": 2.62, "avg_draw": 3.05, "avg_lose": 2.81, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 4.5, "jc_lose": 4.7, "rq_win": 2.24, "rq_draw": 3.75, "rq_lose": 2.4, "avg_win": 1.63, "avg_draw": 4.27, "avg_lose": 4.52, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0"},
    {"handicap": 1, "jc_win": 2.13, "jc_draw": 3.15, "jc_lose": 2.92, "rq_win": 4.45, "rq_draw": 3.92, "rq_lose": 1.54, "avg_win": 2.11, "avg_draw": 3.43, "avg_lose": 3.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:2"},
    {"handicap": -1, "jc_win": 3.85, "jc_draw": 3.55, "jc_lose": 1.7, "rq_win": 1.9, "rq_draw": 3.58, "rq_lose": 3.1, "avg_win": 3.61, "avg_draw": 3.58, "avg_lose": 1.9, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:6"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.05, "jc_lose": 2.45, "rq_win": 1.41, "rq_draw": 4.1, "rq_lose": 5.75, "avg_win": 2.61, "avg_draw": 3.24, "avg_lose": 2.59, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1"},
    {"handicap": -1, "jc_win": 2.92, "jc_draw": 3.15, "jc_lose": 2.13, "rq_win": 1.55, "rq_draw": 3.8, "rq_lose": 4.55, "avg_win": 3.34, "avg_draw": 3.36, "avg_lose": 2.03, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6100; Y=1.4900; X=2.7400; cold_risk=16.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.24, "jc_draw": 2.98, "jc_lose": 2.88, "rq_win": 5.35, "rq_draw": 3.7, "rq_lose": 1.49, "avg_win": 2.6, "avg_draw": 3.02, "avg_lose": 2.71, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8400; Y=1.3800; X=1.7100; cold_risk=24.0%; dev_level=一致"},
    {"handicap": -2, "jc_win": 9.75, "jc_draw": 6.35, "jc_lose": 1.15, "rq_win": 2.1, "rq_draw": 4.05, "rq_lose": 2.47, "avg_win": 7.95, "avg_draw": 6.21, "avg_lose": 1.27, "shenjia": "未输入", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.1800; Y=1.8100; X=19.9700; cold_risk=2.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.64, "jc_draw": 3.0, "jc_lose": 2.4, "rq_win": 1.42, "rq_draw": 4.15, "rq_lose": 5.45, "avg_win": 2.76, "avg_draw": 3.26, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.4500; X=2.2100; cold_risk=23.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.7, "jc_lose": 3.3, "rq_win": 3.25, "rq_draw": 3.75, "rq_lose": 1.8, "avg_win": 2.62, "avg_draw": 3.05, "avg_lose": 2.81, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.6400; Y=1.2900; X=1.7100; cold_risk=8.6%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 2.09, "jc_draw": 3.3, "jc_lose": 2.88, "rq_win": 4.4, "rq_draw": 3.8, "rq_lose": 1.57, "avg_win": 2.29, "avg_draw": 3.41, "avg_lose": 2.78, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.1400; Y=1.3500; X=1.8600; cold_risk=10.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.0, "jc_draw": 3.0, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.75, "rq_lose": 4.8, "avg_win": 3.11, "avg_draw": 3.11, "avg_lose": 2.31, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "平局共振", "match_context": "Z=1.5000; Y=1.5000; X=2.5900; cold_risk=18.0%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.14, "jc_draw": 6.2, "jc_lose": 11.0, "rq_win": 2.6, "rq_draw": 4.0, "rq_lose": 2.02, "avg_win": 1.28, "avg_draw": 5.43, "avg_lose": 8.46, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.7900; Y=1.0700; X=0.6900; cold_risk=10.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.27, "jc_draw": 4.85, "jc_lose": 7.35, "rq_win": 1.9, "rq_draw": 3.65, "rq_lose": 3.05, "avg_win": 1.46, "avg_draw": 4.49, "avg_lose": 5.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.2700; Y=1.1200; X=0.8500; cold_risk=15.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.42, "jc_draw": 3.8, "jc_lose": 6.25, "rq_win": 2.48, "rq_draw": 3.15, "rq_lose": 2.45, "avg_win": 1.56, "avg_draw": 3.68, "avg_lose": 6.18, "shenjia": "未输入", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.1400; Y=1.1700; X=0.8200; cold_risk=12.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.2, "jc_lose": 2.77, "rq_win": 4.7, "rq_draw": 3.9, "rq_lose": 1.52, "avg_win": 2.63, "avg_draw": 3.03, "avg_lose": 2.78, "shenjia": "未输入", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.0000; Y=1.3800; X=1.9100; cold_risk=8.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.35, "jc_lose": 2.53, "rq_win": 4.8, "rq_draw": 4.1, "rq_lose": 1.48, "avg_win": 2.61, "avg_draw": 3.37, "avg_lose": 2.53, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=2.0300; Y=1.3900; X=2.2400; cold_risk=8.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.35, "jc_lose": 3.4, "rq_win": 3.7, "rq_draw": 3.6, "rq_lose": 1.72, "avg_win": 1.93, "avg_draw": 3.43, "avg_lose": 3.75, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.3000; X=1.5200; cold_risk=13.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.55, "jc_draw": 4.0, "jc_lose": 1.43, "rq_win": 2.4, "rq_draw": 3.5, "rq_lose": 2.34, "avg_win": 5.54, "avg_draw": 4.1, "avg_lose": 1.52, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.2200; Y=1.6900; X=6.7800; cold_risk=16.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.4, "jc_lose": 8.1, "rq_win": 1.72, "rq_draw": 4.05, "rq_lose": 3.32, "avg_win": 1.41, "avg_draw": 4.69, "avg_lose": 6.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.8600; Y=1.1000; X=0.8400; cold_risk=14.3%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 3.7, "jc_lose": 5.8, "rq_win": 2.6, "rq_draw": 3.15, "rq_lose": 2.35, "avg_win": 1.47, "avg_draw": 3.96, "avg_lose": 6.36, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.0100; Y=1.1900; X=0.8700; cold_risk=14.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 3.7, "jc_lose": 5.9, "rq_win": 2.57, "rq_draw": 3.2, "rq_lose": 2.34, "avg_win": 1.7, "avg_draw": 3.52, "avg_lose": 4.65, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.0200; Y=1.1800; X=0.8600; cold_risk=19.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.65, "jc_lose": 2.92, "rq_win": 3.75, "rq_draw": 3.8, "rq_lose": 1.67, "avg_win": 2.36, "avg_draw": 3.47, "avg_lose": 2.79, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.4700; Y=1.3200; X=1.9800; cold_risk=6.3%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.2, "jc_lose": 3.55, "rq_win": 3.85, "rq_draw": 3.43, "rq_lose": 1.73, "avg_win": 1.91, "avg_draw": 3.45, "avg_lose": 3.84, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.2300; Y=1.3000; X=1.3900; cold_risk=11.3%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 5.8, "jc_lose": 10.5, "rq_win": 2.69, "rq_draw": 3.88, "rq_lose": 2.0, "avg_win": 1.26, "avg_draw": 5.43, "avg_lose": 11.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.3700; Y=1.0700; X=0.6800; cold_risk=8.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 4.7, "jc_lose": 1.33, "rq_win": 2.71, "rq_draw": 3.65, "rq_lose": 2.06, "avg_win": 6.85, "avg_draw": 4.8, "avg_lose": 1.38, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3200; Y=1.7200; X=9.2200; cold_risk=13.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.83, "jc_draw": 3.15, "jc_lose": 2.18, "rq_win": 1.53, "rq_draw": 3.9, "rq_lose": 4.55, "avg_win": 2.84, "avg_draw": 3.5, "avg_lose": 2.32, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6400; Y=1.4800; X=2.6500; cold_risk=22.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.28, "jc_draw": 4.6, "jc_lose": 7.65, "rq_win": 1.97, "rq_draw": 3.5, "rq_lose": 2.98, "avg_win": 1.38, "avg_draw": 4.54, "avg_lose": 7.64, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.0400; Y=1.1200; X=0.7800; cold_risk=12.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.78, "jc_draw": 3.1, "jc_lose": 4.1, "rq_win": 3.7, "rq_draw": 3.3, "rq_lose": 1.8, "avg_win": 2.01, "avg_draw": 3.4, "avg_lose": 3.69, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.2300; Y=1.2800; X=1.1300; cold_risk=25.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.3, "jc_lose": 8.3, "rq_win": 1.75, "rq_draw": 3.85, "rq_lose": 3.35, "avg_win": 1.44, "avg_draw": 4.55, "avg_lose": 5.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.7700; Y=1.1000; X=0.8000; cold_risk=15.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.51, "jc_draw": 3.35, "jc_lose": 2.31, "rq_win": 1.46, "rq_draw": 4.1, "rq_lose": 5.0, "avg_win": 2.79, "avg_draw": 3.51, "avg_lose": 2.26, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "3:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9100; Y=1.4300; X=2.5500; cold_risk=21.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 3.9, "jc_lose": 4.75, "rq_win": 2.6, "rq_draw": 3.45, "rq_lose": 2.2, "avg_win": 1.51, "avg_draw": 4.14, "avg_lose": 5.39, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.1100; Y=1.2000; X=1.1500; cold_risk=17.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.35, "jc_lose": 3.15, "rq_win": 4.02, "rq_draw": 3.65, "rq_lose": 1.65, "avg_win": 2.5, "avg_draw": 3.35, "avg_lose": 2.76, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.2700; Y=1.3200; X=1.6700; cold_risk=7.7%; dev_level=轻微偏离"},
    {"handicap": -2, "jc_win": 9.0, "jc_draw": 5.85, "jc_lose": 1.18, "rq_win": 1.96, "rq_draw": 4.1, "rq_lose": 2.67, "avg_win": 8.58, "avg_draw": 5.94, "avg_lose": 1.26, "shenjia": "未输入", "real_result": "负", "real_score": "1:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1700; Y=1.8000; X=16.5000; cold_risk=3.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.3, "jc_lose": 4.7, "rq_win": 3.2, "rq_draw": 3.2, "rq_lose": 1.99, "avg_win": 1.67, "avg_draw": 3.64, "avg_lose": 4.82, "shenjia": "未输入", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.5100; Y=1.2400; X=1.0100; cold_risk=11.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 4.25, "jc_lose": 4.8, "rq_win": 2.31, "rq_draw": 3.7, "rq_lose": 2.35, "avg_win": 1.45, "avg_draw": 4.74, "avg_lose": 5.86, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.4600; Y=1.1900; X=1.2200; cold_risk=15.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 3.43, "jc_lose": 1.96, "rq_win": 1.66, "rq_draw": 3.85, "rq_lose": 3.75, "avg_win": 3.0, "avg_draw": 3.62, "avg_lose": 2.06, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6900; Y=1.5100; X=3.3300; cold_risk=20.4%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.17, "jc_draw": 6.5, "jc_lose": 8.25, "rq_win": 2.29, "rq_draw": 4.4, "rq_lose": 2.15, "avg_win": 1.23, "avg_draw": 6.9, "avg_lose": 9.6, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=5.9900; Y=1.0800; X=0.9800; cold_risk=9.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.3, "jc_draw": 4.4, "jc_lose": 7.5, "rq_win": 2.01, "rq_draw": 3.45, "rq_lose": 2.93, "avg_win": 1.3, "avg_draw": 5.15, "avg_lose": 9.88, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.8300; Y=1.1300; X=0.7600; cold_risk=9.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.4, "jc_draw": 3.9, "jc_lose": 1.55, "rq_win": 2.09, "rq_draw": 3.55, "rq_lose": 2.72, "avg_win": 4.09, "avg_draw": 3.89, "avg_lose": 1.79, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4400; Y=1.6300; X=5.5900; cold_risk=23.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.9, "jc_draw": 4.0, "jc_lose": 1.48, "rq_win": 2.26, "rq_draw": 3.5, "rq_lose": 2.5, "avg_win": 5.14, "avg_draw": 4.12, "avg_lose": 1.59, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3600; Y=1.6600; X=6.2900; cold_risk=18.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.07, "jc_lose": 2.72, "rq_win": 5.25, "rq_draw": 3.8, "rq_lose": 1.48, "avg_win": 2.42, "avg_draw": 3.32, "avg_lose": 2.8, "shenjia": "未输入", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8600; Y=1.3900; X=1.8900; cold_risk=11.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 8.75, "jc_draw": 5.3, "jc_lose": 1.21, "rq_win": 3.4, "rq_draw": 3.8, "rq_lose": 1.75, "avg_win": 8.62, "avg_draw": 5.92, "avg_lose": 1.27, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.0900; Y=1.7900; X=13.7200; cold_risk=10.8%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.9, "jc_draw": 3.25, "jc_lose": 2.1, "rq_win": 1.56, "rq_draw": 3.8, "rq_lose": 4.45, "avg_win": 2.76, "avg_draw": 3.52, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6700; Y=1.4900; X=2.8700; cold_risk=23.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.95, "jc_draw": 3.28, "jc_lose": 1.75, "rq_win": 1.84, "rq_draw": 3.3, "rq_lose": 3.55, "avg_win": 3.73, "avg_draw": 3.1, "avg_lose": 2.03, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3300; Y=1.6000; X=3.8900; cold_risk=24.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.5, "jc_draw": 3.25, "jc_lose": 1.87, "rq_win": 1.72, "rq_draw": 3.48, "rq_lose": 3.85, "avg_win": 3.25, "avg_draw": 3.23, "avg_lose": 2.15, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4400; Y=1.5600; X=3.4500; cold_risk=28.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.35, "jc_lose": 3.45, "rq_win": 3.61, "rq_draw": 3.6, "rq_lose": 1.74, "avg_win": 2.33, "avg_draw": 3.29, "avg_lose": 2.76, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3500; Y=1.3000; X=1.4900; cold_risk=2.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 3.28, "jc_lose": 3.08, "rq_win": 4.2, "rq_draw": 3.7, "rq_lose": 1.61, "avg_win": 1.81, "avg_draw": 3.56, "avg_lose": 3.78, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.1900; Y=1.3300; X=1.6900; cold_risk=14.1%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.25, "jc_draw": 3.71, "jc_lose": 1.81, "rq_win": 1.78, "rq_draw": 3.8, "rq_lose": 3.28, "avg_win": 4.11, "avg_draw": 3.67, "avg_lose": 1.74, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7500; Y=1.5300; X=4.0400; cold_risk=11.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.4, "jc_lose": 5.8, "rq_win": 2.2, "rq_draw": 3.55, "rq_lose": 2.55, "avg_win": 1.43, "avg_draw": 4.57, "avg_lose": 6.46, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.7100; Y=1.1600; X=1.0100; cold_risk=14.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.47, "jc_draw": 3.82, "jc_lose": 5.35, "rq_win": 2.5, "rq_draw": 3.35, "rq_lose": 2.32, "avg_win": 1.38, "avg_draw": 4.83, "avg_lose": 7.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.0900; Y=1.1900; X=0.9800; cold_risk=12.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 3.88, "jc_lose": 5.65, "rq_win": 2.5, "rq_draw": 3.3, "rq_lose": 2.35, "avg_win": 1.59, "avg_draw": 3.78, "avg_lose": 5.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.1800; Y=1.1800; X=0.9400; cold_risk=17.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.6, "jc_draw": 4.07, "jc_lose": 1.5, "rq_win": 2.24, "rq_draw": 3.65, "rq_lose": 2.45, "avg_win": 6.2, "avg_draw": 4.91, "avg_lose": 1.43, "shenjia": "未输入", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.4500; Y=1.6400; X=6.1900; cold_risk=4.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.43, "jc_draw": 4.3, "jc_lose": 5.05, "rq_win": 2.31, "rq_draw": 3.7, "rq_lose": 2.35, "avg_win": 1.48, "avg_draw": 4.57, "avg_lose": 5.92, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.5400; Y=1.1800; X=1.1600; cold_risk=15.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.34, "jc_draw": 3.4, "jc_lose": 2.45, "rq_win": 5.0, "rq_draw": 4.25, "rq_lose": 1.44, "avg_win": 2.51, "avg_draw": 3.58, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "3:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜", "resonance_type": "正常", "match_context": "Z=2.0400; Y=1.4000; X=2.3700; cold_risk=17.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 3.57, "jc_lose": 2.06, "rq_win": 1.57, "rq_draw": 4.0, "rq_lose": 4.12, "avg_win": 3.28, "avg_draw": 3.72, "avg_lose": 2.02, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9000; Y=1.4700; X=3.1800; cold_risk=16.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.5, "jc_draw": 3.93, "jc_lose": 4.8, "rq_win": 2.6, "rq_draw": 3.4, "rq_lose": 2.22, "avg_win": 1.59, "avg_draw": 4.06, "avg_lose": 4.95, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.1400; Y=1.2000; X=1.1400; cold_risk=18.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.46, "jc_lose": 4.4, "rq_win": 3.0, "rq_draw": 3.45, "rq_lose": 1.98, "avg_win": 1.91, "avg_draw": 3.62, "avg_lose": 3.71, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.6300; Y=1.2400; X=1.1400; cold_risk=25.2%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.87, "jc_draw": 3.35, "jc_lose": 3.38, "rq_win": 3.6, "rq_draw": 3.7, "rq_lose": 1.72, "avg_win": 1.77, "avg_draw": 3.86, "avg_lose": 4.16, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.3000; X=1.5300; cold_risk=11.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.2, "jc_lose": 2.1, "rq_win": 1.56, "rq_draw": 3.8, "rq_lose": 4.45, "avg_win": 2.57, "avg_draw": 3.45, "avg_lose": 2.54, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6200; Y=1.4900; X=2.8300; cold_risk=25.2%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.02, "jc_draw": 3.48, "jc_lose": 1.96, "rq_win": 1.65, "rq_draw": 3.8, "rq_lose": 3.85, "avg_win": 2.86, "avg_draw": 3.66, "avg_lose": 2.29, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "正常", "match_context": "Z=1.7300; Y=1.5000; X=3.3700; cold_risk=16.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.06, "jc_draw": 3.48, "jc_lose": 2.8, "rq_win": 4.0, "rq_draw": 4.05, "rq_lose": 1.58, "avg_win": 2.09, "avg_draw": 3.66, "avg_lose": 3.17, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.2700; Y=1.3500; X=2.0100; cold_risk=11.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.24, "jc_draw": 5.05, "jc_lose": 8.0, "rq_win": 1.8, "rq_draw": 3.75, "rq_lose": 3.25, "avg_win": 1.32, "avg_draw": 5.37, "avg_lose": 8.57, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.5100; Y=1.1100; X=0.8000; cold_risk=11.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.82, "jc_draw": 2.95, "jc_lose": 2.3, "rq_win": 1.48, "rq_draw": 3.7, "rq_lose": 5.45, "avg_win": 3.06, "avg_draw": 3.16, "avg_lose": 2.4, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5400; Y=1.4800; X=2.3200; cold_risk=20.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.5, "jc_draw": 3.8, "jc_lose": 5.0, "rq_win": 2.7, "rq_draw": 3.3, "rq_lose": 2.2, "avg_win": 1.52, "avg_draw": 4.26, "avg_lose": 5.77, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.0400; Y=1.2000; X=1.0600; cold_risk=16.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.08, "jc_draw": 3.1, "jc_lose": 3.08, "rq_win": 4.6, "rq_draw": 3.65, "rq_lose": 1.57, "avg_win": 2.34, "avg_draw": 3.33, "avg_lose": 2.96, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.0100; Y=1.3500; X=1.6200; cold_risk=21.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.26, "jc_draw": 5.2, "jc_lose": 7.0, "rq_win": 1.85, "rq_draw": 3.8, "rq_lose": 3.07, "avg_win": 1.49, "avg_draw": 4.54, "avg_lose": 5.45, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "同向共振", "match_context": "Z=4.6000; Y=1.1200; X=0.9500; cold_risk=17.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.83, "jc_draw": 3.3, "jc_lose": 3.6, "rq_win": 3.65, "rq_draw": 3.55, "rq_lose": 1.75, "avg_win": 1.79, "avg_draw": 3.65, "avg_lose": 4.22, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.2900; X=1.3900; cold_risk=22.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 9.2, "jc_draw": 5.0, "jc_lose": 1.22, "rq_win": 3.3, "rq_draw": 3.55, "rq_lose": 1.84, "avg_win": 8.28, "avg_draw": 5.09, "avg_lose": 1.33, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "同向共振", "match_context": "Z=0.9800; Y=1.8000; X=12.6600; cold_risk=11.3%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.12, "jc_draw": 6.25, "jc_lose": 13.0, "rq_win": 2.6, "rq_draw": 3.85, "rq_lose": 2.06, "avg_win": 1.22, "avg_draw": 6.14, "avg_lose": 12.09, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.9000; Y=1.0600; X=0.5800; cold_risk=7.8%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.55, "jc_draw": 3.3, "jc_lose": 1.84, "rq_win": 1.74, "rq_draw": 3.5, "rq_lose": 3.75, "avg_win": 2.85, "avg_draw": 3.33, "avg_lose": 2.37, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4500; Y=1.5600; X=3.5800; cold_risk=32.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.36, "jc_draw": 3.5, "jc_lose": 1.83, "rq_win": 1.74, "rq_draw": 3.7, "rq_lose": 3.52, "avg_win": 3.31, "avg_draw": 3.6, "avg_lose": 2.01, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6100; Y=1.5400; X=3.7900; cold_risk=16.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.12, "jc_draw": 4.3, "jc_lose": 1.53, "rq_win": 2.14, "rq_draw": 3.9, "rq_lose": 2.47, "avg_win": 4.17, "avg_draw": 4.27, "avg_lose": 1.66, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:6", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.6800; Y=1.6100; X=6.2100; cold_risk=11.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.5, "jc_draw": 3.3, "jc_lose": 1.85, "rq_win": 1.73, "rq_draw": 3.5, "rq_lose": 3.78, "avg_win": 3.16, "avg_draw": 3.25, "avg_lose": 2.13, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4700; Y=1.5600; X=3.5600; cold_risk=28.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.95, "jc_draw": 3.0, "jc_lose": 2.19, "rq_win": 1.5, "rq_draw": 3.7, "rq_lose": 5.2, "avg_win": 2.78, "avg_draw": 3.09, "avg_lose": 2.44, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5200; Y=1.4900; X=2.5300; cold_risk=22.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.85, "jc_draw": 4.4, "jc_lose": 1.44, "rq_win": 2.38, "rq_draw": 3.65, "rq_lose": 2.3, "avg_win": 4.99, "avg_draw": 4.5, "avg_lose": 1.51, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.5000; Y=1.6600; X=7.1900; cold_risk=18.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.24, "jc_draw": 5.35, "jc_lose": 7.4, "rq_win": 1.75, "rq_draw": 4.1, "rq_lose": 3.18, "avg_win": 1.31, "avg_draw": 5.4, "avg_lose": 7.26, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.7800; Y=1.1100; X=0.9200; cold_risk=12.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.29, "jc_draw": 3.05, "jc_lose": 2.74, "rq_win": 5.1, "rq_draw": 3.95, "rq_lose": 1.47, "avg_win": 2.79, "avg_draw": 3.37, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.8500; Y=1.3900; X=1.8700; cold_risk=13.5%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.3, "jc_draw": 3.2, "jc_lose": 2.62, "rq_win": 4.9, "rq_draw": 4.25, "rq_lose": 1.45, "avg_win": 2.61, "avg_draw": 3.53, "avg_lose": 2.48, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.9400; Y=1.3900; X=2.0600; cold_risk=17.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.98, "jc_draw": 3.15, "jc_lose": 3.26, "rq_win": 4.15, "rq_draw": 3.55, "rq_lose": 1.65, "avg_win": 2.17, "avg_draw": 3.45, "avg_lose": 3.22, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1100; Y=1.3300; X=1.5200; cold_risk=13.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.5, "jc_lose": 3.67, "rq_win": 3.35, "rq_draw": 3.55, "rq_lose": 1.82, "avg_win": 1.9, "avg_draw": 3.57, "avg_lose": 3.83, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.5500; Y=1.2700; X=1.4300; cold_risk=24.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 4.4, "jc_lose": 1.43, "rq_win": 2.38, "rq_draw": 3.8, "rq_lose": 2.25, "avg_win": 3.63, "avg_draw": 3.74, "avg_lose": 1.85, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.4800; Y=1.6600; X=7.3100; cold_risk=25.4%; dev_level=显著偏离"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 6.5, "jc_lose": 9.5, "rq_win": 2.47, "rq_draw": 4.2, "rq_lose": 2.06, "avg_win": 1.19, "avg_draw": 6.4, "avg_lose": 10.47, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=6.0500; Y=1.0700; X=0.8400; cold_risk=16.9%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.16, "jc_draw": 7.21, "jc_lose": 14.51, "rq_win": 1.75, "rq_draw": 4.28, "rq_lose": 3.1, "avg_win": 1.18, "avg_draw": 7.0, "avg_lose": 15.0, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=6.6800; Y=1.0700; X=0.5700; cold_risk=6.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.26, "jc_draw": 5.0, "jc_lose": 7.35, "rq_win": 1.88, "rq_draw": 3.7, "rq_lose": 3.06, "avg_win": 1.39, "avg_draw": 4.67, "avg_lose": 7.3, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.4200; Y=1.1200; X=0.8700; cold_risk=12.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.4, "jc_lose": 3.15, "rq_win": 3.9, "rq_draw": 3.75, "rq_lose": 1.65, "avg_win": 1.97, "avg_draw": 3.82, "avg_lose": 3.27, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3200; Y=1.3200; X=1.6900; cold_risk=18.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.22, "jc_draw": 2.97, "jc_lose": 2.92, "rq_win": 5.2, "rq_draw": 3.7, "rq_lose": 1.5, "avg_win": 2.33, "avg_draw": 3.08, "avg_lose": 3.17, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8400; Y=1.3800; X=1.6800; cold_risk=19.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.45, "jc_draw": 2.85, "jc_lose": 2.7, "rq_win": 6.1, "rq_draw": 3.9, "rq_lose": 1.41, "avg_win": 2.66, "avg_draw": 3.12, "avg_lose": 2.68, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.4200; X=1.8100; cold_risk=24.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 8.05, "jc_draw": 5.2, "jc_lose": 1.23, "rq_win": 3.22, "rq_draw": 3.9, "rq_lose": 1.78, "avg_win": 5.93, "avg_draw": 4.49, "avg_lose": 1.46, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.1500; Y=1.7800; X=12.7300; cold_risk=15.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.91, "jc_draw": 2.95, "jc_lose": 3.75, "rq_win": 4.2, "rq_draw": 3.35, "rq_lose": 1.69, "avg_win": 1.9, "avg_draw": 3.3, "avg_lose": 4.21, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.0300; Y=1.3100; X=1.2100; cold_risk=22.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 8.0, "jc_draw": 4.6, "jc_lose": 1.27, "rq_win": 2.97, "rq_draw": 3.45, "rq_lose": 1.99, "avg_win": 6.03, "avg_draw": 3.85, "avg_lose": 1.54, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.0200; Y=1.7800; X=10.3700; cold_risk=15.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 3.5, "jc_lose": 2.65, "rq_win": 4.35, "rq_draw": 4.0, "rq_lose": 1.54, "avg_win": 2.32, "avg_draw": 3.75, "avg_lose": 2.71, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2200; Y=1.3700; X=2.1700; cold_risk=16.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.28, "jc_draw": 4.7, "jc_lose": 7.5, "rq_win": 1.96, "rq_draw": 3.5, "rq_lose": 3.0, "avg_win": 1.43, "avg_draw": 4.35, "avg_lose": 6.48, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.1200; Y=1.1200; X=0.8100; cold_risk=14.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.1, "jc_lose": 2.85, "rq_win": 4.9, "rq_draw": 3.8, "rq_lose": 1.51, "avg_win": 2.31, "avg_draw": 3.31, "avg_lose": 3.01, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9400; Y=1.3800; X=1.7900; cold_risk=20.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.05, "jc_lose": 3.55, "rq_win": 4.25, "rq_draw": 3.45, "rq_lose": 1.66, "avg_win": 1.91, "avg_draw": 3.26, "avg_lose": 3.99, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0800; Y=1.3200; X=1.3300; cold_risk=23.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 3.2, "jc_lose": 2.85, "rq_win": 4.6, "rq_draw": 3.75, "rq_lose": 1.55, "avg_win": 2.14, "avg_draw": 3.27, "avg_lose": 3.15, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.0300; Y=1.3700; X=1.8400; cold_risk=12.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.9, "jc_draw": 3.5, "jc_lose": 3.15, "rq_win": 3.7, "rq_draw": 3.7, "rq_lose": 1.7, "avg_win": 1.91, "avg_draw": 3.62, "avg_lose": 3.45, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4100; Y=1.3100; X=1.7300; cold_risk=15.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 7.0, "jc_draw": 3.9, "jc_lose": 1.37, "rq_win": 2.6, "rq_draw": 3.2, "rq_lose": 2.32, "avg_win": 5.16, "avg_draw": 3.44, "avg_lose": 1.71, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=0.9700; Y=1.7500; X=7.3600; cold_risk=18.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 4.22, "jc_lose": 5.05, "rq_win": 2.32, "rq_draw": 3.55, "rq_lose": 2.4, "avg_win": 1.58, "avg_draw": 3.99, "avg_lose": 4.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4600; Y=1.1800; X=1.1500; cold_risk=19.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.8, "jc_lose": 3.6, "rq_win": 3.06, "rq_draw": 3.7, "rq_lose": 1.88, "avg_win": 1.69, "avg_draw": 3.99, "avg_lose": 3.99, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.8100; Y=1.2600; X=1.5700; cold_risk=16.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 2.7, "jc_lose": 4.08, "rq_win": 4.65, "rq_draw": 3.25, "rq_lose": 1.65, "avg_win": 2.09, "avg_draw": 3.17, "avg_lose": 3.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.8300; Y=1.3200; X=1.0200; cold_risk=26.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.16, "jc_draw": 3.4, "jc_lose": 1.68, "rq_win": 1.91, "rq_draw": 3.35, "rq_lose": 3.25, "avg_win": 3.81, "avg_draw": 3.38, "avg_lose": 1.89, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3200; Y=1.6100; X=4.3100; cold_risk=24.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.35, "jc_draw": 3.75, "jc_lose": 1.48, "rq_win": 2.28, "rq_draw": 3.35, "rq_lose": 2.55, "avg_win": 4.09, "avg_draw": 3.61, "avg_lose": 1.83, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1800; Y=1.6900; X=5.9700; cold_risk=22.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.55, "jc_draw": 3.65, "jc_lose": 4.75, "rq_win": 2.82, "rq_draw": 3.35, "rq_lose": 2.1, "avg_win": 1.69, "avg_draw": 3.69, "avg_lose": 4.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8600; Y=1.2200; X=1.0900; cold_risk=19.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 4.05, "jc_lose": 4.4, "rq_win": 2.55, "rq_draw": 3.6, "rq_lose": 2.18, "avg_win": 1.65, "avg_draw": 4.07, "avg_lose": 4.25, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.2000; Y=1.2100; X=1.3000; cold_risk=21.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.8, "jc_draw": 3.35, "jc_lose": 3.65, "rq_win": 3.45, "rq_draw": 3.52, "rq_lose": 1.8, "avg_win": 2.1, "avg_draw": 3.51, "avg_lose": 3.24, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3900; Y=1.2900; X=1.3900; cold_risk=7.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.78, "jc_draw": 3.5, "jc_lose": 3.55, "rq_win": 3.38, "rq_draw": 3.6, "rq_lose": 1.8, "avg_win": 1.79, "avg_draw": 3.71, "avg_lose": 4.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.5200; Y=1.2800; X=1.4900; cold_risk=22.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.99, "jc_draw": 3.14, "jc_lose": 3.25, "rq_win": 4.1, "rq_draw": 3.68, "rq_lose": 1.63, "avg_win": 2.6, "avg_draw": 3.31, "avg_lose": 2.6, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1000; Y=1.3300; X=1.5300; cold_risk=5.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 3.2, "jc_lose": 3.05, "rq_win": 4.2, "rq_draw": 3.75, "rq_lose": 1.6, "avg_win": 2.55, "avg_draw": 3.5, "avg_lose": 2.55, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1000; Y=1.3400; X=1.6800; cold_risk=6.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.46, "jc_draw": 3.16, "jc_lose": 2.46, "rq_win": 5.5, "rq_draw": 4.2, "rq_lose": 1.41, "avg_win": 2.57, "avg_draw": 3.36, "avg_lose": 2.55, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.8300; Y=1.4200; X=2.2300; cold_risk=26.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 3.85, "jc_lose": 4.85, "rq_win": 2.6, "rq_draw": 3.45, "rq_lose": 2.2, "avg_win": 1.49, "avg_draw": 4.25, "avg_lose": 6.39, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0700; Y=1.2000; X=1.1100; cold_risk=14.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 3.2, "jc_lose": 2.65, "rq_win": 4.9, "rq_draw": 4.0, "rq_lose": 1.48, "avg_win": 2.3, "avg_draw": 3.47, "avg_lose": 2.87, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.9500; Y=1.3900; X=2.0300; cold_risk=22.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.85, "jc_draw": 3.36, "jc_lose": 2.08, "rq_win": 1.57, "rq_draw": 3.95, "rq_lose": 4.2, "avg_win": 2.6, "avg_draw": 3.44, "avg_lose": 2.53, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7500; Y=1.4800; X=2.9900; cold_risk=24.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.28, "jc_lose": 3.95, "rq_win": 3.45, "rq_draw": 3.35, "rq_lose": 1.85, "avg_win": 1.94, "avg_draw": 3.3, "avg_lose": 3.89, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3900; Y=1.2700; X=1.2400; cold_risk=23.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.58, "jc_draw": 3.09, "jc_lose": 2.39, "rq_win": 1.42, "rq_draw": 4.0, "rq_lose": 5.7, "avg_win": 3.39, "avg_draw": 3.61, "avg_lose": 1.94, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7300; Y=1.4400; X=2.2800; cold_risk=14.1%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 3.08, "jc_draw": 3.4, "jc_lose": 1.96, "rq_win": 1.65, "rq_draw": 3.7, "rq_lose": 3.95, "avg_win": 2.91, "avg_draw": 3.46, "avg_lose": 2.25, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6700; Y=1.5100; X=3.3100; cold_risk=21.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.8, "jc_draw": 3.25, "jc_lose": 1.79, "rq_win": 1.78, "rq_draw": 3.4, "rq_lose": 3.65, "avg_win": 3.52, "avg_draw": 3.26, "avg_lose": 2.05, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3500; Y=1.5800; X=3.7200; cold_risk=26.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.6, "jc_lose": 3.75, "rq_win": 3.22, "rq_draw": 3.5, "rq_lose": 1.88, "avg_win": 1.85, "avg_draw": 3.57, "avg_lose": 3.92, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.6600; Y=1.2600; X=1.4300; cold_risk=11.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.76, "jc_draw": 3.4, "jc_lose": 3.75, "rq_win": 3.35, "rq_draw": 3.5, "rq_lose": 1.84, "avg_win": 1.88, "avg_draw": 3.45, "avg_lose": 3.88, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4600; Y=1.2800; X=1.3600; cold_risk=23.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.99, "jc_draw": 3.15, "jc_lose": 3.25, "rq_win": 4.08, "rq_draw": 3.65, "rq_lose": 1.64, "avg_win": 1.87, "avg_draw": 3.53, "avg_lose": 3.93, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1100; Y=1.3300; X=1.5300; cold_risk=13.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 3.19, "jc_lose": 2.85, "rq_win": 4.5, "rq_draw": 3.88, "rq_lose": 1.54, "avg_win": 1.91, "avg_draw": 3.53, "avg_lose": 3.83, "shenjia": "未输入", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0300; Y=1.3700; X=1.8300; cold_risk=4.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.32, "jc_lose": 4.1, "rq_win": 3.2, "rq_draw": 3.45, "rq_lose": 1.9, "avg_win": 1.71, "avg_draw": 3.63, "avg_lose": 4.8, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4500; Y=1.2600; X=1.2000; cold_risk=19.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.5, "jc_lose": 3.3, "rq_win": 3.4, "rq_draw": 3.8, "rq_lose": 1.75, "avg_win": 1.89, "avg_draw": 3.59, "avg_lose": 3.81, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4600; Y=1.3000; X=1.6300; cold_risk=13.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.32, "jc_lose": 2.22, "rq_win": 1.5, "rq_draw": 4.15, "rq_lose": 4.5, "avg_win": 2.11, "avg_draw": 3.53, "avg_lose": 3.2, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.8200; Y=1.4500; X=2.6800; cold_risk=20.1%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 3.05, "jc_lose": 2.36, "rq_win": 1.45, "rq_draw": 3.95, "rq_lose": 5.35, "avg_win": 2.59, "avg_draw": 3.1, "avg_lose": 2.62, "shenjia": "未输入", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6700; Y=1.4500; X=2.3000; cold_risk=13.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.64, "jc_draw": 3.75, "jc_lose": 3.95, "rq_win": 3.0, "rq_draw": 3.42, "rq_lose": 1.99, "avg_win": 1.95, "avg_draw": 3.49, "avg_lose": 3.43, "shenjia": "未输入", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8400; Y=1.2400; X=1.3800; cold_risk=12.4%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.8, "jc_lose": 1.7, "rq_win": 1.9, "rq_draw": 3.7, "rq_lose": 3.0, "avg_win": 2.45, "avg_draw": 3.43, "avg_lose": 2.61, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.5700; X=4.6000; cold_risk=16.9%; dev_level=极高偏离"},
    {"handicap": -1, "jc_win": 4.6, "jc_draw": 4.5, "jc_lose": 1.45, "rq_win": 2.37, "rq_draw": 3.6, "rq_lose": 2.33, "avg_win": 5.38, "avg_draw": 4.28, "avg_lose": 1.47, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.6100; Y=1.6400; X=7.2200; cold_risk=8.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.1, "jc_draw": 3.25, "jc_lose": 2.01, "rq_win": 1.62, "rq_draw": 3.7, "rq_lose": 4.15, "avg_win": 3.1, "avg_draw": 3.29, "avg_lose": 2.29, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5900; Y=1.5100; X=3.0700; cold_risk=20.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.88, "jc_draw": 3.35, "jc_lose": 3.35, "rq_win": 3.65, "rq_draw": 3.7, "rq_lose": 1.71, "avg_win": 2.3, "avg_draw": 3.25, "avg_lose": 3.16, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3300; Y=1.3100; X=1.5500; cold_risk=19.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.49, "jc_draw": 4.23, "jc_lose": 4.5, "rq_win": 2.43, "rq_draw": 3.65, "rq_lose": 2.25, "avg_win": 1.54, "avg_draw": 4.03, "avg_lose": 5.74, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4000; Y=1.2000; X=1.3100; cold_risk=16.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.4, "jc_draw": 4.2, "jc_lose": 5.65, "rq_win": 2.2, "rq_draw": 3.6, "rq_lose": 2.52, "avg_win": 1.48, "avg_draw": 4.39, "avg_lose": 6.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.5000; Y=1.1700; X=1.0000; cold_risk=15.1%; dev_level=一致"},
    {"handicap": -2, "jc_win": 8.8, "jc_draw": 5.7, "jc_lose": 1.19, "rq_win": 1.91, "rq_draw": 4.25, "rq_lose": 2.7, "avg_win": 6.38, "avg_draw": 4.86, "avg_lose": 1.39, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1600; Y=1.8000; X=15.5700; cold_risk=14.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 5.7, "jc_draw": 5.1, "jc_lose": 1.32, "rq_win": 2.83, "rq_draw": 3.92, "rq_lose": 1.92, "avg_win": 6.64, "avg_draw": 4.72, "avg_lose": 1.39, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.5200; Y=1.7000; X=10.0700; cold_risk=7.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.0, "jc_draw": 3.0, "jc_lose": 2.17, "rq_win": 1.51, "rq_draw": 3.65, "rq_lose": 5.2, "avg_win": 2.89, "avg_draw": 3.07, "avg_lose": 2.42, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "平局共振", "match_context": "Z=1.5000; Y=1.5000; X=2.5600; cold_risk=15.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.82, "jc_lose": 3.68, "rq_win": 2.89, "rq_draw": 3.9, "rq_lose": 1.9, "avg_win": 1.74, "avg_draw": 4.02, "avg_lose": 3.96, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8500; Y=1.2500; X=1.5300; cold_risk=11.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 3.6, "jc_lose": 2.52, "rq_win": 4.25, "rq_draw": 4.25, "rq_lose": 1.52, "avg_win": 2.8, "avg_draw": 3.52, "avg_lose": 2.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "5:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=2.2500; Y=1.3800; X=2.3800; cold_risk=5.3%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.39, "jc_draw": 4.55, "jc_lose": 5.25, "rq_win": 2.16, "rq_draw": 3.75, "rq_lose": 2.5, "avg_win": 1.44, "avg_draw": 5.05, "avg_lose": 5.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.8100; Y=1.1600; X=1.1700; cold_risk=16.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.2, "jc_draw": 3.3, "jc_lose": 1.7, "rq_win": 1.9, "rq_draw": 3.25, "rq_lose": 3.4, "avg_win": 5.15, "avg_draw": 3.48, "avg_lose": 1.71, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.2700; Y=1.6200; X=4.1200; cold_risk=18.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.0, "jc_draw": 4.55, "jc_lose": 1.41, "rq_win": 2.49, "rq_draw": 3.85, "rq_lose": 2.14, "avg_win": 5.18, "avg_draw": 3.98, "avg_lose": 1.62, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.5200; Y=1.6700; X=7.7600; cold_risk=12.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 6.1, "jc_draw": 5.15, "jc_lose": 1.3, "rq_win": 2.9, "rq_draw": 3.95, "rq_lose": 1.88, "avg_win": 3.83, "avg_draw": 3.88, "avg_lose": 1.83, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.4500; Y=1.7200; X=10.5600; cold_risk=24.5%; dev_level=极高偏离"},
    {"handicap": 1, "jc_win": 1.23, "jc_draw": 5.25, "jc_lose": 7.95, "rq_win": 1.74, "rq_draw": 4.11, "rq_lose": 3.21, "avg_win": 1.44, "avg_draw": 4.9, "avg_lose": 6.13, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.7100; Y=1.1000; X=0.8400; cold_risk=15.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.96, "jc_draw": 3.05, "jc_lose": 3.45, "rq_win": 4.4, "rq_draw": 3.38, "rq_lose": 1.65, "avg_win": 2.14, "avg_draw": 3.12, "avg_lose": 3.46, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0600; Y=1.3200; X=1.3800; cold_risk=26.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.95, "jc_draw": 3.2, "jc_lose": 3.29, "rq_win": 4.1, "rq_draw": 3.55, "rq_lose": 1.66, "avg_win": 1.68, "avg_draw": 3.58, "avg_lose": 4.65, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1700; Y=1.3200; X=1.5200; cold_risk=9.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.96, "jc_draw": 3.35, "jc_lose": 2.03, "rq_win": 1.6, "rq_draw": 3.75, "rq_lose": 4.22, "avg_win": 2.92, "avg_draw": 3.36, "avg_lose": 2.24, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6900; Y=1.4900; X=3.0900; cold_risk=20.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.03, "jc_draw": 3.55, "jc_lose": 2.82, "rq_win": 4.0, "rq_draw": 3.95, "rq_lose": 1.6, "avg_win": 2.35, "avg_draw": 3.61, "avg_lose": 2.77, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3400; Y=1.3400; X=2.0200; cold_risk=13.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 3.58, "jc_lose": 1.75, "rq_win": 1.85, "rq_draw": 3.75, "rq_lose": 3.1, "avg_win": 4.29, "avg_draw": 3.71, "avg_lose": 1.77, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5600; Y=1.5700; X=4.1600; cold_risk=10.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.71, "jc_draw": 3.35, "jc_lose": 4.1, "rq_win": 3.35, "rq_draw": 3.35, "rq_lose": 1.88, "avg_win": 1.76, "avg_draw": 3.46, "avg_lose": 4.7, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.4700; Y=1.2600; X=1.2000; cold_risk=19.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.66, "jc_draw": 3.8, "jc_lose": 3.8, "rq_win": 3.0, "rq_draw": 3.63, "rq_lose": 1.92, "avg_win": 1.59, "avg_draw": 4.17, "avg_lose": 5.07, "shenjia": "未输入", "real_result": "负", "real_score": "3:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8600; Y=1.2500; X=1.4700; cold_risk=5.8%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.86, "jc_draw": 3.95, "jc_lose": 1.62, "rq_win": 2.02, "rq_draw": 3.8, "rq_lose": 2.7, "avg_win": 3.18, "avg_draw": 3.8, "avg_lose": 2.04, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6300; Y=1.5900; X=5.1800; cold_risk=16.9%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 3.22, "jc_draw": 3.55, "jc_lose": 1.86, "rq_win": 1.73, "rq_draw": 3.76, "rq_lose": 3.5, "avg_win": 2.79, "avg_draw": 3.48, "avg_lose": 2.38, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6800; Y=1.5300; X=3.7300; cold_risk=22.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.51, "jc_draw": 3.7, "jc_lose": 2.17, "rq_win": 1.51, "rq_draw": 4.31, "rq_lose": 4.25, "avg_win": 2.56, "avg_draw": 3.84, "avg_lose": 2.4, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1100; Y=1.4300; X=3.0200; cold_risk=14.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.7, "jc_lose": 6.05, "rq_win": 2.0, "rq_draw": 3.76, "rq_lose": 2.75, "avg_win": 1.49, "avg_draw": 4.7, "avg_lose": 5.5, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.0300; Y=1.1400; X=1.0200; cold_risk=17.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 3.15, "jc_lose": 2.75, "rq_win": 4.95, "rq_draw": 3.9, "rq_lose": 1.49, "avg_win": 2.65, "avg_draw": 3.36, "avg_lose": 2.59, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9500; Y=1.3800; X=1.9000; cold_risk=15.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.52, "jc_draw": 3.7, "jc_lose": 5.0, "rq_win": 2.7, "rq_draw": 3.3, "rq_lose": 2.2, "avg_win": 1.66, "avg_draw": 3.9, "avg_lose": 4.91, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9400; Y=1.2100; X=1.0400; cold_risk=19.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.28, "jc_draw": 3.12, "jc_lose": 2.7, "rq_win": 5.25, "rq_draw": 3.95, "rq_lose": 1.46, "avg_win": 2.19, "avg_draw": 3.42, "avg_lose": 3.17, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9000; Y=1.3900; X=1.9400; cold_risk=22.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.25, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 3.9, "rq_lose": 4.6, "avg_win": 2.5, "avg_draw": 3.5, "avg_lose": 2.63, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7100; Y=1.4700; X=2.7500; cold_risk=26.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.33, "jc_draw": 4.45, "jc_lose": 6.55, "rq_win": 2.1, "rq_draw": 3.5, "rq_lose": 2.72, "avg_win": 1.45, "avg_draw": 4.56, "avg_lose": 6.41, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.8200; Y=1.1400; X=0.8900; cold_risk=14.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 3.75, "jc_lose": 5.65, "rq_win": 2.63, "rq_draw": 3.2, "rq_lose": 2.29, "avg_win": 1.78, "avg_draw": 3.46, "avg_lose": 4.6, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0500; Y=1.1900; X=0.9100; cold_risk=20.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.69, "jc_draw": 3.85, "jc_lose": 3.6, "rq_win": 3.04, "rq_draw": 3.65, "rq_lose": 1.9, "avg_win": 1.86, "avg_draw": 3.75, "avg_lose": 3.52, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8600; Y=1.2600; X=1.5800; cold_risk=13.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.0, "jc_draw": 3.35, "jc_lose": 1.72, "rq_win": 1.85, "rq_draw": 3.45, "rq_lose": 3.35, "avg_win": 4.63, "avg_draw": 3.94, "avg_lose": 1.69, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3400; Y=1.6000; X=4.0800; cold_risk=20.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.06, "jc_draw": 3.35, "jc_lose": 2.9, "rq_win": 4.2, "rq_draw": 3.9, "rq_lose": 1.58, "avg_win": 1.81, "avg_draw": 3.49, "avg_lose": 4.49, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1900; Y=1.3500; X=1.8600; cold_risk=11.0%; dev_level=轻微偏离"},
    {"handicap": -2, "jc_win": 12.0, "jc_draw": 6.0, "jc_lose": 1.14, "rq_win": 1.98, "rq_draw": 4.05, "rq_lose": 2.65, "avg_win": 9.3, "avg_draw": 5.28, "avg_lose": 1.29, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=0.9200; Y=1.8500; X=19.7800; cold_risk=10.0%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 4.6, "jc_lose": 1.41, "rq_win": 2.48, "rq_draw": 3.65, "rq_lose": 2.22, "avg_win": 4.52, "avg_draw": 4.3, "avg_lose": 1.58, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.5500; Y=1.6600; X=7.8300; cold_risk=10.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.54, "jc_draw": 3.86, "jc_lose": 2.1, "rq_win": 1.55, "rq_draw": 4.45, "rq_lose": 3.85, "avg_win": 2.5, "avg_draw": 3.92, "avg_lose": 2.4, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1800; Y=1.4400; X=3.2900; cold_risk=15.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.45, "jc_lose": 4.1, "rq_win": 3.2, "rq_draw": 3.4, "rq_lose": 1.92, "avg_win": 2.14, "avg_draw": 3.3, "avg_lose": 3.35, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.5700; Y=1.2500; X=1.2300; cold_risk=27.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.45, "jc_draw": 3.1, "jc_lose": 2.51, "rq_win": 5.5, "rq_draw": 4.1, "rq_lose": 1.42, "avg_win": 2.42, "avg_draw": 3.26, "avg_lose": 2.88, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.8000; Y=1.4200; X=2.1300; cold_risk=28.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.25, "jc_lose": 6.1, "rq_win": 2.2, "rq_draw": 3.5, "rq_lose": 2.57, "avg_win": 1.48, "avg_draw": 4.27, "avg_lose": 6.56, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.5900; Y=1.1600; X=0.9300; cold_risk=14.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.88, "jc_draw": 3.25, "jc_lose": 3.45, "rq_win": 3.85, "rq_draw": 3.48, "rq_lose": 1.72, "avg_win": 2.14, "avg_draw": 3.3, "avg_lose": 3.19, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2600; Y=1.3100; X=1.4500; cold_risk=5.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.69, "jc_draw": 3.55, "jc_lose": 3.9, "rq_win": 3.22, "rq_draw": 3.4, "rq_lose": 1.91, "avg_win": 1.83, "avg_draw": 3.5, "avg_lose": 4.05, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.6400; Y=1.2600; X=1.3400; cold_risk=22.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 3.35, "jc_lose": 1.99, "rq_win": 1.62, "rq_draw": 3.7, "rq_lose": 4.15, "avg_win": 3.23, "avg_draw": 3.37, "avg_lose": 2.11, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.5100; X=3.1900; cold_risk=18.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.98, "jc_draw": 3.1, "jc_lose": 2.12, "rq_win": 1.55, "rq_draw": 3.7, "rq_lose": 4.7, "avg_win": 3.4, "avg_draw": 3.27, "avg_lose": 2.04, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5600; Y=1.5000; X=2.7300; cold_risk=17.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 3.8, "jc_lose": 5.5, "rq_win": 2.6, "rq_draw": 3.25, "rq_lose": 2.3, "avg_win": 1.58, "avg_draw": 3.77, "avg_lose": 5.37, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0900; Y=1.1900; X=0.9500; cold_risk=17.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 3.9, "jc_lose": 5.1, "rq_win": 2.6, "rq_draw": 3.3, "rq_lose": 2.27, "avg_win": 1.72, "avg_draw": 3.67, "avg_lose": 4.41, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.1500; Y=1.1900; X=1.0600; cold_risk=14.1%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.62, "jc_draw": 3.0, "jc_lose": 2.42, "rq_win": 1.42, "rq_draw": 4.15, "rq_lose": 5.45, "avg_win": 2.85, "avg_draw": 3.27, "avg_lose": 2.41, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6600; Y=1.4500; X=2.1900; cold_risk=22.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.5, "jc_draw": 3.82, "jc_lose": 1.72, "rq_win": 1.85, "rq_draw": 3.95, "rq_lose": 2.98, "avg_win": 3.48, "avg_draw": 3.92, "avg_lose": 1.88, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7000; Y=1.5600; X=4.5200; cold_risk=14.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.05, "jc_draw": 3.4, "jc_lose": 1.97, "rq_win": 1.65, "rq_draw": 3.75, "rq_lose": 3.9, "avg_win": 2.75, "avg_draw": 3.38, "avg_lose": 2.48, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6800; Y=1.5100; X=3.2800; cold_risk=24.2%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.2, "jc_lose": 2.36, "rq_win": 1.44, "rq_draw": 3.95, "rq_lose": 5.5, "avg_win": 2.73, "avg_draw": 3.28, "avg_lose": 2.52, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8000; Y=1.4400; X=2.3800; cold_risk=24.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.17, "jc_draw": 2.9, "jc_lose": 3.1, "rq_win": 5.15, "rq_draw": 3.55, "rq_lose": 1.53, "avg_win": 1.83, "avg_draw": 3.35, "avg_lose": 4.5, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "冷门预警", "match_context": "Z=1.8300; Y=1.3700; X=1.5200; cold_risk=10.8%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 2.93, "jc_draw": 3.3, "jc_lose": 2.06, "rq_win": 1.58, "rq_draw": 3.85, "rq_lose": 4.25, "avg_win": 3.41, "avg_draw": 3.47, "avg_lose": 2.07, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:6", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6800; Y=1.4900; X=2.9900; cold_risk=16.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.52, "jc_draw": 3.3, "jc_lose": 2.33, "rq_win": 1.45, "rq_draw": 4.05, "rq_lose": 5.2, "avg_win": 2.53, "avg_draw": 3.55, "avg_lose": 2.58, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8800; Y=1.4300; X=2.4900; cold_risk=16.4%; dev_level=一致"},
    {"handicap": -2, "jc_win": 8.75, "jc_draw": 6.0, "jc_lose": 1.18, "rq_win": 1.99, "rq_draw": 4.2, "rq_lose": 2.57, "avg_win": 5.11, "avg_draw": 4.31, "avg_lose": 1.56, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:5", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "冷门预警", "match_context": "Z=1.2300; Y=1.7900; X=16.8100; cold_risk=18.3%; dev_level=极高偏离"},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.12, "jc_lose": 4.1, "rq_win": 3.75, "rq_draw": 3.22, "rq_lose": 1.81, "avg_win": 1.91, "avg_draw": 3.27, "avg_lose": 4.01, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2500; Y=1.2800; X=1.1400; cold_risk=23.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.22, "jc_draw": 5.7, "jc_lose": 7.5, "rq_win": 1.7, "rq_draw": 4.2, "rq_lose": 3.3, "avg_win": 1.53, "avg_draw": 4.3, "avg_lose": 4.99, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=5.1400; Y=1.1000; X=0.9600; cold_risk=18.4%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 1.52, "jc_draw": 3.75, "jc_lose": 4.9, "rq_win": 2.7, "rq_draw": 3.35, "rq_lose": 2.18, "avg_win": 1.65, "avg_draw": 3.85, "avg_lose": 5.09, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9800; Y=1.2100; X=1.0700; cold_risk=18.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.77, "jc_lose": 3.41, "rq_win": 3.2, "rq_draw": 3.78, "rq_lose": 1.81, "avg_win": 1.91, "avg_draw": 3.96, "avg_lose": 3.46, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7400; Y=1.2700; X=1.6700; cold_risk=14.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.88, "jc_draw": 3.25, "jc_lose": 3.45, "rq_win": 3.95, "rq_draw": 3.5, "rq_lose": 1.7, "avg_win": 1.91, "avg_draw": 3.39, "avg_lose": 4.01, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2600; Y=1.3100; X=1.4500; cold_risk=23.4%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 2.95, "jc_lose": 3.2, "rq_win": 4.75, "rq_draw": 3.6, "rq_lose": 1.56, "avg_win": 2.25, "avg_draw": 3.22, "avg_lose": 3.21, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "5:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.9000; Y=1.3500; X=1.4800; cold_risk=16.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.25, "jc_draw": 3.15, "jc_lose": 2.72, "rq_win": 4.95, "rq_draw": 3.9, "rq_lose": 1.49, "avg_win": 2.13, "avg_draw": 3.23, "avg_lose": 3.44, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9400; Y=1.3800; X=1.9300; cold_risk=23.9%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.84, "jc_draw": 3.25, "jc_lose": 3.6, "rq_win": 3.75, "rq_draw": 3.45, "rq_lose": 1.75, "avg_win": 2.25, "avg_draw": 3.23, "avg_lose": 3.18, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2900; Y=1.3000; X=1.3800; cold_risk=29.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.7, "jc_lose": 4.2, "rq_win": 2.89, "rq_draw": 3.5, "rq_lose": 2.01, "avg_win": 1.55, "avg_draw": 4.23, "avg_lose": 5.28, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8400; Y=1.2300; X=1.2700; cold_risk=17.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 2.95, "jc_lose": 3.3, "rq_win": 4.65, "rq_draw": 3.5, "rq_lose": 1.59, "avg_win": 2.26, "avg_draw": 3.21, "avg_lose": 3.21, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.9300; Y=1.3400; X=1.4300; cold_risk=16.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.1, "jc_draw": 3.22, "jc_lose": 2.02, "rq_win": 1.62, "rq_draw": 3.58, "rq_lose": 4.3, "avg_win": 3.09, "avg_draw": 3.3, "avg_lose": 2.2, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5700; Y=1.5100; X=3.0200; cold_risk=19.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.83, "jc_draw": 3.05, "jc_lose": 3.95, "rq_win": 3.95, "rq_draw": 3.3, "rq_lose": 1.75, "avg_win": 2.31, "avg_draw": 3.04, "avg_lose": 3.28, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1600; Y=1.2900; X=1.1700; cold_risk=28.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.34, "jc_draw": 2.65, "jc_lose": 3.08, "rq_win": 5.9, "rq_draw": 3.7, "rq_lose": 1.45, "avg_win": 2.51, "avg_draw": 3.0, "avg_lose": 2.97, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5900; Y=1.4000; X=1.4400; cold_risk=24.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.67, "jc_draw": 3.85, "jc_lose": 3.7, "rq_win": 2.9, "rq_draw": 3.7, "rq_lose": 1.95, "avg_win": 1.73, "avg_draw": 3.89, "avg_lose": 3.95, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8800; Y=1.2500; X=1.5300; cold_risk=11.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.3, "jc_draw": 3.85, "jc_lose": 1.57, "rq_win": 2.05, "rq_draw": 3.5, "rq_lose": 2.81, "avg_win": 3.87, "avg_draw": 3.71, "avg_lose": 1.77, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4500; Y=1.6200; X=5.4000; cold_risk=23.6%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.12, "jc_draw": 6.7, "jc_lose": 11.75, "rq_win": 2.3, "rq_draw": 4.1, "rq_lose": 2.22, "avg_win": 1.32, "avg_draw": 5.24, "avg_lose": 6.93, "shenjia": "未输入", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=6.3200; Y=1.0600; X=0.6900; cold_risk=7.5%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 2.9, "jc_lose": 2.38, "rq_win": 1.43, "rq_draw": 3.8, "rq_lose": 6.0, "avg_win": 2.52, "avg_draw": 3.04, "avg_lose": 2.92, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.5500; Y=1.4700; X=2.1800; cold_risk=27.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.19, "jc_draw": 3.25, "jc_lose": 2.75, "rq_win": 4.85, "rq_draw": 3.85, "rq_lose": 1.51, "avg_win": 2.05, "avg_draw": 3.41, "avg_lose": 3.38, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0400; Y=1.3700; X=1.9500; cold_risk=17.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 3.3, "jc_lose": 2.16, "rq_win": 1.53, "rq_draw": 4.0, "rq_lose": 4.45, "avg_win": 3.06, "avg_draw": 3.17, "avg_lose": 2.35, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7600; Y=1.4700; X=2.7800; cold_risk=19.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.21, "jc_draw": 3.5, "jc_lose": 1.88, "rq_win": 1.7, "rq_draw": 3.75, "rq_lose": 3.65, "avg_win": 2.93, "avg_draw": 3.38, "avg_lose": 2.19, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.6600; Y=1.5200; X=3.6200; cold_risk=8.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.68, "jc_draw": 3.65, "jc_lose": 3.85, "rq_win": 3.0, "rq_draw": 3.6, "rq_lose": 1.93, "avg_win": 1.69, "avg_draw": 3.97, "avg_lose": 4.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7200; Y=1.2500; X=1.4000; cold_risk=20.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.35, "jc_lose": 2.25, "rq_win": 1.49, "rq_draw": 4.1, "rq_lose": 4.7, "avg_win": 2.62, "avg_draw": 3.6, "avg_lose": 2.45, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8600; Y=1.4400; X=2.6400; cold_risk=24.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.48, "jc_draw": 4.3, "jc_lose": 4.55, "rq_win": 2.35, "rq_draw": 3.9, "rq_lose": 2.24, "avg_win": 1.4, "avg_draw": 4.74, "avg_lose": 6.44, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4700; Y=1.1900; X=1.3100; cold_risk=14.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.94, "jc_draw": 3.1, "jc_lose": 3.45, "rq_win": 4.1, "rq_draw": 3.45, "rq_lose": 1.68, "avg_win": 2.08, "avg_draw": 3.27, "avg_lose": 3.38, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1100; Y=1.3200; X=1.4000; cold_risk=6.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.75, "jc_draw": 3.8, "jc_lose": 3.4, "rq_win": 3.1, "rq_draw": 3.85, "rq_lose": 1.83, "avg_win": 1.76, "avg_draw": 3.94, "avg_lose": 3.75, "shenjia": "未输入", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7600; Y=1.2700; X=1.6800; cold_risk=9.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.67, "jc_draw": 3.6, "jc_lose": 3.95, "rq_win": 3.05, "rq_draw": 3.56, "rq_lose": 1.92, "avg_win": 1.85, "avg_draw": 3.55, "avg_lose": 3.95, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7000; Y=1.2500; X=1.3400; cold_risk=23.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.53, "jc_draw": 3.65, "jc_lose": 5.0, "rq_win": 2.82, "rq_draw": 3.25, "rq_lose": 2.15, "avg_win": 1.85, "avg_draw": 3.48, "avg_lose": 4.02, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8900; Y=1.2100; X=1.0200; cold_risk=23.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.45, "jc_draw": 4.2, "jc_lose": 4.95, "rq_win": 2.3, "rq_draw": 3.75, "rq_lose": 2.35, "avg_win": 1.61, "avg_draw": 4.21, "avg_lose": 4.89, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4300; Y=1.1800; X=1.1700; cold_risk=19.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.65, "jc_draw": 3.8, "jc_lose": 3.85, "rq_win": 2.85, "rq_draw": 3.78, "rq_lose": 1.95, "avg_win": 1.79, "avg_draw": 3.96, "avg_lose": 4.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8700; Y=1.2500; X=1.4400; cold_risk=23.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.9, "jc_draw": 3.3, "jc_lose": 3.33, "rq_win": 3.75, "rq_draw": 3.7, "rq_lose": 1.69, "avg_win": 2.27, "avg_draw": 3.48, "avg_lose": 2.96, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2800; Y=1.3100; X=1.5400; cold_risk=21.7%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 4.85, "jc_draw": 4.05, "jc_lose": 1.48, "rq_win": 2.26, "rq_draw": 3.65, "rq_lose": 2.42, "avg_win": 4.16, "avg_draw": 3.88, "avg_lose": 1.77, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3800; Y=1.6600; X=6.3400; cold_risk=22.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.38, "jc_draw": 3.55, "jc_lose": 8.25, "rq_win": 2.45, "rq_draw": 3.05, "rq_lose": 2.55, "avg_win": 1.52, "avg_draw": 3.48, "avg_lose": 7.06, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=2.9800; Y=1.1600; X=0.5700; cold_risk=15.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.65, "jc_draw": 2.92, "jc_lose": 2.44, "rq_win": 1.41, "rq_draw": 3.85, "rq_lose": 6.25, "avg_win": 2.45, "avg_draw": 3.08, "avg_lose": 2.79, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.6000; Y=1.4500; X=2.1200; cold_risk=27.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.51, "jc_draw": 3.35, "jc_lose": 2.31, "rq_win": 1.47, "rq_draw": 4.15, "rq_lose": 4.8, "avg_win": 3.06, "avg_draw": 3.45, "avg_lose": 2.1, "shenjia": "未输入", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9100; Y=1.4300; X=2.5500; cold_risk=6.1%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.58, "jc_draw": 3.75, "jc_lose": 4.35, "rq_win": 2.86, "rq_draw": 3.45, "rq_lose": 2.04, "avg_win": 1.96, "avg_draw": 3.61, "avg_lose": 3.63, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9100; Y=1.2200; X=1.2300; cold_risk=25.9%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 4.4, "jc_draw": 3.38, "jc_lose": 1.65, "rq_win": 1.98, "rq_draw": 3.35, "rq_lose": 3.07, "avg_win": 3.88, "avg_draw": 3.6, "avg_lose": 1.9, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.2500; Y=1.6300; X=4.4300; cold_risk=24.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.63, "jc_draw": 3.7, "jc_lose": 4.07, "rq_win": 2.85, "rq_draw": 3.65, "rq_lose": 1.98, "avg_win": 1.73, "avg_draw": 3.88, "avg_lose": 4.32, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8100; Y=1.2400; X=1.3200; cold_risk=21.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.85, "jc_draw": 3.15, "jc_lose": 2.17, "rq_win": 1.52, "rq_draw": 3.8, "rq_lose": 4.8, "avg_win": 2.6, "avg_draw": 3.3, "avg_lose": 2.58, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6400; Y=1.4800; X=2.6600; cold_risk=25.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.51, "jc_draw": 3.85, "jc_lose": 4.85, "rq_win": 2.6, "rq_draw": 3.45, "rq_lose": 2.2, "avg_win": 1.63, "avg_draw": 3.87, "avg_lose": 4.87, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "6:3", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=3.0700; Y=1.2000; X=1.1100; cold_risk=19.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.2, "jc_draw": 4.95, "jc_lose": 11.0, "rq_win": 1.81, "rq_draw": 3.35, "rq_lose": 3.6, "avg_win": 1.41, "avg_draw": 3.87, "avg_lose": 8.55, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.5000; Y=1.0900; X=0.5600; cold_risk=14.7%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 2.58, "jc_lose": 4.15, "rq_win": 4.7, "rq_draw": 3.3, "rq_lose": 1.63, "avg_win": 2.45, "avg_draw": 2.91, "avg_lose": 3.01, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=胜", "resonance_type": "正常", "match_context": "Z=1.7200; Y=1.3300; X=0.9700; cold_risk=15.0%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.23, "jc_draw": 4.06, "jc_lose": 2.3, "rq_win": 4.2, "rq_draw": 4.55, "rq_lose": 1.49, "avg_win": 2.13, "avg_draw": 4.06, "avg_lose": 2.75, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.5100; Y=1.3800; X=3.0000; cold_risk=13.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.03, "jc_draw": 3.35, "jc_lose": 2.0, "rq_win": 1.62, "rq_draw": 3.8, "rq_lose": 4.05, "avg_win": 2.51, "avg_draw": 3.37, "avg_lose": 2.73, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6600; Y=1.5000; X=3.1700; cold_risk=26.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.7, "jc_lose": 3.7, "rq_win": 3.0, "rq_draw": 3.75, "rq_lose": 1.89, "avg_win": 2.12, "avg_draw": 3.59, "avg_lose": 3.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7400; Y=1.2600; X=1.4800; cold_risk=11.9%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.28, "jc_lose": 2.28, "rq_win": 1.47, "rq_draw": 4.1, "rq_lose": 4.9, "avg_win": 2.74, "avg_draw": 3.4, "avg_lose": 2.46, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8200; Y=1.4400; X=2.5500; cold_risk=23.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.25, "jc_draw": 3.8, "jc_lose": 1.48, "rq_win": 2.25, "rq_draw": 3.25, "rq_lose": 2.65, "avg_win": 3.97, "avg_draw": 3.42, "avg_lose": 1.89, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "冷门预警", "match_context": "Z=1.2200; Y=1.6800; X=6.0300; cold_risk=23.5%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 4.05, "jc_lose": 1.47, "rq_win": 2.3, "rq_draw": 3.45, "rq_lose": 2.47, "avg_win": 3.87, "avg_draw": 3.94, "avg_lose": 1.75, "shenjia": "未输入", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3600; Y=1.6600; X=6.4400; cold_risk=9.6%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 4.07, "jc_draw": 3.65, "jc_lose": 1.64, "rq_win": 1.98, "rq_draw": 3.45, "rq_lose": 3.0, "avg_win": 3.85, "avg_draw": 3.53, "avg_lose": 1.86, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4400; Y=1.6100; X=4.7600; cold_risk=24.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.4, "jc_draw": 3.65, "jc_lose": 2.28, "rq_win": 1.47, "rq_draw": 4.35, "rq_lose": 4.55, "avg_win": 2.46, "avg_draw": 3.57, "avg_lose": 2.57, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.1500; Y=1.4100; X=2.7800; cold_risk=17.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.5, "jc_draw": 2.93, "jc_lose": 2.58, "rq_win": 5.95, "rq_draw": 4.05, "rq_lose": 1.4, "avg_win": 2.62, "avg_draw": 2.94, "avg_lose": 2.77, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.6700; Y=1.4300; X=1.9600; cold_risk=24.1%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.85, "jc_draw": 3.65, "jc_lose": 1.98, "rq_win": 1.65, "rq_draw": 4.02, "rq_lose": 3.65, "avg_win": 3.29, "avg_draw": 3.93, "avg_lose": 1.91, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9000; Y=1.4800; X=3.4500; cold_risk=15.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 3.45, "jc_lose": 2.84, "rq_win": 4.15, "rq_draw": 3.91, "rq_lose": 1.58, "avg_win": 1.95, "avg_draw": 3.74, "avg_lose": 3.49, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.2600; Y=1.3400; X=1.9600; cold_risk=16.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.05, "jc_draw": 3.13, "jc_lose": 3.1, "rq_win": 4.3, "rq_draw": 3.75, "rq_lose": 1.59, "avg_win": 2.23, "avg_draw": 3.25, "avg_lose": 2.99, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0500; Y=1.3400; X=1.6200; cold_risk=20.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.2, "jc_lose": 2.18, "rq_win": 1.52, "rq_draw": 3.9, "rq_lose": 4.65, "avg_win": 2.66, "avg_draw": 3.29, "avg_lose": 2.41, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.6800; Y=1.4700; X=2.6800; cold_risk=15.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 4.2, "jc_lose": 4.85, "rq_win": 2.4, "rq_draw": 3.55, "rq_lose": 2.32, "avg_win": 1.53, "avg_draw": 4.28, "avg_lose": 5.08, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "6:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.4100; Y=1.1900; X=1.2000; cold_risk=18.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.65, "jc_draw": 3.5, "jc_lose": 1.76, "rq_win": 1.82, "rq_draw": 3.5, "rq_lose": 3.4, "avg_win": 3.68, "avg_draw": 3.68, "avg_lose": 1.85, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5100; Y=1.5700; X=4.0500; cold_risk=14.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.22, "jc_draw": 3.4, "jc_lose": 2.6, "rq_win": 4.6, "rq_draw": 4.1, "rq_lose": 1.5, "avg_win": 2.5, "avg_draw": 3.36, "avg_lose": 2.7, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1100; Y=1.3800; X=2.1800; cold_risk=10.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.94, "jc_draw": 3.3, "jc_lose": 3.22, "rq_win": 3.95, "rq_draw": 3.7, "rq_lose": 1.65, "avg_win": 1.63, "avg_draw": 3.59, "avg_lose": 5.6, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "冷门预警", "match_context": "Z=2.2400; Y=1.3200; X=1.6100; cold_risk=6.7%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.87, "jc_lose": 4.0, "rq_win": 2.7, "rq_draw": 3.72, "rq_lose": 2.04, "avg_win": 2.03, "avg_draw": 3.67, "avg_lose": 3.3, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9700; Y=1.2300; X=1.4000; cold_risk=28.4%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.85, "jc_draw": 3.73, "jc_lose": 3.12, "rq_win": 3.4, "rq_draw": 3.9, "rq_lose": 1.73, "avg_win": 2.4, "avg_draw": 3.66, "avg_lose": 2.67, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.6200; Y=1.3000; X=1.8500; cold_risk=5.8%; dev_level=轻微偏离"},
    {"handicap": 2, "jc_win": 1.18, "jc_draw": 5.95, "jc_lose": 8.75, "rq_win": 2.5, "rq_draw": 4.15, "rq_lose": 2.05, "avg_win": 1.21, "avg_draw": 6.82, "avg_lose": 11.38, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=5.4600; Y=1.0800; X=0.8400; cold_risk=8.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.6, "jc_draw": 4.01, "jc_lose": 1.66, "rq_win": 1.95, "rq_draw": 3.85, "rq_lose": 2.8, "avg_win": 4.0, "avg_draw": 4.16, "avg_lose": 1.74, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7400; Y=1.5700; X=5.0100; cold_risk=11.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.17, "jc_draw": 3.8, "jc_lose": 2.47, "rq_win": 4.16, "rq_draw": 4.4, "rq_lose": 1.51, "avg_win": 2.18, "avg_draw": 3.87, "avg_lose": 2.87, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.4000; Y=1.3700; X=2.5600; cold_risk=13.0%; dev_level=一致", "match_id": "#537"},
    {"handicap": 2, "jc_win": 1.12, "jc_draw": 6.4, "jc_lose": 12.5, "rq_win": 2.37, "rq_draw": 3.95, "rq_lose": 2.2, "avg_win": 1.19, "avg_draw": 6.32, "avg_lose": 13.86, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=6.0400; Y=1.0600; X=0.6200; cold_risk=6.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.33, "jc_draw": 3.42, "jc_lose": 2.45, "rq_win": 5.0, "rq_draw": 4.2, "rq_lose": 1.45, "avg_win": 2.38, "avg_draw": 3.49, "avg_lose": 2.76, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0500; Y=1.4000; X=2.3800; cold_risk=13.9%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 3.1, "jc_lose": 3.02, "rq_win": 4.6, "rq_draw": 3.7, "rq_lose": 1.56, "avg_win": 1.72, "avg_draw": 3.67, "avg_lose": 4.74, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.0000; Y=1.3500; X=1.6600; cold_risk=32.4%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 1.69, "jc_draw": 3.5, "jc_lose": 4.0, "rq_win": 3.15, "rq_draw": 3.5, "rq_lose": 1.9, "avg_win": 1.75, "avg_draw": 3.61, "avg_lose": 4.5, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "2:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.6000; Y=1.2600; X=1.2900; cold_risk=20.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.37, "jc_draw": 4.5, "jc_lose": 5.7, "rq_win": 2.07, "rq_draw": 3.8, "rq_lose": 2.62, "avg_win": 1.42, "avg_draw": 4.69, "avg_lose": 6.72, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.8000; Y=1.1600; X=1.0500; cold_risk=14.0%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.0, "jc_draw": 3.05, "jc_lose": 3.32, "rq_win": 4.35, "rq_draw": 3.55, "rq_lose": 1.62, "avg_win": 1.87, "avg_draw": 3.41, "avg_lose": 4.18, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.0300; Y=1.3300; X=1.4500; cold_risk=16.8%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.91, "jc_draw": 3.5, "jc_lose": 2.0, "rq_win": 1.63, "rq_draw": 4.0, "rq_lose": 3.76, "avg_win": 3.0, "avg_draw": 3.79, "avg_lose": 2.13, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7900; Y=1.4900; X=3.2800; cold_risk=18.7%; dev_level=一致"},
    {"handicap": -2, "jc_win": 9.1, "jc_draw": 5.8, "jc_lose": 1.18, "rq_win": 1.96, "rq_draw": 3.9, "rq_lose": 2.76, "avg_win": 7.42, "avg_draw": 5.44, "avg_lose": 1.31, "shenjia": "未输入", "real_result": "负", "real_score": "0:6", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1500; Y=1.8000; X=16.3900; cold_risk=4.5%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.35, "jc_draw": 3.1, "jc_lose": 1.97, "rq_win": 1.62, "rq_draw": 3.5, "rq_lose": 4.45, "avg_win": 3.57, "avg_draw": 3.21, "avg_lose": 2.1, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.4300; Y=1.5400; X=3.0600; cold_risk=26.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.85, "jc_lose": 4.05, "rq_win": 2.84, "rq_draw": 3.55, "rq_lose": 2.02, "avg_win": 2.06, "avg_draw": 3.6, "avg_lose": 3.2, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "5:3", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.9500; Y=1.2300; X=1.3700; cold_risk=13.3%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.9, "jc_draw": 3.35, "jc_lose": 3.3, "rq_win": 3.75, "rq_draw": 3.7, "rq_lose": 1.69, "avg_win": 2.12, "avg_draw": 3.4, "avg_lose": 3.31, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.3100; Y=1.3100; X=1.5700; cold_risk=18.3%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.92, "jc_draw": 3.56, "jc_lose": 3.05, "rq_win": 3.6, "rq_draw": 3.9, "rq_lose": 1.68, "avg_win": 2.38, "avg_draw": 3.6, "avg_lose": 2.71, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.4400; Y=1.3200; X=1.8300; cold_risk=6.0%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.35, "jc_draw": 4.3, "jc_lose": 6.4, "rq_win": 2.15, "rq_draw": 3.5, "rq_lose": 2.65, "avg_win": 1.58, "avg_draw": 3.96, "avg_lose": 5.46, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.6600; Y=1.1500; X=0.8900; cold_risk=17.1%; dev_level=轻微偏离"},
    {"handicap": -2, "jc_win": 12.0, "jc_draw": 5.42, "jc_lose": 1.16, "rq_win": 1.88, "rq_draw": 3.9, "rq_lose": 2.94, "avg_win": 9.99, "avg_draw": 4.88, "avg_lose": 1.3, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=0.8300; Y=1.8500; X=16.7500; cold_risk=9.3%; dev_level=一致"},
    {"handicap": -1, "jc_win": 6.5, "jc_draw": 5.0, "jc_lose": 1.29, "rq_win": 2.92, "rq_draw": 3.9, "rq_lose": 1.89, "avg_win": 4.38, "avg_draw": 4.31, "avg_lose": 1.61, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:5", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=1.3300; Y=1.7300; X=10.5700; cold_risk=21.1%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 3.85, "jc_lose": 5.7, "rq_win": 2.44, "rq_draw": 3.3, "rq_lose": 2.4, "avg_win": 1.45, "avg_draw": 4.21, "avg_lose": 6.96, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.1600; Y=1.1800; X=0.9200; cold_risk=13.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.6, "jc_draw": 3.35, "jc_lose": 2.24, "rq_win": 1.49, "rq_draw": 4.15, "rq_lose": 4.6, "avg_win": 3.3, "avg_draw": 3.57, "avg_lose": 2.08, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8600; Y=1.4400; X=2.6700; cold_risk=17.4%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 6.3, "jc_draw": 3.9, "jc_lose": 1.4, "rq_win": 2.5, "rq_draw": 3.35, "rq_lose": 2.32, "avg_win": 6.61, "avg_draw": 3.94, "avg_lose": 1.51, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.0700; Y=1.7300; X=6.9900; cold_risk=14.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.27, "jc_draw": 5.15, "jc_lose": 6.8, "rq_win": 1.83, "rq_draw": 3.95, "rq_lose": 3.03, "avg_win": 1.34, "avg_draw": 5.33, "avg_lose": 7.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.5400; Y=1.1200; X=0.9800; cold_risk=12.2%; dev_level=一致", "match_id": "#554"},
    {"handicap": 1, "jc_win": 1.21, "jc_draw": 4.82, "jc_lose": 10.5, "rq_win": 1.81, "rq_draw": 3.53, "rq_lose": 3.4, "avg_win": 1.44, "avg_draw": 4.12, "avg_lose": 7.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.3600; Y=1.1000; X=0.5700; cold_risk=13.5%; dev_level=轻微偏离", "match_id": "#555"},
    {"handicap": 1, "jc_win": 2.1, "jc_draw": 3.05, "jc_lose": 3.08, "rq_win": 4.9, "rq_draw": 3.55, "rq_lose": 1.56, "avg_win": 2.16, "avg_draw": 3.28, "avg_lose": 3.14, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.9700; Y=1.3500; X=1.6000; cold_risk=22.6%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.65, "jc_lose": 4.26, "rq_win": 2.95, "rq_draw": 3.45, "rq_lose": 2.0, "avg_win": 1.96, "avg_draw": 3.32, "avg_lose": 3.46, "shenjia": "主身 = 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8000; Y=1.2300; X=1.2400; cold_risk=13.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.56, "jc_draw": 3.45, "jc_lose": 5.05, "rq_win": 2.82, "rq_draw": 3.35, "rq_lose": 2.1, "avg_win": 1.69, "avg_draw": 3.61, "avg_lose": 5.17, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.7000; Y=1.2200; X=0.9700; cold_risk=18.2%; dev_level=一致"},
    {"handicap": 1, "jc_win": 2.08, "jc_draw": 3.3, "jc_lose": 2.9, "rq_win": 4.35, "rq_draw": 3.75, "rq_lose": 1.58, "avg_win": 2.25, "avg_draw": 3.43, "avg_lose": 2.77, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=2.1400; Y=1.3500; X=1.8400; cold_risk=10.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.43, "jc_draw": 4.45, "jc_lose": 4.9, "rq_win": 2.22, "rq_draw": 3.9, "rq_lose": 2.38, "avg_win": 1.8, "avg_draw": 3.95, "avg_lose": 3.61, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=3.6600; Y=1.1800; X=1.2400; cold_risk=25.5%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 2.36, "jc_draw": 2.9, "jc_lose": 2.78, "rq_win": 5.7, "rq_draw": 3.8, "rq_lose": 1.45, "avg_win": 1.78, "avg_draw": 3.4, "avg_lose": 4.79, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "冷门预警", "match_context": "Z=1.7300; Y=1.4000; X=1.7600; cold_risk=8.5%; dev_level=极高偏离"},
    {"handicap": 1, "jc_win": 1.3, "jc_draw": 4.5, "jc_lose": 7.25, "rq_win": 1.98, "rq_draw": 3.55, "rq_lose": 2.92, "avg_win": 1.31, "avg_draw": 5.12, "avg_lose": 9.62, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=3.9100; Y=1.1300; X=0.8100; cold_risk=9.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.27, "jc_draw": 5.15, "jc_lose": 6.8, "rq_win": 1.83, "rq_draw": 3.95, "rq_lose": 3.03, "avg_win": 1.34, "avg_draw": 5.33, "avg_lose": 7.74, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.5400; Y=1.1200; X=0.9800; cold_risk=12.2%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.96, "jc_draw": 4.1, "jc_lose": 1.58, "rq_win": 2.05, "rq_draw": 3.75, "rq_lose": 2.67, "avg_win": 4.08, "avg_draw": 3.92, "avg_lose": 1.7, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:5", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6500; Y=1.6000; X=5.6000; cold_risk=10.9%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.7, "jc_draw": 3.95, "jc_lose": 1.51, "rq_win": 2.2, "rq_draw": 3.45, "rq_lose": 2.6, "avg_win": 5.04, "avg_draw": 4.09, "avg_lose": 1.6, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.3900; Y=1.6500; X=5.9500; cold_risk=18.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.8, "jc_draw": 3.6, "jc_lose": 2.03, "rq_win": 1.6, "rq_draw": 4.0, "rq_lose": 3.95, "avg_win": 3.1, "avg_draw": 3.67, "avg_lose": 2.12, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8900; Y=1.4700; X=3.2700; cold_risk=17.7%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.61, "jc_draw": 3.5, "jc_lose": 4.5, "rq_win": 3.07, "rq_draw": 3.3, "rq_lose": 2.0, "avg_win": 1.54, "avg_draw": 3.94, "avg_lose": 6.0, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.6800; Y=1.2300; X=1.1200; cold_risk=15.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.2, "jc_draw": 2.7, "jc_lose": 3.3, "rq_win": 5.5, "rq_draw": 3.5, "rq_lose": 1.51, "avg_win": 2.12, "avg_draw": 2.93, "avg_lose": 3.96, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.6900; Y=1.3800; X=1.3300; cold_risk=23.7%; dev_level=一致"},
    {"handicap": -1, "jc_win": 4.95, "jc_draw": 3.85, "jc_lose": 1.5, "rq_win": 2.21, "rq_draw": 3.35, "rq_lose": 2.65, "avg_win": 5.56, "avg_draw": 3.87, "avg_lose": 1.57, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "3:2", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.2900; Y=1.6600; X=5.9200; cold_risk=16.7%; dev_level=一致"},
    {"handicap": -2, "jc_win": 8.7, "jc_draw": 5.75, "jc_lose": 1.19, "rq_win": 1.92, "rq_draw": 4.15, "rq_lose": 2.72, "avg_win": 8.72, "avg_draw": 5.68, "avg_lose": 1.29, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.1900; Y=1.7900; X=15.6800; cold_risk=10.8%; dev_level=一致"},
    {"handicap": -1, "jc_win": 2.75, "jc_draw": 3.45, "jc_lose": 2.1, "rq_win": 1.56, "rq_draw": 3.95, "rq_lose": 4.25, "avg_win": 2.97, "avg_draw": 3.56, "avg_lose": 2.22, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:3", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.8400; Y=1.4700; X=3.0100; cold_risk=20.4%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.5, "jc_draw": 4.1, "jc_lose": 1.42, "rq_win": 2.4, "rq_draw": 3.45, "rq_lose": 2.37, "avg_win": 4.73, "avg_draw": 3.71, "avg_lose": 1.68, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.2600; Y=1.6900; X=7.0300; cold_risk=19.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.21, "jc_draw": 4.82, "jc_lose": 10.5, "rq_win": 1.81, "rq_draw": 3.53, "rq_lose": 3.4, "avg_win": 1.44, "avg_draw": 4.12, "avg_lose": 7.2, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=4.3600; Y=1.1000; X=0.5700; cold_risk=13.5%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.72, "jc_draw": 3.82, "jc_lose": 3.5, "rq_win": 3.0, "rq_draw": 3.9, "rq_lose": 1.86, "avg_win": 1.66, "avg_draw": 4.17, "avg_lose": 4.26, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=2.8100; Y=1.2600; X=1.6300; cold_risk=9.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.55, "jc_draw": 3.65, "jc_lose": 4.75, "rq_win": 2.81, "rq_draw": 3.25, "rq_lose": 2.15, "avg_win": 1.94, "avg_draw": 3.4, "avg_lose": 3.47, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "冷门预警", "match_context": "Z=2.8600; Y=1.2200; X=1.0900; cold_risk=26.3%; dev_level=显著偏离"},
    {"handicap": 2, "jc_win": 1.14, "jc_draw": 5.8, "jc_lose": 12.5, "rq_win": 2.76, "rq_draw": 3.9, "rq_lose": 1.96, "avg_win": 1.26, "avg_draw": 5.29, "avg_lose": 11.48, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.4200; Y=1.0700; X=0.5600; cold_risk=8.6%; dev_level=一致"},
    {"handicap": -1, "jc_win": 5.2, "jc_draw": 3.9, "jc_lose": 1.47, "rq_win": 2.32, "rq_draw": 3.4, "rq_lose": 2.48, "avg_win": 4.58, "avg_draw": 3.41, "avg_lose": 1.8, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.2600; Y=1.6800; X=6.2500; cold_risk=20.5%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.46, "jc_draw": 4.1, "jc_lose": 5.0, "rq_win": 2.45, "rq_draw": 3.5, "rq_lose": 2.3, "avg_win": 1.55, "avg_draw": 4.1, "avg_lose": 5.05, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "2:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.3300; Y=1.1900; X=1.1300; cold_risk=18.2%; dev_level=一致"},
    {"handicap": 2, "jc_win": 1.15, "jc_draw": 6.0, "jc_lose": 10.7, "rq_win": 2.67, "rq_draw": 4.0, "rq_lose": 1.98, "avg_win": 1.33, "avg_draw": 5.03, "avg_lose": 8.72, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "5:3", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=5.5800; Y=1.0700; X=0.6900; cold_risk=10.8%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.4, "jc_draw": 3.05, "jc_lose": 2.6, "rq_win": 5.5, "rq_draw": 4.05, "rq_lose": 1.43, "avg_win": 2.35, "avg_draw": 3.15, "avg_lose": 2.85, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.7900; Y=1.4100; X=2.0000; cold_risk=27.8%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.77, "jc_draw": 3.65, "jc_lose": 3.45, "rq_win": 3.2, "rq_draw": 3.75, "rq_lose": 1.82, "avg_win": 2.03, "avg_draw": 3.67, "avg_lose": 3.32, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "1:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.6400; Y=1.2800; X=1.6000; cold_risk=17.1%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.35, "jc_draw": 4.3, "jc_lose": 6.4, "rq_win": 2.15, "rq_draw": 3.45, "rq_lose": 2.67, "avg_win": 1.43, "avg_draw": 4.35, "avg_lose": 6.7, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "同向共振", "match_context": "Z=3.6600; Y=1.1500; X=0.8900; cold_risk=13.8%; dev_level=一致"},
    {"handicap": -2, "jc_win": 12.5, "jc_draw": 5.8, "jc_lose": 1.14, "rq_win": 2.05, "rq_draw": 3.95, "rq_lose": 2.58, "avg_win": 8.66, "avg_draw": 4.87, "avg_lose": 4.02, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=0.8600; Y=1.8500; X=19.3700; cold_risk=26.1%; dev_level=极高偏离", "match_id": "#629"},
    {"handicap": 1, "jc_win": 1.52, "jc_draw": 3.9, "jc_lose": 4.65, "rq_win": 2.65, "rq_draw": 3.45, "rq_lose": 2.17, "avg_win": 1.79, "avg_draw": 3.71, "avg_lose": 4.05, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "1:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=3.1000; Y=1.2100; X=1.1800; cold_risk=14.0%; dev_level=轻微偏离", "match_id": "#630"},
    {"handicap": 1, "jc_win": 1.7, "jc_draw": 3.5, "jc_lose": 3.92, "rq_win": 3.2, "rq_draw": 3.45, "rq_lose": 1.9, "avg_win": 1.79, "avg_draw": 3.85, "avg_lose": 3.81, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.5900; Y=1.2600; X=1.3200; cold_risk=24.3%; dev_level=一致", "match_id": "#631"},
    {"handicap": -1, "jc_win": 3.8, "jc_draw": 3.9, "jc_lose": 1.64, "rq_win": 1.99, "rq_draw": 3.65, "rq_lose": 2.83, "avg_win": 7.67, "avg_draw": 5.33, "avg_lose": 1.34, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "冷门预警", "match_context": "Z=1.6200; Y=1.5800; X=5.0100; cold_risk=5.1%; dev_level=极高偏离", "match_id": "#632"},
    {"handicap": 1, "jc_win": 2.35, "jc_draw": 2.85, "jc_lose": 2.83, "rq_win": 5.85, "rq_draw": 3.65, "rq_lose": 1.46, "avg_win": 2.54, "avg_draw": 3.18, "avg_lose": 2.68, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.7000; Y=1.4000; X=1.7000; cold_risk=25.3%; dev_level=一致", "match_id": "#633"},
    {"handicap": -1, "jc_win": 6.8, "jc_draw": 4.45, "jc_lose": 1.32, "rq_win": 2.8, "rq_draw": 3.65, "rq_lose": 2.01, "avg_win": 5.32, "avg_draw": 4.1, "avg_lose": 1.53, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "2:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "同向共振", "match_context": "Z=1.1400; Y=1.7400; X=9.0100; cold_risk=17.3%; dev_level=轻微偏离", "match_id": "#634"},
    {"handicap": 1, "jc_win": 1.62, "jc_draw": 3.82, "jc_lose": 4.0, "rq_win": 2.78, "rq_draw": 3.65, "rq_lose": 2.02, "avg_win": 1.67, "avg_draw": 3.91, "avg_lose": 4.38, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "3:1", "engine_summary": "A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.9200; Y=1.2400; X=1.3800; cold_risk=21.1%; dev_level=一致", "match_id": "#635"},
    {"handicap": 1, "jc_win": 1.44, "jc_draw": 4.15, "jc_lose": 5.15, "rq_win": 2.3, "rq_draw": 3.6, "rq_lose": 2.4, "avg_win": 1.87, "avg_draw": 3.58, "avg_lose": 3.8, "shenjia": "主身 > 客身", "real_result": "平", "real_score": "2:2", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "正常", "match_context": "Z=3.4000; Y=1.1800; X=1.1000; cold_risk=24.4%; dev_level=显著偏离", "match_id": "#636"},
    {"handicap": 1, "jc_win": 1.93, "jc_draw": 3.35, "jc_lose": 3.2, "rq_win": 3.9, "rq_draw": 3.62, "rq_lose": 1.68, "avg_win": 2.18, "avg_draw": 3.39, "avg_lose": 3.05, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "正常", "match_context": "Z=2.2900; Y=1.3200; X=1.6400; cold_risk=12.4%; dev_level=一致"},
    {"handicap": -2, "jc_win": 12.5, "jc_draw": 5.8, "jc_lose": 1.14, "rq_win": 2.05, "rq_draw": 3.95, "rq_lose": 2.58, "avg_win": 8.66, "avg_draw": 4.87, "avg_lose": 4.02, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "1:4", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "正常", "match_context": "Z=0.8600; Y=1.8500; X=19.3700; cold_risk=26.1%; dev_level=极高偏离"},
    {"handicap": 1, "jc_win": 1.67, "jc_draw": 3.2, "jc_lose": 4.6, "rq_win": 3.3, "rq_draw": 3.25, "rq_lose": 1.93, "avg_win": 2.22, "avg_draw": 3.12, "avg_lose": 3.4, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "平局共振", "match_context": "Z=2.4000; Y=1.2500; X=1.0100; cold_risk=15.8%; dev_level=显著偏离"},
    {"handicap": 1, "jc_win": 2.59, "jc_draw": 2.8, "jc_lose": 2.59, "rq_win": 6.5, "rq_draw": 4.0, "rq_lose": 1.38, "avg_win": 2.6, "avg_draw": 2.94, "avg_lose": 2.56, "shenjia": "未输入", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=负", "resonance_type": "平局共振", "match_context": "Z=1.5600; Y=1.4400; X=1.8900; cold_risk=10.0%; dev_level=一致"},
    {"handicap": -1, "jc_win": 3.4, "jc_draw": 3.4, "jc_lose": 1.85, "rq_win": 1.75, "rq_draw": 3.5, "rq_lose": 3.7, "avg_win": 3.09, "avg_draw": 3.43, "avg_lose": 2.1, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "2:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.5500; Y=1.5500; X=3.6400; cold_risk=18.5%; dev_level=一致"},
    {"handicap": 1, "jc_win": 1.98, "jc_draw": 3.4, "jc_lose": 3.03, "rq_win": 4.05, "rq_draw": 3.75, "rq_lose": 1.63, "avg_win": 1.81, "avg_draw": 3.7, "avg_lose": 3.94, "shenjia": "主身 > 客身", "real_result": "负", "real_score": "0:2", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=2.2800; Y=1.3300; X=1.7800; cold_risk=13.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 1.41, "jc_draw": 4.2, "jc_lose": 5.5, "rq_win": 2.3, "rq_draw": 3.45, "rq_lose": 2.48, "avg_win": 1.84, "avg_draw": 3.72, "avg_lose": 3.76, "shenjia": "主身 > 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜", "resonance_type": "正常", "match_context": "Z=3.4900; Y=1.1700; X=1.0300; cold_risk=24.7%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 3.7, "jc_draw": 3.8, "jc_lose": 1.68, "rq_win": 1.94, "rq_draw": 3.5, "rq_lose": 3.05, "avg_win": 2.68, "avg_draw": 3.43, "avg_lose": 2.42, "shenjia": "主身 < 客身", "real_result": "平", "real_score": "0:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "冷门预警", "match_context": "Z=1.6200; Y=1.5700; X=4.6900; cold_risk=22.1%; dev_level=显著偏离"},
    {"handicap": -1, "jc_win": 4.2, "jc_draw": 3.5, "jc_lose": 1.65, "rq_win": 1.95, "rq_draw": 3.35, "rq_lose": 3.15, "avg_win": 3.34, "avg_draw": 3.4, "avg_lose": 2.07, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "1:0", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负", "resonance_type": "反向背离", "match_context": "Z=1.3500; Y=1.6200; X=4.5600; cold_risk=27.8%; dev_level=轻微偏离"},
    {"handicap": -1, "jc_win": 2.55, "jc_draw": 3.05, "jc_lose": 2.45, "rq_win": 1.41, "rq_draw": 4.1, "rq_lose": 5.75, "avg_win": 2.14, "avg_draw": 3.14, "avg_lose": 3.5, "shenjia": "主身 < 客身", "real_result": "负", "real_score": "0:1", "engine_summary": "A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=负|F-概率区间映射引擎=胜", "resonance_type": "反向背离", "match_context": "Z=1.7200; Y=1.4400; X=2.1800; cold_risk=33.6%; dev_level=轻微偏离"},
    {"handicap": 1, "jc_win": 2.15, "jc_draw": 3.3, "jc_lose": 2.77, "rq_win": 4.55, "rq_draw": 4.0, "rq_lose": 1.52, "avg_win": 2.57, "avg_draw": 3.46, "avg_lose": 2.56, "shenjia": "主身 < 客身", "real_result": "胜", "real_score": "4:1", "engine_summary": "A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平", "resonance_type": "同向共振", "match_context": "Z=2.1000; Y=1.3700; X=1.9500; cold_risk=6.4%; dev_level=一致"},
    {'handicap': 2, 'jc_win': 1.22, 'jc_draw': 5.3, 'jc_lose': 8.3, 'rq_win': 3.1, 'rq_draw': 4.08, 'rq_lose': 1.78, 'avg_win': 1.16, 'avg_draw': 6.33, 'avg_lose': 11.99, 'shenjia': '未输入', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=4.7700; Y=1.1000; X=0.8000; cold_risk=3.2%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 6.0, 'jc_draw': 4.62, 'jc_lose': 1.34, 'rq_win': 2.73, 'rq_draw': 3.55, 'rq_lose': 2.08, 'avg_win': 5.18, 'avg_draw': 3.96, 'avg_lose': 1.58, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.3200; Y=1.7100; X=8.9200; cold_risk=17.9%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.55, 'jc_draw': 3.3, 'jc_lose': 5.52, 'rq_win': 2.9, 'rq_draw': 3.2, 'rq_lose': 2.12, 'avg_win': 1.75, 'avg_draw': 3.49, 'avg_lose': 4.81, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.5900; Y=1.2200; X=0.8400; cold_risk=19.5%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.26, 'jc_draw': 4.95, 'jc_lose': 7.55, 'rq_win': 1.92, 'rq_draw': 3.5, 'rq_lose': 3.1, 'avg_win': 1.39, 'avg_draw': 4.63, 'avg_lose': 7.07, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '4:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.3800; Y=1.1200; X=0.8400; cold_risk=13.1%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.57, 'jc_draw': 3.42, 'jc_lose': 2.23, 'rq_win': 1.51, 'rq_draw': 4.05, 'rq_lose': 4.55, 'avg_win': 2.22, 'avg_draw': 3.48, 'avg_lose': 2.91, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.9200; Y=1.4400; X=2.7300; cold_risk=30.5%; dev_level=轻微偏离'},
    {'handicap': 2, 'jc_win': 1.13, 'jc_draw': 6.0, 'jc_lose': 13.0, 'rq_win': 2.57, 'rq_draw': 3.78, 'rq_lose': 2.1, 'avg_win': 1.39, 'avg_draw': 4.63, 'avg_lose': 7.05, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '5:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=5.6300; Y=1.0600; X=0.5600; cold_risk=13.2%; dev_level=显著偏离'},
    {'handicap': 1, 'jc_win': 1.74, 'jc_draw': 3.7, 'jc_lose': 3.52, 'rq_win': 3.15, 'rq_draw': 3.65, 'rq_lose': 1.86, 'avg_win': 2.36, 'avg_draw': 3.33, 'avg_lose': 2.81, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '4:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=2.7000; Y=1.2700; X=1.5800; cold_risk=5.9%; dev_level=显著偏离'},
    {'handicap': 1, 'jc_win': 1.35, 'jc_draw': 4.32, 'jc_lose': 6.35, 'rq_win': 2.17, 'rq_draw': 3.43, 'rq_lose': 2.65, 'avg_win': 1.73, 'avg_draw': 3.84, 'avg_lose': 4.17, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=3.6800; Y=1.1500; X=0.9000; cold_risk=22.2%; dev_level=显著偏离'},
    {'handicap': -1, 'jc_win': 3.45, 'jc_draw': 3.6, 'jc_lose': 1.78, 'rq_win': 1.8, 'rq_draw': 3.75, 'rq_lose': 3.25, 'avg_win': 3.56, 'avg_draw': 3.57, 'avg_lose': 1.98, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6200; Y=1.5500; X=4.0600; cold_risk=15.2%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.25, 'jc_draw': 4.77, 'jc_lose': 8.35, 'rq_win': 1.9, 'rq_draw': 3.5, 'rq_lose': 3.15, 'avg_win': 1.33, 'avg_draw': 5.25, 'avg_lose': 7.78, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.2400; Y=1.1100; X=0.7300; cold_risk=12.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.45, 'jc_draw': 3.85, 'jc_lose': 5.55, 'rq_win': 2.45, 'rq_draw': 3.4, 'rq_lose': 2.34, 'avg_win': 1.35, 'avg_draw': 4.25, 'avg_lose': 7.42, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.1400; Y=1.1800; X=0.9500; cold_risk=12.1%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 3.8, 'jc_draw': 3.8, 'jc_lose': 1.67, 'rq_win': 1.92, 'rq_draw': 3.65, 'rq_lose': 2.99, 'avg_win': 3.03, 'avg_draw': 3.69, 'avg_lose': 2.02, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.5800; Y=1.5800; X=4.7300; cold_risk=17.6%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.5, 'jc_draw': 4.13, 'jc_lose': 4.53, 'rq_win': 2.45, 'rq_draw': 3.61, 'rq_lose': 2.25, 'avg_win': 1.56, 'avg_draw': 4.21, 'avg_lose': 5.05, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '5:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.3000; Y=1.2000; X=1.2800; cold_risk=18.4%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.43, 'jc_draw': 4.35, 'jc_lose': 5.0, 'rq_win': 2.3, 'rq_draw': 3.65, 'rq_lose': 2.38, 'avg_win': 1.6, 'avg_draw': 4.16, 'avg_lose': 4.58, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '1:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.5800; Y=1.1800; X=1.1900; cold_risk=20.1%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.71, 'jc_draw': 3.5, 'jc_lose': 3.9, 'rq_win': 3.2, 'rq_draw': 3.5, 'rq_lose': 1.89, 'avg_win': 1.72, 'avg_draw': 3.78, 'avg_lose': 4.12, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.5800; Y=1.2600; X=1.3300; cold_risk=22.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.44, 'jc_draw': 4.3, 'jc_lose': 4.95, 'rq_win': 2.3, 'rq_draw': 3.75, 'rq_lose': 2.34, 'avg_win': 1.62, 'avg_draw': 4.15, 'avg_lose': 4.46, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.5200; Y=1.1800; X=1.1900; cold_risk=20.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.62, 'jc_draw': 4.25, 'jc_lose': 3.62, 'rq_win': 2.65, 'rq_draw': 3.9, 'rq_lose': 2.02, 'avg_win': 1.63, 'avg_draw': 4.17, 'avg_lose': 4.26, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=3.2400; Y=1.2400; X=1.7100; cold_risk=12.0%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.67, 'jc_draw': 3.22, 'jc_lose': 2.25, 'rq_win': 1.47, 'rq_draw': 3.95, 'rq_lose': 5.1, 'avg_win': 2.97, 'avg_draw': 3.34, 'avg_lose': 2.33, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.7500; Y=1.4600; X=2.5700; cold_risk=21.6%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.98, 'jc_draw': 3.5, 'jc_lose': 2.95, 'rq_win': 3.75, 'rq_draw': 3.95, 'rq_lose': 1.64, 'avg_win': 2.28, 'avg_draw': 3.66, 'avg_lose': 2.81, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=2.3500; Y=1.3300; X=1.8900; cold_risk=22.2%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.65, 'jc_draw': 3.58, 'jc_lose': 2.12, 'rq_win': 1.54, 'rq_draw': 4.05, 'rq_lose': 4.28, 'avg_win': 2.57, 'avg_draw': 3.59, 'avg_lose': 2.52, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.9600; Y=1.4500; X=3.0500; cold_risk=25.4%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.74, 'jc_draw': 3.46, 'jc_lose': 3.76, 'rq_win': 3.25, 'rq_draw': 3.55, 'rq_lose': 1.85, 'avg_win': 2.01, 'avg_draw': 3.5, 'avg_lose': 3.38, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.5300; Y=1.2700; X=1.3800; cold_risk=12.2%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.65, 'jc_draw': 3.5, 'jc_lose': 4.2, 'rq_win': 3.05, 'rq_draw': 3.48, 'rq_lose': 1.95, 'avg_win': 2.07, 'avg_draw': 3.16, 'avg_lose': 3.75, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '1:3', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.6400; Y=1.2500; X=1.2100; cold_risk=25.0%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 3.25, 'jc_draw': 3.4, 'jc_lose': 1.9, 'rq_win': 1.69, 'rq_draw': 3.6, 'rq_lose': 3.85, 'avg_win': 3.5, 'avg_draw': 3.53, 'avg_lose': 1.93, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '正常', 'match_context': 'Z=1.6000; Y=1.5300; X=3.4800; cold_risk=14.3%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.15, 'jc_draw': 3.45, 'jc_lose': 1.92, 'rq_win': 1.69, 'rq_draw': 3.75, 'rq_lose': 3.7, 'avg_win': 3.07, 'avg_draw': 3.36, 'avg_lose': 2.07, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '正常', 'match_context': 'Z=1.6600; Y=1.5200; X=3.4600; cold_risk=10.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.88, 'jc_draw': 3.35, 'jc_lose': 3.35, 'rq_win': 3.8, 'rq_draw': 3.55, 'rq_lose': 1.71, 'avg_win': 1.95, 'avg_draw': 3.59, 'avg_lose': 3.4, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.3300; Y=1.3100; X=1.5500; cold_risk=17.1%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.36, 'jc_draw': 3.4, 'jc_lose': 1.86, 'rq_win': 1.72, 'rq_draw': 3.65, 'rq_lose': 3.65, 'avg_win': 3.36, 'avg_draw': 3.5, 'avg_lose': 1.94, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.5600; Y=1.5400; X=3.6100; cold_risk=16.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.82, 'jc_draw': 3.45, 'jc_lose': 3.45, 'rq_win': 3.5, 'rq_draw': 3.6, 'rq_lose': 1.77, 'avg_win': 2.37, 'avg_draw': 3.39, 'avg_lose': 2.88, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '2:3', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.4500; Y=1.2900; X=1.5300; cold_risk=21.5%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 2.3, 'jc_draw': 3.15, 'jc_lose': 2.65, 'rq_win': 4.95, 'rq_draw': 4.05, 'rq_lose': 1.47, 'avg_win': 2.71, 'avg_draw': 3.41, 'avg_lose': 2.41, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.9100; Y=1.3900; X=2.0000; cold_risk=14.3%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 2.06, 'jc_draw': 3.2, 'jc_lose': 3.02, 'rq_win': 4.38, 'rq_draw': 3.75, 'rq_lose': 1.58, 'avg_win': 2.05, 'avg_draw': 3.25, 'avg_lose': 3.68, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=2.0900; Y=1.3500; X=1.7000; cold_risk=15.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.12, 'jc_draw': 3.0, 'jc_lose': 3.08, 'rq_win': 4.85, 'rq_draw': 3.65, 'rq_lose': 1.54, 'avg_win': 2.02, 'avg_draw': 3.23, 'avg_lose': 3.81, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.9200; Y=1.3600; X=1.5800; cold_risk=14.6%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.76, 'jc_draw': 3.3, 'jc_lose': 3.88, 'rq_win': 3.6, 'rq_draw': 3.4, 'rq_lose': 1.8, 'avg_win': 2.03, 'avg_draw': 3.31, 'avg_lose': 3.67, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.3900; Y=1.2800; X=1.2700; cold_risk=25.5%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.4, 'jc_draw': 3.55, 'jc_lose': 1.81, 'rq_win': 1.75, 'rq_draw': 3.7, 'rq_lose': 3.48, 'avg_win': 3.12, 'avg_draw': 3.59, 'avg_lose': 2.07, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6100; Y=1.5500; X=3.9000; cold_risk=18.5%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.28, 'jc_draw': 3.58, 'jc_lose': 2.43, 'rq_win': 4.71, 'rq_draw': 4.3, 'rq_lose': 1.46, 'avg_win': 2.17, 'avg_draw': 3.65, 'avg_lose': 3.03, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '2:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.1800; Y=1.3900; X=2.5000; cold_risk=12.8%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 2.39, 'jc_draw': 3.43, 'jc_lose': 2.39, 'rq_win': 5.05, 'rq_draw': 4.3, 'rq_lose': 1.43, 'avg_win': 2.52, 'avg_draw': 3.64, 'avg_lose': 2.55, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.0200; Y=1.4100; X=2.4700; cold_risk=16.9%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.6, 'jc_draw': 3.55, 'jc_lose': 2.16, 'rq_win': 1.53, 'rq_draw': 4.15, 'rq_lose': 4.25, 'avg_win': 2.51, 'avg_draw': 3.7, 'avg_lose': 2.52, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '3:4', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.9700; Y=1.4400; X=2.9500; cold_risk=26.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.08, 'jc_draw': 3.65, 'jc_lose': 2.67, 'rq_win': 4.1, 'rq_draw': 4.1, 'rq_lose': 1.56, 'avg_win': 2.15, 'avg_draw': 3.74, 'avg_lose': 3.0, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=2.3700; Y=1.3500; X=2.2300; cold_risk=11.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.7, 'jc_draw': 3.52, 'jc_lose': 3.9, 'rq_win': 3.12, 'rq_draw': 3.55, 'rq_lose': 1.9, 'avg_win': 1.67, 'avg_draw': 3.83, 'avg_lose': 4.93, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.6100; Y=1.2600; X=1.3300; cold_risk=19.1%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.41, 'jc_draw': 4.15, 'jc_lose': 5.6, 'rq_win': 2.3, 'rq_draw': 3.5, 'rq_lose': 2.45, 'avg_win': 1.4, 'avg_draw': 5.01, 'avg_lose': 6.66, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.4400; Y=1.1700; X=1.0000; cold_risk=14.1%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 5.05, 'jc_draw': 4.5, 'jc_lose': 1.41, 'rq_win': 2.47, 'rq_draw': 3.7, 'rq_lose': 2.2, 'avg_win': 4.06, 'avg_draw': 3.92, 'avg_lose': 1.73, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:3', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.4900; Y=1.6700; X=7.7000; cold_risk=22.8%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.48, 'jc_draw': 3.75, 'jc_lose': 5.35, 'rq_win': 2.6, 'rq_draw': 3.35, 'rq_lose': 2.25, 'avg_win': 1.75, 'avg_draw': 3.52, 'avg_lose': 4.73, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.0200; Y=1.1900; X=0.9700; cold_risk=19.8%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.79, 'jc_draw': 3.6, 'jc_lose': 3.42, 'rq_win': 3.25, 'rq_draw': 3.8, 'rq_lose': 1.79, 'avg_win': 2.24, 'avg_draw': 3.49, 'avg_lose': 3.01, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=2.5800; Y=1.2800; X=1.6000; cold_risk=8.6%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 2.42, 'jc_draw': 3.3, 'jc_lose': 2.42, 'rq_win': 5.35, 'rq_draw': 4.2, 'rq_lose': 1.42, 'avg_win': 2.4, 'avg_draw': 3.41, 'avg_lose': 2.79, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '2:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=1.9300; Y=1.4200; X=2.3600; cold_risk=29.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.6, 'jc_draw': 3.55, 'jc_lose': 4.5, 'rq_win': 2.88, 'rq_draw': 3.4, 'rq_lose': 2.05, 'avg_win': 1.75, 'avg_draw': 3.72, 'avg_lose': 4.44, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.7300; Y=1.2300; X=1.1300; cold_risk=21.1%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.64, 'jc_draw': 3.75, 'jc_lose': 3.95, 'rq_win': 2.9, 'rq_draw': 3.65, 'rq_lose': 1.96, 'avg_win': 1.78, 'avg_draw': 3.64, 'avg_lose': 4.27, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '5:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.8400; Y=1.2400; X=1.3800; cold_risk=21.9%; dev_level=一致'},
    {'handicap': 2, 'jc_win': 1.33, 'jc_draw': 5.12, 'jc_lose': 7.23, 'rq_win': 2.32, 'rq_draw': 4.2, 'rq_lose': 2.18, 'avg_win': 1.36, 'avg_draw': 5.0, 'avg_lose': 7.0, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '2:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.3900; Y=1.1400; X=0.8900; cold_risk=13.3%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.15, 'jc_draw': 3.4, 'jc_lose': 1.93, 'rq_win': 1.68, 'rq_draw': 3.65, 'rq_lose': 3.85, 'avg_win': 2.38, 'avg_draw': 3.32, 'avg_lose': 2.89, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6400; Y=1.5200; X=3.3900; cold_risk=6.0%; dev_level=显著偏离'},
    {'handicap': 1, 'jc_win': 1.96, 'jc_draw': 3.3, 'jc_lose': 3.16, 'rq_win': 3.9, 'rq_draw': 3.75, 'rq_lose': 1.65, 'avg_win': 1.98, 'avg_draw': 3.31, 'avg_lose': 3.85, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.2300; Y=1.3200; X=1.6500; cold_risk=14.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.03, 'jc_draw': 3.55, 'jc_lose': 2.82, 'rq_win': 3.88, 'rq_draw': 4.05, 'rq_lose': 1.6, 'avg_win': 1.92, 'avg_draw': 3.85, 'avg_lose': 3.51, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '4:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=2.3400; Y=1.3400; X=2.0200; cold_risk=6.7%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.91, 'jc_draw': 3.3, 'jc_lose': 3.3, 'rq_win': 3.8, 'rq_draw': 3.6, 'rq_lose': 1.7, 'avg_win': 2.23, 'avg_draw': 3.29, 'avg_lose': 3.03, 'shenjia': '未输入', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.2700; Y=1.3100; X=1.5600; cold_risk=8.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.07, 'jc_draw': 3.1, 'jc_lose': 3.1, 'rq_win': 4.5, 'rq_draw': 3.6, 'rq_lose': 1.59, 'avg_win': 1.68, 'avg_draw': 3.43, 'avg_lose': 4.53, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=2.0200; Y=1.3500; X=1.6000; cold_risk=23.7%; dev_level=显著偏离'},
    {'handicap': 1, 'jc_win': 2.28, 'jc_draw': 3.2, 'jc_lose': 2.65, 'rq_win': 5.2, 'rq_draw': 3.9, 'rq_lose': 1.47, 'avg_win': 2.47, 'avg_draw': 3.27, 'avg_lose': 2.65, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '2:4', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.9500; Y=1.3900; X=2.0300; cold_risk=16.5%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.05, 'jc_draw': 3.25, 'jc_lose': 2.03, 'rq_win': 1.6, 'rq_draw': 3.65, 'rq_lose': 4.35, 'avg_win': 3.31, 'avg_draw': 3.28, 'avg_lose': 2.08, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6000; Y=1.5100; X=3.0200; cold_risk=17.8%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.92, 'jc_draw': 3.62, 'jc_lose': 1.96, 'rq_win': 1.66, 'rq_draw': 4.05, 'rq_lose': 3.58, 'avg_win': 3.06, 'avg_draw': 3.72, 'avg_lose': 2.12, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.8500; Y=1.4900; X=3.4800; cold_risk=18.1%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.3, 'jc_draw': 3.5, 'jc_lose': 1.85, 'rq_win': 1.73, 'rq_draw': 3.65, 'rq_lose': 3.6, 'avg_win': 2.69, 'avg_draw': 3.24, 'avg_lose': 2.6, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '冷门预警', 'match_context': 'Z=1.6300; Y=1.5300; X=3.7200; cold_risk=23.8%; dev_level=显著偏离'},
    {'handicap': -1, 'jc_win': 3.37, 'jc_draw': 3.65, 'jc_lose': 1.79, 'rq_win': 1.8, 'rq_draw': 3.75, 'rq_lose': 3.25, 'avg_win': 3.57, 'avg_draw': 3.8, 'avg_lose': 1.9, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6700; Y=1.5400; X=4.0700; cold_risk=15.1%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.82, 'jc_draw': 3.12, 'jc_lose': 2.2, 'rq_win': 1.51, 'rq_draw': 3.85, 'rq_lose': 4.85, 'avg_win': 2.67, 'avg_draw': 3.23, 'avg_lose': 2.43, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.6300; Y=1.4800; X=2.5900; cold_risk=24.2%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.02, 'jc_draw': 3.2, 'jc_lose': 2.06, 'rq_win': 1.57, 'rq_draw': 3.7, 'rq_lose': 4.5, 'avg_win': 3.09, 'avg_draw': 3.29, 'avg_lose': 2.27, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.5900; Y=1.5000; X=2.9200; cold_risk=19.2%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.72, 'jc_draw': 3.4, 'jc_lose': 3.95, 'rq_win': 3.2, 'rq_draw': 3.55, 'rq_lose': 1.87, 'avg_win': 1.76, 'avg_draw': 3.68, 'avg_lose': 4.21, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.5000; Y=1.2600; X=1.2800; cold_risk=22.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.95, 'jc_draw': 2.8, 'jc_lose': 3.85, 'rq_win': 4.45, 'rq_draw': 3.35, 'rq_lose': 1.65, 'avg_win': 1.97, 'avg_draw': 3.07, 'avg_lose': 4.3, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=1.9000; Y=1.3200; X=1.1300; cold_risk=21.8%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.61, 'jc_draw': 3.95, 'jc_lose': 2.03, 'rq_win': 1.59, 'rq_draw': 4.5, 'rq_lose': 3.6, 'avg_win': 2.72, 'avg_draw': 4.0, 'avg_lose': 2.16, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=2.1900; Y=1.4500; X=3.5300; cold_risk=11.8%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.69, 'jc_draw': 3.5, 'jc_lose': 3.98, 'rq_win': 3.05, 'rq_draw': 3.6, 'rq_lose': 1.91, 'avg_win': 2.15, 'avg_draw': 3.43, 'avg_lose': 3.12, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.6000; Y=1.2600; X=1.2900; cold_risk=12.8%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.19, 'jc_draw': 5.45, 'jc_lose': 9.5, 'rq_win': 1.7, 'rq_draw': 3.75, 'rq_lose': 3.65, 'avg_win': 1.24, 'avg_draw': 6.0, 'avg_lose': 10.88, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '5:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.9800; Y=1.0900; X=0.7100; cold_risk=8.6%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.05, 'jc_draw': 2.8, 'jc_lose': 2.25, 'rq_win': 1.48, 'rq_draw': 3.6, 'rq_lose': 5.7, 'avg_win': 2.78, 'avg_draw': 2.97, 'avg_lose': 2.7, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=平|D-结构形态引擎=负|E-动态临界引擎=平|F-概率区间映射引擎=负', 'resonance_type': '平局共振', 'match_context': 'Z=1.3800; Y=1.5100; X=2.3100; cold_risk=4.7%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 5.2, 'jc_draw': 4.3, 'jc_lose': 1.42, 'rq_win': 2.45, 'rq_draw': 3.65, 'rq_lose': 2.24, 'avg_win': 4.95, 'avg_draw': 4.06, 'avg_lose': 1.62, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.3900; Y=1.6800; X=7.3000; cold_risk=19.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.95, 'jc_draw': 3.95, 'jc_lose': 2.75, 'rq_win': 3.6, 'rq_draw': 4.15, 'rq_lose': 1.64, 'avg_win': 1.77, 'avg_draw': 4.14, 'avg_lose': 3.87, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '正常', 'match_context': 'Z=2.6800; Y=1.3200; X=2.2900; cold_risk=19.7%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.55, 'jc_draw': 3.7, 'jc_lose': 4.7, 'rq_win': 2.8, 'rq_draw': 3.4, 'rq_lose': 2.09, 'avg_win': 1.73, 'avg_draw': 3.74, 'avg_lose': 4.52, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.9000; Y=1.2200; X=1.1100; cold_risk=20.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.41, 'jc_draw': 4.4, 'jc_lose': 5.18, 'rq_win': 2.22, 'rq_draw': 3.7, 'rq_lose': 2.45, 'avg_win': 1.63, 'avg_draw': 3.96, 'avg_lose': 4.93, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.6500; Y=1.1700; X=1.1500; cold_risk=19.0%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 4.1, 'jc_draw': 4.1, 'jc_lose': 1.56, 'rq_win': 2.12, 'rq_draw': 3.7, 'rq_lose': 2.58, 'avg_win': 4.4, 'avg_draw': 4.41, 'avg_lose': 1.65, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '正常', 'match_context': 'Z=1.6100; Y=1.6100; X=5.7400; cold_risk=10.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.19, 'jc_draw': 5.3, 'jc_lose': 10.0, 'rq_win': 1.7, 'rq_draw': 3.7, 'rq_lose': 3.7, 'avg_win': 1.29, 'avg_draw': 5.14, 'avg_lose': 10.54, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.8400; Y=1.0900; X=0.6600; cold_risk=9.2%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 5.55, 'jc_draw': 4.8, 'jc_lose': 1.35, 'rq_win': 2.64, 'rq_draw': 3.9, 'rq_lose': 2.03, 'avg_win': 4.43, 'avg_draw': 4.15, 'avg_lose': 1.67, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.4700; Y=1.6900; X=9.0300; cold_risk=21.2%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 2.65, 'jc_draw': 3.25, 'jc_lose': 2.26, 'rq_win': 1.48, 'rq_draw': 4.0, 'rq_lose': 4.9, 'avg_win': 2.63, 'avg_draw': 3.4, 'avg_lose': 2.55, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '2:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.7800; Y=1.4500; X=2.5700; cold_risk=25.7%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.62, 'jc_draw': 3.16, 'jc_lose': 2.32, 'rq_win': 1.46, 'rq_draw': 3.9, 'rq_lose': 5.35, 'avg_win': 2.94, 'avg_draw': 3.38, 'avg_lose': 2.3, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.7500; Y=1.4500; X=2.4200; cold_risk=20.6%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.34, 'jc_draw': 4.9, 'jc_lose': 5.6, 'rq_win': 1.97, 'rq_draw': 3.9, 'rq_lose': 2.74, 'avg_win': 1.48, 'avg_draw': 4.63, 'avg_lose': 5.44, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.1900; Y=1.1500; X=1.1600; cold_risk=9.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.27, 'jc_draw': 4.55, 'jc_lose': 8.2, 'rq_win': 1.94, 'rq_draw': 3.5, 'rq_lose': 3.05, 'avg_win': 1.31, 'avg_draw': 4.28, 'avg_lose': 9.02, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.0100; Y=1.1200; X=0.7100; cold_risk=12.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.27, 'jc_draw': 4.55, 'jc_lose': 8.2, 'rq_win': 1.94, 'rq_draw': 3.5, 'rq_lose': 3.05, 'avg_win': 1.31, 'avg_draw': 4.28, 'avg_lose': 9.02, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.0100; Y=1.1200; X=0.7100; cold_risk=12.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.44, 'jc_draw': 4.3, 'jc_lose': 4.95, 'rq_win': 2.28, 'rq_draw': 3.7, 'rq_lose': 2.38, 'avg_win': 1.62, 'avg_draw': 4.19, 'avg_lose': 4.11, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '4:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.5200; Y=1.1800; X=1.1900; cold_risk=22.1%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 2.08, 'jc_draw': 3.45, 'jc_lose': 2.79, 'rq_win': 4.2, 'rq_draw': 3.88, 'rq_lose': 1.58, 'avg_win': 2.06, 'avg_draw': 3.55, 'avg_lose': 3.0, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '正常', 'match_context': 'Z=2.2400; Y=1.3500; X=2.0100; cold_risk=16.8%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.05, 'jc_draw': 3.55, 'jc_lose': 2.78, 'rq_win': 4.05, 'rq_draw': 3.95, 'rq_lose': 1.59, 'avg_win': 2.31, 'avg_draw': 3.33, 'avg_lose': 2.73, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '正常', 'match_context': 'Z=2.3300; Y=1.3400; X=2.0600; cold_risk=9.4%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.02, 'jc_draw': 2.9, 'jc_lose': 3.45, 'rq_win': 4.5, 'rq_draw': 3.45, 'rq_lose': 1.62, 'avg_win': 2.11, 'avg_draw': 3.03, 'avg_lose': 3.24, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=1.9200; Y=1.3400; X=1.3300; cold_risk=27.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.89, 'jc_draw': 3.15, 'jc_lose': 3.53, 'rq_win': 3.88, 'rq_draw': 3.45, 'rq_lose': 1.72, 'avg_win': 2.02, 'avg_draw': 3.34, 'avg_lose': 3.44, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.1800; Y=1.3100; X=1.3800; cold_risk=8.1%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.08, 'jc_draw': 2.94, 'jc_lose': 3.25, 'rq_win': 4.75, 'rq_draw': 3.5, 'rq_lose': 1.58, 'avg_win': 2.67, 'avg_draw': 3.28, 'avg_lose': 2.73, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '正常', 'match_context': 'Z=1.9100; Y=1.3500; X=1.4500; cold_risk=10.8%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 2.38, 'jc_draw': 2.92, 'jc_lose': 2.73, 'rq_win': 5.5, 'rq_draw': 3.95, 'rq_lose': 1.44, 'avg_win': 2.79, 'avg_draw': 3.07, 'avg_lose': 2.54, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.7300; Y=1.4100; X=1.8100; cold_risk=25.4%; dev_level=一致'},
    {'handicap': 2, 'jc_win': 1.13, 'jc_draw': 6.1, 'jc_lose': 12.5, 'rq_win': 2.45, 'rq_draw': 3.88, 'rq_lose': 2.16, 'avg_win': 1.24, 'avg_draw': 5.68, 'avg_lose': 11.03, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=5.7300; Y=1.0600; X=0.5900; cold_risk=8.4%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.23, 'jc_draw': 3.56, 'jc_lose': 2.5, 'rq_win': 4.35, 'rq_draw': 4.22, 'rq_lose': 1.51, 'avg_win': 2.27, 'avg_draw': 3.71, 'avg_lose': 2.78, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=2.2000; Y=1.3800; X=2.3900; cold_risk=13.9%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.36, 'jc_draw': 3.03, 'jc_lose': 2.66, 'rq_win': 5.4, 'rq_draw': 4.0, 'rq_lose': 1.44, 'avg_win': 2.56, 'avg_draw': 3.26, 'avg_lose': 2.7, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.8000; Y=1.4000; X=1.9300; cold_risk=25.5%; dev_level=一致'},
        {'handicap': 1, 'jc_win': 1.73, 'jc_draw': 3.58, 'jc_lose': 3.67, 'rq_win': 3.22, 'rq_draw': 3.65, 'rq_lose': 1.84, 'avg_win': 1.9, 'avg_draw': 3.58, 'avg_lose': 3.79, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.6200; Y=1.2700; X=1.4600; cold_risk=24.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.73, 'jc_draw': 3.58, 'jc_lose': 3.67, 'rq_win': 3.22, 'rq_draw': 3.65, 'rq_lose': 1.84, 'avg_win': 1.9, 'avg_draw': 3.58, 'avg_lose': 3.79, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.6200; Y=1.2700; X=1.4600; cold_risk=24.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.8, 'jc_draw': 3.0, 'jc_lose': 4.15, 'rq_win': 3.8, 'rq_draw': 3.25, 'rq_lose': 1.79, 'avg_win': 2.03, 'avg_draw': 3.13, 'avg_lose': 3.3, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.1400; Y=1.2900; X=1.0900; cold_risk=27.2%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 3.3, 'jc_draw': 3.3, 'jc_lose': 1.91, 'rq_win': 1.69, 'rq_draw': 3.65, 'rq_lose': 3.8, 'avg_win': 3.25, 'avg_draw': 3.27, 'avg_lose': 2.05, 'shenjia': '未输入', 'real_result': '负', 'real_score': '0:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.5300; Y=1.5300; X=3.3700; cold_risk=5.7%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.56, 'jc_draw': 3.44, 'jc_lose': 2.23, 'rq_win': 1.49, 'rq_draw': 4.1, 'rq_lose': 4.66, 'avg_win': 2.59, 'avg_draw': 3.41, 'avg_lose': 2.36, 'shenjia': '未输入', 'real_result': '平', 'real_score': '3:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.9300; Y=1.4400; X=2.7400; cold_risk=10.0%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.35, 'jc_draw': 2.94, 'jc_lose': 2.75, 'rq_win': 5.45, 'rq_draw': 3.9, 'rq_lose': 1.45, 'avg_win': 2.4, 'avg_draw': 3.0, 'avg_lose': 2.84, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '2:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.7600; Y=1.4000; X=1.8000; cold_risk=26.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.51, 'jc_draw': 3.85, 'jc_lose': 4.81, 'rq_win': 2.6, 'rq_draw': 3.45, 'rq_lose': 2.2, 'avg_win': 1.51, 'avg_draw': 4.01, 'avg_lose': 5.25, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '5:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.0700; Y=1.2000; X=1.1200; cold_risk=11.5%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.45, 'jc_draw': 2.9, 'jc_lose': 2.66, 'rq_win': 6.1, 'rq_draw': 3.9, 'rq_lose': 1.41, 'avg_win': 2.67, 'avg_draw': 3.01, 'avg_lose': 2.53, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6800; Y=1.4200; X=1.8700; cold_risk=22.9%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.25, 'jc_draw': 4.8, 'jc_lose': 8.3, 'rq_win': 1.89, 'rq_draw': 3.55, 'rq_lose': 3.15, 'avg_win': 1.41, 'avg_draw': 4.07, 'avg_lose': 6.06, 'shenjia': '未输入', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.2700; Y=1.1100; X=0.7400; cold_risk=11.9%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 2.25, 'jc_draw': 3.0, 'jc_lose': 2.85, 'rq_win': 5.1, 'rq_draw': 3.85, 'rq_lose': 1.49, 'avg_win': 2.67, 'avg_draw': 3.1, 'avg_lose': 2.59, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.8500; Y=1.3800; X=1.7500; cold_risk=14.6%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.42, 'jc_draw': 4.55, 'jc_lose': 4.88, 'rq_win': 2.22, 'rq_draw': 3.72, 'rq_lose': 2.44, 'avg_win': 1.53, 'avg_draw': 4.38, 'avg_lose': 4.76, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.7600; Y=1.1700; X=1.2700; cold_risk=19.2%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.1, 'jc_draw': 2.9, 'jc_lose': 3.25, 'rq_win': 4.75, 'rq_draw': 3.6, 'rq_lose': 1.56, 'avg_win': 2.45, 'avg_draw': 3.02, 'avg_lose': 2.92, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=1.8700; Y=1.3500; X=1.4300; cold_risk=12.7%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 6.65, 'jc_draw': 4.2, 'jc_lose': 1.35, 'rq_win': 2.7, 'rq_draw': 3.4, 'rq_lose': 2.15, 'avg_win': 7.36, 'avg_draw': 4.6, 'avg_lose': 1.4, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:3', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.1000; Y=1.7400; X=8.1000; cold_risk=12.7%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.7, 'jc_draw': 3.2, 'jc_lose': 2.25, 'rq_win': 1.49, 'rq_draw': 4.0, 'rq_lose': 4.8, 'avg_win': 2.72, 'avg_draw': 3.3, 'avg_lose': 2.49, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '2:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.7300; Y=1.4600; X=2.5500; cold_risk=17.5%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.46, 'jc_draw': 3.83, 'jc_lose': 5.45, 'rq_win': 2.5, 'rq_draw': 3.3, 'rq_lose': 2.35, 'avg_win': 1.38, 'avg_draw': 4.39, 'avg_lose': 7.15, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '4:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.1100; Y=1.1900; X=0.9700; cold_risk=12.8%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.68, 'jc_draw': 3.42, 'jc_lose': 4.15, 'rq_win': 3.15, 'rq_draw': 3.38, 'rq_lose': 1.94, 'avg_win': 1.71, 'avg_draw': 3.5, 'avg_lose': 4.5, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.5500; Y=1.2500; X=1.2100; cold_risk=20.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.43, 'jc_draw': 4.6, 'jc_lose': 4.7, 'rq_win': 2.19, 'rq_draw': 3.85, 'rq_lose': 2.42, 'avg_win': 1.48, 'avg_draw': 4.67, 'avg_lose': 5.14, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '4:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.7900; Y=1.1800; X=1.3400; cold_risk=8.6%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.05, 'jc_draw': 3.45, 'jc_lose': 2.85, 'rq_win': 4.2, 'rq_draw': 3.85, 'rq_lose': 1.59, 'avg_win': 2.36, 'avg_draw': 3.71, 'avg_lose': 2.54, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '正常', 'match_context': 'Z=2.2600; Y=1.3400; X=1.9500; cold_risk=9.0%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.28, 'jc_draw': 4.9, 'jc_lose': 6.95, 'rq_win': 1.9, 'rq_draw': 3.83, 'rq_lose': 2.92, 'avg_win': 1.35, 'avg_draw': 5.02, 'avg_lose': 6.96, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.3000; Y=1.1200; X=0.9100; cold_risk=8.4%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.27, 'jc_draw': 3.5, 'jc_lose': 2.48, 'rq_win': 4.7, 'rq_draw': 4.15, 'rq_lose': 1.48, 'avg_win': 2.06, 'avg_draw': 3.72, 'avg_lose': 3.01, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.1400; Y=1.3900; X=2.3800; cold_risk=12.4%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.82, 'jc_draw': 3.82, 'jc_lose': 3.14, 'rq_win': 3.35, 'rq_draw': 3.9, 'rq_lose': 1.74, 'avg_win': 1.92, 'avg_draw': 3.96, 'avg_lose': 3.22, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=2.7100; Y=1.2900; X=1.8700; cold_risk=14.7%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.01, 'jc_draw': 3.52, 'jc_lose': 2.88, 'rq_win': 4.02, 'rq_draw': 3.8, 'rq_lose': 1.62, 'avg_win': 2.13, 'avg_draw': 3.61, 'avg_lose': 2.95, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=2.3400; Y=1.3400; X=1.9500; cold_risk=20.1%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.28, 'jc_draw': 2.75, 'jc_lose': 3.06, 'rq_win': 5.55, 'rq_draw': 3.65, 'rq_lose': 1.48, 'avg_win': 2.33, 'avg_draw': 3.0, 'avg_lose': 2.97, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=平|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=1.6800; Y=1.3900; X=1.4900; cold_risk=30.6%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.0, 'jc_draw': 3.02, 'jc_lose': 2.15, 'rq_win': 1.54, 'rq_draw': 3.65, 'rq_lose': 4.85, 'avg_win': 2.55, 'avg_draw': 3.45, 'avg_lose': 2.54, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.5100; Y=1.5000; X=2.6200; cold_risk=26.5%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.88, 'jc_draw': 4.05, 'jc_lose': 2.85, 'rq_win': 3.15, 'rq_draw': 4.35, 'rq_lose': 1.72, 'avg_win': 1.86, 'avg_draw': 4.1, 'avg_lose': 3.25, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=2.8100; Y=1.3100; X=2.2300; cold_risk=11.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.38, 'jc_draw': 4.08, 'jc_lose': 6.25, 'rq_win': 2.25, 'rq_draw': 3.35, 'rq_lose': 2.59, 'avg_win': 1.68, 'avg_draw': 3.69, 'avg_lose': 4.94, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.4300; Y=1.1600; X=0.8700; cold_risk=18.9%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 5.05, 'jc_draw': 4.22, 'jc_lose': 1.44, 'rq_win': 2.4, 'rq_draw': 3.65, 'rq_lose': 2.28, 'avg_win': 4.38, 'avg_draw': 3.478, 'avg_lose': 1.72, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.4000; Y=1.6700; X=6.9600; cold_risk=20.8%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.41, 'jc_draw': 4.0, 'jc_lose': 5.9, 'rq_win': 2.35, 'rq_draw': 3.35, 'rq_lose': 2.47, 'avg_win': 1.45, 'avg_draw': 4.31, 'avg_lose': 6.51, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.3200; Y=1.1700; X=0.9200; cold_risk=14.3%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.32, 'jc_draw': 4.6, 'jc_lose': 6.5, 'rq_win': 2.0, 'rq_draw': 3.62, 'rq_lose': 2.83, 'avg_win': 1.28, 'avg_draw': 5.31, 'avg_lose': 11.12, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.9700; Y=1.1400; X=0.9300; cold_risk=8.5%; dev_level=轻微偏离'},
    {'handicap': -1, 'jc_win': 2.39, 'jc_draw': 3.55, 'jc_lose': 2.33, 'rq_win': 1.46, 'rq_draw': 4.32, 'rq_lose': 4.7, 'avg_win': 2.79, 'avg_draw': 3.58, 'avg_lose': 2.26, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=胜|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.0900; Y=1.4100; X=2.6300; cold_risk=13.2%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.68, 'jc_draw': 3.95, 'jc_lose': 1.99, 'rq_win': 1.62, 'rq_draw': 4.15, 'rq_lose': 3.7, 'avg_win': 2.83, 'avg_draw': 3.98, 'avg_lose': 2.1, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=2.1500; Y=1.4600; X=3.6400; cold_risk=10.5%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 1.18, 'jc_draw': 5.15, 'jc_lose': 11.5, 'rq_win': 1.71, 'rq_draw': 3.65, 'rq_lose': 3.7, 'avg_win': 1.43, 'avg_draw': 3.99, 'avg_lose': 7.26, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=4.7200; Y=1.0800; X=0.5500; cold_risk=14.0%; dev_level=显著偏离'},
    {'handicap': 1, 'jc_win': 2.31, 'jc_draw': 3.05, 'jc_lose': 2.71, 'rq_win': 5.18, 'rq_draw': 3.9, 'rq_lose': 1.47, 'avg_win': 2.15, 'avg_draw': 3.24, 'avg_lose': 3.26, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:4', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=1.8400; Y=1.4000; X=1.8900; cold_risk=31.9%; dev_level=一致'},
    {'handicap': 1, 'jc_win': 2.5, 'jc_draw': 3.05, 'jc_lose': 2.5, 'rq_win': 5.75, 'rq_draw': 4.15, 'rq_lose': 1.4, 'avg_win': 2.62, 'avg_draw': 3.21, 'avg_lose': 2.59, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '2:3', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=1.7400; Y=1.4300; X=2.1100; cold_risk=25.4%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 2.65, 'jc_draw': 3.3, 'jc_lose': 2.23, 'rq_win': 1.5, 'rq_draw': 4.1, 'rq_lose': 4.6, 'avg_win': 2.84, 'avg_draw': 3.37, 'avg_lose': 2.3, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '1:4', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=胜', 'resonance_type': '正常', 'match_context': 'Z=1.8100; Y=1.4500; X=2.6500; cold_risk=17.9%; dev_level=一致'},
    {'handicap': -1, 'jc_win': 3.55, 'jc_draw': 3.71, 'jc_lose': 1.73, 'rq_win': 1.87, 'rq_draw': 3.65, 'rq_lose': 3.12, 'avg_win': 3.18, 'avg_draw': 3.53, 'avg_lose': 2.08, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6300; Y=1.5600; X=4.3700; cold_risk=18.0%; dev_level=轻微偏离'},
    {'handicap': 1, 'jc_win': 1.92, 'jc_draw': 3.22, 'jc_lose': 3.35, 'rq_win': 4.05, 'rq_draw': 3.58, 'rq_lose': 1.66, 'avg_win': 1.95, 'avg_draw': 3.36, 'avg_lose': 3.61, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '2:4', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.2100; Y=1.3200; X=1.5000; cold_risk=13.8%; dev_level=一致', 'match_id': '#756'},
    {'handicap': 1, 'jc_win': 1.82, 'jc_draw': 3.4, 'jc_lose': 3.5, 'rq_win': 3.45, 'rq_draw': 3.65, 'rq_lose': 1.77, 'avg_win': 2.0, 'avg_draw': 3.27, 'avg_lose': 3.49, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.4100; Y=1.2900; X=1.4800; cold_risk=26.2%; dev_level=一致', 'match_id': '#757'},
    {'handicap': -1, 'jc_win': 2.6, 'jc_draw': 2.87, 'jc_lose': 2.52, 'rq_win': 1.39, 'rq_draw': 4.1, 'rq_lose': 6.05, 'avg_win': 2.61, 'avg_draw': 2.92, 'avg_lose': 2.76, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.5900; Y=1.4400; X=2.0000; cold_risk=24.1%; dev_level=一致', 'match_id': '#758'},
    {'handicap': 1, 'jc_win': 1.32, 'jc_draw': 4.25, 'jc_lose': 7.3, 'rq_win': 2.07, 'rq_draw': 3.42, 'rq_lose': 2.83, 'avg_win': 1.37, 'avg_draw': 4.1, 'avg_lose': 7.08, 'shenjia': '未输入', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.6600; Y=1.1400; X=0.7600; cold_risk=11.9%; dev_level=一致', 'match_id': '#759'},
    {'handicap': -1, 'jc_win': 7.15, 'jc_draw': 4.8, 'jc_lose': 1.28, 'rq_win': 3.0, 'rq_draw': 3.6, 'rq_lose': 1.93, 'avg_win': 8.82, 'avg_draw': 4.98, 'avg_lose': 1.31, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '2:4', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.1800; Y=1.7500; X=10.4700; cold_risk=10.5%; dev_level=一致', 'match_id': '#760'},
    {'handicap': -1, 'jc_win': 5.35, 'jc_draw': 4.05, 'jc_lose': 1.44, 'rq_win': 2.37, 'rq_draw': 3.5, 'rq_lose': 2.37, 'avg_win': 4.95, 'avg_draw': 3.94, 'avg_lose': 1.57, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.2800; Y=1.6900; X=6.7300; cold_risk=18.5%; dev_level=一致', 'match_id': '#761'},
    {'handicap': -2, 'jc_win': 12.0, 'jc_draw': 6.55, 'jc_lose': 1.12, 'rq_win': 2.2, 'rq_draw': 4.0, 'rq_lose': 2.36, 'avg_win': 8.37, 'avg_draw': 5.52, 'avg_lose': 1.27, 'shenjia': '未输入', 'real_result': '负', 'real_score': '0:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.0100; Y=1.8500; X=23.7800; cold_risk=4.2%; dev_level=轻微偏离', 'match_id': '#762'},
    {'handicap': -1, 'jc_win': 4.05, 'jc_draw': 3.95, 'jc_lose': 1.59, 'rq_win': 2.05, 'rq_draw': 3.65, 'rq_lose': 2.72, 'avg_win': 3.97, 'avg_draw': 3.8, 'avg_lose': 1.73, 'shenjia': '未输入', 'real_result': '负', 'real_score': '2:3', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.5600; Y=1.6000; X=5.3700; cold_risk=9.8%; dev_level=一致', 'match_id': '#763'},
    {'handicap': -1, 'jc_win': 5.6, 'jc_draw': 4.15, 'jc_lose': 1.41, 'rq_win': 2.45, 'rq_draw': 3.4, 'rq_lose': 2.35, 'avg_win': 4.51, 'avg_draw': 3.86, 'avg_lose': 1.62, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.2600; Y=1.7000; X=7.2100; cold_risk=20.2%; dev_level=轻微偏离', 'match_id': '#764'},
    {'handicap': 2, 'jc_win': 1.15, 'jc_draw': 5.8, 'jc_lose': 11.5, 'rq_win': 2.73, 'rq_draw': 3.8, 'rq_lose': 2.0, 'avg_win': 1.19, 'avg_draw': 5.26, 'avg_lose': 11.2, 'shenjia': '未输入', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=5.4000; Y=1.0700; X=0.6200; cold_risk=7.0%; dev_level=一致', 'match_id': '#765'},
    {'handicap': -1, 'jc_win': 3.7, 'jc_draw': 3.25, 'jc_lose': 1.82, 'rq_win': 1.77, 'rq_draw': 3.5, 'rq_lose': 3.6, 'avg_win': 2.93, 'avg_draw': 3.35, 'avg_lose': 2.24, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.3800; Y=1.5700; X=3.6100; cold_risk=31.4%; dev_level=轻微偏离', 'match_id': '#766'},
    {'handicap': -1, 'jc_win': 7.65, 'jc_draw': 4.6, 'jc_lose': 1.28, 'rq_win': 3.0, 'rq_draw': 3.55, 'rq_lose': 1.95, 'avg_win': 5.72, 'avg_draw': 4.25, 'avg_lose': 1.5, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.0600; Y=1.7700; X=10.1200; cold_risk=16.2%; dev_level=轻微偏离', 'match_id': '#767'},
    {'handicap': 1, 'jc_win': 1.49, 'jc_draw': 3.5, 'jc_lose': 5.8, 'rq_win': 2.7, 'rq_draw': 3.2, 'rq_lose': 2.24, 'avg_win': 1.71, 'avg_draw': 3.49, 'avg_lose': 4.8, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.8100; Y=1.2000; X=0.8400; cold_risk=19.3%; dev_level=轻微偏离', 'match_id': '#768'},
    {'handicap': 1, 'jc_win': 1.18, 'jc_draw': 5.15, 'jc_lose': 11.5, 'rq_win': 1.73, 'rq_draw': 3.55, 'rq_lose': 3.71, 'avg_win': 1.33, 'avg_draw': 4.57, 'avg_lose': 9.48, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.7200; Y=1.0800; X=0.5500; cold_risk=11.2%; dev_level=轻微偏离', 'match_id': '#769'},
    {'handicap': -1, 'jc_win': 3.05, 'jc_draw': 3.0, 'jc_lose': 2.14, 'rq_win': 1.55, 'rq_draw': 3.7, 'rq_lose': 4.7, 'avg_win': 2.79, 'avg_draw': 3.24, 'avg_lose': 2.43, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:3', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.4800; Y=1.5100; X=2.6200; cold_risk=33.2%; dev_level=一致', 'match_id': '#770'},
    {'handicap': 2, 'jc_win': 1.16, 'jc_draw': 5.55, 'jc_lose': 11.5, 'rq_win': 2.65, 'rq_draw': 4.0, 'rq_lose': 2.0, 'avg_win': 1.35, 'avg_draw': 4.77, 'avg_lose': 8.02, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '4:1', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=5.1400; Y=1.0700; X=0.5900; cold_risk=11.6%; dev_level=轻微偏离', 'match_id': '#771'},
    {'handicap': 1, 'jc_win': 1.52, 'jc_draw': 3.5, 'jc_lose': 5.4, 'rq_win': 2.76, 'rq_draw': 3.25, 'rq_lose': 2.18, 'avg_win': 1.54, 'avg_draw': 3.63, 'avg_lose': 6.53, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.7800; Y=1.2100; X=0.9100; cold_risk=14.2%; dev_level=一致', 'match_id': '#772'},
    {'handicap': 1, 'jc_win': 1.42, 'jc_draw': 4.05, 'jc_lose': 5.6, 'rq_win': 2.32, 'rq_draw': 3.45, 'rq_lose': 2.45, 'avg_win': 1.5, 'avg_draw': 3.97, 'avg_lose': 5.99, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '4:2', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.3500; Y=1.1700; X=0.9800; cold_risk=15.4%; dev_level=一致', 'match_id': '#773'},
    {'handicap': 1, 'jc_win': 1.22, 'jc_draw': 4.7, 'jc_lose': 10.5, 'rq_win': 1.82, 'rq_draw': 3.5, 'rq_lose': 3.4, 'avg_win': 1.28, 'avg_draw': 4.77, 'avg_lose': 9.32, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=4.2300; Y=1.1000; X=0.5600; cold_risk=10.0%; dev_level=一致', 'match_id': '#774'},
    {'handicap': -1, 'jc_win': 4.45, 'jc_draw': 3.35, 'jc_lose': 1.65, 'rq_win': 1.95, 'rq_draw': 3.3, 'rq_lose': 3.2, 'avg_win': 3.35, 'avg_draw': 3.34, 'avg_lose': 1.98, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.2300; Y=1.6300; X=4.4000; cold_risk=27.1%; dev_level=轻微偏离', 'match_id': '#775'},
    {'handicap': 1, 'jc_win': 1.52, 'jc_draw': 3.55, 'jc_lose': 5.3, 'rq_win': 2.77, 'rq_draw': 3.25, 'rq_lose': 2.17, 'avg_win': 1.66, 'avg_draw': 3.7, 'avg_lose': 4.81, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.8200; Y=1.2100; X=0.9400; cold_risk=19.2%; dev_level=一致', 'match_id': '#776'},
    {'handicap': 1, 'jc_win': 1.34, 'jc_draw': 4.5, 'jc_lose': 6.2, 'rq_win': 2.06, 'rq_draw': 3.65, 'rq_lose': 2.7, 'avg_win': 1.49, 'avg_draw': 4.43, 'avg_lose': 5.68, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '4:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.8500; Y=1.1500; X=0.9600; cold_risk=16.4%; dev_level=一致', 'match_id': '#777'},
    {'handicap': -1, 'jc_win': 3.6, 'jc_draw': 3.7, 'jc_lose': 1.72, 'rq_win': 1.86, 'rq_draw': 3.65, 'rq_lose': 3.15, 'avg_win': 3.63, 'avg_draw': 3.75, 'avg_lose': 1.85, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6100; Y=1.5700; X=4.4100; cold_risk=14.3%; dev_level=一致', 'match_id': '#778'},
    {'handicap': 1, 'jc_win': 1.37, 'jc_draw': 4.5, 'jc_lose': 5.7, 'rq_win': 2.14, 'rq_draw': 3.65, 'rq_lose': 2.58, 'avg_win': 1.6, 'avg_draw': 3.93, 'avg_lose': 5.21, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '3:1', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.8000; Y=1.1600; X=1.0500; cold_risk=12.6%; dev_level=轻微偏离', 'match_id': '#779'},
    {'handicap': 1, 'jc_win': 1.44, 'jc_draw': 4.0, 'jc_lose': 5.4, 'rq_win': 2.38, 'rq_draw': 3.5, 'rq_lose': 2.36, 'avg_win': 1.58, 'avg_draw': 3.84, 'avg_lose': 5.34, 'shenjia': '主身 > 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '同向共振', 'match_context': 'Z=3.2800; Y=1.1800; X=1.0100; cold_risk=17.3%; dev_level=一致', 'match_id': '#780'},
    {'handicap': -1, 'jc_win': 2.95, 'jc_draw': 3.25, 'jc_lose': 2.08, 'rq_win': 1.57, 'rq_draw': 3.85, 'rq_lose': 4.3, 'avg_win': 3.24, 'avg_draw': 3.4, 'avg_lose': 2.14, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '1:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.6500; Y=1.4900; X=2.9100; cold_risk=17.7%; dev_level=一致', 'match_id': '#781'},
    {'handicap': 1, 'jc_win': 1.5, 'jc_draw': 3.7, 'jc_lose': 5.2, 'rq_win': 2.73, 'rq_draw': 3.2, 'rq_lose': 2.22, 'avg_win': 1.6, 'avg_draw': 3.71, 'avg_lose': 5.31, 'shenjia': '主身 > 客身', 'real_result': '胜', 'real_score': '2:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.9600; Y=1.2000; X=0.9900; cold_risk=17.4%; dev_level=一致', 'match_id': '#782'},
    {'handicap': 1, 'jc_win': 1.45, 'jc_draw': 3.8, 'jc_lose': 5.7, 'rq_win': 2.62, 'rq_draw': 3.15, 'rq_lose': 2.33, 'avg_win': 1.85, 'avg_draw': 3.45, 'avg_lose': 4.04, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '0:1', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '冷门预警', 'match_context': 'Z=3.1000; Y=1.1800; X=0.9100; cold_risk=23.0%; dev_level=显著偏离', 'match_id': '#783'},
    {'handicap': -1, 'jc_win': 4.9, 'jc_draw': 3.6, 'jc_lose': 1.55, 'rq_win': 2.15, 'rq_draw': 3.25, 'rq_lose': 2.82, 'avg_win': 3.39, 'avg_draw': 3.82, 'avg_lose': 1.91, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.2200; Y=1.6600; X=5.2400; cold_risk=27.3%; dev_level=轻微偏离', 'match_id': '#784'},
    {'handicap': 1, 'jc_win': 1.85, 'jc_draw': 3.1, 'jc_lose': 3.75, 'rq_win': 3.95, 'rq_draw': 3.35, 'rq_lose': 1.73, 'avg_win': 1.84, 'avg_draw': 3.77, 'avg_lose': 3.8, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.1800; Y=1.3000; X=1.2600; cold_risk=13.2%; dev_level=一致', 'match_id': '#785'},
    {'handicap': 1, 'jc_win': 1.65, 'jc_draw': 3.35, 'jc_lose': 4.45, 'rq_win': 3.25, 'rq_draw': 3.2, 'rq_lose': 1.97, 'avg_win': 2.09, 'avg_draw': 3.14, 'avg_lose': 3.65, 'shenjia': '主身 > 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.5300; Y=1.2500; X=1.0900; cold_risk=25.6%; dev_level=轻微偏离', 'match_id': '#786'},
    {'handicap': -2, 'jc_win': 10.0, 'jc_draw': 5.8, 'jc_lose': 1.17, 'rq_win': 2.0, 'rq_draw': 4.15, 'rq_lose': 2.58, 'avg_win': 6.58, 'avg_draw': 4.59, 'avg_lose': 1.43, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '1:2', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '正常', 'match_context': 'Z=1.0500; Y=1.8200; X=16.9000; cold_risk=14.2%; dev_level=显著偏离', 'match_id': '#787'},
    {'handicap': -1, 'jc_win': 7.2, 'jc_draw': 4.3, 'jc_lose': 1.32, 'rq_win': 2.82, 'rq_draw': 3.35, 'rq_lose': 2.1, 'avg_win': 5.81, 'avg_draw': 4.21, 'avg_lose': 1.49, 'shenjia': '主身 < 客身', 'real_result': '负', 'real_score': '0:4', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '同向共振', 'match_context': 'Z=1.0500; Y=1.7600; X=8.7700; cold_risk=15.9%; dev_level=轻微偏离', 'match_id': '#788'},
    {'handicap': -1, 'jc_win': 3.75, 'jc_draw': 3.7, 'jc_lose': 1.69, 'rq_win': 1.92, 'rq_draw': 3.45, 'rq_lose': 3.15, 'avg_win': 4.08, 'avg_draw': 3.62, 'avg_lose': 1.73, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': '0:0', 'engine_summary': 'A-纯让分引擎=让胜|B-综合验证引擎=负|C-数学指标引擎(超级计算版)=负|D-结构形态引擎=负|E-动态临界引擎=负|F-概率区间映射引擎=负', 'resonance_type': '反向背离', 'match_context': 'Z=1.5600; Y=1.5800; X=4.5500; cold_risk=12.6%; dev_level=一致', 'match_id': '#789'},
    {'handicap': 1, 'jc_win': 2.08, 'jc_draw': 3.2, 'jc_lose': 2.98, 'rq_win': 4.5, 'rq_draw': 3.65, 'rq_lose': 1.58, 'avg_win': 2.46, 'avg_draw': 3.23, 'avg_lose': 2.66, 'shenjia': '未输入', 'real_result': '胜', 'real_score': '2:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=2.0800; Y=1.3500; X=1.7300; cold_risk=12.2%; dev_level=轻微偏离', 'match_id': '#790'},
    {'handicap': 1, 'jc_win': 2.08, 'jc_draw': 3.2, 'jc_lose': 2.98, 'rq_win': 4.5, 'rq_draw': 3.65, 'rq_lose': 1.58, 'avg_win': 2.46, 'avg_draw': 3.23, 'avg_lose': 2.66, 'shenjia': '未输入', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让负|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=平', 'resonance_type': '反向背离', 'match_context': 'Z=2.0800; Y=1.3500; X=1.7300; cold_risk=12.2%; dev_level=轻微偏离', 'match_id': '#791'},
    {'handicap': 1, 'jc_win': 1.62, 'jc_draw': 3.6, 'jc_lose': 4.28, 'rq_win': 3.02, 'rq_draw': 3.35, 'rq_lose': 2.0, 'avg_win': 1.73, 'avg_draw': 3.56, 'avg_lose': 4.42, 'shenjia': '未输入', 'real_result': '平', 'real_score': '1:1', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=2.7500; Y=1.2400; X=1.2100; cold_risk=11.6%; dev_level=一致', 'match_id': '#792'},
    {'handicap': 1, 'jc_win': 1.47, 'jc_draw': 3.85, 'jc_lose': 5.3, 'rq_win': 2.61, 'rq_draw': 3.25, 'rq_lose': 2.28, 'avg_win': 1.65, 'avg_draw': 3.62, 'avg_lose': 5.01, 'shenjia': '主身 < 客身', 'real_result': '胜', 'real_score': '4:0', 'engine_summary': 'A-纯让分引擎=让平|B-综合验证引擎=胜|C-数学指标引擎(超级计算版)=胜|D-结构形态引擎=胜|E-动态临界引擎=胜|F-概率区间映射引擎=胜', 'resonance_type': '反向背离', 'match_context': 'Z=3.1200; Y=1.1900; X=1.0000; cold_risk=14.4%; dev_level=一致', 'match_id': '#793'},
]# [V15+补丁] 已禁用自动去重逻辑，保留所有数据不做任何删减
_init_existing_ids()

# 4新增: 重复编号检测与修复
def _fix_duplicate_ids():
    """扫描ERROR_BOOK检测重复match_id并修复"""
    seen_ids = {}
    duplicates_found = []
    for idx, item in enumerate(ERROR_BOOK):
        mid = item.get('match_id')
        if mid:
            if mid in seen_ids:
                duplicates_found.append((seen_ids[mid], idx, mid))
            seen_ids[mid] = idx
    
    if duplicates_found:
        print("\n[编号修复] 检测到重复编号，正在修复...")
        for first_idx, dup_idx, dup_id in duplicates_found:
            # 保留第一条，重新编号后续重复的
            # 从ERROR_BOOK中收集所有已有的编号数字，取最大值+1作为新编号
            existing_nums = [int(item['match_id'][1:]) for item in ERROR_BOOK if item.get('match_id') and str(item['match_id']).startswith('#')]
            new_num = max(existing_nums) + 1 if existing_nums else 999
            # 找一个未被使用的编号
            all_ids = set(item.get('match_id', '') for item in ERROR_BOOK if item.get('match_id'))
            candidate = new_num
            while '#{:03d}'.format(candidate) in all_ids:
                candidate += 1
            new_id = '#{:03d}'.format(candidate)
            ERROR_BOOK[dup_idx]['match_id'] = new_id
            all_ids.add(new_id)
            print("  [{}] -> [{}] (重复编号已修复)".format(dup_id, new_id))
        print("[编号修复] 全部重复编号已修复完成")
    else:
        print("[编号检查] 所有编号唯一，无需修复")

_fix_duplicate_ids()

# ==========================================
# 数据指纹识别系统（智能防重 + 自动编号匹配）
# ==========================================

def generate_fingerprint(data):
    """生成比赛数据指纹（基于核心字段）
    指纹由：让分数 + 赛事概率 + 身价对比 组成
    用于快速识别是否已存在相同比赛"""
    fingerprint_parts = [
        str(data.get('handicap', '')),
        str(data.get('jc_win', '')),
        str(data.get('jc_draw', '')),
        str(data.get('jc_lose', '')),
        str(data.get('shenjia', '')),
    ]
    return '|'.join(fingerprint_parts)


def check_fingerprint_in_book(fingerprint):
    """在错题本中查找相同指纹的记录
    返回: (是否找到, 匹配的记录列表)"""
    matches = []
    for item in ERROR_BOOK:
        # 为每条记录动态生成指纹（兼容可能缺少match_id的历史数据）
        item_fingerprint = generate_fingerprint({
            'handicap': item.get('handicap', ''),
            'jc_win': item.get('jc_win', ''),
            'jc_draw': item.get('jc_draw', ''),
            'jc_lose': item.get('jc_lose', ''),
            'shenjia': item.get('shenjia', ''),
        })
        if item_fingerprint == fingerprint:
            matches.append(item)
    return len(matches) > 0, matches


def print_matched_match_info(matched_item):
    """打印匹配到的比赛详细信息"""
    mid = matched_item.get('match_id', '未编号')
    h = matched_item.get('handicap', 0)
    h_str = "主让{}球".format(h) if h > 0 else "客让{}球".format(abs(h)) if h < 0 else "平手/无让分"
    real_res = matched_item.get('real_result', '待赛')
    real_score = matched_item.get('real_score', '')
    score_str = " 真实比分: {}".format(real_score) if real_score else ""
    
    print("")
    print("=" * 45)
    print("  【数据指纹匹配成功】检测到重复比赛！")
    print("=" * 45)
    print("  该比赛已存在于错题本中：")
    print("  编号: [{}]".format(mid))
    print("  让分: {}".format(h_str))
    print("  赛事概率: 胜{} | 平{} | 负{}".format(
        matched_item.get('jc_win', ''), 
        matched_item.get('jc_draw', ''), 
        matched_item.get('jc_lose', '')
    ))
    print("  身价对比: {}".format(matched_item.get('shenjia', '未输入')))
    print("  赛果: {}{}".format(real_res, score_str))
    print("=" * 45)
    print("")


def check_and_warn_duplicate(new_data):
    """[V15+补丁] 仅提示不拦截：检查新输入数据是否与错题本重复，仅打印警告不阻止流程"""
    fingerprint = generate_fingerprint(new_data)
    is_duplicate, matches = check_fingerprint_in_book(fingerprint)
    
    if is_duplicate:
        # 打印所有匹配的记录（仅提示）
        for match in matches:
            print_matched_match_info(match)
        print("[提示] 检测到与已有比赛数据指纹匹配！以下记录仅供参考，将继续分析并保存。")
        for match in matches:
            mid = match.get('match_id', '未编号')
            print("  已有记录 [{}] 赛事概率: 胜{} | 平{} | 负{} | 让分: {}".format(
                mid,
                match['jc_win'], match['jc_draw'], match['jc_lose'],
                "主让{}球".format(match['handicap']) if match['handicap'] > 0 else
                "客让{}球".format(abs(match['handicap'])) if match['handicap'] < 0 else "平手/无让分"
            ))
        print("-" * 45)
    # [补丁] 不再询问用户，不再拦截，始终返回False表示继续分析
    return False
def warn_before_save_duplicate(new_data):
    """[V15+补丁] 仅提示不拦截：检查重复但仅打印警告不阻止保存"""
    key_fields = ['handicap', 'jc_win', 'jc_draw', 'jc_lose',
                  'rq_win', 'rq_draw', 'rq_lose',
                  'avg_win', 'avg_draw', 'avg_lose', 'shenjia']
    
    for item in ERROR_BOOK:
        match = True
        for field in key_fields:
            if item.get(field) != new_data.get(field):
                match = False
                break
        if match:
            # 找到完全一致的记录，仅提示不拦截
            match_item = item
            mid = match_item.get('match_id', '未编号')
            print("")
            print("=" * 45)
            print("  【提示】该比赛数据与错题本中已有记录字段完全一致！")
            print("=" * 45)
            print("  已有编号: [{}]".format(mid))
            print("  赛事概率: 胜{} | 平{} | 负{}".format(
                match_item.get('jc_win', ''), match_item.get('jc_draw', ''), match_item.get('jc_lose', '')))
            print("  让分: {}".format(
                "主让{}球".format(match_item['handicap']) if match_item['handicap'] > 0 else
                "客让{}球".format(abs(match_item['handicap'])) if match_item['handicap'] < 0 else "平手/无让分"
            ))
            print("  身价对比: {}".format(match_item.get('shenjia', '未输入')))
            print("  [补丁] 已改为仅提示，将继续保存为新记录。")
            print("=" * 45)
            print("")
            # [补丁] 不再返回 DUPLICATE，继续执行保存
    return True

# [V15+补丁] 去重提示已禁用
#if _dedup_count > 0:
#    print(f"[去重] 已删除 {_dedup_count} 条重复错题数据，剩余 {len(ERROR_BOOK)} 条")

    # --- 在此处粘贴你的错题集数据 ---
    # 示例数据（请删除或保留，程序会自动识别）：
    # {'handicap': 1, 'jc_win': 2.02, 'jc_draw': 3.65, 'jc_lose': 3.02, 'rq_win': 3.95, 'rq_draw': 3.95, 'rq_lose': 1.61, 'avg_win': 2.02, 'avg_draw': 3.5, 'avg_lose': 2.88, 'shenjia': '主身 < 客身', 'real_result': '平', 'real_score': ''},


# ==========================================
# V15 新增: 引擎性能追踪与自适应权重
# ==========================================
# 引擎历史准确率追踪（每次回测后自动更新）
_ENGINE_PERFORMANCE = {
    'A': {'hits': 0, 'total': 0, 'weight': 1.0},
    'B': {'hits': 0, 'total': 0, 'weight': 1.0},
    'C': {'hits': 0, 'total': 0, 'weight': 1.0},
    'D': {'hits': 0, 'total': 0, 'weight': 1.0},
    'E': {'hits': 0, 'total': 0, 'weight': 1.0},
    'F': {'hits': 0, 'total': 0, 'weight': 1.0},
}

def update_engine_performance(engine_key, is_correct):
    """更新引擎性能追踪数据"""
    if engine_key in _ENGINE_PERFORMANCE:
        _ENGINE_PERFORMANCE[engine_key]['total'] += 1
        if is_correct:
            _ENGINE_PERFORMANCE[engine_key]['hits'] += 1
        # 计算当前准确率
        rate = _ENGINE_PERFORMANCE[engine_key]['hits'] / _ENGINE_PERFORMANCE[engine_key]['total']
        # 用指数衰减计算新权重
        decay = CONFIG.get('ENGINE_PERFORMANCE_DECAY', 0.98)
        new_weight = rate * decay + (1 - decay) * _ENGINE_PERFORMANCE[engine_key].get('prev_weight', 0.5)
        _ENGINE_PERFORMANCE[engine_key]['prev_weight'] = new_weight
        # 应用最低权重限制
        min_weight = CONFIG.get('MIN_ENGINE_WEIGHT', 0.3)
        _ENGINE_PERFORMANCE[engine_key]['weight'] = max(min_weight, new_weight)

def get_engine_weights():
    """获取当前引擎权重字典"""
    weights = {}
    for key, data in _ENGINE_PERFORMANCE.items():
        weights[key] = data['weight']
    return weights

def get_system_confidence(vote_count, total_engines=6):
    """计算系统综合信心指数 (0~1)
    vote_count: {结果: 票数} 字典
    total_engines: 参与投票的引擎总数
    """
    if not vote_count:
        return 0.0
    max_votes = max(vote_count.values())
    confidence = max_votes / total_engines
    return confidence

def suggest_skip(vote_count, total_engines=6):
    """判断是否建议放弃本场
    条件: 最高票数 <= 最低共识阈值 且 最高票只比第二名多1票
    """
    if not vote_count or len(vote_count) > total_engines:
        return False
    votes_sorted = sorted(vote_count.values(), reverse=True)
    max_votes = votes_sorted[0]
    second_votes = votes_sorted[1] if len(votes_sorted) > 1 else 0
    min_agree = CONFIG.get('MIN_AGREE_COUNT', 4)
    # 分歧严重: 最高票<=3 且 与第二名差距<=1
    if max_votes < min_agree and (max_votes - second_votes) <= 1:
        return True
    return False


# ==========================================
# [V17新增] 市场条件检查引擎 - 胶着数据面板/概率差距过小预警
# ==========================================
def _check_yupan_single(data, hot_result_key, cold_avg_key, hot_label, extreme_thresh, medium_thresh, avg_ratio_thresh):
    """检测单一方向的干扰信号 [V23重构] 提取自check_market_risk消除主胜/客胜代码重复"""
    warnings = []
    hot_odds = data.get(hot_result_key, 0)
    cold_avg = data.get(cold_avg_key, 0)
    
    if hot_odds > 0 and cold_avg > 0:
        # 需要获取对应的平均概率来计算比值
        if 'win' in hot_result_key:  # 主胜方向
            avg_hot = data.get('avg_win', 0)
            avg_cold = data.get('avg_lose', 0)
        else:  # 客胜方向
            avg_hot = data.get('avg_lose', 0)
            avg_cold = data.get('avg_win', 0)
        
        if avg_hot > 0 and avg_cold > 0:
            avg_ratio = avg_cold / avg_hot
            if avg_ratio > avg_ratio_thresh:
                if hot_odds < extreme_thresh:
                    warnings.append(
                        "[V20干扰信号检测-极端] 赛事{}概率极低({:.2f}<{:.2f})，但多家机构平均概率极差比达{:.2f}(>阈值{:.1f})，"
                        "呈现经典干扰信号结构！大量资金涌向热门方，机构压低热门方概率吸引建仓，"
                        "实际赛果往往相反，请高度警惕冷门！".format(hot_label, hot_odds, extreme_thresh, avg_ratio, avg_ratio_thresh)
                    )
                elif hot_odds < medium_thresh:
                    warnings.append(
                        "[V20干扰信号检测-中等] 赛事{}概率处于中等区间({:.2f})，但多家机构平均概率极差比达{:.2f}(>阈值{:.1f})，"
                        "存在中等概率干扰信号可能！该区间历史低概率结果频率较高，请保持警惕！".format(hot_label, hot_odds, avg_ratio, avg_ratio_thresh)
                    )
    return warnings


def check_market_risk(data):
    """检查市场条件是否适合下单
    【重要】赛事中没有平手/无让分输入选项，让分数由赛事中心设定
    本函数主要通过赛事概率本身来判断是否为胶着数据面板：
    条件1: 赛事概率胜平负绝对差距过小 -> 建议不能下场 (主要检测)
    条件2: 赛事概率胜平负比值接近 -> 建议不能买 (补充检测)
    条件3: 让分数为0(平手/无让分) -> 补充兜底检测
    返回: (should_skip, warnings_list)
    """
    warnings = []
    handicap = data.get('handicap', 0)
    jc_win = data.get('jc_win', 0)
    jc_draw = data.get('jc_draw', 0)
    jc_lose = data.get('jc_lose', 0)

    # 检查1(主要): 赛事概率胜平负绝对差距很小
    # 当最高概率-最低概率 < 阈值时，说明三结果概率过于接近
    odds_range = max(jc_win, jc_draw, jc_lose) - min(jc_win, jc_draw, jc_lose)
    odds_threshold = CONFIG.get('MARKET_ODDS_RANGE_THRESHOLD', 1.0)
    if odds_range < odds_threshold:
        warnings.append(
            "[胶着数据面板警告] 赛事概率胜平负差距过小({:.2f} < 阈值:{:.2f})，"
            "三结果概率过于接近，市场无法做出有效区分，"
            "建议不要下场！(胜:{:.2f} 平:{:.2f} 负:{:.2f})".format(
                odds_range, odds_threshold, jc_win, jc_draw, jc_lose
            )
        )

    # 检查2(补充): 赛事概率胜平负比值接近 (相对差距检测)
    # 当最高概率/最低概率 < 阈值时，说明实力接近
    if jc_win > 0 and jc_draw > 0 and jc_lose > 0:
        odds_ratio = max(jc_win, jc_draw, jc_lose) / min(jc_win, jc_draw, jc_lose)
        ratio_threshold = CONFIG.get('MARKET_ODDS_RATIO_THRESHOLD', 1.3)
        # 仅在绝对差距未触发时，用比值检测作为补充
        if odds_ratio < ratio_threshold and odds_range >= odds_threshold:
            warnings.append(
                "[概率比值警告] 赛事概率胜平负比值接近({:.2f} < 阈值:{:.2f})，"
                "最高概率/最低概率过于接近，市场分歧小，"
                "建议不要购买！(胜:{:.2f} 平:{:.2f} 负:{:.2f})".format(
                    odds_ratio, ratio_threshold, jc_win, jc_draw, jc_lose
                )
            )

    # 检查3(兜底): 让分数为0(平手/无让分)
    # 注意: 赛事中赛事中心极少开平手/无让分，此检查作为补充兜底
    handicap_warn_enabled = CONFIG.get('MARKET_HANDICAP_EVEN_WARN', True)
    if handicap_warn_enabled and handicap == 0:
        warnings.append(
            "[数据面板警告] 当前让分数为0(平手/无让分)，双方无让分优势，"
            "比赛结果不确定性高，建议谨慎！"
        )

    # [V18新增] 分级响应机制：不再简单"全有或全无"，而是根据胶着程度分级处理
    should_skip = len(warnings) > 0
    should_warn_only = False  # [V18新增] 仅警告(降仓)标志
    confidence_penalty = 0.0  # [V18新增] 信心扣减幅度
    
    # 检查是否有"仅警告"级别的胶着(介于WARN和SKIP之间)
    jc_win = data.get('jc_win', 0)
    jc_draw = data.get('jc_draw', 0)
    jc_lose = data.get('jc_lose', 0)
    odds_range_val = max(jc_win, jc_draw, jc_lose) - min(jc_win, jc_draw, jc_lose)
    warn_threshold = CONFIG.get('MARKET_ODDS_RANGE_WARN', 0.8)
    skip_threshold = CONFIG.get('MARKET_ODDS_RANGE_SKIP', 0.3)
    
    # 如果胶着程度在WARN~SKIP之间，仅警告+降仓而非放弃
    if odds_range_val < warn_threshold and odds_range_val >= skip_threshold and not should_skip:
        should_warn_only = True
        confidence_penalty = 0.15  # 信心扣减15%
        warnings.append(
            "[V18分级响应] 数据面板存在一定胶着({:.2f}介于{:.2f}~{:.2f})，建议降低仓位(信心扣减15%)而非放弃！".format(
                odds_range_val, skip_threshold, warn_threshold
            )
        )
    elif odds_range_val < skip_threshold:
        # 极胶着，强制放弃
        should_skip = True
        warnings.append(
            "[V18强制放弃] 数据面板极度胶着({:.2f}<{:.2f})，市场完全无法区分，强制放弃！".format(
                odds_range_val, skip_threshold
            )
        )
    
    # [V23重构] 干扰信号检测：使用参数化函数消除主胜/客胜代码重复
    extreme_odds_thresh = CONFIG.get('EXTREME_ODDS_THRESHOLD', 1.60)
    medium_odds_thresh = CONFIG.get('MEDIUM_ODDS_THRESHOLD', 1.65)
    avg_odds_ratio_thresh = CONFIG.get('AVG_ODDS_RATIO_THRESHOLD', 3.0)

    # 检测主胜方向干扰信号
    yupan_warnings = _check_yupan_single(
        data, 'jc_win', 'avg_lose', '主胜',
        extreme_odds_thresh, medium_odds_thresh, avg_odds_ratio_thresh
    )
    # 检测客胜方向干扰信号
    yupan_warnings += _check_yupan_single(
        data, 'jc_lose', 'avg_win', '客胜',
        extreme_odds_thresh, medium_odds_thresh, avg_odds_ratio_thresh
    )
    warnings.extend(yupan_warnings)

    # 如果检测到干扰信号，提升为警告级别(降仓而非放弃)
    if yupan_warnings and not should_skip:
        should_warn_only = True
        confidence_penalty = max(confidence_penalty, 0.20)
        warnings.append(
            "[V20干扰信号响应] 检测到干扰信号，建议降低仓位(信心扣减20%)或放弃本场！"
        )
    elif yupan_warnings and should_warn_only:
        confidence_penalty = max(confidence_penalty, 0.20)
    return should_skip, should_warn_only, confidence_penalty, warnings



# ==========================================
# 2. 核心数学指标计算
# ==========================================
def calculate_metrics(win, draw, lose):
    """计算核心数学指标 Z, Y, X"""
    try:
        if win <= 0 or draw <= 0 or lose <= 1:  # 修复：原始条件 (win+1)==0 永不为 True
            return 0, 0, 0
        z = (draw * 2) / (win + 1)
        y = ((draw * 2) - (draw * 2) / (win + 1)) / draw
        x = (z + y) / (lose - 1)
        return round(z, 2), round(y, 2), round(x, 2)
    except Exception:
        return 0, 0, 0

# ==========================================
# 新增：比分预测引擎（基于泊松分布模型）
# ==========================================
def predict_score(data):
    """比分预测引擎 - 基于赛事概率推算期望进球数，用泊松分布计算最可能比分"""
    jc_win, jc_draw, jc_lose = data['jc_win'], data['jc_draw'], data['jc_lose']
    
    # 从赛事概率计算隐含概率（去费用）
    inv_total = 1/jc_win + 1/jc_draw + 1/jc_lose
    p_win = (1/jc_win) / inv_total
    p_draw = (1/jc_draw) / inv_total
    p_lose = (1/jc_lose) / inv_total
    
    # 推算期望进球数（简化模型：概率倒数 * 系数）
    # V13: 动态进球系数（基于概率区间）
    zone_h = get_odds_zone(jc_win)
    zone_a = get_odds_zone(jc_lose)
    zone_d = get_odds_zone(jc_draw)
    multiplier_h = get_dynamic_goal_multiplier(zone_h)
    multiplier_a = get_dynamic_goal_multiplier(zone_a)
    home_correction, away_correction = get_handicap_correction(data["handicap"], zone_h, zone_a)
    home_exp = (1/jc_win) * 2.5 * multiplier_h + home_correction
    away_exp = (1/jc_lose) * 2.5 * multiplier_a + away_correction
    
    # 泊松分布概率质量函数
    def poisson_pmf(k, lam):
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    
    # 计算所有可能比分的概率
    score_probs = []
    for h in range(0, 7):
        for a in range(0, 7):
            prob = poisson_pmf(h, home_exp) * poisson_pmf(a, away_exp)
            score_probs.append((f"{h}:{a}", round(prob, 4)))
    score_probs.sort(key=lambda x: x[1], reverse=True)
    
    top3 = [s[0] for s in score_probs[:3]]
    top_probs = [s[1] for s in score_probs[:3]]
    
    # 根据最可能比分推断胜平负
    top_score = top3[0]
    h_goals, a_goals = map(int, top_score.split(":"))
    if h_goals > a_goals:
        score_conclusion = '胜'
    elif h_goals < a_goals:
        score_conclusion = '负'
    else:
        score_conclusion = '平'
    
    return {
        'predicted_score': top3[0],
        'alt_scores': top3[1:3],
        'top3_scores': top3,
        'top3_probs': top_probs,
        'home_exp': round(home_exp, 2),
        'away_exp': round(away_exp, 2),
        'score_conclusion': score_conclusion,
        'probabilities': {'win': round(p_win, 2), 'draw': round(p_draw, 2), 'lose': round(p_lose, 2)},
        # V13 新增信息
        'zone_h': zone_h, 'zone_a': zone_a, 'zone_d': zone_d,
        'multiplier_h': multiplier_h, 'multiplier_a': multiplier_a,
        'home_correction': home_correction, 'away_correction': away_correction,
        'home_exp_raw': round((1/jc_win) * 2.5, 2),
        'away_exp_raw': round((1/jc_lose) * 2.5, 2)
    }


# ==========================================
# [V18新增] 比分-方向一致性校验引擎
# ==========================================
def check_score_direction_consistency(score_pred, direction_conclusion):
    """比分预测引擎与方向引擎一致性校验
    【V18新增】当比分引擎输出的方向与方向引擎共识不一致时，
    1. 输出警告提示
    2. 如果方向共识强度>=5票(6票中)，优先调整比分预测方向
    3. 返回调整后的比分和一致性标志
    
    参数:
        score_pred: predict_score()返回的比分预测结果字典
        direction_conclusion: 方向引擎共识结论('胜'/'平'/'负')
    
    返回:
        dict: 包含调整后的比分预测和一致性信息
    """
    score_conclusion = score_pred.get('score_conclusion', '')
    top_score = score_pred.get('predicted_score', '')
    
    consistency = {
        'is_consistent': score_conclusion == direction_conclusion,
        'score_direction': score_conclusion,
        'direction_conclusion': direction_conclusion,
        'adjusted': False,
        'adjusted_score': top_score,
        'warning': ''
    }
    
    # 如果方向一致，直接返回
    if score_conclusion == direction_conclusion:
        return consistency
    
    # 方向不一致，检查共识强度
    # 这里direction_conclusion已经是投票后的共识结论
    # 如果共识强度足够高(>=4票)，则调整比分方向
    consistency['warning'] = '【V18警告】比分引擎预测({})与方向引擎共识({})不一致！'.format(
        score_conclusion, direction_conclusion
    )
    
    # 根据方向共识调整比分预测
    # 获取比分概率分布
    top3_scores = score_pred.get('top3_scores', [top_score])
    top3_probs = score_pred.get('top3_probs', [0])
    
    # 尝试找到与方向共识一致的比分
    adjusted_found = False
    for score_str in top3_scores:
        h, a = map(int, score_str.split(':'))
        if direction_conclusion == '胜' and h > a:
            consistency['adjusted_score'] = score_str
            consistency['is_consistent'] = True
            consistency['adjusted'] = True
            consistency['warning'] += ' 已根据方向共识调整比分至{}'.format(score_str)
            adjusted_found = True
            break
        elif direction_conclusion == '负' and h < a:
            consistency['adjusted_score'] = score_str
            consistency['is_consistent'] = True
            consistency['adjusted'] = True
            consistency['warning'] += ' 已根据方向共识调整比分至{}'.format(score_str)
            adjusted_found = True
            break
    
    if not adjusted_found:
        # 如果top3中没有一致方向的比分，构造一个最可能的比分
        if direction_conclusion == '胜':
            # 构造主胜比分：根据期望进球调整
            home_exp = score_pred.get('home_exp', 1.5)
            away_exp = score_pred.get('away_exp', 1.0)
            if home_exp >= away_exp * 1.5:
                consistency['adjusted_score'] = '{}:{}'.format(max(1, int(home_exp)), max(0, int(away_exp)))
            else:
                consistency['adjusted_score'] = '2:1'  # 默认主胜最小比分
        elif direction_conclusion == '负':
            home_exp = score_pred.get('home_exp', 1.0)
            away_exp = score_pred.get('away_exp', 1.5)
            if away_exp >= home_exp * 1.5:
                consistency['adjusted_score'] = '{}:{}'.format(max(0, int(home_exp)), max(1, int(away_exp)))
            else:
                consistency['adjusted_score'] = '1:2'  # 默认客胜最小比分
        consistency['adjusted'] = True
        consistency['warning'] += ' 已从备选比分中构造方向一致比分{}'.format(consistency['adjusted_score'])
    
    return consistency

# ==========================================
# 3. 辅助函数：结果转换与匹配
# ==========================================
def convert_rq_to_standard(handicap, rq_conclusion):
    """将让分结论(让胜/让平/让负)转换为标准胜平负"""
    if handicap == 0: return rq_conclusion
    mapping = {'让胜': '胜', '让平': '平', '让负': '负'}
    return mapping.get(rq_conclusion, rq_conclusion)

def convert_real_to_rq(handicap, real_result, real_score=''):
    """将真实结果转换为让分结果（用于回测）
    real_score 格式如 '2:1'，用于判断让平情况
    """
    if handicap == 0:
        return real_result
    if real_score and ':' in real_score:
        # 有实际比分，精确计算让分结果
        sh, sa = map(int, real_score.split(':'))
        adjusted = sh - sa - handicap  # 让分后的净胜球
        if adjusted > 0:
            return '让胜'
        elif adjusted < 0:
            return '让负'
        else:
            return '让平'
    # 无比分时，保守估计（可能遗漏让平）
    if handicap > 0:  # 主让
        return '让胜' if real_result == '胜' else '让负'
    else:  # 客让
        return '让负' if real_result == '负' else '让胜'

def _calculate_similarity(case, data, current_z, current_y, current_x):
    """计算单个案例的六维加权相似度得分 [V23重构] 提取自find_similar_cases避免代码重复"""
    # 维度1: 赛事概率相似度 (40%)
    score_jc = (get_score(case['jc_win'], data['jc_win']) +
                get_score(case['jc_draw'], data['jc_draw']) +
                get_score(case['jc_lose'], data['jc_lose'])) / 3

    # 维度2: 让分概率相似度 (15%)
    score_rq = (get_score(case['rq_win'], data['rq_win']) +
                get_score(case['rq_draw'], data['rq_draw']) +
                get_score(case['rq_lose'], data['rq_lose'])) / 3

    # 维度3: 多家机构平均概率相似度 (10%)
    score_avg = (get_score(case['avg_win'], data['avg_win']) +
                 get_score(case['avg_draw'], data['avg_draw']) +
                 get_score(case['avg_lose'], data['avg_lose'])) / 3

    # 维度4: 让分形态相似度 (15%)
    h_diff = abs(case['handicap'] - data['handicap'])
    score_handicap = 1 - (h_diff / 2) if h_diff <= 2 else 0

    # 维度5: 数学指标 Z/Y/X 相似度 (15%)
    case_z, case_y, case_x = calculate_metrics(case['jc_win'], case['jc_draw'], case['jc_lose'])
    z_sim = 1 - (abs(current_z - case_z) / max(abs(current_z), 1)) if current_z != 0 else 1
    y_sim = 1 - (abs(current_y - case_y) / max(abs(current_y), 1)) if current_y != 0 else 1
    x_sim = 1 - (abs(current_x - case_x) / max(abs(current_x), 1)) if current_x != 0 else 1
    score_metric = (z_sim + y_sim + x_sim) / 3

    # 维度6: 身价对比相似度 (5%)
    case_shen = case.get('shenjia', '未输入')
    data_shen = data.get('shenjia_info', '未输入')
    if case_shen == data_shen:
        score_strength = 1.0
    elif case_shen == '未输入' or data_shen == '未输入':
        score_strength = 0.5
    else:
        score_strength = 0.2

    # 加权总分
    total_score = (score_jc * 0.40 + score_rq * 0.15 + score_avg * 0.10 +
                   score_handicap * 0.15 + score_metric * 0.15 + score_strength * 0.05)

    return total_score, {
        'jc_odds': round(score_jc, 4),
        'handicap_odds': round(score_rq, 4),
        'avg_odds': round(score_avg, 4),
        'handicap_shape': round(score_handicap, 4),
        'metrics': round(score_metric, 4),
        'strength': round(score_strength, 4),
    }


def find_similar_cases(data):
    """
    智能错题本匹配 (V15 合并增强版)
    六维加权评分匹配算法：
    1. 赛事概率相似度 (40%)
    2. 让分概率相似度 (15%)
    3. 多家机构平均概率相似度 (10%)
    4. 让分形态相似度 (15%)
    5. 数学指标 Z/Y/X 相似度 (15%)
    6. 身价对比相似度 (5%)
    """
    # 使用全局CONFIG参数，确保参数统一（原硬编码局部变量已移除）
    TOLERANCE = CONFIG['TOLERANCE']
    SIMILARITY_THRESHOLD = CONFIG['SIMILARITY_THRESHOLD']
    METRIC_TOLERANCE = CONFIG['METRIC_TOLERANCE']

    matched = []
    current_z, current_y, current_x = calculate_metrics(data['jc_win'], data['jc_draw'], data['jc_lose'])

    for case in ERROR_BOOK:
        # [已移除限制] 不再跳过让分数差异大的比赛，全量对比
            # if abs(case['handicap'] - data['handicap']) > 0.25:
            #     continue
        if (abs(case['handicap'] - data['handicap']) <= 0.01 and
            abs(case['jc_win'] - data['jc_win']) <= 0.01 and
            abs(case['jc_draw'] - data['jc_draw']) <= 0.01 and
            abs(case['jc_lose'] - data['jc_lose']) <= 0.01 and
            abs(case['rq_win'] - data['rq_win']) <= 0.01 and
            abs(case['rq_draw'] - data['rq_draw']) <= 0.01 and
            abs(case['rq_lose'] - data['rq_lose']) <= 0.01):
            continue

        # [V23重构] 使用提取的相似度计算函数
        total_score, score_details = _calculate_similarity(case, data, current_z, current_y, current_x)

        if total_score >= SIMILARITY_THRESHOLD:
            matched.append({
                **case,
                'similarity_score': round(total_score, 4),
                'score_details': score_details,
            })

    # [V18新增] 错题本样本时间加权 - 近期数据更高权重
    # 为每个匹配结果添加时间权重(越新的数据权重越高)
    total_matches = len(matched)
    for i, m in enumerate(matched):
        # [V26修复] 原代码把时间权重直接乘进 similarity_score, 使原始相似度(如0.749)被放大, 高相似度(>=0.85)虚报。
        #   改为 similarity_score 保持原始值(供阈值诚实判断), 另设 rank_score 仅用于排序。
        m['raw_similarity'] = m['similarity_score']
        recency_idx = total_matches - i
        if recency_idx <= 10:
            weight = CONFIG.get('ERROR_BOOK_RECENT_WEIGHT', 1.5)
            decay = CONFIG.get('ERROR_BOOK_WEIGHT_DECAY', 0.95)
            time_weight = weight * (decay ** (10 - recency_idx))
            m['time_weight'] = time_weight
            m['rank_score'] = m['similarity_score'] * time_weight
        else:
            m['time_weight'] = 1.0
            m['rank_score'] = m['similarity_score']

    matched.sort(key=lambda x: x.get('rank_score', x['similarity_score']), reverse=True)
    
    # [V19新增] 二级匹配容差：当一级匹配数不足时，使用宽松容差二次搜索
    secondary_min_sample = CONFIG.get('ERROR_BOOK_MIN_SAMPLE', 5)
    secondary_tolerance = CONFIG.get('SECONDARY_TOLERANCE', 0.35)
    primary_threshold = CONFIG.get('SIMILARITY_THRESHOLD', 0.7)
    
    if len(matched) < secondary_min_sample:
        # 一级匹配不足，启动二级宽松搜索
        secondary_matched = []
        for case in ERROR_BOOK:
            # 跳过已匹配的
            case_id = id(case)
            if any(m.get('case_id', 0) == case_id for m in matched):
                continue
            
            # 重新计算该case的相似度（使用原始分数，不更新时间权重）
            if (abs(case['handicap'] - data['handicap']) <= 0.01 and
                abs(case['jc_win'] - data['jc_win']) <= 0.01 and
                abs(case['jc_draw'] - data['jc_draw']) <= 0.01 and
                abs(case['jc_lose'] - data['jc_lose']) <= 0.01 and
                abs(case['rq_win'] - data['rq_win']) <= 0.01 and
                abs(case['rq_draw'] - data['rq_draw']) <= 0.01 and
                abs(case['rq_lose'] - data['rq_lose']) <= 0.01):
                continue
            
            # [V23重构] 使用提取的相似度计算函数
            total_score, score_details = _calculate_similarity(case, data, current_z, current_y, current_x)
            
            # 使用二级容差（低于一级阈值但仍有参考价值）
            if total_score >= secondary_tolerance and total_score < primary_threshold:
                secondary_matched.append({
                    **case,
                    'similarity_score': round(total_score, 4),
                    'score_details': score_details,
                    'is_secondary': True,
                })
        
        if secondary_matched:
            matched.extend(secondary_matched)
            matched.sort(key=lambda x: x['similarity_score'], reverse=True)
    
    return matched


# ==========================================
# 4. 五大分析引擎
# ==========================================
def engine_pure_rq(data, shenjia_info):
    """引擎A：纯粹让分分析引擎 (V9逻辑) [阈值已基于错题集优化]"""
    handicap = data['handicap']
    rq_win, rq_draw, rq_lose = data['rq_win'], data['rq_draw'], data['rq_lose']
    result = {'engine': 'A-纯让分引擎', 'conclusion': '观望', 'reason': ''}

    if handicap >= 1: # 主让
        if rq_win < 1.7:
            result['reason'] = '主让深度让分低概率({})'.format(rq_win)
            if rq_draw > 3.8 and rq_lose > 5.0: result['conclusion'] = '让胜'
            elif rq_draw < 3.5: result['conclusion'] = '让平'
            else: result['conclusion'] = '让负'
        elif rq_win > 2.6:
            result['reason'] = '主让深度让分高概率({})'.format(rq_win)
            if rq_lose < 2.0: result['conclusion'] = '让负'
            else: result['conclusion'] = '让平'
        else:
            result['reason'] = '主让中低概率({})'.format(rq_win)
            # [V19新增] 让分概率深层分析：检测客队防范信号
            # 当让分负概率偏低(<=2.50)时，说明让分面板对客队有一定防范
            if rq_draw < 2.9:
                result['conclusion'] = '让平'
            elif rq_lose < 2.0:
                result['conclusion'] = '让负'
            elif rq_lose <= 2.50:
                # [V19] 让分负概率偏低，客队有防范，谨慎看好主胜
                result['conclusion'] = '让胜'
                result['reason'] += ' | 让负防范({:.2f})'.format(rq_lose)
            else:
                result['conclusion'] = '让胜'
            
    elif handicap <= -1: # 客让
        if rq_lose < 1.7:
            result['reason'] = '客让深度让分低概率({})'.format(rq_lose)
            if rq_draw > 3.8 and rq_win > 5.0: result['conclusion'] = '让负'
            elif rq_draw < 3.5: result['conclusion'] = '让平'
            else: result['conclusion'] = '让胜'
        elif rq_lose > 2.6:
            result['reason'] = '客让深度让分高概率({})'.format(rq_lose)
            if rq_win < 2.0: result['conclusion'] = '让胜'
            else: result['conclusion'] = '让平'
        else:
            result['reason'] = '客让中低概率({})'.format(rq_lose)
            # [V19新增] 让分概率深层分析：检测主队防范信号
            if rq_draw < 2.9:
                result['conclusion'] = '让平'
            elif rq_win < 2.0:
                result['conclusion'] = '让胜'
            elif rq_win <= 2.50:
                # [V19] 让分胜概率偏低，主队有防范，谨慎看好客胜
                result['conclusion'] = '让负'
                result['reason'] += ' | 让胜防范({:.2f})'.format(rq_win)
            else:
                result['conclusion'] = '让负'
            
    else: # 平手
        if rq_win < 2.0 and rq_lose > 3.0:
            result['conclusion'] = '胜'; result['reason'] = '平手主胜倾斜'
        elif rq_lose < 2.0 and rq_win > 3.0:
            result['conclusion'] = '负'; result['reason'] = '平手客胜倾斜'
        else:
            result['conclusion'] = '平'; result['reason'] = '平手胶着'

    # 兜底
    if result['conclusion'] == '观望':
        final_min = min(rq_win, rq_draw, rq_lose)
        if final_min == rq_win: result['conclusion'] = '让胜' if handicap != 0 else '胜'
        elif final_min == rq_lose: result['conclusion'] = '让负' if handicap != 0 else '负'
        else: result['conclusion'] = '让平' if handicap != 0 else '平'
        result['reason'] += ' (兜底)'
    return result

def engine_combined(data, shenjia_info):
    """引擎B：综合验证分析引擎 [V23重构] 简化为概率最低值验证器
    该引擎作为基础验证层，通过赛事末段数据最低概率方向提供基准判断。
    与其他复杂引擎形成互补：当其他引擎给出复杂信号时，本引擎提供简单基准。
    """
    jc_win, jc_draw, jc_lose = data['jc_win'], data['jc_draw'], data['jc_lose']
    result = {'engine': 'B-综合验证引擎', 'conclusion': '观望', 'reason': ''}
    final_min = min(jc_win, jc_draw, jc_lose)
    if final_min == jc_win:
        result['conclusion'] = '胜'
    elif final_min == jc_lose:
        result['conclusion'] = '负'
    else:
        result['conclusion'] = '平'
    result['reason'] = '跟随末段数据最低概率'
    return result

def engine_metrics(data, shenjia_info):
    """引擎C：数学指标引擎（终极升级 - 三维交叉验证超级计算器）
    
    三大核心升级：
    1. 引入多家机构平均概率作为真实市场基准
    2. 引入身价对比作为实力权重
    3. 三维交叉验证算法（概率偏离度 + 实力权重 + 数学指标）
    """
    jc_win, jc_draw, jc_lose = data['jc_win'], data['jc_draw'], data['jc_lose']
    avg_win, avg_draw, avg_lose = data['avg_win'], data['avg_draw'], data['avg_lose']
    z, y, x = calculate_metrics(jc_win, jc_draw, jc_lose)
    
    # ==========================================
    # 维度一：概率偏离度（赛事概率 vs 多家机构平均概率）
    # ==========================================
    # 1a. 赛事隐含概率
    jc_inv_win = 1.0 / jc_win
    jc_inv_draw = 1.0 / jc_draw
    jc_inv_lose = 1.0 / jc_lose
    jc_total = jc_inv_win + jc_inv_draw + jc_inv_lose
    jc_prob_win = jc_inv_win / jc_total
    jc_prob_draw = jc_inv_draw / jc_total
    jc_prob_lose = jc_inv_lose / jc_total
    
    # 1b. 多家机构平均概率隐含概率（全球资金真实反映）
    avg_inv_win = 1.0 / avg_win
    avg_inv_draw = 1.0 / avg_draw
    avg_inv_lose = 1.0 / avg_lose
    avg_total = avg_inv_win + avg_inv_draw + avg_inv_lose
    avg_prob_win = avg_inv_win / avg_total
    avg_prob_draw = avg_inv_draw / avg_total
    avg_prob_lose = avg_inv_lose / avg_total
    
    # 1c. 偏离度 = |赛事概率 - 多家机构概率|
    dev_win = abs(jc_prob_win - avg_prob_win)
    dev_draw = abs(jc_prob_draw - avg_prob_draw)
    dev_lose = abs(jc_prob_lose - avg_prob_lose)
    devs = {'胜': dev_win, '平': dev_draw, '负': dev_lose}
    max_dev = max(devs.values())
    max_dev_direction = max(devs, key=devs.get)
    
    # 偏离度分级（注：此处0.15为偏离度阈值，与COLD_RISK_THRESHOLD不同，属于独立阈值）
    if max_dev >= 0.15:
        deviation_level = '极高偏离'
    elif max_dev >= 0.10:
        deviation_level = '显著偏离'
    elif max_dev >= 0.05:
        deviation_level = '轻微偏离'
    else:
        deviation_level = '一致'
    
    # 多家机构和赛事看好方向
    avg_probs = {'胜': avg_prob_win, '平': avg_prob_draw, '负': avg_prob_lose}
    jc_probs = {'胜': jc_prob_win, '平': jc_prob_draw, '负': jc_prob_lose}
    avg_favors = max(avg_probs, key=avg_probs.get)
    jc_favors = max(jc_probs, key=jc_probs.get)
    market_diverge = avg_favors != jc_favors  # 多家机构和赛事看好方向不一致
    
    # ==========================================
    # 维度二：实力权重（身价对比）
    # ==========================================
    strength_bonus = {'win': 0, 'draw': 0, 'lose': 0}
    shenjia_note = ''
    
    if '未输入' in str(shenjia_info):
        shenjia_note = '身价未输入'
    elif '主身 > 客身' in str(shenjia_info):
        strength_bonus['win'] = 2
        strength_bonus['lose'] = -1
        shenjia_note = '主队身价占优(+2主胜,-1客胜)'
    elif '主身 < 客身' in str(shenjia_info):
        strength_bonus['lose'] = 2
        strength_bonus['win'] = -1
        shenjia_note = '客队身价占优(+2客胜,-1主胜)'
    elif '主身 = 客身' in str(shenjia_info):
        strength_bonus['draw'] = 1
        shenjia_note = '双方身价持平(+1平局)'
    
    # ==========================================
    # 维度三：数学指标评分（Z/Y/X结构）
    # ==========================================
    score_win = 0
    score_draw = 0
    score_lose = 0
    
    # Z = (draw*2)/(win+1)
    if z > 3.0:
        score_win += 3
    elif z > 2.0:
        score_win += 2
    elif z > 1.5:
        score_win += 1
    elif z < 1.0:
        score_lose += 2
    elif z < 1.3:
        score_lose += 1
    
    # Y = 2 - 2/(win+1)
    if y < 1.15:
        score_win += 3
    elif y < 1.25:
        score_win += 2
    elif y < 1.4:
        score_win += 1
    elif y > 1.6:
        score_lose += 2
    elif y > 1.5:
        score_lose += 1
    
    # X = (z+y)/(lose-1)
    if x < 0.5:
        score_win += 2
    elif x < 0.8:
        score_win += 1
    elif x > 2.0:
        score_lose += 2
    elif x > 1.5:
        score_lose += 1
    
    # 平局加分：三概率接近时
    odds_range = max(jc_win, jc_draw, jc_lose) - min(jc_win, jc_draw, jc_lose)
    if odds_range < 1.0:
        score_draw += 3
    elif odds_range < 1.5:
        score_draw += 2
    elif odds_range < 2.0:
        score_draw += 1
    if jc_draw <= jc_win and jc_draw <= jc_lose:
        score_draw += 1
    
    # === 应用身价权重到评分 ===
    score_win += strength_bonus['win']
    score_draw += strength_bonus['draw']
    score_lose += strength_bonus['lose']
    
    # ==========================================
    # 三维交叉验证：综合评分
    # ==========================================
    # 如果偏离度极高且多家机构与赛事方向不一致，说明赛事在诱导
    if market_diverge and max_dev >= 0.10:
        if avg_favors == '胜':
            score_win += 3
            score_lose -= 1
        elif avg_favors == '负':
            score_lose += 3
            score_win -= 1
        elif avg_favors == '平':
            score_draw += 3
            score_win -= 1
            score_lose -= 1
    
    # === 冷门风险公式（升级：用多家机构概率 vs 模型概率）===
    total_score = score_win + score_draw + score_lose
    if total_score > 0:
        model_prob_win = (score_win + 1) / (total_score + 3)
        model_prob_draw = (score_draw + 1) / (total_score + 3)
        model_prob_lose = (score_lose + 1) / (total_score + 3)
    else:
        model_prob_win = avg_prob_win
        model_prob_draw = avg_prob_draw
        model_prob_lose = avg_prob_lose
    
    cold_risk_win = avg_prob_win - model_prob_win
    cold_risk_draw = avg_prob_draw - model_prob_draw
    cold_risk_lose = avg_prob_lose - model_prob_lose
    
    cold_risks = {'胜': cold_risk_win, '平': cold_risk_draw, '负': cold_risk_lose}
    max_cold_risk = max(cold_risks.values())
    cold_risk_direction = max(cold_risks, key=cold_risks.get)
    
    # === 最终模型方向判定 ===
    model_direction = ''
    model_reason_parts = []
    
    if score_win > score_lose and score_win > score_draw:
        model_direction = '胜'
        model_reason_parts.append("主胜综合得分最高")
    elif score_lose > score_win and score_lose > score_draw:
        model_direction = '负'
        model_reason_parts.append("客胜综合得分最高")
    elif score_draw > score_win and score_draw > score_lose:
        model_direction = '平'
        model_reason_parts.append("平局综合得分最高")
    else:
        if max_cold_risk > CONFIG['COLD_RISK_THRESHOLD']:
            model_direction = cold_risk_direction
            model_reason_parts.append("冷门风险触发({:.1f}%)".format(max_cold_risk * 100))
        else:
            if score_win >= score_lose and score_win >= score_draw:
                model_direction = '胜'
                model_reason_parts.append("评分持平，模型倾向主胜")
            elif score_lose >= score_win and score_lose >= score_draw:
                model_direction = '负'
                model_reason_parts.append("评分持平，模型倾向客胜")
            else:
                model_direction = '平'
                model_reason_parts.append("评分持平，模型倾向平局")
    
    # === 最终结论：模型方向 vs 市场方向 ===
    min_odds_val = min(jc_win, jc_draw, jc_lose)
    market_direction = ''
    if abs(min_odds_val - jc_win) < 0.01:
        market_direction = '胜'
    elif abs(min_odds_val - jc_lose) < 0.01:
        market_direction = '负'
    else:
        market_direction = '平'
    
    # 构建原因字符串
    reason_parts = []
    reason_parts.append(" | ".join(model_reason_parts))
    reason_parts.append("偏离度:{}({})".format(deviation_level, max_dev_direction))
    reason_parts.append(shenjia_note)
    if market_diverge:
        reason_parts.append("多家机构看好{}但赛事不看好=诱导".format(avg_favors))
    
    if model_direction == market_direction:
        conclusion = model_direction
        reason = " | ".join(reason_parts)
    else:
        market_cold_risk = cold_risks[market_direction]
        if market_cold_risk > CONFIG['COLD_RISK_THRESHOLD']:
            conclusion = model_direction
            market_prob_val = avg_prob_win if market_direction == '胜' else (avg_prob_draw if market_direction == '平' else avg_prob_lose)
            model_prob_val = model_prob_win if model_direction == '胜' else (model_prob_draw if model_direction == '平' else model_prob_lose)
            reason = "干扰信号预警！多家机构平均概率显示{}隐含概率{:.1f}%，模型真实概率{:.1f}%，冷门风险{:.1f}%，反判【{}】！".format(
                market_direction, market_prob_val * 100, model_prob_val * 100, market_cold_risk * 100, model_direction
            )
        else:
            conclusion = model_direction
            reason = "模型独立判断为【{}】，与市场方向【{}】不一致，冷门风险{:.1f}%".format(
                model_direction, market_direction, market_cold_risk * 100
            )
    
    return {
        'engine': 'C-数学指标引擎(超级计算版)',
        'z': z, 'y': y, 'x': x,
        'conclusion': conclusion,
        'reason': reason,
        'cold_risk': max_cold_risk,
        'cold_risk_direction': cold_risk_direction,
        'deviation_level': deviation_level,
        'deviation_direction': max_dev_direction,
        'max_deviation': max_dev,
        'market_diverge': market_diverge,
        'avg_favors': avg_favors,
        'jc_favors': jc_favors,
        'strength_bonus': strength_bonus,
        'scores': {'win': score_win, 'draw': score_draw, 'lose': score_lose},
    }
def engine_shape_decision(data):
    """引擎D：概率结构形态引擎"""
    jc_win, jc_draw, jc_lose = data['jc_win'], data['jc_draw'], data['jc_lose']
    odds_map = {'胜': jc_win, '平': jc_draw, '负': jc_lose}
    sorted_odds = sorted(odds_map.items(), key=lambda x: x[1])
    pattern_str = "<".join([item[0] for item in sorted_odds])
    lowest, middle, highest = sorted_odds[0], sorted_odds[1], sorted_odds[2]
    gap_low_mid = middle[1] - lowest[1]
    
    result = {'engine': 'D-结构形态引擎', 'conclusion': '观望', 'reason': '结构: {}'.format(pattern_str)}
    
    if gap_low_mid <= 0.15 and pattern_str not in ("平<胜<负", "平<负<胜"):
        result['conclusion'] = middle[0]
        result['reason'] += ' | 低中粘连，防{}'.format(middle[0])
    elif lowest[0] == '平':
        result['conclusion'] = '平'
        result['reason'] += ' | 平概率断层领先'
    elif highest[0] == '平':
        result['conclusion'] = lowest[0]
        result['reason'] += ' | 分胜负格局，首选{}'.format(lowest[0])
    else:
        result['conclusion'] = lowest[0]
        result['reason'] += ' | 跟随最低概率'
    return result

def engine_critical_pattern(data):
    """引擎E：概率动态临界引擎"""
    jc_win, jc_draw, jc_lose = data['jc_win'], data['jc_draw'], data['jc_lose']
    odds_map = {'胜': jc_win, '平': jc_draw, '负': jc_lose}
    sorted_odds = sorted(odds_map.items(), key=lambda x: x[1])
    pattern_str = "<".join([item[0] for item in sorted_odds])
    lowest, middle, highest = sorted_odds[0], sorted_odds[1], sorted_odds[2]
    gap_low_mid = middle[1] - lowest[1]
    
    result = {'engine': 'E-动态临界引擎', 'conclusion': '观望', 'reason': '临界: {}'.format(pattern_str)}
    
    if pattern_str in ("负<平<胜", "胜<平<负"):
        if middle[1] > CONFIG['ENGINE_E_CRITICAL_DRAW']:
            result['conclusion'] = lowest[0]
            result['reason'] += ' | 平概率正常，跟随{}'.format(lowest[0])
        else:
            result['conclusion'] = '平'
            result['reason'] += ' | 平概率低位防范'
    elif gap_low_mid > 0.4:
        result['conclusion'] = lowest[0]
        result['reason'] += ' | 低概率优势巨大'
    else:
        result['conclusion'] = lowest[0]
        result['reason'] += ' | 结构均衡跟随'
    return result

# ==========================================
# 4.5 双维度共振分析模块（让分维度 + 标准维度联合分析）
# ==========================================
def analyze_risk_and_standard(data, engine_c_result, shenjia_info):
    """
    双维度共振分析函数（终极升级 - 降低冷门预警泛滥，引入多家机构概率确认）
    
    升级要点：
    1. 冷门预警需要额外确认条件（偏离度阈值、身价对比支持）
    2. 同向共振加入多家机构平均概率确认
    3. 引入引擎C的偏离度信息作为共振判断依据
    """
    handicap = data['handicap']
    rq_win, rq_draw, rq_lose = data['rq_win'], data['rq_draw'], data['rq_lose']
    jc_win, jc_draw, jc_lose = data['jc_win'], data['jc_draw'], data['jc_lose']
    avg_win, avg_draw, avg_lose = data['avg_win'], data['avg_draw'], data['avg_lose']
    
    # 获取引擎C的结论和指标
    c_conclusion = engine_c_result.get('conclusion', '观望')
    z_val = engine_c_result.get('z', 0)
    y_val = engine_c_result.get('y', 0)
    x_val = engine_c_result.get('x', 0)
    
    # 获取引擎C的偏离度信息
    deviation_level = engine_c_result.get('deviation_level', '一致')
    max_deviation = engine_c_result.get('max_deviation', 0)
    market_diverge = engine_c_result.get('market_diverge', False)
    avg_favors = engine_c_result.get('avg_favors', '')
    
    # 获取引擎A的让分结论 (V14修复：使用CONFIG统一阈值)
    rq_conclusion = ''
    if handicap >= 1:
        if rq_win < CONFIG['DEEP_ODDS_LOW']:
            rq_conclusion = '主让胜'
        elif rq_win > CONFIG['DEEP_ODDS_HIGH']:
            rq_conclusion = '主让负'
        else:
            if rq_draw < CONFIG['MID_ODDS_DRAW']:
                rq_conclusion = '主让平'
            elif rq_lose < 2.0:
                rq_conclusion = '主让负'
            else:
                rq_conclusion = '主让胜'
    elif handicap <= -1:
        if rq_lose < CONFIG['DEEP_ODDS_LOW']:
            rq_conclusion = '客让负'
        elif rq_lose > CONFIG['DEEP_ODDS_HIGH']:
            rq_conclusion = '客让胜'
        else:
            if rq_draw < CONFIG['MID_ODDS_DRAW']:
                rq_conclusion = '客让平'
            elif rq_win < 2.0:
                rq_conclusion = '客让胜'
            else:
                rq_conclusion = '客让负'
    else:
        if rq_win < 2.0 and rq_lose > 3.0:
            rq_conclusion = '平手主胜'
        elif rq_lose < 2.0 and rq_win > 3.0:
            rq_conclusion = '平手客胜'
        else:
            rq_conclusion = '平手胶着'
    
    # 映射为标准方向
    def get_direction(conc):
        if conc in ['主让胜', '平手主胜', '客让胜']:
            return '胜'
        elif conc in ['客让负', '平手客胜']:
            return '负'
        elif conc in ['主让负']:
            return '负'
        elif conc in ['主让平', '客让平', '平手胶着']:
            return '平'
        return '观望'
    
    rq_direction = get_direction(rq_conclusion)
    c_direction = c_conclusion
    
    # 判断数据面板深浅
    is_deep_handicap = abs(handicap) >= 1
    is_level_handicap = handicap == 0
    
    # Z/Y差值
    zy_gap = abs(z_val - y_val) if isinstance(z_val, (int, float)) and isinstance(y_val, (int, float)) else 0
    
    # === 共振判断逻辑（终极升级 - 降低冷门预警泛滥）===
    resonance_type = '正常'
    resonance_detail = ''
    recommendation = '观望'
    risk_level = '低'
    
    # 1. 平局共振（精准抓平）—— 优先级最高
    if c_direction == '平' and (zy_gap < CONFIG['RESONANCE_DRAW_GAP'] or rq_draw < 3.5):
        resonance_type = '平局共振'
        recommendation = '精准抓平'
        risk_level = '中'
        if is_level_handicap:
            resonance_detail = '平手/无让分 + 数学指标判定势均力敌 = 大概率真平'
        elif is_deep_handicap:
            resonance_detail = '深度让分 + 数学指标判定平局 = 深度让分干扰平局，需警惕'
        else:
            resonance_detail = '数学指标判定势均力敌(Z/Y收敛) + 让分平概率偏低 = 大概率真平'
    
    # 2. 冷门预警（深度让分干扰信号）—— 升级：需要额外确认条件
    # 原来：深度让分 + 引擎C和让分维度方向不一致 → 直接触发（太泛滥！）
    # 现在：需要满足以下至少2个条件才触发：
    #   a) 深度让分 + 引擎C和让分维度方向不一致
    #   b) 偏离度 >= 显著偏离 或 多家机构与赛事方向不一致
    #   c) 身价对比支持引擎C的方向
    elif is_deep_handicap and c_direction in ['胜', '负'] and rq_direction != '观望' and rq_direction != c_direction:
        # 计算确认条件数量
        confirm_count = 0
        confirm_reasons = []
        
        # 条件a: 偏离度确认
        if max_deviation >= 0.10 or market_diverge:
            confirm_count += 1
            confirm_reasons.append("概率偏离度确认")
        
        # 条件b: 身价对比支持引擎C方向
        strength_bonus = engine_c_result.get('strength_bonus', {})
        c_dir_key = c_direction.lower() if c_direction != '平' else 'draw'
        if c_dir_key in strength_bonus and strength_bonus[c_dir_key] > 0:
            confirm_count += 1
            confirm_reasons.append("身价对比支持")
        
        # 条件c: 多家机构平均概率也支持引擎C方向
        if avg_favors == c_direction:
            confirm_count += 1
            confirm_reasons.append("多家机构概率支持")
        
        # 只有确认条件>=2时才触发冷门预警
        if confirm_count >= 2:
            resonance_type = '冷门预警'
            recommendation = '关注低概率'
            risk_level = '高'
            if handicap > 0 and c_direction == '胜' and rq_direction == '负':
                resonance_detail = '主让深度让分但让分维度看客胜，数学指标力挺主胜 = 深度让分诱导客胜，看好主胜方向冷门 | 确认信号: ' + '、'.join(confirm_reasons)
            elif handicap < 0 and c_direction == '负' and rq_direction == '胜':
                resonance_detail = '客让深度让分但让分维度看主胜，数学指标力挺客胜 = 深度让分诱导主胜，看好客胜方向冷门 | 确认信号: ' + '、'.join(confirm_reasons)
            else:
                resonance_detail = '深度让分与数学指标方向背离，冷门信号强烈 | 确认信号: ' + '、'.join(confirm_reasons)
        else:
            # 确认条件不足，降级为"反向背离"
            resonance_type = '反向背离'
            recommendation = '警惕干扰信号'
            risk_level = '中'
            resonance_detail = '深度让分方向与数学指标不一致，但确认信号不足({}/3)，谨慎观望'
    
    # 3. 同向共振（重仓出击）—— 升级：加入多家机构概率确认
    elif rq_direction != '观望' and c_direction != '观望' and rq_direction == c_direction and zy_gap >= CONFIG['RESONANCE_DRAW_GAP']:
        # 检查多家机构概率是否也支持
        avg_confirms = (avg_favors == c_direction)
        dev_confirms = (max_deviation < 0.10)  # 偏离度低说明市场一致
        
        if avg_confirms and dev_confirms:
            resonance_type = '同向共振'
            recommendation = '重仓出击'
            risk_level = '极低'
            if rq_direction == '胜':
                resonance_detail = '让分维度+数学指标+多家机构概率三者一致看好主胜 = 极度看好主胜'
            elif rq_direction == '负':
                resonance_detail = '让分维度+数学指标+多家机构概率三者一致看好客胜 = 极度看好客胜'
            else:
                resonance_detail = '让分维度和数学指标均看好平局，多家机构概率也支持'
        else:
            # 多家机构概率不支持或偏离度高，降级为"正常"
            resonance_type = '正常'
            recommendation = '观望'
            risk_level = '低'
            detail_parts = ['双维度方向一致但']
            if not avg_confirms:
                detail_parts.append("多家机构概率未完全支持")
            if not dev_confirms:
                detail_parts.append("概率偏离度较高")
            resonance_detail = '、'.join(detail_parts) + '，信心不足'
    
    # 4. 同向但信心不足
    elif rq_direction != '观望' and c_direction != '观望' and rq_direction == c_direction and zy_gap < 0.15:
        resonance_type = '正常'
        recommendation = '观望'
        risk_level = '低'
        resonance_detail = '双维度方向一致但数学指标过于收敛，信心不足，建议观望'
    
    # 5. 反向背离（警惕干扰信号）—— 排除已处理的冷门预警和平局共振
    elif rq_direction != '观望' and c_direction != '观望' and rq_direction != c_direction:
        resonance_type = '反向背离'
        recommendation = '警惕干扰信号'
        risk_level = '中'
        if rq_direction == '胜' and c_direction in ['平', '负']:
            resonance_detail = '让分维度力挺主胜，但数学指标显示主胜支撑力下降（引擎C判{}），典型干扰信号！'.format(c_direction)
        elif rq_direction == '负' and c_direction in ['平', '胜']:
            resonance_detail = '让分维度力挺客胜，但数学指标显示客胜支撑力下降（引擎C判{}），典型干扰信号！'.format(c_direction)
        else:
            resonance_detail = '让分维度与数学指标方向背离，需谨慎对待'
    
    # 6. 正常（默认）
    else:
        resonance_type = '正常'
        resonance_detail = '未出现明显共振信号，按常规策略操作即可'
    
    return {
        'resonance_type': resonance_type,
        'resonance_detail': resonance_detail,
        'rq_conclusion': rq_conclusion,
        'rq_direction': rq_direction,
        'c_conclusion': c_conclusion,
        'c_direction': c_direction,
        'recommendation': recommendation,
        'risk_level': risk_level,
        'zy_gap': zy_gap,
        'is_deep_handicap': is_deep_handicap,
        'handicap': handicap,
    }
def _find_error_book_close(lines):
    """【V16新增】查找ERROR_BOOK列表的闭合括号位置
    使用状态机追踪，正确处理字符串字面量和注释中的方括号
    返回闭合括号行的索引，未找到返回-1
    """
    import re
    error_book_def_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if re.match(r'^\s*ERROR_BOOK\s*=\s*\[', line):
            error_book_def_lines.append(i)
    
    if not error_book_def_lines:
        return -1
    
    eb_def = error_book_def_lines[-1]
    depth = 0
    found_open = False
    
    for j in range(eb_def, len(lines)):
        line = lines[j]
        in_single_quote = False
        in_double_quote = False
        in_comment = False
        
        for idx, ch in enumerate(line):
            if ch == '#' and not in_single_quote and not in_double_quote:
                in_comment = True
                break
            
            if in_comment:
                continue
            
            if ch == "'" and not in_double_quote:
                if idx > 0 and line[idx-1] == '\\':
                    continue
                in_single_quote = not in_single_quote
                continue
            
            if ch == '"' and not in_single_quote:
                if idx > 0 and line[idx-1] == '\\':
                    continue
                in_double_quote = not in_double_quote
                continue
            
            if not in_single_quote and not in_double_quote:
                if ch == '[':
                    depth += 1
                    found_open = True
                elif ch == ']':
                    depth -= 1
                    if found_open and depth == 0:
                        return j
    
    for i in range(len(lines) - 1, eb_def, -1):
        stripped = lines[i].strip()
        if stripped == ']':
            return i
    
    return -1


def save_to_code(real_res, data, shenjia_info, real_score='', engine_results=None, resonance_info=None):
    """将错题数据追加到ERROR_BOOK（V16 终极修复版）
    V16修复:
    1. 括号追踪器正确处理字符串字面量和注释中的方括号
    2. 插入逻辑确保正确的逗号分隔
    3. 写入前后均验证文件可正常编译
    4. 验证失败自动从备份恢复
    """
    engine_summary = ''
    if engine_results:
        parts = []
        for r in engine_results:
            eng = r.get('engine', '')
            conc = r.get('conclusion', '')
            parts.append("{}={}".format(eng, conc))
        engine_summary = '|'.join(parts)
    
    resonance_type = ''
    if resonance_info:
        resonance_type = resonance_info.get('resonance_type', '')
    
    z, y, x = calculate_metrics(data['jc_win'], data['jc_draw'], data['jc_lose'])
    match_context_parts = []
    match_context_parts.append("Z={:.4f}".format(z))
    match_context_parts.append("Y={:.4f}".format(y))
    match_context_parts.append("X={:.4f}".format(x))
    if engine_results:
        for r in engine_results:
            if 'cold_risk' in r:
                match_context_parts.append("cold_risk={:.1f}%".format(r['cold_risk'] * 100))
            if 'deviation_level' in r:
                match_context_parts.append("dev_level={}".format(r['deviation_level']))
    match_context = '; '.join(match_context_parts)
    
    warn_before_save_duplicate(data)
    match_id = _assign_match_id()
    
    entry_dict = {
        'handicap': data['handicap'],
        'jc_win': data['jc_win'], 'jc_draw': data['jc_draw'], 'jc_lose': data['jc_lose'],
        'rq_win': data['rq_win'], 'rq_draw': data['rq_draw'], 'rq_lose': data['rq_lose'],
        'avg_win': data['avg_win'], 'avg_draw': data['avg_draw'], 'avg_lose': data['avg_lose'],
        'shenjia': shenjia_info, 'real_result': real_res, 'real_score': real_score,
        'engine_summary': engine_summary, 'resonance_type': resonance_type, 'match_context': match_context, 'match_id': match_id
    }
    
    # 构建条目代码（安全转义字符串特殊字符）
    parts_str = []
    for k, v in entry_dict.items():
        if isinstance(v, str):
            escaped = v.replace('\\', '\\\\').replace("'", "\\'")
            parts_str.append("'{}': '{}'".format(k, escaped))
        else:
            parts_str.append("'{}': {}".format(k, v))
    # 【V16修复】条目末尾加逗号确保列表分隔正确
    entry_code = "    {" + ", ".join(parts_str) + "},"
    
    try:
        import shutil
        backup_path = _SCRIPT_PATH + '.backup'
        try:
            shutil.copy2(_SCRIPT_PATH, backup_path)
            print("[备份] 已创建错题本备份: {}".format(backup_path))
        except Exception as backup_err:
            print("[警告] 创建备份失败: {}，继续执行但请注意风险".format(backup_err))
        
        with open(_SCRIPT_PATH, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        lines = file_content.split('\n')
        insert_idx = _find_error_book_close(lines)
        
        if insert_idx > 0:
            # 确保前一行有逗号结尾
            prev_idx = insert_idx - 1
            if prev_idx >= 0:
                prev_line = lines[prev_idx]
                stripped = prev_line.strip()
                if stripped and not stripped.endswith('},'):
                    lines[prev_idx] = prev_line.rstrip() + ','
            
            # 插入新条目
            lines.insert(insert_idx, entry_code)
            new_content = '\n'.join(lines)
            
            # 【V16修复】写入前语法验证
            try:
                compile(new_content, _SCRIPT_PATH, 'exec')
            except SyntaxError as se:
                print("[!] 写入验证失败，语法错误: {}".format(se))
                print("[!] 文件已回滚到备份状态")
                try:
                    shutil.copy2(backup_path, _SCRIPT_PATH)
                    print("[恢复] 已从备份恢复文件")
                except Exception as rollback_err:
                    print("[!] 回滚失败: {}".format(rollback_err))
                return None
            
            with open(_SCRIPT_PATH, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # 【V16修复】写入后验证
            try:
                with open(_SCRIPT_PATH, 'r', encoding='utf-8') as f:
                    compile(f.read(), _SCRIPT_PATH, 'exec')
                print("[验证] 写入后文件语法验证通过")
            except SyntaxError as se:
                print("[!] 写入后验证失败: {}".format(se))
                print("[!] 尝试从备份恢复...")
                try:
                    shutil.copy2(backup_path, _SCRIPT_PATH)
                    print("[恢复] 已从备份恢复文件")
                except Exception as rollback_err:
                    print("[!] 回滚失败: {}".format(rollback_err))
                return None
            
            ERROR_BOOK.append(entry_dict)
            print("\n[OK] 错题数据已成功追加到错题本！（含引擎结论、共振信息、比赛上下文）")
            print("[提示] 备份文件已保存为: {} + '.backup'，确认数据无误后可手动删除".format(_SCRIPT_PATH))
            return match_id
        else:
            print("\n[!] 无法定位错题本末尾，请手动添加以下数据：\n{}".format(entry_code))
    except Exception as e:
        print("\n[!] 写入失败: {}".format(e))
        import traceback
        traceback.print_exc()

def get_data_input():
    """获取用户输入的概率数据"""
    try:
        handicap = int(input("请输入主队让分数 (主让1球输入1, 客让1球输入-1, 平手/无让分输入0): ").strip())
        vals1 = list(map(float, input("请输入让分胜平负概率 (三个数字，空格分隔): ").split()))
        vals2 = list(map(float, input("请输入赛事胜平负概率 (三个数字，空格分隔): ").split()))
        vals3 = list(map(float, input("请输入多家机构平均概率 (三个数字，空格分隔): ").split()))
        if len(vals1) != 3 or len(vals2) != 3 or len(vals3) != 3:
            raise ValueError
        return {
            'handicap': handicap,
            'rq_win': vals1[0], 'rq_draw': vals1[1], 'rq_lose': vals1[2],
            'jc_win': vals2[0], 'jc_draw': vals2[1], 'jc_lose': vals2[2],
            'avg_win': vals3[0], 'avg_draw': vals3[1], 'avg_lose': vals3[2]
        }
    except Exception:
        print("输入错误，请检查格式")
        return None


def validate_odds_data(data):
    """V15修复: 验证概率数据的有效性"""
    odds_fields = ['jc_win', 'jc_draw', 'jc_lose', 'rq_win', 'rq_draw', 'rq_lose', 'avg_win', 'avg_draw', 'avg_lose']
    for field in odds_fields:
        val = data.get(field)
        if val is None:
            print("[验证失败] 缺少字段: {}".format(field))
            return False
        if not isinstance(val, (int, float)):
            print("[验证失败] 字段 {} 不是数值: {}".format(field, val))
            return False
        if val <= 0:
            print("[验证失败] 字段 {} 必须为正数: {}".format(field, val))
            return False
        if val > 100:
            print("[验证失败] 字段 {} 数值异常(>100): {}".format(field, val))
            return False
    
    # 验证让分数为整数
    handicap = data.get('handicap')
    if handicap is not None and not isinstance(handicap, int):
        print("[验证失败] 让分数必须为整数: {}".format(handicap))
        return False
    
    return True

def get_extra_inputs():
    """获取身价对比"""
    print("\n--- 请输入身价对比 ---")
    print("1. 主身 > 客身  2. 主身 < 客身  3. 主身 = 客身  0. 跳过")
    choice = input("请选择 (1/2/3/0): ").strip()
    return {'1': '主身 > 客身', '2': '主身 < 客身', '3': '主身 = 客身', '0': '未输入'}.get(choice, '未输入')

def verify_all_against_book():
    """对错题本全部数据进行回测，统计各引擎准确率"""
    if not ERROR_BOOK:
        print("\n[提示] 错题本为空，无法回测。")
        return

    print("\n" + "=" * 50)
    print(" 错题本全量回测 ({} 条数据)".format(len(ERROR_BOOK)))
    print("=" * 50)
    engine_hits = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0}
    engine_total = 0
    system_hits = 0
    system_hits_6eng = 0
    details = []

    for idx, case in enumerate(ERROR_BOOK, 1):
        shenjia = case.get('shenjia', '未输入')
        real = case['real_result']
        handicap = case['handicap']

        # 引擎A
        r_a = engine_pure_rq(case, shenjia)
        a_std = convert_rq_to_standard(handicap, r_a['conclusion'])
        a_hit = (a_std == real)
        engine_hits['A'] += 1 if a_hit else 0
        engine_total += 1
        # V15: 更新引擎性能追踪
        update_engine_performance('A', a_hit)

        # 引擎B
        r_b = engine_combined(case, shenjia)
        b_hit = (r_b['conclusion'] == real)
        engine_hits['B'] += 1 if b_hit else 0
        update_engine_performance('B', b_hit)

        # 引擎C
        r_c = engine_metrics(case, shenjia)
        c_hit = (r_c['conclusion'] == real)
        engine_hits['C'] += 1 if c_hit else 0
        update_engine_performance('C', c_hit)

        # 引擎D
        r_d = engine_shape_decision(case)
        d_hit = (r_d['conclusion'] == real)
        engine_hits['D'] += 1 if d_hit else 0
        update_engine_performance('D', d_hit)

        # 引擎E
        r_e = engine_critical_pattern(case)
        e_hit = (r_e['conclusion'] == real)
        engine_hits['E'] += 1 if e_hit else 0
        update_engine_performance('E', e_hit)

        # 引擎F（V14新增：纳入回测统计）
        r_f = engine_zone_mapping(case, shenjia)
        f_hit = (r_f['conclusion'] == real)
        engine_hits['F'] += 1 if f_hit else 0
        update_engine_performance('F', f_hit)
        # 系统综合（6引擎简单多数投票）
        votes = [a_std, r_b['conclusion'], r_c['conclusion'], r_d['conclusion'], r_e['conclusion'], r_f['conclusion']]
        vote_count = {}
        for v in votes: vote_count[v] = vote_count.get(v, 0) + 1
        sys_pred = max(vote_count, key=vote_count.get)
        sys_hit = (sys_pred == real)
        system_hits += 1 if sys_hit else 0
        system_hits_6eng += sys_hit


        details.append({
            'idx': idx, 'handicap': handicap, 'real': real,
            'a': r_a['conclusion'], 'a_std': a_std, 'b': r_b['conclusion'],
            'c': r_c['conclusion'], 'd': r_d['conclusion'], 'e': r_e['conclusion'],
            'system': sys_pred, 'hit': sys_hit
        })

    # 打印各引擎准确率（移到循环外）
    print("\n--- 各引擎准确率 ---")
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        rate = (engine_hits[key] / engine_total * 100) if engine_total > 0 else 0
        print(" 引擎{}: {:.1f}% ({}/{})".format(key, rate, engine_hits[key], engine_total))

    sys_rate = system_hits / engine_total * 100 if engine_total > 0 else 0
    sys_rate_6 = system_hits_6eng / engine_total * 100 if engine_total > 0 else 0
    print("-" * 30)
    print(" 系统综合(6引擎): {:.1f}% ({}/{})".format(sys_rate, system_hits, engine_total))
    print(" 系统综合(6引擎-备用): {:.1f}% ({}/{})".format(sys_rate_6, system_hits_6eng, engine_total))
    
    # V15新增: 输出引擎性能权重
    print("\n--- V15 引擎性能权重(自适应) ---")
    current_weights = get_engine_weights()
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        perf = _ENGINE_PERFORMANCE[key]
        rate = (perf['hits'] / perf['total'] * 100) if perf['total'] > 0 else 0
        print("  引擎{}: 准确率{:.1f}%({}/{}) 权重{:.2f}".format(
            key, rate, perf['hits'], perf['total'], current_weights.get(key, 1.0)))
    
    # 【新增】比分准确率统计
    score_total = 0
    score_exact = 0
    score_direction = 0
    for case in ERROR_BOOK:
        rs = case.get('real_score', '')
        if rs and ':' in rs:
            score_total += 1
            pred = predict_score(case)
            pred_score = pred['predicted_score']
            ph, pa = map(int, pred_score.split(":"))
            rh, ra = map(int, rs.split(":"))
            if rs == pred_score:
                score_exact += 1
            elif (rh > ra and ph > pa) or (rh < ra and ph < pa) or (rh == ra and ph == pa):
                score_direction += 1
    
    if score_total > 0:
        exact_rate = score_exact / score_total * 100
        dir_rate = score_direction / score_total * 100
        print(" 比分精确命中: {:.1f}% ({}/{})".format(exact_rate, score_exact, score_total))
        print(" 比分方向正确: {:.1f}% ({}/{})".format(dir_rate, score_direction, score_total))
    
    print("=" * 50)
    input("\n按回车键返回主菜单...")


# ==========================================
# 6. 主控分析函数
# ==========================================

def generate_review_report(data, shenjia_info, matched_results, engine_results, resonance, score_pred, final_conclusion):
    """生成智能复盘报告 (V11 新增)"""
    handicap = data['handicap']
    h_str = "主让{}球".format(handicap) if handicap > 0 else "客让{}球".format(abs(handicap)) if handicap < 0 else "平手/无让分"
    print("\n" + "=" * 60)
    print("  智 能 复 盘 报 告 (V11)")
    print("=" * 60)
    print("\n【当前比赛概况】")
    print("  让分面板: {} | 身价对比: {}".format(h_str, shenjia_info))
    print("  赛事概率: 胜 {} | 平 {} | 负 {}".format(data['jc_win'], data['jc_draw'], data['jc_lose']))
    print("  让分概率: 胜 {} | 平 {} | 负 {}".format(data['rq_win'], data['rq_draw'], data['rq_lose']))
    avg_w = data.get('avg_win', 0)
    if avg_w:
        print("  多家机构平均: 胜 {} | 平 {} | 负 {}".format(avg_w, data.get('avg_draw', 0), data.get('avg_lose', 0)))
    print("\n【相似案例模式分析】")
    if matched_results:
        high_sim = [m for m in matched_results if m.get('similarity_score', 0) >= 0.85]
        print("  总匹配案例数: {} 个".format(len(matched_results)))
        print("  高相似度案例(>=85%): {} 个".format(len(high_sim)))
        if high_sim:
            high_result_count = {}
            for m in high_sim:
                r = m.get('real_result', '')
                high_result_count[r] = high_result_count.get(r, 0) + 1
            print("  高相似度案例结果分布:")
            for r, c in sorted(high_result_count.items(), key=lambda x: -x[1]):
                print("    {} : {} 次 ({:.1f}%)".format(r, c, c / len(high_sim) * 100))
            all_result_count = {}
            for m in matched_results:
                r = m.get('real_result', '')
                all_result_count[r] = all_result_count.get(r, 0) + 1
            print("  全部匹配案例结果分布:")
            for r, c in sorted(all_result_count.items(), key=lambda x: -x[1]):
                print("    {} : {} 次 ({:.1f}%)".format(r, c, c / len(matched_results) * 100))
            avg_jc = sum(m['score_details']['jc_odds'] for m in high_sim) / len(high_sim)
            avg_rq = sum(m['score_details']['handicap_odds'] for m in high_sim) / len(high_sim)
            avg_avg = sum(m['score_details']['avg_odds'] for m in high_sim) / len(high_sim)
            avg_hap = sum(m['score_details']['handicap_shape'] for m in high_sim) / len(high_sim)
            avg_met = sum(m['score_details']['metrics'] for m in high_sim) / len(high_sim)
            avg_str = sum(m['score_details']['strength'] for m in high_sim) / len(high_sim)
            print("  高相似度案例平均维度评分:")
            print("    赛事概率: {:.4f} | 让分概率: {:.4f} | 多家机构平均: {:.4f}".format(avg_jc, avg_rq, avg_avg))
            print("    让分形态: {:.4f} | 数学指标: {:.4f} | 身价对比: {:.4f}".format(avg_hap, avg_met, avg_str))
    else:
        print("  未找到高度相似的历史案例，建议参考基本面分析。")
    if matched_results:
        print("\n【详细匹配案例（全部）】")
        for idx, m in enumerate(matched_results, 1):
            sim = m.get('similarity_score', 0)
            sd = m.get('score_details', {})
            mid = m.get('match_id', '')
            mid_str = '[{}] '.format(mid) if mid else ''
            print("  --- {}案例 {} (相似度: {:.1f}%) ---".format(mid_str, idx, sim * 100))
            print("    让分: {} | 身价: {}".format(
                "主让{}球".format(m['handicap']) if m['handicap'] > 0 else
                "客让{}球".format(abs(m['handicap'])) if m['handicap'] < 0 else "平手/无让分",
                m.get('shenjia', '未输入')))
            print("    赛事概率: 胜{} | 平{} | 负{}".format(m['jc_win'], m['jc_draw'], m['jc_lose']))
            print("    维度评分: 赛事{:.2f} 让分{:.2f} 多家机构{:.2f} 形态{:.2f} 指标{:.2f} 身价{:.2f}".format(
                sd.get('jc_odds', 0), sd.get('handicap_odds', 0), sd.get('avg_odds', 0),
                sd.get('handicap_shape', 0), sd.get('metrics', 0), sd.get('strength', 0)))
            print("    结果: {} | 比分: {}".format(m.get('real_result', ''), m.get('real_score', '')))
    print("\n【引擎投票总结】")
    for res in engine_results:
        eng = res.get('engine', '')
        conc = res.get('conclusion', '')
        reason = res.get('reason', '')
        print("  {} -> {} ({})".format(eng, conc, reason[:30] if len(reason) > 30 else reason))
    print("\n【共振信号总结】")
    print("  共振类型: {} | 建议: {} | 风险: {}".format(
        resonance['resonance_type'], resonance['recommendation'], resonance['risk_level']))
    print("\n【比分预测】")
    print("  最可能比分: {} (概率: {})".format(score_pred['predicted_score'], score_pred['top3_probs'][0]))
    alt = score_pred.get('alt_scores', [])
    probs = score_pred.get('top3_probs', [])
    if len(alt) > 1:
        print("  备选: {} (概率: {}) | {} (概率: {})".format(alt[0], probs[1] if len(probs) > 1 else '-',
            alt[1] if len(alt) > 1 else '-', probs[2] if len(probs) > 2 else '-'))
    print("\n" + "=" * 40 + " 综合复盘结论 " + "=" * 40)
    if matched_results:
        high_sim_results = [m for m in matched_results if m.get('similarity_score', 0) >= 0.85]
        if high_sim_results:
            high_result_count = {}
            for m in high_sim_results:
                r = m.get('real_result', '')
                high_result_count[r] = high_result_count.get(r, 0) + 1
            most_common_hist = max(high_result_count, key=high_result_count.get)
            hist_ratio = high_result_count[most_common_hist] / len(high_sim_results)
            print("  历史模式: 高相似度案例中【{}】出现最多 ({:.1f}%)".format(most_common_hist, hist_ratio * 100))
            if most_common_hist == final_conclusion:
                print("  交叉验证: 历史模式与引擎判定【{}】一致，结论可信度较高！".format(final_conclusion))
            else:
                print("  交叉验证: 历史模式【{}】与引擎判定【{}】不一致，需警惕冷门风险！".format(most_common_hist, final_conclusion))
    else:
        print("  无相似案例参考，建议结合基本面独立判断。")
    if final_conclusion == '观望':
        print('\n  最终建议: 【观望】本场风控信号不足以下单, 请勿建仓')
    else:
        print("\n  最终建议: 重点关注【{}】".format(final_conclusion))
    print("=" * 60)




# ==========================================

# 7.5 数据指纹比分分析引擎（V15+ 新增）

# 说明：基于「让分面板 + 身价对比 + 平均概率指向」三维指纹，

#       匹配历史数据中相同指纹的最常见比分，为比分预测提供数据支撑

# ==========================================



# 数据指纹比分数据库（从赛事数据指纹比分分析Excel中提取的核心指纹->比分映射）

FINGERPRINT_SCORE_DB = {

    '主让1球+主身>客身+平均指向主胜': {

        'top1_score': '2:0', 'top1_count': 208, 'top2_score': '1:0', 'top2_count': 149,

        'total': 447, 'win': 229, 'draw': 109, 'lose': 109

    },

    '客让1球+主身<客身+平均指向客胜': {

        'top1_score': '1:1', 'top1_count': 103, 'top2_score': '0:2', 'top2_count': 101,

        'total': 307, 'win': 72, 'draw': 72, 'lose': 163

    },

    '主让1球+主身<客身+平均指向主胜': {

        'top1_score': '1:0', 'top1_count': 90, 'top2_score': '1:1', 'top2_count': 67,

        'total': 172, 'win': 77, 'draw': 59, 'lose': 36

    },

    '主让1球+未输入+平均指向主胜': {

        'top1_score': '2:0', 'top1_count': 26, 'top2_score': '1:0', 'top2_count': 16,

        'total': 52, 'win': 26, 'draw': 18, 'lose': 8

    },

    '客让1球+主身>客身+平均指向客胜': {

        'top1_score': '0:1', 'top1_count': 16, 'top2_score': '1:1', 'top2_count': 15,

        'total': 33, 'win': 18, 'draw': 6, 'lose': 9

    },

    '主让1球+主身<客身+平均指向客胜': {

        'top1_score': '1:1', 'top1_count': 24, 'top2_score': '1:0', 'top2_count': 4,

        'total': 30, 'win': 14, 'draw': 12, 'lose': 4

    },

    '主让2球+主身>客身+平均指向主胜': {

        'top1_score': '3:0', 'top1_count': 28, 'top2_score': '-', 'top2_count': 0,

        'total': 28, 'win': 25, 'draw': 3, 'lose': 0

    },

    '客让1球+主身<客身+平均指向主胜': {

        'top1_score': '1:1', 'top1_count': 17, 'top2_score': '0:1', 'top2_count': 6,

        'total': 23, 'win': 5, 'draw': 4, 'lose': 14

    },

    '客让1球+未输入+平均指向客胜': {

        'top1_score': '0:2', 'top1_count': 11, 'top2_score': '1:1', 'top2_count': 6,

        'total': 19, 'win': 4, 'draw': 2, 'lose': 13

    },

    '客让2球+未输入+平均指向客胜': {

        'top1_score': '0:3', 'top1_count': 11, 'top2_score': '-', 'top2_count': 0,

        'total': 11, 'win': 0, 'draw': 0, 'lose': 11

    },

    '客让1球+主身>客身+平均指向主胜': {

        'top1_score': '1:1', 'top1_count': 10, 'top2_score': '-', 'top2_count': 0,

        'total': 10, 'win': 0, 'draw': 6, 'lose': 4

    },

    '客让2球+主身<客身+平均指向客胜': {

        'top1_score': '0:3', 'top1_count': 9, 'top2_score': '-', 'top2_count': 0,

        'total': 9, 'win': 0, 'draw': 0, 'lose': 9

    },

    '主让1球+主身<客身+平均指向平局': {

        'top1_score': '1:0', 'top1_count': 4, 'top2_score': '1:1', 'top2_count': 2,

        'total': 6, 'win': 0, 'draw': 2, 'lose': 4

    },

    '主让1球+主身>客身+平均指向客胜': {

        'top1_score': '1:1', 'top1_count': 4, 'top2_score': '-', 'top2_count': 0,

        'total': 4, 'win': 2, 'draw': 2, 'lose': 0

    },

    '主让2球+主身<客身+平均指向主胜': {

        'top1_score': '3:0', 'top1_count': 4, 'top2_score': '-', 'top2_count': 0,

        'total': 4, 'win': 4, 'draw': 0, 'lose': 0

    },

    '主让1球+主身=客身+平均指向主胜': {

        'top1_score': '1:1', 'top1_count': 2, 'top2_score': '2:0', 'top2_count': 1,

        'total': 3, 'win': 0, 'draw': 1, 'lose': 2

    },

    '客让1球+未输入+平均指向主胜': {

        'top1_score': '1:1', 'top1_count': 2, 'top2_score': '-', 'top2_count': 0,

        'total': 2, 'win': 0, 'draw': 2, 'lose': 0

    },

    '主让2球+未输入+平均指向主胜': {

        'top1_score': '3:0', 'top1_count': 2, 'top2_score': '-', 'top2_count': 0,

        'total': 2, 'win': 0, 'draw': 0, 'lose': 2

    },

}







# ==========================================
# 7.6 零球/一球数据指纹识别系统（V15+ 新增）
# ==========================================
# 说明：基于赛事数据指纹分析结果，建立0球(0:0)和1球(1:0/0:1)的指纹特征库，
#       当输入比赛数据匹配到对应指纹时，自动识别并输出清晰的指纹分析结果
# 数据来源：赛事数据指纹分析_有比分归档.xlsx
#   - "0球数据指纹" sheet: 32条0:0记录的特征统计
#   - "1球数据指纹" sheet: 65条1球记录(1:0+0:1)的特征统计
#   - "指纹对比总览" sheet: 0球vs1球的关键差异维度

# ---------- 0球(0:0)数据指纹特征库 ----------
# 来源："0球数据指纹" sheet
# 统计基础：32条记录，占有比分记录比例6.3%
# 核心特征：100%为平局 | 平概率3.x + 让平概率3.x + 赛事胜概率2.x分散
ZERO_GOAL_FINGERPRINT = {
    'name': '0球(0:0)指纹',
    'target_score': '0:0',
    'description': '零球平局指纹 - 当比赛数据匹配此指纹时，高度疑似0:0平局',
    # 让分面板特征：主让1球65.6%，客让1球34.4%
    'handicap_values': [1, -1],
    'handicap_preference': '主让1球(65.6%) > 客让1球(34.4%)',
    # 神秘家特征：主身<客身53.1%，主身>客身37.5%
    'shenjia_values': ['主身 < 客身', '主身 > 客身'],
    'shenjia_preference': '主身<客身(53.1%)略多于主身>客身(37.5%)',
    # 概率特征指纹
    'odds_profile': {
        'jc_draw_range': (3.0, 4.0),       # 赛事平概率集中在3.0-4.0区间(81.2%)
        'rq_draw_range': (3.0, 4.0),       # 让分平概率集中在3.0-4.0区间(90.6%)
        'avg_draw_range': (3.0, 4.0),      # 平均平概率集中在3.0-4.0区间(87.5%)
        'jc_win_mean': 2.40,               # 赛事胜均值2.40
        'jc_draw_mean': 3.40,              # 赛事平均值3.40
        'jc_lose_mean': 3.02,              # 赛事负均值3.02
        'rq_win_mean': 3.17,               # 让分胜均值3.17
        'rq_draw_mean': 3.72,              # 让分平均值3.72
        'rq_lose_mean': 2.61,              # 让分负均值2.61
    },
    # 赛事胜概率分布：<2.0占37.5%，2.0-3.0占46.9%（分散）
    'jc_win_distribution': '分散型(<2.0:37.5%, 2.0-3.0:46.9%)',
    # 识别关键词
    'key_phrase': '平概率3.x + 让平概率3.x + 赛事胜概率2.x的组合',
    # 实际赛果：100%为平局
    'actual_result': '平',
    'actual_score': '0:0',
    'record_count': 32,
    'record_ratio': '6.3%',
    # 基础置信度
    'confidence_base': 0.85,
}

# ---------- 1球(1:0/0:1)数据指纹特征库 ----------
# 来源："1球数据指纹" sheet
# 统计基础：65条记录，占有比分记录比例12.8%
# 比分构成：1:0(33条) + 0:1(32条) 几乎均分
# 核心特征：胜/负几乎均分(50.8%/50.8%) | 反向背离共振占主导(64.9%)
ONE_GOAL_FINGERPRINT = {
    'name': '1球(1:0/0:1)指纹',
    'target_scores': ['1:0', '0:1'],
    'description': '一球指纹 - 当比赛数据匹配此指纹时，高度疑似1球赛果(1:0或0:1)',
    # 让分面板特征：主让1球66.2%，客让1球32.3%
    'handicap_values': [1, -1],
    'handicap_preference': '主让1球(66.2%) > 客让1球(32.3%)',
    # 神秘家特征：主身<客身52.3%，主身>客身46.2%（几乎均衡）
    'shenjia_values': ['主身 < 客身', '主身 > 客身'],
    'shenjia_preference': '主身<客身(52.3%)与主身>客身(46.2%)几乎均衡',
    # 概率特征指纹
    'odds_profile': {
        'jc_draw_range': (3.0, 4.0),       # 赛事平概率集中在3.0-4.0区间(75.4%)
        'rq_draw_range': (3.0, 4.0),       # 让分平概率集中在3.0-4.0区间(86.2%)
        'avg_draw_range': (3.0, 4.0),      # 平均平概率集中在3.0-4.0区间(86.2%)
        'jc_win_mean': 2.65,               # 赛事胜均值2.65
        'jc_draw_mean': 3.57,              # 赛事平均值3.57
        'jc_lose_mean': 3.29,              # 赛事负均值3.29
        'rq_win_mean': 3.14,               # 让分胜均值3.14
        'rq_draw_mean': 3.62,              # 让分平均值3.62
        'rq_lose_mean': 2.44,              # 让分负均值2.44
    },
    # 引擎结论指纹（有引擎总结的记录中的统计）
    'engine_patterns': {
        'engine_a': {'让负': 0.432, '让平': 0.243, '让胜': 0.324},
        'engine_b': {'胜': 0.649, '负': 0.351},
        'engine_c': {'负': 0.459, '胜': 0.541},
        'engine_d': {'胜': 0.649, '负': 0.351},
        'engine_e': {'胜': 0.568, '负': 0.351, '平': 0.081},
        'engine_f': {'负': 0.750, '胜': 0.250},
    },
    # 共振类型指纹
    'resonance_pattern': {
        '反向背离': 0.649,
        '正常': 0.162,
        '同向共振': 0.135,
        '冷门预警': 0.054,
    },
    # 实际赛果分布：胜50.8% / 负50.8%（完全均衡，无方向倾向）
    'result_distribution': {'胜': 0.508, '负': 0.508},
    # 识别关键词
    'key_phrase': '平概率3.x + 让平概率3.x + 共振类型=反向背离 + 引擎F指向负',
    # 基础置信度
    'confidence_base': 0.80,
    'record_count': 65,
    'record_ratio': '12.8%',
}

# ---------- 指纹对比总览（关键区分维度） ----------
# 来源："指纹对比总览" sheet
# 0球vs1球的核心差异维度，用于区分两者
GOAL_FINGERPRINT_COMPARISON = {
    'record_count': {'0球': '32条', '1球': '65条'},
    'score_composition': {'0球': '仅0:0', '1球': '1:0(33条)+0:1(32条)'},
    'handicap': {
        '0球': '主让1球65.6% / 客让1球34.4%',
        '1球': '主让1球66.2% / 客让1球32.3% / 客让2球1.5%'
    },
    'jc_draw_mean': {'0球': '3.40', '1球': '3.57'},
    'rq_draw_mean': {'0球': '3.72', '1球': '3.62'},
    'avg_draw_mean': {'0球': '3.52', '1球': '3.59'},
    'shenjia_tendency': {
        '0球': '主身<客身53.1% (偏客强)',
        '1球': '主身<客身52.3% / 主身>客身46.2% (均衡)'
    },
    'actual_result': {'0球': '100%平', '1球': '胜50.8%/负50.8%(完全均衡)'},
    'resonance_type': {'0球': '数据不足', '1球': '反向背离64.9%(主导特征)'},
    'engine_f_tendency': {'0球': '数据不足', '1球': '负75.0%(强烈倾向)'},
    'core_identifier': {
        '0球': '平概率3.x + 让平概率3.x + 赛事胜概率2.x分散',
        '1球': '平概率3.x + 让平概率3.x + 反向背离共振 + 引擎F指向负'
    },
}

# ==========================================
# [V17新增] 0球/1球指纹识别阈值配置（可调参数）
# 说明：提高阈值可减少误报，只有高度匹配的比赛才会触发指纹识别
# 建议值：85以上才有参考价值（低于此值的匹配视为"弱信号"，不触发预警）
# ==========================================
GOAL_FINGERPRINT_ZERO_THRESHOLD = 90   # [V18优化] 从85提升至90，进一步减少误报   # 0球(0:0)指纹匹配阈值（得分>=此值才触发）
GOAL_FINGERPRINT_ONE_THRESHOLD = 90    # [V18优化] 从85提升至90，进一步减少误报     # 1球(1:0/0:1)指纹匹配阈值（得分>=此值才触发）



def check_goal_fingerprint(data, engine_results=None, resonance_info=None):
    """检查输入比赛数据是否匹配0球或1球指纹特征

    参数:
        data: 比赛数据字典，包含 handicap, jc_win, jc_draw, jc_lose,
              rq_win, rq_draw, rq_lose, avg_win, avg_draw, avg_lose, shenjia
        engine_results: 引擎分析结果列表（可选），用于引擎指纹匹配
        resonance_info: 共振分析结果字典（可选），用于共振类型匹配

    返回:
        dict: 包含匹配结果和详细分析信息
            - matched: 是否匹配到指纹
            - match_type: 'zero_goal'(0球) / 'one_goal'(1球) / None
            - match_score: 匹配得分(0-100)
            - fingerprint: 匹配的指纹名称
            - details: 详细匹配信息
    """
    if engine_results is None:
        engine_results = []
    if resonance_info is None:
        resonance_info = {}

    results = []

    # ========== 0球指纹匹配 ==========
    zero_score = _check_zero_goal_fingerprint(data)
    if zero_score['match']:
        results.append(zero_score)

    # ========== 1球指纹匹配 ==========
    one_score = _check_one_goal_fingerprint(data, engine_results, resonance_info)
    if one_score['match']:
        results.append(one_score)

    # 返回最佳匹配
    if results:
        best = max(results, key=lambda x: x['match_score'])
        return {
            'matched': True,
            'match_type': best['match_type'],
            'match_score': best['match_score'],
            'fingerprint': best['fingerprint'],
            'description': best['description'],
            'details': best.get('details', {}),
            'all_matches': results,
        }

    return {
        'matched': False,
        'match_type': None,
        'match_score': 0,
        'fingerprint': None,
        'description': '当前比赛数据未匹配到0球或1球指纹特征',
        'details': {},
        'all_matches': [],
    }


def _check_zero_goal_fingerprint(data):
    """检查是否匹配0球(0:0)指纹

    匹配维度：
    1. 让分面板：主让1球或客让1球
    2. 赛事平概率：3.0-4.0区间
    3. 让分平概率：3.0-4.0区间
    4. 平均平概率：3.0-4.0区间
    5. 赛事胜概率：分散型（<2.0或2.0-3.0）
    """
    score = 0
    checks = []

    # 维度1: 让分面板 (权重25分)
    handicap = data.get('handicap', 0)
    if handicap in [1, -1]:
        score += 25
        h_str = "主让{}球".format(handicap) if handicap > 0 else "客让{}球".format(abs(handicap))
        checks.append({'check': '让分面板', 'value': h_str, 'match': True, 'weight': 25})
    else:
        checks.append({'check': '让分面板', 'value': '平手/无让分或其他', 'match': False, 'weight': 0})

    # 维度2: 赛事平概率区间 (权重25分)
    jc_draw = data.get('jc_draw', 0)
    if 3.0 <= jc_draw <= 4.0:
        score += 25
        checks.append({'check': '赛事平概率', 'value': str(jc_draw), 'match': True, 'weight': 25, 'note': '集中在3.0-4.0区间(81.2%)'})
    else:
        checks.append({'check': '赛事平概率', 'value': str(jc_draw) if jc_draw else '未输入', 'match': False, 'weight': 0, 'note': '0球特征:集中在3.0-4.0区间'})

    # 维度3: 让分平概率区间 (权重20分)
    rq_draw = data.get('rq_draw', 0)
    if 3.0 <= rq_draw <= 4.0:
        score += 20
        checks.append({'check': '让分平概率', 'value': str(rq_draw), 'match': True, 'weight': 20, 'note': '集中在3.0-4.0区间(90.6%)'})
    else:
        checks.append({'check': '让分平概率', 'value': str(rq_draw) if rq_draw else '未输入', 'match': False, 'weight': 0, 'note': '0球特征:集中在3.0-4.0区间'})

    # 维度4: 平均平概率区间 (权重15分)
    avg_draw = data.get('avg_draw', 0)
    if 3.0 <= avg_draw <= 4.0:
        score += 15
        checks.append({'check': '平均平概率', 'value': str(avg_draw), 'match': True, 'weight': 15, 'note': '集中在3.0-4.0区间(87.5%)'})
    else:
        checks.append({'check': '平均平概率', 'value': str(avg_draw) if avg_draw else '未输入', 'match': False, 'weight': 0, 'note': '0球特征:集中在3.0-4.0区间'})

    # 维度5: 赛事胜概率分散型 (权重15分)
    jc_win = data.get('jc_win', 0)
    if jc_win and (jc_win < 2.0 or (2.0 <= jc_win <= 3.0)):
        score += 15
        checks.append({'check': '赛事胜概率', 'value': str(jc_win), 'match': True, 'weight': 15, 'note': '分散型分布'})
    else:
        checks.append({'check': '赛事胜概率', 'value': str(jc_win) if jc_win else '未输入', 'match': False, 'weight': 0, 'note': '0球特征:分散型(<2.0:37.5%, 2.0-3.0:46.9%)'})

    # [V18新增] 额外过滤条件：两队期望进球都低时才匹配0球指纹
    # 避免在强队对决中误触发0:0指纹
    jc_win_val = data.get('jc_win', 0)
    jc_lose_val = data.get('jc_lose', 0)
    jc_draw_val = data.get('jc_draw', 0)
    
    # 条件：赛事胜概率不能太低(低于1.30说明强弱悬殊，不太可能0:0)
    # 且赛事负概率不能太低(低于1.30说明强弱悬殊，不太可能0:0)
    # 且平概率不能太高(高于4.0说明不太看好平局)
    extra_filter_score = 0
    if jc_win_val > 1.30 and jc_lose_val > 1.30:
        extra_filter_score += 5  # 双方都不是绝对热门，增加0:0可能性
        checks.append({'check': 'V18强弱过滤', 'value': '双方非绝对热门', 'match': True, 'weight': 5, 'note': '双方概率均>1.30，存在0:0可能'})
    else:
        checks.append({'check': 'V18强弱过滤', 'value': '存在绝对热门', 'match': False, 'weight': 5, 'note': '存在强弱悬殊，0:0概率极低'})
    
    if jc_draw_val > 4.0:
        extra_filter_score += 0  # 平概率偏高，不太看好平局
        checks.append({'check': 'V18平概率过滤', 'value': '平概率>4.0', 'match': False, 'weight': 3, 'note': '平概率偏高，0:0可能性降低'})
    else:
        extra_filter_score += 3
        checks.append({'check': 'V18平概率过滤', 'value': '平概率<=4.0', 'match': True, 'weight': 3, 'note': '平概率合理，支持0:0可能'})
    
    score += extra_filter_score
    
    # 调整置信度（根据匹配维度数量）
    matched_count = sum(1 for c in checks if c.get('match'))
    confidence_adjust = matched_count / len(checks) if checks else 1.0
    final_score = score * confidence_adjust

    return {
        'match_type': 'zero_goal',
        'match': final_score >= GOAL_FINGERPRINT_ZERO_THRESHOLD,
        'match_score': round(final_score, 1),
        'fingerprint': '0球(0:0)指纹',
        'description': '匹配到0球(0:0)指纹特征',
        'target_score': '0:0',
        'actual_result': '平',
        'checks': checks,
        'matched_count': matched_count,
        'total_checks': len(checks),
        'key_phrase': ZERO_GOAL_FINGERPRINT['key_phrase'],
        'record_info': '历史样本{}条(占比{})'.format(
            ZERO_GOAL_FINGERPRINT['record_count'],
            ZERO_GOAL_FINGERPRINT['record_ratio']
        ),
    }


def _check_one_goal_fingerprint(data, engine_results=None, resonance_info=None):
    """检查是否匹配1球(1:0/0:1)指纹

    匹配维度：
    1. 让分面板：主让1球或客让1球
    2. 赛事平概率：3.0-4.0区间
    3. 让分平概率：3.0-4.0区间
    4. 平均平概率：3.0-4.0区间
    5. 引擎结论指纹（如果有引擎数据）
    6. 共振类型指纹（如果有共振数据）
    """
    score = 0
    checks = []

    # 维度1: 让分面板 (权重20分)
    handicap = data.get('handicap', 0)
    if handicap in [1, -1]:
        score += 20
        h_str = "主让{}球".format(handicap) if handicap > 0 else "客让{}球".format(abs(handicap))
        checks.append({'check': '让分面板', 'value': h_str, 'match': True, 'weight': 20})
    else:
        checks.append({'check': '让分面板', 'value': '平手/无让分或其他', 'match': False, 'weight': 0})

    # 维度2: 赛事平概率区间 (权重20分)
    jc_draw = data.get('jc_draw', 0)
    if 3.0 <= jc_draw <= 4.0:
        score += 20
        checks.append({'check': '赛事平概率', 'value': str(jc_draw), 'match': True, 'weight': 20, 'note': '集中在3.0-4.0区间(75.4%)'})
    else:
        checks.append({'check': '赛事平概率', 'value': str(jc_draw) if jc_draw else '未输入', 'match': False, 'weight': 0, 'note': '1球特征:集中在3.0-4.0区间'})

    # 维度3: 让分平概率区间 (权重15分)
    rq_draw = data.get('rq_draw', 0)
    if 3.0 <= rq_draw <= 4.0:
        score += 15
        checks.append({'check': '让分平概率', 'value': str(rq_draw), 'match': True, 'weight': 15, 'note': '集中在3.0-4.0区间(86.2%)'})
    else:
        checks.append({'check': '让分平概率', 'value': str(rq_draw) if rq_draw else '未输入', 'match': False, 'weight': 0, 'note': '1球特征:集中在3.0-4.0区间'})

    # 维度4: 平均平概率区间 (权重15分)
    avg_draw = data.get('avg_draw', 0)
    if 3.0 <= avg_draw <= 4.0:
        score += 15
        checks.append({'check': '平均平概率', 'value': str(avg_draw), 'match': True, 'weight': 15, 'note': '集中在3.0-4.0区间(86.2%)'})
    else:
        checks.append({'check': '平均平概率', 'value': str(avg_draw) if avg_draw else '未输入', 'match': False, 'weight': 0, 'note': '1球特征:集中在3.0-4.0区间'})

    # 维度5: 引擎结论指纹 (权重15分) - 如果有引擎数据
    engine_score = _check_engine_fingerprint(data, engine_results)
    score += engine_score['score']
    checks.extend(engine_score['checks'])

    # 维度6: 共振类型指纹 (权重15分) - 如果有共振数据
    resonance_score = _check_resonance_fingerprint(resonance_info)
    score += resonance_score['score']
    checks.extend(resonance_score['checks'])

    # 调整置信度
    matched_count = sum(1 for c in checks if c.get('match'))
    confidence_adjust = matched_count / len(checks) if checks else 1.0
    final_score = score * confidence_adjust

    return {
        'match_type': 'one_goal',
        'match': final_score >= GOAL_FINGERPRINT_ONE_THRESHOLD,
        'match_score': round(final_score, 1),
        'fingerprint': '1球(1:0/0:1)指纹',
        'description': '匹配到1球(1:0/0:1)指纹特征',
        'target_scores': ['1:0', '0:1'],
        'result_distribution': '胜50.8%/负50.8%(完全均衡)',
        'checks': checks,
        'matched_count': matched_count,
        'total_checks': len(checks),
        'key_phrase': ONE_GOAL_FINGERPRINT['key_phrase'],
        'record_info': '历史样本{}条(占比{})'.format(
            ONE_GOAL_FINGERPRINT['record_count'],
            ONE_GOAL_FINGERPRINT['record_ratio']
        ),
    }


def _check_engine_fingerprint(data, engine_results):
    """检查引擎结论是否匹配1球指纹的引擎模式"""
    checks = []
    score = 0

    if not engine_results:
        checks.append({'check': '引擎结论指纹', 'value': '无引擎数据', 'match': False, 'weight': 0, 'note': '1球特征:可提供引擎指纹分析'})
        return {'score': 0, 'checks': checks}

    # 解析引擎结论
    engine_conclusions = {}
    for eng in engine_results:
        eng_name = eng.get('engine', '')
        conclusion = eng.get('conclusion', '')
        if eng_name:
            engine_conclusions[eng_name] = conclusion

    # 引擎F(概率区间映射)倾向分析 - 1球指纹中引擎F强烈倾向"负"(75.0%)
    eng_f = engine_conclusions.get('F', '')
    if eng_f == '负':
        score += 15
        checks.append({'check': '引擎F(概率区间)', 'value': '负', 'match': True, 'weight': 15, 'note': '1球指纹中引擎F倾向负75.0%'})
    elif eng_f == '胜':
        score += 5
        checks.append({'check': '引擎F(概率区间)', 'value': '胜', 'match': False, 'weight': 15, 'note': '1球指纹中引擎F倾向负75.0%(本场指向胜，减弱匹配)'})
    else:
        checks.append({'check': '引擎F(概率区间)', 'value': eng_f or '未输出', 'match': False, 'weight': 0, 'note': '1球特征:引擎F倾向负75.0%'})

    # 引擎B(综合验证)倾向分析 - 1球指纹中引擎B倾向胜(64.9%)
    eng_b = engine_conclusions.get('B', '')
    if eng_b == '胜':
        score += 5
        checks.append({'check': '引擎B(综合验证)', 'value': '胜', 'match': True, 'weight': 5, 'note': '1球指纹中引擎B倾向胜64.9%'})
    elif eng_b == '负':
        score += 3
        checks.append({'check': '引擎B(综合验证)', 'value': '负', 'match': False, 'weight': 5, 'note': '1球指纹中引擎B倾向胜64.9%'})
    else:
        checks.append({'check': '引擎B(综合验证)', 'value': eng_b or '未输出', 'match': False, 'weight': 0})

    return {'score': min(score, 15), 'checks': checks}


def _check_resonance_fingerprint(resonance_info):
    """检查共振类型是否匹配1球指纹的共振模式"""
    checks = []
    score = 0

    if not resonance_info:
        checks.append({'check': '共振类型指纹', 'value': '无共振数据', 'match': False, 'weight': 0, 'note': '1球特征:可提供共振分析'})
        return {'score': 0, 'checks': checks}

    r_type = resonance_info.get('resonance_type', '')

    # 1球指纹中"反向背离"占主导(64.9%)
    if r_type == '反向背离':
        score += 15
        checks.append({'check': '共振类型', 'value': '反向背离', 'match': True, 'weight': 15, 'note': '1球指纹中反向背离占64.9%(主导特征)'})
    elif r_type in ['正常', '同向共振', '冷门预警']:
        score += 5
        checks.append({'check': '共振类型', 'value': r_type, 'match': False, 'weight': 15, 'note': '1球指纹中反向背离占64.9%(本场为{}，减弱匹配)'.format(r_type)})
    else:
        checks.append({'check': '共振类型', 'value': r_type or '未输出', 'match': False, 'weight': 0, 'note': '1球特征:反向背离占主导(64.9%)'})

    return {'score': min(score, 15), 'checks': checks}


def print_goal_fingerprint_result(result):
    """打印0球/1球指纹分析结果（格式化输出）"""
    print("\n" + "=" * 50)
    print("  【V15+ 零球/一球指纹识别】")
    print("=" * 50)

    if not result.get('matched'):
        print("[指纹识别] 当前比赛数据未匹配到0球或1球指纹特征")
        print("[说明] 该场比赛不太可能是0:0或1球(1:0/0:1)的赛果，请参考其他分析引擎")
        return

    match_type = result['match_type']
    match_score = result['match_score']

    # 根据匹配类型输出不同内容
    if match_type == 'zero_goal':
        print("\n" + "!" * 30)
        print("  >>> 检测到【0球(0:0)】指纹特征 <<<")
        print("!" * 30)
        print("[指纹名称] {}".format(result['fingerprint']))
        print("[匹配得分] {}/100 (阈值>=85匹配)".format(match_score))
        print("[目标比分] {}".format(result.get('target_score', '0:0')))
        print("[预测赛果] {}".format(result.get('actual_result', '平')))
        print("[历史样本] {}".format(result.get('record_info', '')))
        print("[识别关键词] {}".format(result.get('key_phrase', '')))
        print("\n--- 匹配维度详情 ---")
        for c in result.get('checks', []):
            status = "PASS" if c.get('match') else "FAIL"
            note = " [{}]".format(c['note']) if c.get('note') else ""
            print("  {} {} | 值: {} | 权重: {}分{}".format(
                status, c['check'], c['value'], c['weight'], note
            ))
        print("\n[指纹提示] >>> 该场比赛数据高度匹配0球(0:0)指纹特征！")
        print("[指纹提示] >>> 历史{}场0:0比赛中，100%打出平局，建议重点关注平局选项！".format(
            ZERO_GOAL_FINGERPRINT['record_count']
        ))

    elif match_type == 'one_goal':
        print("\n" + "!" * 30)
        print("  >>> 检测到【1球(1:0/0:1)】指纹特征 <<<")
        print("!" * 30)
        print("[指纹名称] {}".format(result['fingerprint']))
        print("[匹配得分] {}/100 (阈值>=85匹配)".format(match_score))
        print("[目标比分] {}".format(' / '.join(result.get('target_scores', ['1:0', '0:1']))))
        print("[赛果分布] {}".format(result.get('result_distribution', '胜50.8%/负50.8%')))
        print("[历史样本] {}".format(result.get('record_info', '')))
        print("[识别关键词] {}".format(result.get('key_phrase', '')))
        print("\n--- 匹配维度详情 ---")
        for c in result.get('checks', []):
            status = "PASS" if c.get('match') else "FAIL"
            note = " [{}]".format(c['note']) if c.get('note') else ""
            print("  {} {} | 值: {} | 权重: {}分{}".format(
                status, c['check'], c['value'], c['weight'], note
            ))

        # 如果有引擎指纹详情
        engine_checks = [c for c in result.get('checks', []) if '引擎' in c.get('check', '')]
        if engine_checks:
            print("\n--- 引擎指纹分析 ---")
            for c in engine_checks:
                status = "PASS" if c.get('match') else "FAIL"
                note = " [{}]".format(c['note']) if c.get('note') else ""
                print("  {} {} | 值: {}{}".format(status, c['check'], c['value'], note))

        # 如果有共振指纹详情
        resonance_checks = [c for c in result.get('checks', []) if '共振' in c.get('check', '')]
        if resonance_checks:
            print("\n--- 共振指纹分析 ---")
            for c in resonance_checks:
                status = "PASS" if c.get('match') else "FAIL"
                note = " [{}]".format(c['note']) if c.get('note') else ""
                print("  {} {} | 值: {}{}".format(status, c['check'], c['value'], note))

        print("\n[指纹提示] >>> 该场比赛数据高度匹配1球(1:0/0:1)指纹特征！")
        print("[指纹提示] >>> 历史{}场1球比赛中，反向背离共振占主导(64.9%)，".format(
            ONE_GOAL_FINGERPRINT['record_count']
        ))
        print("[指纹提示] >>> 胜/负几乎均分(50.8%/50.8%)，无明显方向倾向，建议关注1球比分选项！")

    # 如果有多个匹配，显示对比
    all_matches = result.get('all_matches', [])
    if len(all_matches) > 1:
        print("\n--- 多指纹匹配对比 ---")
        for m in all_matches:
            print("  {} | 得分: {}/100 | {}".format(
                m['fingerprint'], m['match_score'],
                '匹配' if m['match'] else '未匹配'
            ))

    print("=" * 50)


def compare_zero_vs_one_fingerprint(data, engine_results=None, resonance_info=None):
    """对比0球和1球指纹的匹配程度，给出区分建议"""
    zero_result = _check_zero_goal_fingerprint(data)
    one_result = _check_one_goal_fingerprint(data, engine_results, resonance_info)

    zero_score = zero_result['match_score'] if zero_result['match'] else 0
    one_score = one_result['match_score'] if one_result['match'] else 0

    print("\n" + "=" * 50)
    print("  【0球 vs 1球 指纹对比】")
    print("=" * 50)
    print("[当前数据] 让分:{} | 赛事平概率:{} | 让分平概率:{} | 平均平概率:{}".format(
        data.get('handicap', 'N/A'),
        data.get('jc_draw', 'N/A'),
        data.get('rq_draw', 'N/A'),
        data.get('avg_draw', 'N/A'),
    ))
    print("-" * 40)

    # 打印对比表
    header = "{:<20} {:<32} {:<32}".format("指纹维度", "0球(0:0)特征", "1球(1:0/0:1)特征")
    print(header)
    print("-" * 88)
    for key in GOAL_FINGERPRINT_COMPARISON:
        label = key.replace('_', ' ')
        val_0 = GOAL_FINGERPRINT_COMPARISON[key].get('0球', 'N/A')
        val_1 = GOAL_FINGERPRINT_COMPARISON[key].get('1球', 'N/A')
        print("{:<20} {:<32} {:<32}".format(label, val_0, val_1))

    print("-" * 40)
    print("[0球匹配度] {}/100 {}".format(zero_score, "(匹配)" if zero_result['match'] else "(未匹配)"))
    print("[1球匹配度] {}/100 {}".format(one_score, "(匹配)" if one_result['match'] else "(未匹配)"))

    if zero_result['match'] and one_result['match']:
        if zero_score > one_score:
            print("[区分结论] >>> 当前数据更偏向【0球(0:0)】指纹特征，0球可能性大于1球")
        elif one_score > zero_score:
            print("[区分结论] >>> 当前数据更偏向【1球(1:0/0:1)】指纹特征，1球可能性大于0球")
        else:
            print("[区分结论] >>> 0球和1球指纹匹配度接近，需结合其他分析维度综合判断")
    elif zero_result['match']:
        print("[区分结论] >>> 当前数据匹配【0球(0:0)】指纹，不匹配1球指纹")
    elif one_result['match']:
        print("[区分结论] >>> 当前数据匹配【1球(1:0/0:1)】指纹，不匹配0球指纹")
    else:
        print("[区分结论] >>> 当前数据不匹配0球或1球指纹特征")

    print("=" * 50)

def generate_analysis_fingerprint(data):

    """生成分析用数据指纹（三维：让分面板 + 身价对比 + 平均概率指向）

    

    指纹格式示例：'主让1球+主身>客身+平均指向主胜'

    用于匹配指纹比分数据库

    """

    # 1. 让分面板部分

    handicap = data.get('handicap', 0)

    if handicap > 0:

        fp_handicap = '主让{}球'.format(handicap)

    elif handicap < 0:

        fp_handicap = '客让{}球'.format(abs(handicap))

    else:

        fp_handicap = '平手/无让分'

    

    # 2. 身价对比部分

    shenjia = data.get('shenjia', data.get('shenjia_info', '未输入'))

    if shenjia == '主身 > 客身':

        fp_shen = '主身>客身'

    elif shenjia == '主身 < 客身':

        fp_shen = '主身<客身'

    elif shenjia == '主身 = 客身':

        fp_shen = '主身=客身'

    else:

        fp_shen = '未输入'

    

    # 3. 平均概率指向部分

    avg_win = data.get('avg_win', 0)

    avg_draw = data.get('avg_draw', 0)

    avg_lose = data.get('avg_lose', 0)

    

    if avg_win and avg_draw and avg_lose:

        if avg_win <= avg_draw and avg_win <= avg_lose:

            fp_avg = '平均指向主胜'

        elif avg_lose <= avg_win and avg_lose <= avg_draw:

            fp_avg = '平均指向客胜'

        else:

            fp_avg = '平均指向平局'

    else:

        fp_avg = '平均指向主胜'

    

    # 拼接指纹

    fingerprint = '{}+{}+{}'.format(fp_handicap, fp_shen, fp_avg)

    return fingerprint





def fingerprint_score_predict(data):

    """根据数据指纹查询最可能比分（数据指纹比分分析引擎）

    

    返回:

        dict: 包含指纹匹配结果和比分预测

    """

    fingerprint = generate_analysis_fingerprint(data)

    

    # 精确匹配

    if fingerprint in FINGERPRINT_SCORE_DB:

        info = FINGERPRINT_SCORE_DB[fingerprint]

        total = info['total']

        win_rate = info['win'] / total * 100 if total > 0 else 0

        draw_rate = info['draw'] / total * 100 if total > 0 else 0

        lose_rate = info['lose'] / total * 100 if total > 0 else 0

        

        if info['win'] >= info['draw'] and info['win'] >= info['lose']:

            highest = '主胜'

        elif info['lose'] >= info['win'] and info['lose'] >= info['draw']:

            highest = '客胜'

        else:

            highest = '平局'

        

        return {

            'fingerprint': fingerprint,

            'matched': True,

            'top1_score': info['top1_score'],

            'top1_count': info['top1_count'],

            'top2_score': info['top2_score'],

            'top2_count': info['top2_count'],

            'total': total,

            'win': info['win'], 'draw': info['draw'], 'lose': info['lose'],

            'win_rate': round(win_rate, 1),

            'draw_rate': round(draw_rate, 1),

            'lose_rate': round(lose_rate, 1),

            'highest': highest,

            'message': '[数据指纹分析] 匹配到指纹库，样本{}场'.format(total)

        }

    

    # 模糊匹配：身价未输入时尝试匹配任意身价

    fp_normalized = fingerprint.replace('未输入', '*')

    for key, info in FINGERPRINT_SCORE_DB.items():

        key_normalized = key.replace('主身>客身', '*').replace('主身<客身', '*').replace('主身=客身', '*')

        if key_normalized == fp_normalized and '*' in key_normalized:

            total = info['total']

            win_rate = info['win'] / total * 100 if total > 0 else 0

            draw_rate = info['draw'] / total * 100 if total > 0 else 0

            lose_rate = info['lose'] / total * 100 if total > 0 else 0

            

            if info['win'] >= info['draw'] and info['win'] >= info['lose']:

                highest = '主胜'

            elif info['lose'] >= info['win'] and info['lose'] >= info['draw']:

                highest = '客胜'

            else:

                highest = '平局'

            

            return {

                'fingerprint': fingerprint,

                'matched': True,

                'top1_score': info['top1_score'],

                'top1_count': info['top1_count'],

                'top2_score': info['top2_score'],

                'top2_count': info['top2_count'],

                'total': total,

                'win': info['win'], 'draw': info['draw'], 'lose': info['lose'],

                'win_rate': round(win_rate, 1),

                'draw_rate': round(draw_rate, 1),

                'lose_rate': round(lose_rate, 1),

                'highest': highest,

                'message': '[数据指纹分析] 模糊匹配到指纹库（身价未输入），样本{}场'.format(total)

            }

    

    # 未匹配

    return {

        'fingerprint': fingerprint,

        'matched': False,

        'top1_score': '-',

        'top1_count': 0,

        'top2_score': '-',

        'top2_count': 0,

        'total': 0,

        'win': 0, 'draw': 0, 'lose': 0,

        'win_rate': 0, 'draw_rate': 0, 'lose_rate': 0,

        'highest': '-',

        'message': '[数据指纹分析] 当前指纹在历史库中无匹配记录，请参考泊松分布比分预测'

    }





def print_fingerprint_analysis(fingerprint_result):

    """打印数据指纹比分分析结果"""

    print("\n" + "=" * 50)

    print("  数据指纹比分分析（历史指纹库匹配）")

    print("=" * 50)

    print("[当前指纹] {}".format(fingerprint_result['fingerprint']))

    print("[匹配状态] {}".format(fingerprint_result['message']))

    

    if fingerprint_result['matched']:

        print("[样本总量] {} 场".format(fingerprint_result['total']))

        print("[胜平负分布] 主胜:{}场({:.1f}%) | 平局:{}场({:.1f}%) | 客胜:{}场({:.1f}%)".format(

            fingerprint_result['win'], fingerprint_result['win_rate'],

            fingerprint_result['draw'], fingerprint_result['draw_rate'],

            fingerprint_result['lose'], fingerprint_result['lose_rate']

        ))

        print("[最可能比分] {} (历史出现{}次)".format(

            fingerprint_result['top1_score'], fingerprint_result['top1_count']

        ))

        if fingerprint_result['top2_score'] != '-':

            print("[次可能比分] {} (历史出现{}次)".format(

                fingerprint_result['top2_score'], fingerprint_result['top2_count']

            ))

        print("[最高概率指向] {}".format(fingerprint_result['highest']))

        

        # 高概率提示

        if fingerprint_result['total'] >= 10:

            if fingerprint_result['highest'] == '主胜' and fingerprint_result['win_rate'] >= 50:

                print("[指纹提示] >>> 该指纹下主胜率达{:.1f}%，主胜信号强烈！".format(fingerprint_result['win_rate']))

            elif fingerprint_result['highest'] == '客胜' and fingerprint_result['lose_rate'] >= 50:

                print("[指纹提示] >>> 该指纹下客胜率达{:.1f}%，客胜信号强烈！".format(fingerprint_result['lose_rate']))

            elif fingerprint_result['highest'] == '平局' and fingerprint_result['draw_rate'] >= 30:

                print("[指纹提示] >>> 该指纹下平局率达{:.1f}%，平局值得关注！".format(fingerprint_result['draw_rate']))

    else:

        print("[提示] 当前比赛数据指纹在历史库中无直接匹配")

        print("[建议] 可参考上方泊松分布比分预测结果，或等待更多历史数据积累")

# ==========================================
# [V24新增] 冷门预测独立模块
# 独立阈值: CONFIG['COLD_UPSET_GAP_THRESHOLD'] = 0.01
# ==========================================
# 设计说明:
# 1) 本模块与引擎C的 cold_risk、干扰信号检测、COLD_RATIO_THRESHOLD 等原有冷门逻辑完全解耦,
#    冷门是否预测只由本模块 + 本模块独立阈值控制。
# 2) 冷门场景定义(严格遵循用户口径):
#    - "实际赛果方向" = 输入的赛事胜平负概率 jc_win/jc_draw/jc_lose 中【最大值】所对应的结果方向
#      (概率最大 = 机构最不看好的方向, 该方向打出即为冷门);
#    - 当"预测结果"与"实际赛果方向"【不同】时, 本场属于冷门场景。
# 3) 触发规则: 只有当 冷门方向概率 与 预测方向概率 的差距落在 0.01 范围内(<= 0.01)时,
#    才进行冷门预测(把结论改判为冷门方向);
#    差距 > 0.01 说明两项概率区分度明确, 维持原预测, 不进行冷门预测。
COLD_RESULT_ODDS_KEY = {'胜': 'jc_win', '平': 'jc_draw', '负': 'jc_lose'}


# ==========================================
# [V28新增] 信心区间追踪分析器
# ==========================================
class ConfidenceTracker:
    """[V28] 自动记录每次预测的信心指数与实际结果，按区间统计命中率"""
    
    def __init__(self):
        self.history = []  # [{'prediction': '胜', 'confidence': 0.85, 'actual': '胜', 'match_info': '...', 'timestamp': ...}]
    
    def record_prediction(self, prediction, confidence, match_info=''):
        """记录一次预测（赛前提出的方向和信心）"""
        if not CONFIG.get('CONFIDENCE_TRACKING_ENABLED', True):
            return
        import datetime
        self.history.append({
            'prediction': prediction,
            'confidence': confidence,
            'actual': None,  # 赛果待填入
            'match_info': str(match_info)[:80],
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            'hit': None  # 待实际结果填入后判定
        })
    
    def record_actual_result(self, match_info, actual_result):
        """填入实际赛果，自动匹配最近的未判定记录"""
        if not CONFIG.get('CONFIDENCE_TRACKING_ENABLED', True):
            return
        # 从后往前找最近一条未判定的记录
        for record in reversed(self.history):
            if record['actual'] is None:
                record['actual'] = actual_result
                record['hit'] = (record['prediction'] == actual_result)
                break
    
    def get_confidence_zone(self, confidence):
        """[V29] 将信心指数映射到回测校准的三档区间(放弃/降仓/正常), 阈值来自CONFIG可配项,
        未校准或不可用时回退默认三档, 不再用肉眼挑的固定点。"""
        high = CONFIG.get('ZONE_HIGH_CUT')
        mid = CONFIG.get('ZONE_MID_CUT')
        if high is None:
            high = CONFIG.get('ZONE_DEFAULT_HIGH', 0.78)
        if mid is None:
            mid = CONFIG.get('ZONE_DEFAULT_MID', 0.62)
        if confidence >= high:
            return '正常区(信心>=%.2f)' % high
        elif confidence >= mid:
            return '降仓区(%.2f<=信心<%.2f)' % (mid, high)
        else:
            return '放弃区(信心<%.2f)' % mid
    
    def get_zone_stats(self):
        """按信心区间统计命中率"""
        # 只统计已填入实际结果的记录
        settled = [r for r in self.history if r['actual'] is not None]
        if not settled:
            return '暂无已完成的预测数据用于统计'
        
        zone_data = {}
        for record in settled:
            zone = self.get_confidence_zone(record['confidence'])
            if zone not in zone_data:
                zone_data[zone] = {'total': 0, 'hit': 0, 'miss': 0}
            zone_data[zone]['total'] += 1
            if record['hit']:
                zone_data[zone]['hit'] += 1
            else:
                zone_data[zone]['miss'] += 1
        
        # 按命中率排序
        zone_list = []
        for zone, stats in zone_data.items():
            rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
            zone_list.append((zone, stats['total'], stats['hit'], stats['miss'], rate))
        
        # 按命中率降序排列
        zone_list.sort(key=lambda x: x[4], reverse=True)
        
        return zone_list, settled
    
    def print_report(self):
        """打印信心区间分析报告"""
        print("\n" + "=" * 60)
        print("  [V28] 信心区间命中率分析报告")
        print("=" * 60)
        # [修复] 追踪器无已结算记录(无赛后录入)时, 回退到既有错题本派生的信心记录。
        if len([r for r in self.history if r.get('actual') is not None]) < CONFIG.get('CALIB_MIN_SAMPLES', 15):
            self.history = book_confidence_records()
        result = self.get_zone_stats()
        if isinstance(result, str):
            print(result)
            return
        
        zone_list, settled = result
        total = len(settled)
        total_hit = sum(1 for r in settled if r['hit'])
        overall_rate = total_hit / total * 100 if total > 0 else 0
        
        print(f"  总预测数: {total}  |  命中: {total_hit}  |  未命中: {total - total_hit}  |  总体命中率: {overall_rate:.1f}%")
        print("-" * 60)
        print(f"  {'信心区间':<16} {'总场次':>6} {'命中':>4} {'未中':>4} {'命中率':>8}")
        print("-" * 60)
        
        # 逐档打印各信心区间命中率(此处区间已是V29三档)
        for zone, total_z, hit_z, miss_z, rate in zone_list:
            print(f"  {zone:<22} {total_z:>6} {hit_z:>4} {miss_z:>4} {rate:>7.1f}%")
        print("-" * 60)
        # [V29] 不再肉眼挑0.01/单点, 而是跑约登指数+滚动交叉验证自动校准三档阈值
        if CONFIG.get('CALIBRATION_ENABLED', True):
            calibrate_confidence_zones(settled)
        else:
            print('  [提示] V29回测校准已关闭(CALIBRATION_ENABLED=False), 沿用CONFIG现有三档阈值')
        print("=" * 60)


# [V28新增] 全局信心追踪器实例
confidence_tracker = ConfidenceTracker()


# ==========================================
# [V29新增] 信心区间回测校准：约登指数 + ROC/AUC + 时间序列滚动交叉验证
# 目的：把"0.01单点/肉眼挑最稳区间"换成数据驱动、可配、稳定的三档阈值。
# 设计依据(用户分析)：好的阈值应是"区间"不是"点"; 0.01差异会让结论翻转=阈值不稳定;
#                    冷门是多信号叠加问题, 不能靠单评分一刀切。
# 全部使用标准库, 不依赖numpy/pandas。
# ==========================================
import bisect as _bisect
import datetime as _dt


def _auc_mannwhitney(pos_scores, neg_scores):
    """ROC下面积AUC(Mann-Whitney U), pos=命中样本信心, neg=未命中样本信心。返回[0,1]。"""
    if not pos_scores or not neg_scores:
        return 0.5
    pos = sorted(pos_scores)
    neg = sorted(neg_scores)
    # 对每个pos, 统计neg中小于它的数量(=rank), ties按0.5计
    auc_sum = 0.0
    for p in pos:
        lo = _bisect.bisect_left(neg, p)
        hi = _bisect.bisect_right(neg, p)
        less = lo
        equal = hi - lo
        auc_sum += less + 0.5 * equal
    return auc_sum / (len(pos) * len(neg))


def _youden_cutpoint(scores, labels):
    """约登指数找最佳截断点: 最大化 J = 敏感度 + 特异度 - 1。
    scores: 信心(越大越应判命中); labels: True=命中,False=未命中。
    候选阈值取相邻分数中点, 判定规则 conf>=cut 视为预测命中。
    返回 (最佳cut, 最佳J)。样本单一类别时返回 (None, -1)。"""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None, -1.0
    uniq = sorted(set(scores))
    best_cut, best_j = None, -2.0
    for i in range(len(uniq) - 1):
        cut = (uniq[i] + uniq[i + 1]) / 2.0
        sens = sum(1 for s in pos if s >= cut) / len(pos)     # 命中里被正确留在高信心区
        spec = sum(1 for s in neg if s < cut) / len(neg)      # 未命中里被正确排除到低信心区
        j = sens + spec - 1.0
        if j > best_j:
            best_j, best_cut = j, cut
    return best_cut, best_j


def _rolling_cutpoints(settled, folds):
    """时间序列滚动交叉验证: 按录入时序(timestamp)排序后等分成folds块,
    每块各算约登高/中分界, 返回各折cut序列。块内单类别的折跳过。"""
    def _key(r):
        ts = r.get('timestamp')
        try:
            return _dt.datetime.strptime(ts, '%Y-%m-%d %H:%M')
        except Exception:
            return _dt.datetime.min
    ordered = sorted(settled, key=_key)
    n = len(ordered)
    fold_h, fold_m = [], []
    if folds < 1:
        folds = 1
    size = max(2, n // folds)
    for fi in range(0, n, size):
        chunk = ordered[fi:fi + size]
        if len(chunk) < 3:
            continue
        sc = [c['confidence'] for c in chunk]
        lb = [bool(c['hit']) for c in chunk]
        high, _ = _youden_cutpoint(sc, lb)
        if high is None:
            continue
        fold_h.append(high)
        # 第二档: 在低于high的样本里再跑一次约登, 找降仓/放弃分界
        low_sc = [s for s in sc if s < high]
        low_lb = [y for s, y in zip(sc, lb) if s < high]
        mid, _ = _youden_cutpoint(low_sc, low_lb)
        fold_m.append(mid if mid is not None else high)
    return fold_h, fold_m


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def calibrate_confidence_zones(settled):
    """[V29] 对已结算的(信心,命中)记录做回测校准, 写回CONFIG三档阈值并打印报告。
    核心结论: 信心对命中是否有区分力(AUC)? 约登最佳截断点在哪? 各折是否稳定?
    稳定则采用校准区间; 样本不足或阈值漂移则回归默认三档, 绝不做0.01单点硬切。"""
    print("\n" + "=" * 60)
    print("  [V29] 信心区间回测校准 (约登指数 + ROC/AUC + 滚动交叉验证)")
    print("=" * 60)

    default_high = CONFIG.get('ZONE_DEFAULT_HIGH', 0.78)
    default_mid = CONFIG.get('ZONE_DEFAULT_MID', 0.62)
    min_n = CONFIG.get('CALIB_MIN_SAMPLES', 15)
    folds = CONFIG.get('CALIB_CV_FOLDS', 3)
    tol = CONFIG.get('CALIB_STABILITY_TOL', 0.06)

    n = len(settled)
    pos = [r['confidence'] for r in settled if r.get('hit')]
    neg = [r['confidence'] for r in settled if not r.get('hit')]
    print("  已结算样本: {} (命中{} / 未命中{})".format(n, len(pos), len(neg)))

    # AUC 区分力
    auc = _auc_mannwhitney(pos, neg)
    CONFIG['ZONE_CALIB_AUC'] = round(auc, 3)
    print("  [AUC] 信心评分对命中的区分能力 = {:.3f}  ({})".format(
        auc, '有区分力, 适合设区间' if auc >= 0.60 else ('弱区分力, 谨慎设区间' if auc >= 0.55 else '接近随机, 不宜设区间/保守用默认')))

    # 样本不足: 不校准, 沿用默认(防小样本过拟合)
    if n < min_n or not pos or not neg:
        CONFIG['ZONE_HIGH_CUT'] = default_high
        CONFIG['ZONE_MID_CUT'] = default_mid
        CONFIG['ZONE_CALIB_STABLE'] = False
        print("  [提示] 样本不足(<{}条)或缺单类别, 沿用默认三档: 正常区>=%.2f / 降仓区%.2f-%.2f / 放弃区<%.2f".format(
            min_n, default_high, default_mid, default_high, default_mid))
        print("=" * 60)
        return {'high': default_high, 'mid': default_mid, 'auc': auc, 'stable': False, 'source': 'default-样本不足'}

    # 全样本约登高/中分界
    high_all, j_high = _youden_cutpoint([r['confidence'] for r in settled],
                                        [bool(r['hit']) for r in settled])
    low_sc = [r['confidence'] for r in settled if r['confidence'] < (high_all if high_all is not None else 1.0)]
    low_lb = [bool(r['hit']) for r in settled if r['confidence'] < (high_all if high_all is not None else 1.0)]
    mid_all, j_mid = _youden_cutpoint(low_sc, low_lb)

    # 滚动交叉验证: 看阈值稳不稳
    fold_h, fold_m = _rolling_cutpoints(settled, folds)
    h_std = _stdev(fold_h)
    m_std = _stdev(fold_m)
    stable = (len(fold_h) >= 2) and (h_std <= tol) and (m_std <= tol) and (auc >= 0.55)

    print("  [约登] 全样本高信心分界 cut={:.3f} (J={:.3f}); 降仓/放弃分界 cut={}".format(
        high_all if high_all is not None else float('nan'), j_high,
        '{:.3f} (J={:.3f})'.format(mid_all, j_mid) if mid_all is not None else 'N/A(下半区无单类样本)'))
    if fold_h:
        print("  [交叉验证 {}折] 高分界均值{:.3f} 标准差{:.3f} | 中分界均值{:.3f} 标准差{:.3f}".format(
            len(fold_h), _mean(fold_h), h_std, _mean(fold_m), m_std))
    print("  [稳定性] 阈值标准差高{:.3f}/中{:.3f} <= 容差{:.2f} 且 AUC>=0.55 => {}".format(
        h_std, m_std, tol, '稳定, 采用校准区间' if stable else '漂移大/区分弱, 保守用默认区间(拒绝单点硬切)'))

    if stable and high_all is not None:
        # 采用各折均值(更鲁棒), 保证 mid < high
        high = round(_mean(fold_h) if fold_h else high_all, 3)
        mid = round(_mean(fold_m) if fold_m else (mid_all if mid_all is not None else default_mid), 3)
        if mid >= high:
            mid = round(high - 0.08, 3)
        source = '约登+交叉验证(稳定)'
    else:
        high = default_high
        mid = default_mid
        source = '默认区间(不稳定/样本不足/弱区分)'

    CONFIG['ZONE_HIGH_CUT'] = high
    CONFIG['ZONE_MID_CUT'] = mid
    CONFIG['ZONE_CALIB_STABLE'] = stable

    print("  >>> [V29结论] 三档阈值(写回CONFIG可配, 来源: {}):".format(source))
    print("      正常区: 信心 >= {:.3f}  -> 标准仓/正常输出".format(high))
    print("      降仓区: {:.3f} <= 信心 < {:.3f}  -> 保留方向但降仓".format(mid, high))
    print("      放弃区: 信心 < {:.3f}  -> 整体降权/放弃(非0.01单点判定)".format(mid))
    print("      说明: 采用区间而非单点, 阈值经约登指数与滚动验证; 若阈值随样本漂移会自动退回默认, 避免过拟合。")
    print("=" * 60)
    return {'high': high, 'mid': mid, 'auc': auc, 'stable': stable, 'source': source}




# ==========================================
# [V28新增] 冷门赛前预过滤函数
# ==========================================
def cold_match_pre_filter(data):
    """[V28] 赛前冷门特征扫描 - 在跑完整分析之前先筛掉高危冷门场
    
    检测特征:
    1. 平概率偏低 + 热门概率不高 = 胶着干扰信号形态
    2. 概率极差过小 = 市场无法区分
    3. 让分面板与概率指向矛盾
    
    返回: (is_cold: bool, reasons: list)
    """
    if not CONFIG.get('COLD_PRE_FILTER_ENABLED', True):
        return False, []
    
    reasons = []
    jc_win = data.get('jc_win', 0)
    jc_draw = data.get('jc_draw', 0)
    jc_lose = data.get('jc_lose', 0)
    handicap = data.get('handicap', 0)
    
    # 特征1: 平概率偏低(<=阈值) 且 最热门方向概率不够低
    draw_max = CONFIG.get('COLD_PRE_FILTER_DRAW_MAX', 3.40)
    if jc_draw > 0 and jc_draw <= draw_max:
        # 计算最热门方向概率
        tri_odds = [v for v in (jc_win, jc_draw, jc_lose) if v > 0]
        fav_odds = min(tri_odds) if tri_odds else 999
        if fav_odds >= 1.50:  # 热门概率不够低，说明数据机构对热门没信心
            reasons.append(f'平概率{jc_draw:.2f}偏低+热门概率{fav_odds:.2f}偏高，平局高危形态')
    
    # 特征2: 概率极差过小(三结果过于接近)
    odds_range_min = CONFIG.get('COLD_PRE_FILTER_ODDS_RANGE_MIN', 0.6)
    if jc_win > 0 and jc_draw > 0 and jc_lose > 0:
        odds_range = max(jc_win, jc_draw, jc_lose) - min(jc_win, jc_draw, jc_lose)
        if odds_range <= odds_range_min:
            reasons.append(f'概率极差{odds_range:.2f}过小(<=阈值{odds_range_min})，市场无法区分')
    
    # 特征3: 让分面板与赛事概率指向矛盾
    # 如果赛事概率指向主胜但让分是客让，或者反过来
    jc_fav = 'home' if jc_win <= jc_lose else 'away'  # 赛事看好的方向
    hc = 'home' if handicap > 0 else ('away' if handicap < 0 else 'even')  # 让分方向
    
    if jc_fav != hc and jc_fav != 'even' and hc != 'even':
        # 赛事和让分方向相反
        fav_label = '主胜' if jc_fav == 'home' else '客胜'
        hc_label = '主让' if hc == 'home' else '客让'
        reasons.append(f'赛事看{fav_label}但数据面板开{hc_label}，方向矛盾')
    
    # 特征4: 三项概率比值接近(最高/最低 < 1.5)
    if jc_win > 0 and jc_draw > 0 and jc_lose > 0:
        odds_ratio = max(jc_win, jc_draw, jc_lose) / min(jc_win, jc_draw, jc_lose)
        if odds_ratio < 1.5:
            reasons.append(f'概率比值{odds_ratio:.2f}接近(<=1.5)，三结果概率太均匀')
    
    signal_threshold = CONFIG.get('COLD_PRE_FILTER_SIGNAL_THRESHOLD', 2)
    is_cold = len(reasons) >= signal_threshold
    
    if is_cold:
        print("\n" + "=" * 50)
        print("  [V28冷门预过滤] 检测到以下冷门特征:")
        for idx, r in enumerate(reasons, 1):
            print(f"    {idx}. {r}")
        skip_mode = CONFIG.get('COLD_PRE_FILTER_SKIP', True)
        if skip_mode:
            print("  [V28冷门预过滤] 已达到过滤阈值({}个信号>={}), 本场直接跳过!".format(len(reasons), signal_threshold))
            print("  [V28建议] 该场冷门风险较高，建议放弃本场，等待更清晰的场次")
        else:
            print("  [V28冷门预过滤] 已达到预警阈值，仅提示不跳过，请自行判断")
        print("=" * 50)
    
    return is_cold, reasons


# ==========================================
# [V28新增] 赛后自动记录实际结果到追踪器
# ==========================================
def v28_record_result_to_tracker(actual_result, match_info=''):
    """[V28] 赛后调用此函数记录实际结果，自动关联到最近的预测记录"""
    confidence_tracker.record_actual_result(match_info, actual_result)
    print("[V28追踪器] 已记录实际赛果【{}】到信心追踪系统".format(actual_result))

def get_jc_max_result(data):
    """[V24] 依据输入的赛事胜平负概率, 返回概率【最大值】对应的赛果方向。
    概率最大=最不被看好=打出即冷门(即用户所说"实际赛果取最大值")。
    并列最大时按冷门强度 负>平>胜 取更冷方向。
    返回: (方向, 概率); 无有效概率返回 (None, 0.0)
    """
    pairs = []
    for res, key in COLD_RESULT_ODDS_KEY.items():
        val = data.get(key)
        if isinstance(val, (int, float)) and val > 0:
            pairs.append((res, float(val)))
    if not pairs:
        return None, 0.0
    max_val = max(v for _, v in pairs)
    for res in ['负', '平', '胜']:
        for r, v in pairs:
            if r == res and abs(v - max_val) < 1e-9:
                return res, v
    return pairs[0][0], pairs[0][1]

def get_jc_odds_by_result(data, result):
    """[V24] 取赛事胜平负中某一结果方向对应的概率"""
    key = COLD_RESULT_ODDS_KEY.get(result)
    if not key:
        return 0.0
    val = data.get(key)
    return float(val) if isinstance(val, (int, float)) else 0.0

def predict_cold_upset(data, predicted_result, threshold=None, actual_result=None, actual_score=None):
    """[V26修复] 冷门预测独立判定。
    1. 删除"赛事概率最大值方向=实际赛果"的错误代理(概率最大=最不可能发生);
    2. 仅当录入真实赛果时按真值判定是否冷门(赛后复盘);
    3. 无真值时改用胶着干扰信号形态做风险提示, 不再自动翻转方向, 放弃与否交由V26硬否决闸门定夺。
    """
    thr = CONFIG.get('COLD_UPSET_GAP_THRESHOLD', 0.01) if threshold is None else float(threshold)
    enabled = bool(CONFIG.get('COLD_UPSET_ENABLED', True))
    pattern_mode = bool(CONFIG.get('COLD_UPSET_PATTERN_MODE', True))
    info = {'enabled': enabled, 'cold_result': None, 'cold_odds': 0.0,
            'predicted_result': predicted_result, 'pred_odds': 0.0, 'odds_gap': None,
            'threshold': thr, 'is_cold_scene': False, 'should_predict_cold': False,
            'final_result': predicted_result, 'detail': '', 'cold_source': 'N/A'}
    if not enabled:
        info['detail'] = '[V26冷门预测] 独立逻辑已关闭, 维持原预测【{}】'.format(predicted_result)
        return info
    if predicted_result in (None, '', '观望') or predicted_result not in COLD_RESULT_ODDS_KEY:
        info['detail'] = '[V26冷门预测] 当前结论【{}】非胜平负方向, 不进行冷门预测'.format(predicted_result)
        return info
    pred_odds = get_jc_odds_by_result(data, predicted_result)
    info['pred_odds'] = pred_odds
    jc_win = data.get('jc_win', 0)
    jc_draw = data.get('jc_draw', 0)
    jc_lose = data.get('jc_lose', 0)
    tri_pos = [v for v in (jc_win, jc_draw, jc_lose) if v and v > 0]
    fav_odds = min(tri_pos) if tri_pos else 0
    if CONFIG.get('COLD_UPSET_USE_INPUT_RESULT', True) and actual_result in COLD_RESULT_ODDS_KEY:
        actual_odds = get_jc_odds_by_result(data, actual_result)
        info['cold_result'] = actual_result
        info['cold_odds'] = actual_odds
        info['cold_source'] = '实际赛果输入端({})'.format(actual_score or '')
        info['is_cold_scene'] = (actual_result != predicted_result)
        if actual_odds > 0 and pred_odds > 0:
            info['odds_gap'] = round(abs(actual_odds - pred_odds), 4)
        info['final_result'] = predicted_result
        if info['is_cold_scene']:
            info['detail'] = '[V26冷门复盘] 真实赛果【{}】与预测【{}】不同, 确认出现低概率(仅复盘记录)'.format(actual_result, predicted_result)
        else:
            info['detail'] = '[V26冷门复盘] 真实赛果【{}】与预测一致, 命中'.format(actual_result)
        return info
    draw_max = CONFIG.get('COLD_DRAW_ODDS_MAX', 3.60)
    favor_min = CONFIG.get('COLD_FAVOR_ODDS_MIN', 1.45)
    is_pattern = (jc_draw > 0 and jc_draw <= draw_max and favor_min <= fav_odds < 2.0)
    if pattern_mode and is_pattern:
        info['is_cold_scene'] = True
        info['cold_result'] = '平'
        info['cold_source'] = '胶着干扰信号形态(平概率{:.2f}且热门概率{:.2f})'.format(jc_draw, fav_odds)
        info['detail'] = '[V26冷门形态预警] 命中赢球失利/平局高危形态(平概率偏低+热门方让分压力大), 提示平/冷风险; 维持预测【' + predicted_result + '】仅作形态标记, 放弃与否由V26硬否决闸门定夺'
    else:
        info['detail'] = '[V26冷门预测] 未命中胶着干扰信号形态且无真实赛果输入, 维持原预测【{}】'.format(predicted_result)
    info['should_predict_cold'] = False
    info['final_result'] = predicted_result
    return info

def print_cold_upset_analysis(info, data=None):
    """[V24] 打印冷门预测独立模块的判定结果"""
    print("\n" + "=" * 50)
    print("[V24] 冷门预测独立判定 (差距阈值 = {:.2f})".format(info['threshold']))
    print("=" * 50)
    if data is not None:
        print("  [赛事胜平负概率] 胜 {} | 平 {} | 负 {}".format(
            data.get('jc_win'), data.get('jc_draw'), data.get('jc_lose')))
    if info['cold_result'] is not None:
        print("  [实际赛果方向] 【{}】对应赛事概率 {:.2f} (三项中的最大值 = 最不被看好)".format(
            info['cold_result'], info['cold_odds']))
        if info.get('cold_source'):
            print("  [实际赛果来源] {}".format(info['cold_source']))
    print("  [预测方向概率] {} -> {}".format(info['predicted_result'],
          'N/A' if not info['pred_odds'] else '{:.2f}'.format(info['pred_odds'])))
    print("  [概率差距] {}".format('N/A' if info['odds_gap'] is None else '{:.4f}'.format(info['odds_gap'])))
    print("  [是否冷门场景] {}".format('是' if info['is_cold_scene'] else '否'))
    print("  [是否进行冷门预测] {}".format(
        '是 -> 改判【{}】'.format(info['final_result']) if info['should_predict_cold']
        else '否 -> 维持【{}】'.format(info['final_result'])))
    print("  {}".format(info['detail']))



# ==========================================================
# [V30新增] 冷门模板命中分支: 诚实的条件概率统计
# 设计: 不再用"和错题本一模一样就跳过"(find_similar_cases 里的 0.01 continue 是
#       去重, 不是冷门信号), 而是新增独立通道 —— 拿当前比赛的 9 项概率+让分数,
#       去错题本里找"结构几乎一致"的【已结算】案例(不论当初冷不冷), 统计这批
#       相似案例里真实低概率结果(赛果!=概率最低热门方向)的比例。
# 关键诚实点: 相似度高 != 会低概率结果; 只有当"相似组低概率结果率"明显高于"整体基准低概率结果率"
#             且样本足够时, 才给风险分; 否则一律判"无区分力", 不误导下单。
# ==========================================================
COLD_ODD_FIELDS = ('jc_win', 'jc_draw', 'jc_lose',
                   'rq_win', 'rq_draw', 'rq_lose',
                   'avg_win', 'avg_draw', 'avg_lose')


def _jc_favorite_result(d):
    """按赛事胜平负概率返回热门方向(概率最低=最被看好)。三项皆无则 None。"""
    mp = {'胜': d.get('jc_win', 0) or 0,
          '平': d.get('jc_draw', 0) or 0,
          '负': d.get('jc_lose', 0) or 0}
    pos = {k: v for k, v in mp.items() if v > 0}
    if not pos:
        return None
    return min(pos, key=pos.get)


def _case_is_cold(case):
    """[V33收紧] 已结算案例是否低概率结果。开关 COLD_STRICT_BY_ODDS=True 时, 改为
    '实际赛果方向的概率 >= COLD_UPSET_MIN_ODDS' 才算冷门(真低概率结果=低概率方翻车);
    关闭时沿用旧口径(赛果方向 != 概率最低热门方向)。未结算/无法判定返回 None。"""
    rr = case.get('real_result', '')
    if rr not in ('胜', '平', '负'):
        return None
    strict = bool(CONFIG.get('COLD_STRICT_BY_ODDS', True))
    min_odds = float(CONFIG.get('COLD_UPSET_MIN_ODDS', 3.00))
    fav_ceiling = float(CONFIG.get('COLD_FAV_MAX_ODDS', 2.00))
    if strict and min_odds > 0:
        key = COLD_RESULT_ODDS_KEY.get(rr)
        if not key:
            return None
        odds = case.get(key, 0) or 0
        if odds <= 0:
            return None
        # 条件一: 胜方概率必须够高(真低概率翻车), 否则(如热门自己赢)不算冷
        if odds < min_odds:
            return False
        # 条件二: 该场必须'有明确热门'(热门方概率<=上限), 否则势均力敌不算冷门
        fav = _jc_favorite_result(case)
        if fav is None:
            return None
        fav_key = COLD_RESULT_ODDS_KEY.get(fav)
        fav_odds = (case.get(fav_key, 0) or 0) if fav_key else 0
        if fav_ceiling > 0 and fav_odds > 0 and fav_odds > fav_ceiling:
            return False
        return True
    fav = _jc_favorite_result(case)
    if fav is None:
        return None
    return rr != fav


def _structure_close(case, data, odd_tol, hand_tol):
    """当前比赛与历史案例的结构相似度: 让分数差<=hand_tol 且 9项概率最大偏差<=odd_tol。"""
    h_case = case.get('handicap', 0) or 0
    h_data = data.get('handicap', 0) or 0
    if abs(h_case - h_data) > hand_tol:
        return False
    dmax = 0.0
    for f in COLD_ODD_FIELDS:
        dmax = max(dmax, abs((case.get(f, 0) or 0) - (data.get(f, 0) or 0)))
    return dmax <= odd_tol


def _compute_cold_template_hit_strict(data, tol=None, hand_tol=None):
    """[V30旧法/严格卡阈值] 9项概率最大偏差<=tol才算命中(0.01时几乎命中不到样本)。"""
    t = CONFIG.get('COLD_TEMPLATE_TOL', 0.01) if tol is None else float(tol)
    ht = CONFIG.get('COLD_TEMPLATE_HANDI_TOL', 0.01) if hand_tol is None else float(hand_tol)
    info = {'enabled': bool(CONFIG.get('COLD_TEMPLATE_ENABLED', True)),
            'tol': t, 'hand_tol': ht,
            'settled_total': 0, 'base_cold_rate': 0.0,
            'near_count': 0, 'near_cold_count': 0,
            'cold_rate': None, 'lift': None,
            'usable': False, 'tier': 'N/A', 'risk': 0.0,
            'near_matches': [], 'detail': ''}
    if not info['enabled']:
        info['detail'] = '[V30冷门模板] 开关已关闭, 跳过'
        return info

    min_n = CONFIG.get('COLD_TEMPLATE_MIN_SAMPLE', 5)
    settled = 0
    cold_total = 0
    near = []
    for case in ERROR_BOOK:
        cold = _case_is_cold(case)
        if cold is None:
            continue
        settled += 1
        if cold:
            cold_total += 1
        if _structure_close(case, data, t, ht):
            near.append(case)
    base = (cold_total / settled) if settled else 0.0
    info['settled_total'] = settled
    info['base_cold_rate'] = round(base, 4)
    info['near_count'] = len(near)
    near_cold = sum(1 for c in near if _case_is_cold(c))
    info['near_cold_count'] = near_cold
    info['near_matches'] = [
        {'handicap': c.get('handicap', 0), 'real_result': c.get('real_result', ''),
         'is_cold': bool(_case_is_cold(c)),
         'jc': (c.get('jc_win'), c.get('jc_draw'), c.get('jc_lose'))}
        for c in near[:10]
    ]
    if not near:
        info['tier'] = '无相似案例'
        info['detail'] = ('[V30冷门模板] 容差 {:.3f} 下错题本内无任何已结算相似案例(结构太独特或容差太紧),'
                          ' 无法评估冷门风险。'.format(t))
        return info
    rate = near_cold / len(near)
    lift = rate - base
    info['cold_rate'] = round(rate, 4)
    info['lift'] = round(lift, 4)
    rate_high = CONFIG.get('COLD_TEMPLATE_RATE_HIGH', 0.40)
    rate_mid = CONFIG.get('COLD_TEMPLATE_RATE_MID', 0.25)
    lift_min = CONFIG.get('COLD_TEMPLATE_LIFT_MIN', 0.08)
    # 双重护栏: 样本足够 且 相对基准有明显提升 才可用
    info['usable'] = (len(near) >= min_n) and (lift >= lift_min)
    if len(near) < min_n:
        info['tier'] = '样本不足'
        info['detail'] = ('[V30冷门模板] 相似案例仅 {} 场(<{}), 低概率结果率 {:.0%} 不具统计意义, 判定不可用。'
                          .format(len(near), min_n, rate))
    elif lift < lift_min:
        info['tier'] = '无区分力'
        info['risk'] = round(base, 4)
        info['detail'] = ('[V30冷门模板] 相似组低概率结果率 {:.0%} 与整体基准 {:.0%} 仅差 {:.0%}(<{:.0%}),'
                          ' 相似度对预测冷门没有额外信息量, 不可据此判冷门。'
                          .format(rate, base, lift, lift_min))
    else:
        info['risk'] = round(rate, 4)
        if rate >= rate_high:
            info['tier'] = '高冷门风险'
        elif rate >= rate_mid:
            info['tier'] = '中冷门风险'
        else:
            info['tier'] = '低-中冷门风险'
        info['detail'] = ('[V30冷门模板] 容差 {:.3f} 命中 {} 场相似已结算案例, 其中 {} 场真实低概率结果(低概率结果率 {:.0%},'
                          ' 较整体基准 {:.0%} 提升 {:.0%}) -> 判【{}】。'
                          ' 注意: 这是"这类结构历史上 {}% 会冷"的条件概率, 不是本场必冷; 低概率同样可能稳.'
                          .format(t, len(near), near_cold, rate, base, lift, info['tier'], int(round(rate * 100))))
    return info


def print_cold_template_hit(info):
    """打印冷门模板命中判定。"""
    if not info or not CONFIG.get('COLD_TEMPLATE_PRINT', True):
        return
    print("\n" + "=" * 50)
    if info.get('method') == 'knn':
        print("[V34] 冷门最近邻命中判定 (Top-K={} | 预测阈值={:.1f}%)".format(
            info.get('topk', '?'), float(info.get('predict_thresh', 0.5)) * 100))
    else:
        print("[V30] 冷门模板命中判定 (概率容差={:.3f} | 让分容差={:.3f})".format(
            info['tol'], info['hand_tol']))
    print("=" * 50)
    print("  [错题本已结算] {} 场 | [整体基准低概率结果率] {:.1f}%".format(
        info['settled_total'], info['base_cold_rate'] * 100))
    print("  [相似案例] {} 场 | [其中真实低概率结果] {} 场".format(
        info['near_count'], info['near_cold_count']))
    if info['cold_rate'] is not None:
        print("  [相似组低概率结果率] {:.1f}% | [相对基准提升] {}".format(
            info['cold_rate'] * 100,
            'N/A' if info['lift'] is None else '{:+.1f}%'.format(info['lift'] * 100)))
    print("  [是否可用] {}".format('可用' if info['usable'] else '不可用'))
    print("  [冷门风险档] {}".format(info['tier']))
    print("  {}".format(info['detail']))
    if info.get('near_matches'):
        print("  [相似案例明细(最多10条)]")
        for i, m in enumerate(info['near_matches'], 1):
            jc = m['jc']
            print("    {}-{} 让分{} | 赛事{} 赛果【{}】{}".format(
                i,
                '冷' if m['is_cold'] else '正',
                m['handicap'],
                '{}-{}-{}'.format(jc[0], jc[1], jc[2]),
                m['real_result'],
                ' <=冷门' if m['is_cold'] else ''))


# ==========================================================
# [V32新增] 冷门匹配改为 Top-K 最近邻:
#   旧法把9项概率+让分数同时卡<=0.01, 现实中没有两场能满足, 导致命中均场~0,
#   表里的 0%/负提升 全是"没匹配到", 而非"匹配到却不低概率结果"。
#   新法: 标准化各字段后算欧氏距离, 取最相似的前 K 场, 看这 K 场历史真实低概率结果率,
#   给出"这类结构历史上 X% 会冷"的条件概率, 仍保留样本量/提升双重护栏。
# ==========================================================
COLD_KNN_FIELDS = list(COLD_ODD_FIELDS) + ['handicap']


def _knn_build_scale(cases):
    """按已结算案例池, 逐字段计算标准差用于归一化(零方差兜底为1.0)。"""
    import statistics as _st
    scale = {}
    for fld in COLD_KNN_FIELDS:
        vals = [float((c.get(fld, 0) or 0)) for c in cases]
        sd = _st.pstdev(vals) if len(vals) > 1 else 0.0
        scale[fld] = sd if sd > 1e-9 else 1.0
    return scale


def _knn_distance(a, b, scale):
    """标准化欧氏距离: 各字段先除以字段标准差, 避免高数值字段(如高概率)主导。"""
    total = 0.0
    for fld in COLD_KNN_FIELDS:
        d = (float((a.get(fld, 0) or 0)) - float((b.get(fld, 0) or 0))) / scale[fld]
        total += d * d
    return total ** 0.5


def compute_cold_template_hit_knn(data, k=None, predict_thresh=None):
    """[V32] Top-K最近邻版冷门模板命中: 返回与strict版完全同构的info字典。"""
    import math
    kk = CONFIG.get('COLD_TEMPLATE_TOPK', 30) if k is None else int(k)
    pt = CONFIG.get('COLD_TEMPLATE_PREDICT_THRESH', 0.5) if predict_thresh is None else float(predict_thresh)
    info = {'enabled': bool(CONFIG.get('COLD_TEMPLATE_ENABLED', True)),
            'method': 'knn', 'topk': kk, 'predict_thresh': pt,
            'tol': None, 'hand_tol': None,
            'settled_total': 0, 'base_cold_rate': 0.0,
            'near_count': 0, 'near_cold_count': 0,
            'cold_rate': None, 'lift': None,
            'usable': False, 'tier': 'N/A', 'risk': 0.0,
            'near_matches': [], 'detail': ''}
    if not info['enabled']:
        info['detail'] = '[V32冷门最近邻] 开关已关闭, 跳过'
        return info

    min_n = CONFIG.get('COLD_TEMPLATE_MIN_SAMPLE', 5)
    settled = [c for c in ERROR_BOOK if _case_is_cold(c) is not None]
    info['settled_total'] = len(settled)
    if not settled:
        info['tier'] = '无已结算案例'
        info['detail'] = '[V32冷门最近邻] 错题本内无任何已结算案例, 无法评估。'
        return info
    cold_total = sum(1 for c in settled if _case_is_cold(c))
    base = cold_total / len(settled)
    info['base_cold_rate'] = round(base, 4)

    scale = _knn_build_scale(settled)
    scored = []
    for c in settled:
        # 跳过完全同一场比赛(按match_id), 避免自匹配
        if c.get('match_id') and data.get('match_id') and c.get('match_id') == data.get('match_id'):
            continue
        scored.append((_knn_distance(data, c, scale), c))
    scored.sort(key=lambda x: x[0])
    near = [c for _, c in scored[:kk]]

    info['near_count'] = len(near)
    near_cold = sum(1 for c in near if _case_is_cold(c))
    info['near_cold_count'] = near_cold
    info['near_matches'] = [
        {'handicap': c.get('handicap', 0), 'real_result': c.get('real_result', ''),
         'is_cold': bool(_case_is_cold(c)),
         'jc': (c.get('jc_win'), c.get('jc_draw'), c.get('jc_lose'))}
        for c in near[:10]
    ]
    if not near:
        info['tier'] = '无相似案例'
        info['detail'] = '[V32冷门最近邻] 无可比较的相似案例(错题本已结算样本为空)。'
        return info

    rate = near_cold / len(near)
    lift = rate - base
    info['cold_rate'] = round(rate, 4)
    info['lift'] = round(lift, 4)
    rate_high = CONFIG.get('COLD_TEMPLATE_RATE_HIGH', 0.40)
    rate_mid = CONFIG.get('COLD_TEMPLATE_RATE_MID', 0.25)
    lift_min = CONFIG.get('COLD_TEMPLATE_LIFT_MIN', 0.08)
    # 双重护栏: 邻居数足够 且 相对基准有明显提升 才可用
    info['usable'] = (len(near) >= min_n) and (lift >= lift_min)
    # 本场是否"预测为冷门": 邻居低概率结果率达预测阈值 且 通过护栏
    info['predict_cold'] = bool(info['usable'] and rate >= pt)

    if len(near) < min_n:
        info['tier'] = '样本不足'
        info['detail'] = ('[V32冷门最近邻] 仅取到 {} 场邻居(<{}), 低概率结果率 {:.0%} 不具统计意义, 判定不可用。'
                          .format(len(near), min_n, rate))
    elif lift < lift_min:
        info['tier'] = '无区分力'
        info['risk'] = round(base, 4)
        info['detail'] = ('[V32冷门最近邻] 取最相似 {} 场, 邻居低概率结果率 {:.0%} 与整体基准 {:.0%} 仅差 {:.0%}(<{:.0%}),'
                          ' 最近邻对预测冷门没有额外信息量, 不可据此判冷门。'
                          .format(len(near), rate, base, lift, lift_min))
    else:
        info['risk'] = round(rate, 4)
        if rate >= rate_high:
            info['tier'] = '高冷门风险'
        elif rate >= rate_mid:
            info['tier'] = '中冷门风险'
        else:
            info['tier'] = '低-中冷门风险'
        info['detail'] = ('[V32冷门最近邻] 取最相似 {} 场(容差K={}), 其中 {} 场真实低概率结果(低概率结果率 {:.0%},'
                          ' 较整体基准 {:.0%} 提升 {:.0%}) -> 判【{}】, 本场{}预测冷门。'
                          ' 注意: 这是"这类结构历史上 {}% 会冷"的条件概率, 不是本场必冷。'
                          .format(len(near), kk, near_cold, rate, base, lift, info['tier'],
                                  ('会' if info.get('predict_cold') else '不会'), int(round(rate * 100))))
    return info


def compute_cold_template_hit(data, tol=None, hand_tol=None):
    """[V32] 调度器: 按 COLD_TEMPLATE_METHOD 选择最近邻(knn)或旧严格卡阈值(strict)。
    打印函数 print_cold_template_hit 对两种返回的 info 字段完全兼容。"""
    method = CONFIG.get('COLD_TEMPLATE_METHOD', 'knn')
    if method == 'strict':
        return _compute_cold_template_hit_strict(data, tol=tol, hand_tol=hand_tol)
    return compute_cold_template_hit_knn(data)


def _cold_base_rate_sweep(settled):
    """[V34] 在不同'真低概率结果'口径下打印基准低概率结果率, 帮用户确认收紧是否真的把虚高基准压下来。
    口径 = 胜方概率>=min_odds 且 热门方概率<=fav上限 才算冷门。"""
    combos = [(2.50, 99.0), (3.00, 2.00), (3.50, 1.80), (4.00, 1.50), (4.50, 1.30), (5.00, 1.20)]
    print("  [V34口径扫描] 收紧'真低概率结果'定义后的基准低概率结果率(应随口径收紧明显下降):")
    print("    {:>18} | {:>8} | {:>10}".format('胜方概率/热门上限', '真低概率结果', '基准低概率结果率'))
    print("    " + "-" * 46)
    for mo, fc in combos:
        cnt = tot = 0
        for c in settled:
            rr = c.get('real_result', '')
            key = COLD_RESULT_ODDS_KEY.get(rr)
            if not key:
                continue
            wo = c.get(key, 0) or 0
            if wo <= 0:
                continue
            fav = _jc_favorite_result(c)
            if fav is None:
                continue
            fk = COLD_RESULT_ODDS_KEY.get(fav)
            fo = (c.get(fk, 0) or 0) if fk else 0
            if fo <= 0:
                continue
            tot += 1
            if wo >= mo and fo <= fc:
                cnt += 1
        rate = (cnt / tot) if tot else 0.0
        tag = '(旧:无热门上限,基准虚高)' if fc > 90 else ''
        print("    {:>7.2f}/{:<9.2f} | {:>8} | {:>9.2f}% {}".format(mo, fc, cnt, rate * 100, tag))
    print("    读法: 第一行≈你之前看到的44.65%(2.50且不看热门=没收紧); 往下的行是真正低概率结果。")
    print("          选'基准回落到合理区间(约10~20%)'的那一行的 (胜方概率/热门上限) 写进 CONFIG。")
    print()


def calibrate_cold_template_threshold(k_list=None):
    """[V32] 冷门最近邻留一法(LOO)分类器评估:
    逐条把已结算比赛当查询, 在其余案例里取最相似的前K场, 邻居低概率结果率>=预测阈值
    就判'本场会冷', 再和真实赛果对比, 输出 精确率/召回率/准确率/提升。
    回答: 最近邻到底能不能把冷门预测准(而不是旧表里的'没匹配到')。"""
    if k_list is None:
        k_list = [5, 10, 20, 30, 50]
    settled = [c for c in ERROR_BOOK if _case_is_cold(c) is not None]
    cold_total = sum(1 for c in settled if _case_is_cold(c))
    base = (cold_total / len(settled)) if settled else 0.0
    pt = CONFIG.get('COLD_TEMPLATE_PREDICT_THRESH', 0.5)

    print("\n" + "#" * 60)
    print("[V34] 冷门最近邻阈值回测 (留一法分类器评估)")
    print("#" * 60)
    if not settled:
        print("  错题本无已结算案例, 无法回测。")
        return {'base': 0.0, 'settled': 0, 'k_list': k_list}
    print("  已结算案例 {} 场 | 其中低概率结果 {} 场 | 整体基准低概率结果率 {:.2f}% | 预测阈值 {:.2f}%".format(
        len(settled), cold_total, base * 100, pt * 100))
    _cold_base_rate_sweep(settled)

    scale = _knn_build_scale(settled)
    # 预算每条到其它所有条目的邻居低概率结果率
    n = len(settled)
    print("  {:>6} | {:>7} | {:>8} | {:>8} | {:>8} | {:>8} | {:>7}".format(
        'K', '判冷场数', '命中(TP)', '误报(FP)', '精确率', '召回率', '准确率'))
    print("  " + "-" * 70)
    best = None
    for kk in k_list:
        if kk >= n:
            continue
        tp = fp = tn = fn = flagged = 0
        for idx, q in enumerate(settled):
            q_cold = bool(_case_is_cold(q))
            scored = []
            for j, c in enumerate(settled):
                if j == idx:
                    continue
                scored.append((_knn_distance(q, c, scale), bool(_case_is_cold(c))))
            scored.sort(key=lambda x: x[0])
            neigh = scored[:kk]
            nrate = (sum(1 for _, cc in neigh if cc) / len(neigh)) if neigh else 0.0
            pred_cold = nrate >= pt
            if pred_cold:
                flagged += 1
                if q_cold:
                    tp += 1
                else:
                    fp += 1
            else:
                if q_cold:
                    fn += 1
                else:
                    tn += 1
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        acc = (tp + tn) / n if n else 0.0
        print("  {:>6} | {:>7} | {:>8} | {:>8} | {:>8.0%} | {:>8.0%} | {:>7.0%}".format(
            kk, flagged, tp, fp, prec, rec, acc))
        # 以'相对基准的精确率提升'选最优(精确率>基准且有一定召回)
        if flagged > 0 and (best is None or prec - base > best[1] - base and rec > 0):
            best = (kk, prec, rec)

    print("\n  读表:")
    print("    精确率 = 判为冷门的场次里真冷的比例(越高越可信);")
    print("    召回率 = 全部真冷场次里被抓到的比例(越高越不漏);")
    print("    关键对比: 精确率必须明显>基准 {:.2f}%, 否则最近邻没信息量, 不可用于判冷。".format(base * 100))
    print("    若所有K的精确率都<=基准, 说明'结构相似'对预测冷门无效, 这条路应放弃;")
    print("    若某K精确率高但召回极低(判冷场数很少), 说明只挑得准极少数, 覆盖面有限。")
    if best is not None and best[1] > base:
        print("    当前最可用: K={} (精确率 {:.2f}% > 基准 {:.2f}%, 召回 {:.2f}%)".format(
            best[0], best[1] * 100, base * 100, best[2] * 100))
        print("    建议把 COLD_TEMPLATE_TOPK 设为 {} 试跑单场预警。".format(best[0]))
    else:
        print("    结论: 本次数据下最近邻精确率未超基准, 不建议据此判冷门。")
    return {'base': base, 'settled': len(settled), 'k_list': k_list}


# ==========================================================
# [V35新增] 信心分档低概率结果率校准（市场信心代理 + 相似度交互）
#   动机：内置错题本没有存'系统信心指数'字段，选项14因此跑出0条。
#   本选项用'热门方归一化隐含概率'作为即时可算的市场信心代理值，
#   让全部已结算历史都能参与分档；同时若 confidence_tracker 已攒够
#   带真实信心的已结算记录(>=MIN)，自动切用真实系统信心。
#   并叠加'留一法最近邻冷门率'作为相似度信号，做信心x相似度交叉表，
#   直接检验用户的直觉：相似比赛+低信心 => 更易低概率结果。
# ==========================================================
def _market_proxy_confidence(case):
    """市场信心代理值 = 赛事热门方(最低概率)的归一化隐含概率, 约0.4~0.75。
    值越高=市场越看好热门=该场越'正路'; 越低=越不确定/越接近势均力敌=易冷。"""
    mp = {'胜': (case.get('jc_win', 0) or 0),
          '平': (case.get('jc_draw', 0) or 0),
          '负': (case.get('jc_lose', 0) or 0)}
    pos = {k: v for k, v in mp.items() if v > 0}
    if not pos:
        return None
    inv = {k: 1.0 / v for k, v in pos.items()}
    tot = sum(inv.values())
    if tot <= 0:
        return None
    fav = min(pos, key=pos.get)
    return inv[fav] / tot


def book_confidence_records():
    """[修复] 从既有错题本派生信心记录, 使信心类回测(选项12/14)无需赛后录入即可运行。
    口径: 信心=赛事热门方(最低概率)归一化隐含概率(市场信心代理值);
          预测=热门方向; 命中=热门方向与实际赛果一致。全程基于 ERROR_BOOK, 不依赖运行时追踪器。"""
    recs = []
    for c in ERROR_BOOK:
        rr = c.get('real_result', '')
        if rr not in ('胜', '平', '负'):
            continue
        conf = _market_proxy_confidence(c)
        if conf is None:
            continue
        fav = _jc_favorite_result(c)
        if fav is None:
            continue
        recs.append({'prediction': fav, 'confidence': conf,
                     'actual': rr, 'hit': (fav == rr),
                     'match_info': str(c.get('match_id', '')),
                     'timestamp': ''})
    return recs


def calibrate_confidence_cold(k=None, conf_bins=None, sim_thresh=None):
    """[V35] 信心分档低概率结果率校准 + 与最近邻相似度交叉。
    数据源优先级: 真实系统信心(confidence_tracker已结算>=15) -> 否则市场信心代理。"""
    K = CONFIG.get('COLD_TEMPLATE_TOPK', 30) if k is None else max(1, int(k))

    print("\n" + "#" * 60)
    print("[V35] 信心分档低概率结果率校准 (市场信心x相似度交互)")
    print("#" * 60)

    # ---- 收集已结算案例 ----
    settled = [c for c in ERROR_BOOK if _case_is_cold(c) is not None]
    if len(settled) < 15:
        print("  已结算案例仅 {} 场(<15), 样本不足, 无法校准。".format(len(settled)))
        input("\n按回车键返回主菜单...")
        return

    cold_total = sum(1 for c in settled if _case_is_cold(c))
    base = cold_total / len(settled)

    # ---- 决定信心来源: 真实信心优先, 否则市场代理 ----
    real = [r for r in confidence_tracker.history
            if r.get('actual') in ('胜', '平', '负') and r.get('confidence') is not None]
    use_real = len(real) >= 15

    recs = []  # (conf, is_cold_bool)
    if use_real:
        # 用真实系统信心; 低概率结果判定用该记录对应场次(按 match_info 回查错题本), 回查不到则用hit近似
        idx = {}
        for c in settled:
            mid = c.get('match_id')
            if mid:
                idx[str(mid)] = c
        for r in real:
            mi = str(r.get('match_info', ''))
            is_cold = None
            for key, c in idx.items():
                if key and key in mi:
                    is_cold = bool(_case_is_cold(c)); break
            if is_cold is None:
                continue
            recs.append((float(r['confidence']), is_cold))
        conf_label = '真实系统信心指数'
    else:
        for c in settled:
            p = _market_proxy_confidence(c)
            if p is None:
                continue
            recs.append((p, bool(_case_is_cold(c))))
        conf_label = '市场信心代理值(热门方隐含概率)'

    if len(recs) < 15:
        print("  可计入信心的案例仅 {} 场(<15), 无法校准。".format(len(recs)))
        input("\n按回车键返回主菜单...")
        return

    # 信心口径的低概率结果基准(可能略少于全部已结算, 因部分场次概率缺失)
    cold_n = sum(1 for _, cold in recs if cold)
    base_c = cold_n / len(recs)
    cold_total = cold_n

    print("  信心来源: {}".format(conf_label))
    if not use_real:
        print("  [提示] 错题本未存真实信心(选项14=0条), 本表用概率即时算市场信心代理值。")
    print("  有效样本 {} 场 | 真低概率结果 {} 场 | 该口径基准低概率结果率 {:.2f}% | 最近邻 K={}".format(
        len(recs), cold_total, base_c * 100, K))
    print("  冷门定义: 胜方概率>={:.2f} 且 热门概率<={:.2f} (COLD_STRICT_BY_ODDS={})".format(
        float(CONFIG.get('COLD_UPSET_MIN_ODDS', 3.0)),
        float(CONFIG.get('COLD_FAV_MAX_ODDS', 2.0)),
        bool(CONFIG.get('COLD_STRICT_BY_ODDS', True))))

    # ---- 信心分档 ----
    # 市场代理值典型区间用 0.50/0.60/0.70; 真实信心用 0.65/0.70/0.80(对齐CONFIDENCE_THRESHOLD)
    if use_real:
        edges = conf_bins or [0.0, 0.60, 0.70, 0.80, 1.01]
    else:
        edges = conf_bins or [0.0, 0.50, 0.60, 0.70, 1.01]
    blabels = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        blabels.append('{:.2f}~{:.2f}'.format(lo, hi) if i < len(edges) - 2 else '>= {:.2f}'.format(lo))

    print("\n  [A] 按信心分档:")
    print("  {:>14} | {:>6} | {:>6} | {:>9} | {:>10}".format(
        '信心区间', '样本数', '低概率结果数', '低概率结果率', 'vs基准'))
    print("  " + "-" * 60)
    for i in range(len(blabels)):
        lo, hi = edges[i], edges[i + 1]
        sub = [(cf, cd) for cf, cd in recs if lo <= cf < hi]
        if not sub:
            print("  {:>14} | {:>6} | {:>6} | {:>9} | {:>10}".format(
                blabels[i], 0, '-', '-', '-'))
            continue
        cn = sum(1 for _, cd in sub if cd)
        rate = cn / len(sub)
        diff = (rate - base_c) * 100
        mark = ' 风险区' if diff > 3 else (' 安全区' if diff < -3 else '')
        print("  {:>14} | {:>6} | {:>6} | {:>8.2f}% | {:>+9.2f}%{}".format(
            blabels[i], len(sub), cn, rate * 100, diff, mark))

    # ---- 留一法最近邻冷门率(相似度信号) 针对 settled 全集缓存 ----
    scale = _knn_build_scale(settled)
    # 为每条 settled 计算 its LOO near-cold-rate; 通过 conf 关联回 recs
    # recs 元素与 settled 未必一一对应(市场口径), 用 id 映射
    loo_rate = {}
    for c in settled:
        scored = []
        for o in settled:
            if o is c:
                continue
            mo, mc = o.get('match_id'), c.get('match_id')
            if mo and mc and mo == mc:
                continue
            scored.append((_knn_distance(c, o, scale), o))
        scored.sort(key=lambda x: x[0])
        near = [o for _, o in scored[:K]]
        if not near:
            loo_rate[id(c)] = None
            continue
        ncold = sum(1 for o in near if _case_is_cold(o))
        loo_rate[id(c)] = ncold / len(near)

    # 重建带相似度维度的记录: (conf, sim_rate, is_cold)
    enriched = []
    if use_real:
        # 真实信心路径不易对齐 id, 退回市场代理做相似度交叉(标注)
        for c in settled:
            p = _market_proxy_confidence(c)
            if p is None or loo_rate.get(id(c)) is None:
                continue
            enriched.append((p, loo_rate[id(c)], bool(_case_is_cold(c))))
        cross_note = '交叉表使用市场代理信心(真实信心难逐场回查)'
    else:
        sim_map = {}
        for c in settled:
            p = _market_proxy_confidence(c)
            if p is None:
                continue
            r = loo_rate.get(id(c))
            if r is None:
                continue
            enriched.append((p, r, bool(_case_is_cold(c))))
        cross_note = ''

    print("\n  [B] 留一法最近邻冷门率分布 (本场Top-{}近邻里的真低概率结果比例):".format(K))
    if not enriched:
        print("    无可对齐的相似度样本, 跳过交叉分析。")
    else:
        rates = [s for _, s, _ in enriched]
        cold_cnt = sum(1 for _, _, cd in enriched if cd)
        eb = cold_cnt / len(enriched)
        print("    参与交叉样本 {} 场 | 其基准低概率结果率 {:.2f}%".format(len(enriched), eb * 100))
        # 按相似度分档
        sb = [0.0, 0.20, 0.35, 1.01]
        slabels = ['近邻冷<20%', '近邻冷20~35%', '近邻冷>=35%']
        print("    按相似度(近邻冷门率)分档:")
        for i in range(len(slabels)):
            lo, hi = sb[i], sb[i + 1]
            sub = [(cf, sf, cd) for cf, sf, cd in enriched if lo <= sf < hi]
            if not sub:
                print("      {:>14} | 0".format(slabels[i]))
                continue
            cn = sum(1 for _, _, cd in sub if cd)
            rate = cn / len(sub)
            print("      {:>14} | {:>4} 场 | 低概率结果率 {:>6.2f}% | vs基准 {:+.2f}%".format(
                slabels[i], len(sub), rate * 100, (rate - eb) * 100))

        # 交叉表: 信心档 x 相似度档
        print("  [C] 交叉表 信心x相似度 (低概率结果率%/样本数):")
        if cross_note:
            print("    (" + cross_note + ")")
        header = "  {:>12}".format('信心\\相似度') + "".join("{:>14}".format(l) for l in slabels)
        print(header)
        print("  " + "-" * (12 + 14 * len(slabels)))
        for i in range(len(blabels)):
            clo, chi = edges[i], edges[i + 1]
            cells = []
            for j in range(len(slabels)):
                slo, shi = sb[j], sb[j + 1]
                sub = [(cf, sf, cd) for cf, sf, cd in enriched
                       if clo <= cf < chi and slo <= sf < shi]
                if not sub:
                    cells.append('{:>14}'.format('-'))
                    continue
                cn = sum(1 for _, _, cd in sub if cd)
                rate = cn / len(sub)
                cells.append('{:>10.1f}%({:>3})'.format(rate * 100, len(sub)))
            print("  {:>12}".format(blabels[i]) + "".join(cells))

    # ---- 结论建议 ----
    print("\n  读表:")
    print("    [A]低信心档若低概率结果率明显>基准, 说明'信心不足'确实预示冷门;")
    print("    [C]若'低信心 x 高相似度'格子显著高于其余, 则你直觉的")
    print("       '相似比赛+信心<70~80% 就易冷'成立, 可作为冷门预警组合规则。")
    print("    注意: 市场代理值是'市场对热门的把握', 非引擎输出; 攒够真实信心")
    print("    (选项1跑预测会自动记录, 到>=15条)本表会自动改用真实信心。")

    # 给出可用阈值建议(基于市场代理: 低信心档 lift 最大者)
    best = None
    for i in range(len(blabels)):
        lo, hi = edges[i], edges[i + 1]
        sub = [(cf, cd) for cf, cd in recs if lo <= cf < hi]
        if len(sub) < 15:
            continue
        cn = sum(1 for _, cd in sub if cd)
        rate = cn / len(sub)
        lift = rate / base_c if base_c > 0 else 0
        if best is None or lift > best[0]:
            best = (lift, blabels[i], rate, len(sub))
    if best and best[0] > 1.15:
        print("\n  建议: 信心落在 [{}] 档时, 低概率结果率 {:.1f}% = 基准的 {:.2f} 倍(样本{}场),".format(
            best[1], best[2] * 100, best[0], best[3]))
        print("        该档及以下可作冷门预警触发区。")
    else:
        print("\n  未找到明显高于基准的信心档, 信心分档对判冷暂无强信号, 建议继续攒真实信心样本。")


def calibrate_hot_confidence():
    """[V33] 热门信心校准回测(选项14): 回答'模型喊X%信心时实际到底赢了几场'。
    取信心追踪器里已录入赛果的记录, 按信心分档统计实际命中率, 输出分档校准表 +
    Brier评分 + 可靠性诊断(高估/低估), 并给校准折扣系数。全程仅用标准库。"""
    settled = [r for r in confidence_tracker.history
               if r.get('actual') is not None and r.get('hit') is not None]
    print("\n" + "#" * 60)
    print("[V33] 热门信心校准回测 (分档命中率 + Brier + 可靠性诊断)")
    print("#" * 60)
    # [修复] 追踪器为空(无赛后录入)时, 自动回退到既有错题本派生的信心记录, 保证本项可跑。
    if len(settled) < CONFIG.get('CALIB_MIN_SAMPLES', 15):
        settled = book_confidence_records()
        print("  数据来源: 既有错题本(热门方隐含概率作信心代理值), 共 {} 条。".format(len(settled)))
    else:
        print("  数据来源: 信心追踪器(本次运行实时记录), 共 {} 条。".format(len(settled)))
    if len(settled) < CONFIG.get('CALIB_MIN_SAMPLES', 15):
        print("  有效信心记录仅 {} 条(<{}), 样本不足以校准。".format(
            len(settled), CONFIG.get('CALIB_MIN_SAMPLES', 15)))
        return {'settled': len(settled), 'ready': False}
    n = len(settled)
    base_hit = sum(1 for r in settled if r.get('hit')) / n
    print("  已结算记录 {} 条 | 总体实际命中率 {:.2f}%".format(n, base_hit * 100))
    # 分档表
    bins = list(CONFIG.get('HOT_CALIB_BINS', [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]))
    lo_edge = 0.0
    print("  {:<18} | {:>6} | {:>6} | {:>6} | {:>10} | {:>10}".format(
        '信心区间', '场数', '命中', '未中', '实际命中率', '信心偏差'))
    print("  " + "-" * 74)
    over_flag = under_flag = 0
    for hi in bins:
        grp = [r for r in settled if lo_edge <= r['confidence'] < hi]
        cnt = len(grp)
        if cnt:
            hit = sum(1 for r in grp if r.get('hit'))
            rate = hit / cnt
            nominal = (lo_edge + hi) / 2.0
            bias = (rate - nominal) * 100
            if nominal >= 0.7 and rate < nominal - 0.05:
                over_flag += cnt
            if nominal >= 0.7 and rate >= nominal - 0.05:
                under_flag += cnt
            print("  {:<18} | {:>6} | {:>6} | {:>6} | {:>9.2f}% | {:>+9.2f}%".format(
                '[{:.2f},{:.2f})'.format(lo_edge, hi), cnt, hit, cnt - hit, rate * 100, bias))
        lo_edge = hi
    # Brier 评分 (0=完美, 越低越好)
    brier = sum((r['confidence'] - (1.0 if r.get('hit') else 0.0)) ** 2 for r in settled) / n
    brier_naive = sum((base_hit - (1.0 if r.get('hit') else 0.0)) ** 2 for r in settled) / n
    print("  " + "-" * 74)
    print("  [Brier] 信心评分= {:.3f} (越接近0越准) | 全猜基准率= {:.3f} | 模型{}".format(
        brier, brier_naive, '优于瞎猜' if brier < brier_naive else '不优于瞎猜'))
    # 可靠性诊断
    hi_grp = [r for r in settled if r['confidence'] >= 0.70]
    diag = '样本不足'
    discount = 1.0
    if hi_grp:
        hi_rate = sum(1 for r in hi_grp if r.get('hit')) / len(hi_grp)
        hi_nominal = sum(r['confidence'] for r in hi_grp) / len(hi_grp)
        gap = hi_nominal - hi_rate
        if gap > 0.05:
            diag = '高估(喊得比赢得多): 高信心档标称{:.0f}%实际仅{:.0f}%, 差{:.0f}个点'.format(
                hi_nominal * 100, hi_rate * 100, gap * 100)
            discount = round(hi_rate / hi_nominal, 3) if hi_nominal > 0 else 1.0
        elif gap < -0.05:
            diag = '低估(其实更稳): 高信心档实际{:.0f}%高于标称{:.0f}%'.format(
                hi_rate * 100, hi_nominal * 100)
            discount = 1.0
        else:
            diag = '基本校准: 高信心档标称与实际偏差在5个点内'
        print("  [诊断] 高信心档(>=0.70, {}场): {}".format(len(hi_grp), diag))
    else:
        print("  [诊断] 无高信心档(>=0.70)记录, 无法判高估/低估")
    print("  [建议] 后续单场预测信心按折扣系数 {:.3f} 折算后再定仓位。".format(discount))
    print("#" * 60)
    return {'settled': n, 'brier': round(brier, 4), 'base_hit': round(base_hit, 4),
            'high_conf_discount': discount, 'ready': True}


def analyze_data(data, shenjia_info):
    handicap = data['handicap']
    
    # === 分析流程：显示信息 -> 错题本匹配 -> 六引擎分析 -> 共振分析 -> 投票表决 -> 比分预测 -> 赛后录入 -> 保存 ===
    print("\n" + "=" * 50)
    print(" 当前分析 | 让分数: {} | 身价对比: {}".format(
        "主让{}球".format(handicap) if handicap > 0 else "客让{}球".format(abs(handicap)) if handicap < 0 else "平手/无让分",
        shenjia_info
    ))
    print("=" * 50)

    # === 显示当前比赛数据指纹 ===
    _current_fp = generate_fingerprint(data)
    print("[数据指纹] {}".format(_current_fp))

    # 【步骤1】智能错题本匹配 (V10逻辑)
    matched_results = find_similar_cases(data)
    # [V30新增] 冷门模板命中: 独立通道, 输出相似案例的真实低概率结果率(条件概率), 非'相似=冷门'臆断
    try:
        _cold_tmpl_info = compute_cold_template_hit(data)
        print_cold_template_hit(_cold_tmpl_info)
    except Exception as _cte:
        print('  [V30冷门模板] 计算异常已跳过: {}'.format(_cte))
    history_warning = False
    most_common_result = None
    
    if matched_results:
        print("\n" + "=" * 40 + " 错题本历史预警 " + "=" * 40)
        print("[!] 找到 {} 个高度相似的历史案例：\n".format(len(matched_results)))
        
        #   【子步骤】遍历并打印完整的历史案例数据
        result_count = {}
        for idx, case in enumerate(matched_results, 1):
            handicap = case.get('handicap', 0)
            h_str = "主让{}球".format(handicap) if handicap > 0 else "客让{}球".format(abs(handicap)) if handicap < 0 else "平手/无让分"
            
            mid = case.get("match_id", "")
            mid_str = "[{}] ".format(mid) if mid else ""
            print("【{}案例 {}】".format(mid_str, idx))
            print("  让分数: {} | 身价对比: {}".format(h_str, case.get('shenjia', '未输入')))
            print("  赛事概率: 胜 {} | 平 {} | 负 {}".format(case['jc_win'], case['jc_draw'], case['jc_lose']))
            print("  让分概率: 胜 {} | 平 {} | 负 {}".format(case['rq_win'], case['rq_draw'], case['rq_lose']))
            print("  平均概率: 胜 {} | 平 {} | 负 {}".format(case['avg_win'], case['avg_draw'], case['avg_lose']))
            print("  最终真实结果: 【{}】".format(case['real_result']))
            case_score = case.get('real_score', '')
            if case_score:
                print("  真实比分: 【{}】".format(case_score))
            print("-" * 40)
            
            # 【关键修改点】统计结果出现次数，必须从 case 字典里取 real_result
            real_res = case['real_result']
            result_count[real_res] = result_count.get(real_res, 0) + 1
        
        # 【步骤2】计算并输出预警信息
        most_common_result = max(result_count, key=result_count.get)
        cold_ratio = result_count[most_common_result] / len(matched_results) if len(matched_results) > 0 else 0
        
        print("\n[提示] 历史相似案例中，【{}】出现过 {} 次。请注意防范冷门！".format(most_common_result, result_count[most_common_result]))
        # V14改进：增加最小样本量要求，避免基于过少样本做出预警
        # [V21修复] 使用CONFIG参数控制冷门预警阈值，提高阈值减少误触发
        history_min_samples = CONFIG.get('HISTORY_OVERRIDE_MIN_SAMPLES', 5)
        cold_ratio_thresh = CONFIG.get('COLD_RATIO_THRESHOLD', 0.75)
        if cold_ratio >= cold_ratio_thresh and len(matched_results) >= history_min_samples:
            print("[高能预警] 历史相似案例中，【{}】打出率高达 {}% ({}/{})！".format(most_common_result, int(cold_ratio * 100), result_count[most_common_result], len(matched_results)))
            history_warning = True
        elif len(matched_results) < history_min_samples:
            print("[提示] 找到 {} 个相似案例，样本量不足(>={})，预警参考价值有限".format(len(matched_results), history_min_samples))
    
    # [V19新增] 检查是否有二级匹配结果
    secondary_count = sum(1 for m in matched_results if m.get('is_secondary', False))
    if secondary_count > 0:
        print("[V19二级匹配] 找到 {} 个低相似度参考案例(相似度低于常规阈值但仍具参考价值)，请结合其他引擎综合判断！".format(secondary_count))

    # 【步骤3】启动六引擎分析
    result_a = engine_pure_rq(data, shenjia_info)
    result_b = engine_combined(data, shenjia_info)
    result_c = engine_metrics(data, shenjia_info)
    result_d = engine_shape_decision(data)
    result_e = engine_critical_pattern(data)
    # V13: 加入第六引擎（概率区间映射）- 至此完成六引擎并行
    result_f = engine_zone_mapping(data, shenjia_info)
    engines_results = [result_a, result_b, result_c, result_d, result_e, result_f]

    # 【步骤4】打印分析过程
    print("\n" + "=" * 40 + " 引擎分析过程 " + "=" * 40)
    for res in engines_results:
        if res['engine'].startswith('A'):
            std = convert_rq_to_standard(handicap, res['conclusion'])
            print("[{}] 让分结论: {} | 标准映射: {} | 原因: {}".format(res['engine'], res['conclusion'], std, res['reason']))
        else:
            print("[{}] 结论: {} | 原因: {}".format(res['engine'], res['conclusion'], res['reason']))
        if 'z' in res:
            print("   -> 核心指标: Z={}, Y={}, X={}".format(res['z'], res['y'], res['x']))
        if 'cold_risk' in res:
            print("   -> 冷门风险: {:.1f}% (方向: {}) | 市场方向: {}".format(
                res['cold_risk'] * 100, res['cold_risk_direction'],
                "胜" if res['cold_risk_direction'] == '胜' else ("平" if res['cold_risk_direction'] == '平' else "负")))

    # 【步骤5】双维度共振分析（让分维度 + 标准维度联合分析）
    resonance = analyze_risk_and_standard(data, result_c, shenjia_info)
    print("\n" + "=" * 40 + " 双维度共振分析 " + "=" * 40)
    print("[让分维度倾向] {} | 引擎C倾向: {}".format(resonance['rq_direction'], resonance['c_direction']))
    print("[共振类型] {} | 建议: {} | 风险: {}".format(
        resonance['resonance_type'], resonance['recommendation'], resonance['risk_level']))
    print("[共振详情] {}".format(resonance['resonance_detail']))
    print("[指标差距] Z-Y差值: {:.2f} | 数据面板: {}".format(
        resonance['zy_gap'],
        "主让{}球".format(resonance['handicap']) if resonance['handicap'] > 0 else 
        "客让{}球".format(abs(resonance['handicap'])) if resonance['handicap'] < 0 else "平手/无让分"
    ))
    if resonance['resonance_type'] == '同向共振':
        print("[共振提示] >>> 让分维度与数学指标同向一致，共振信号强烈！建议重点关注！")
    elif resonance['resonance_type'] == '反向背离':
        print("[共振提示] >>> 让分维度与数学指标方向背离，存在干扰信号嫌疑！请谨慎操作或放弃！")
    elif resonance['resonance_type'] in ['平局共振', '浅度让分平局']:
        print("[共振提示] >>> 双维度共振指向平局，平局概率显著提升！可关注平局！")
    elif resonance['resonance_type'] == '冷门预警':
        print("[共振提示] >>> 深度让分与数学指标背离，冷门信号强烈！可考虑关注低概率！")
    
    # 【步骤6】统一投票表决
    # 逻辑：将引擎A的让分结论转换为标准胜平负 -> 六引擎投票 -> 取最高票
    # V13: 概率区间映射分析面板
    print("\n" + "=" * 40 + " 概率区间映射分析(V13) " + "=" * 40)
    print("[区间组合] 主胜:{} | 平局:{} | 客胜:{}".format(
        result_f['zone_h'], result_f['zone_d'], result_f['zone_a']))
    print("[映射方向] {} (置信度: {:.1f}%)".format(
        result_f['conclusion'], result_f['zone_confidence'] * 100))
    print("[概率分布] 主胜:{:.0%} | 平局:{:.0%} | 客胜:{:.0%}".format(
        result_f['zone_win_prob'], result_f['zone_draw_prob'], result_f['zone_lose_prob']))
    print("[动态系数] 主队:{} | 客队:{} | 让分修正: 主{:+.2f}/客{:+.2f}".format(
        result_f.get('multiplier_h', 'N/A'), result_f.get('multiplier_a', 'N/A'),
        result_f.get('home_correction', 0), result_f.get('away_correction', 0)))
    # [V18新增] 引擎F高风险标记处理 - 降低系统信心指数
    engine_f_high_risk = result_f.get('is_high_risk', False)
    if result_f['is_high_risk']:
        print("[警告] 高风险标记 - 各方向概率接近，决策不确定性高！")
        # [V18新增] 引擎F标记高风险时，记录标志供后续信心调整
        engine_f_high_risk = True
    if result_f['is_even_match']:
        print("[提示] 均势面标记 - 概率离散度低，比赛可能胶着")
    print("")
    print("\n" + "=" * 40 + " 最终综合判定 " + "=" * 40)
    conclusions = []
    for r in engines_results:
        if r['engine'].startswith('A'):
            conclusions.append(convert_rq_to_standard(handicap, r['conclusion']))
        else:
            conclusions.append(r['conclusion'])
            
    vote_count = {}
    for c in conclusions: 
        vote_count[c] = vote_count.get(c, 0) + 1
    logic_conclusion = max(vote_count, key=vote_count.get)
    logic_votes = vote_count[logic_conclusion]
    final_conclusion = logic_conclusion
    
    # V15新增: 引擎分歧检测与建议放弃机制
    vote_gap = 0
    if len(vote_count) >= 2:
        votes_sorted = sorted(vote_count.values(), reverse=True)
        vote_gap = votes_sorted[0] - votes_sorted[1] if len(votes_sorted) > 1 else 0
    should_skip = suggest_skip(vote_count)
    
    # [V17新增] 市场条件检查 - 胶着数据面板/概率差距过小
    # [V18新增] check_market_risk返回4个值: (should_skip, should_warn_only, confidence_penalty, warnings)
    market_skip, market_warn_only, confidence_penalty, market_warnings = check_market_risk(data)
    if market_skip:
        print("\n" + "=" * 50)
        print("[市场条件预警]")
        for w in market_warnings:
            print("  >> {}".format(w))
        print("[系统建议] 以上市场条件已触发，建议放弃本场，不要下场/不要购买！")
        print("=" * 50)
    elif market_warn_only:
        # [V18新增] 分级响应：仅警告，不放弃但扣减信心
        print("\n" + "=" * 50)
        print("[V18分级响应-数据面板预警]")
        for w in market_warnings:
            print("  >> {}".format(w))
        print("[系统建议] 数据面板存在一定不确定性，建议降低仓位！系统信心将扣减{:.0%}！".format(confidence_penalty))
        print("=" * 50)
    
    # [V20新增] 多信号叠加自动升级机制
    signal_count = 0
    signal_details = []
    yupan_warnings = [w for w in market_warnings if '干扰信号' in w]
    if yupan_warnings:
        signal_count += 1
        signal_details.append('干扰信号')
    resonance_deviation = resonance.get('resonance_type', '') == '反向背离'
    if resonance_deviation:
        signal_count += 1
        signal_details.append('共振背离')
    engine_c_cold_risk_val = result_c.get('cold_risk', 0)
    cold_risk_boost_thresh_val = CONFIG.get('COLD_RISK_BOOST_THRESHOLD', 0.25)
    if engine_c_cold_risk_val > cold_risk_boost_thresh_val:
        signal_count += 1
        signal_details.append('冷门风险')
    if engine_f_high_risk:
        signal_count += 1
        signal_details.append('引擎F高风险')
    multi_signal_thresh = CONFIG.get('MULTI_SIGNAL_THRESHOLD', 3)
    if signal_count >= multi_signal_thresh:
        print("\n" + "=" * 50)
        print("[V20多信号叠加预警] 检测到{}个风险信号同时存在！".format(signal_count))
        print("[V20多信号叠加预警] 信号列表: {}".format('、'.join(signal_details)))
        print("[V20多信号叠加预警] 风险等级: 自动升级为降仓/观望")
        print("[V20多信号叠加预警] 建议: 直接放弃或仅保留极小仓！")
        print("=" * 50)
        confidence_penalty = max(confidence_penalty, 0.30)

    # V15新增: 系统信心指数
    # [V23重构] 移除dir()检查，confidence_penalty已在上方check_market_risk调用处初始化
    system_confidence_raw = get_system_confidence(vote_count)
    if confidence_penalty > 0:
        system_confidence = max(0, system_confidence_raw * (1 - confidence_penalty))
        print("[V18分级响应] 原始信心{:.1f}%，数据面板胶着扣减{:.0%}后最终信心:{:.1f}%".format(
            system_confidence_raw * 100, confidence_penalty, system_confidence * 100
        ))
    else:
        system_confidence = system_confidence_raw
    
    # [V18新增] 引擎F高风险标记信心扣减
    # 当引擎F标记高风险(各方向概率接近)时，降低系统信心指数10-20%
    if engine_f_high_risk:
        f_penalty = 0.15  # 默认扣减15%
        f_original = system_confidence
        system_confidence = max(0, system_confidence * (1 - f_penalty))
        print("[V18引擎F风控] 引擎F标记高风险(概率接近)，信心扣减{:.0%}({:.1f}%→{:.1f}%)".format(
            f_penalty, f_original * 100, system_confidence * 100
        ))
      
    # [V19新增] 全票一致信心扣减
    unanimous_applied = False
    if unanimous_applied:
        unanimous_penalty = CONFIG.get('UNANIMOUS_PENALTY', 0.10)
        u_original = system_confidence
        system_confidence = max(0, system_confidence * (1 - unanimous_penalty))
        print("[V19全票一致风控] 六引擎全票一致触发信心扣减{:.0%}({:.1f}%→{:.1f}%)".format(
            unanimous_penalty, u_original * 100, system_confidence * 100
        ))
    print("[系统信心指数] {:.1f}%".format(system_confidence * 100))
    print("[引擎共识分布] {}".format(' | '.join('{}={}'.format(k, v) for k, v in sorted(vote_count.items(), key=lambda x: -x[1]))))

    # 【步骤7】最终判定（优先级：市场条件 > 错题本预警 > 分歧放弃 > 投票共识）
    # [V17修复] 市场条件检查优先级提升至高，确保胶着数据面板/概率差距过小时强制观望
    # [V18新增] 分级响应：数据面板胶着时不直接放弃，而是降仓+扣减信心
    # [V21新增] 错题本偏差检测函数 - 检测错题本自身是否存在方向偏差
    error_book_bias = False
    if ERROR_BOOK:
        book_results = [item.get('real_result', '') for item in ERROR_BOOK if item.get('real_result')]
        if book_results:
# (import已移至文件顶部)
            book_counter = __import__('collections').Counter(book_results)
            total_book = len(book_results)
            max_count = max(book_counter.values())
            bias_ratio = max_count / total_book if total_book > 0 else 0
            bias_threshold = CONFIG.get('ERROR_BOOK_BIAS_THRESHOLD', 0.70)
            if bias_ratio > bias_threshold:
                error_book_bias = True
                print("[V21偏差检测] 错题本存在方向偏差({}占比{:.1f}%)，历史预警参考价值降低!".format(
                    book_counter.most_common(1)[0][0], bias_ratio * 100))
    
    yupan_extreme_flag = False  # [V27] 极端干扰信号风险信号, 默认无(在最终判定链前初始化, 供硬否决统一读取)
    if market_skip:
        final_conclusion = '观望'
        # 警告已在上方(check_market_risk调用处)打印，此处仅确认结论
        print("\n" + "=" * 50)
        print("[最终判定] 市场条件不佳(数据面板极度胶着)，最终结论：**观望**")
        print("[系统建议] 不建议下场，请放弃本场！")
        print("=" * 50)
    elif history_warning and most_common_result != logic_conclusion and not error_book_bias:
        # [V21修复] 错题本有偏差时不执行历史预警override，避免偏差放大
        final_conclusion = most_common_result
        print("[逻辑修正] 引擎逻辑共识为【{}】，但错题本预警强烈，最终判定修正为：【{}】".format(logic_conclusion, final_conclusion))
    elif history_warning and most_common_result != logic_conclusion and error_book_bias:
        # [V21修复] 错题本有偏差时，不直接override，改为降低信心
        system_confidence = max(0, system_confidence * 0.85)
        print("[V21偏差保护] 错题本存在方向偏差，不执行历史预警override，信心扣减15%后继续按引擎共识输出")
        final_conclusion = logic_conclusion
    elif should_skip:
        final_conclusion = '观望'
        print("[系统建议] 引擎分歧严重(最高{}票，与第二名差{}票)，建议放弃本场！".format(logic_votes, vote_gap))
    else:
        yupan_extreme_flag = False  # [V27] 极端干扰信号改为独立风险信号, 不再直接观望
        # [V19新增] 全票一致风险检测：6引擎全票一致时，警惕完美一致干扰信号
        unanimous_penalty = CONFIG.get('UNANIMOUS_PENALTY', 0.10)
        cold_risk_boost = CONFIG.get('COLD_RISK_BOOST', 0.12)
        cold_risk_boost_thresh = CONFIG.get('COLD_RISK_BOOST_THRESHOLD', 0.25)
        
        # 检查引擎C的冷门风险
        engine_c_cold_risk = result_c.get('cold_risk', 0)
        engine_c_cold_direction = result_c.get('cold_risk_direction', '')
        
        final_conclusion = logic_conclusion
        
        if logic_votes >= 5:
            # [V20新增] 5:1共识审视机制
            if logic_votes == 5 and resonance.get('resonance_type', '') == '反向背离':
                print("\n" + "=" * 50)
                print("[V21共识审视] 5引擎共识+共振背离双重信号触发审视！")
                cold_dir = result_c.get('cold_risk_direction', '')
                # [V21修复] 提高冷门风险触发门槛(原0.10→0.20)，减少误触发
                cold_risk_val = result_c.get('cold_risk', 0)
                override_threshold = CONFIG.get('COLD_RISK_DIRECTION_OVERRIDE_THRESHOLD', 0.20)
                if cold_dir and cold_dir != logic_conclusion and cold_risk_val > override_threshold:
                    # [V21修复] 不再直接翻转结论，改为信心扣减+提示
                    ov = CONFIG.get('COLD_RISK_DIRECTION_OVERRIDE', 0.12)
                    system_confidence = max(0, system_confidence * (1 - ov))
                    print("[V21共识审视] 冷门方向[{}]与共识[{}]相反，冷门风险{:.1f}%超过阈值{:.0%}".format(
                        cold_dir, logic_conclusion, cold_risk_val, override_threshold))
                    print("[V21共识审视] 信心扣减{:.0%}，建议谨慎操作或放弃".format(ov))
                    # [V21修复] 移除自动翻转结论的逻辑，仅降低信心让用户自行判断
                    # final_conclusion 保持不变，继续输出引擎共识方向
                    print("[V21共识审视] 保持引擎共识方向【{}】，请结合偏差提示自行决策".format(final_conclusion))
                else:
                    pen = CONFIG.get('SIGNAL_5VOTE_RESONANCE_PENALTY', 0.25)
                    system_confidence = max(0, system_confidence * (1 - pen))
                    if cold_risk_val <= override_threshold:
                        print("[V21共识审视] 冷门风险{:.1f}%未达触发阈值{:.0%}，系统信心扣减{:.0%}后继续输出".format(
                            cold_risk_val, override_threshold, pen))
                    else:
                        print("[V21共识审视] 无冷门反向信号，系统信心扣减{:.0%}后继续输出".format(pen))
                print("=" * 50)
            # [V19] 全票一致(6票)特殊处理
            if logic_votes == 6:
                print("[V19全票一致预警] 六引擎100%一致达成，市场可能已过度调整！触发干扰信号检测机制！")
                # 检查是否存在干扰信号特征
                jc_w = data.get('jc_win', 0)
                jc_l = data.get('jc_lose', 0)
                avg_w = data.get('avg_win', 0)
                avg_l = data.get('avg_lose', 0)
                extreme_thresh = CONFIG.get('EXTREME_ODDS_THRESHOLD', 1.60)
                is_extreme = False
                if jc_w < extreme_thresh and avg_l > 0 and avg_w > 0:
                    if avg_l / avg_w > CONFIG.get('AVG_ODDS_RATIO_THRESHOLD', 3.0):
                        is_extreme = True
                elif jc_l < extreme_thresh and avg_w > 0 and avg_l > 0:
                    if avg_w / avg_l > CONFIG.get('AVG_ODDS_RATIO_THRESHOLD', 3.0):
                        is_extreme = True
                
                if is_extreme:
                    # [V27修复] 全票一致+极端干扰信号不再"一刀切观望"。强弱明显的热门场几乎必然命中此形态,
                    #   原V25/V26在此直接 final_conclusion=观望, 是"全是观望"的头号来源。
                    #   V27 改为: 保留引擎共识方向, 把"极端干扰信号"登记为独立强风险信号(yupan_extreme_flag),
                    #   仅施加信心惩罚, 是否降级观望统一交给后面的[V27硬否决加权分]闸门裁决。
                    yupan_extreme_flag = True
                    reverse_pick = "负" if jc_w < extreme_thresh else "胜"
                    print("[V27干扰信号警示] 全票一致+极端概率悬殊, 提示关注低概率风险(反向参考: {})。".format(reverse_pick))
                    print("[V27干扰信号警示] 暂保留方向【{}】并扣减信心, 最终是否观望由硬否决加权分统一裁决".format(final_conclusion))
                    _ue_orig = system_confidence
                    system_confidence = max(0, system_confidence * 0.70)
                    print("[V27干扰信号降信心] 极端干扰信号惩罚30%: {:.1f}%->{:.1f}%".format(_ue_orig*100, system_confidence*100))
                else:
                    # [V27修复] 取消"六引擎全票一致反而扣信心"的反直觉逻辑:
                    #   V25/直觉上全票一致且无干扰信号特征=方向信号最强, 应维持满信心, 而非扣分。
                    #   原V26在此乘 (1-UNANIMOUS_PENALTY) 把6/6共识的0.833信心又压到0.75, 叠加后续
                    #   硬否决的"信心<0.65"信号形成自我闭环, 是"全是观望"主因之一。此处保留提示但不再扣分。
                    unanimous_applied = False
                    print("[V27全票一致] 六引擎100%一致且无干扰信号特征, 方向信号最强, 维持满信心不扣分(已取消V26反向扣减)")
                print("[极高一致] 六引擎中{}个达成共识，最终判定：【{}】(高度信心)".format(logic_votes, final_conclusion))
            else:
                print("[高度一致] 六引擎中{}个达成共识，最终判定：【{}】(较高信心)".format(logic_votes, final_conclusion))
            # [V21修复] 冷门风险处理 - 移除自动翻转逻辑，改为信心扣减+警告
            # [V21修复] 提高冷门风险触发门槛(原cold_risk_boost_thresh即0.18)
            if engine_c_cold_risk > cold_risk_boost_thresh and final_conclusion != "观望":
                print("[V21冷门风险] 引擎C检测到冷门风险{:.1f}%(方向:{})，已超过阈值{:.1f}%！".format(
                    engine_c_cold_risk * 100, engine_c_cold_direction, cold_risk_boost_thresh * 100))
                # [V21修复] 不再根据冷门方向自动翻转结论
                if engine_c_cold_direction and engine_c_cold_direction != final_conclusion:
                    ov = CONFIG.get('COLD_RISK_DIRECTION_OVERRIDE', 0.12)
                    system_confidence = max(0, system_confidence * (1 - ov))
                    print("[V21冷门干预] 冷门方向[{}]与结论[{}]相反，信心扣减{:.0%}".format(
                        engine_c_cold_direction, final_conclusion, ov))
                    # [V21修复] 移除自动翻转逻辑，保持引擎共识方向
                    print("[V21冷门干预] 保持当前结论【{}】，已降低信心提示风险".format(final_conclusion))
                    print("[V21冷门干预] 建议：结合错题本偏差检测提示，自行判断是否调整")
        elif logic_votes >= 4:
            print("[高度一致] 六引擎中{}个达成共识，最终判定：【{}】(较高信心)".format(logic_votes, final_conclusion))
            if engine_c_cold_risk > cold_risk_boost_thresh and final_conclusion != "观望":
                print("[V19冷门风险提醒] 引擎C检测到冷门风险{:.1f}%(方向:{})，已超过阈值{:.1f}%，请警惕冷门！".format(
                    engine_c_cold_risk * 100, engine_c_cold_direction, cold_risk_boost_thresh * 100))
        elif logic_votes == 3:
            print("[多数支持] 六引擎中{}个支持，建议参考：【{}】(一般信心)".format(logic_votes, final_conclusion))
        else:
            print("[严重分歧] 引擎各自为战，无明显共识，建议放弃或结合基本面分析！(低信心)")
    
    # ===== [V24新增] 步骤7.5 冷门预测独立逻辑 (阈值差距 0.01) =====
    # 冷门场景: 预测结果与实际赛果不同, 且实际赛果为赛事胜平负概率最大值方向;
    # 仅当冷门方向概率与预测方向概率差距 <= CONFIG['COLD_UPSET_GAP_THRESHOLD'](=0.01) 时才改判为冷门方向。
    cold_info = predict_cold_upset(data, final_conclusion)
    print_cold_upset_analysis(cold_info, data)
    if cold_info['should_predict_cold'] and cold_info['final_result'] != final_conclusion:
        final_conclusion = cold_info['final_result']
        print("[V24冷门预测] 最终结论已按独立冷门逻辑改判为:【{}】".format(final_conclusion))
    else:
        print("[V24冷门预测] 未触发冷门改判, 最终结论保持:【{}】".format(final_conclusion))
    # ===== [V24] 冷门预测独立逻辑结束 =====

    # [V26修复] 原 try/except NameError 把【步骤8~12】(比分预测/赛后录入/复盘/权重更新/保存)整体误缩进进异常分支,
    #   正常流程(已有 final_conclusion 时)根本不执行, 比分/复盘/录入形同虚设。final_conclusion 上方各分支均已赋值, 此处仅留兜底。
    try:
        _ = final_conclusion
    except NameError:
        final_conclusion = logic_conclusion

    # ===== [V27修复] 引擎相关性去膨胀: 保留V26的洞察(B/D/E/F同源), 但改为温和参考, 不再在否决前直乘闭环 =====
    #   原V26: system_confidence *= decorr_ratio 会在硬否决的"信心<0.65"信号之前把信心二次压低,
    #   与"信心不足即观望"形成自我闭环。V27 用可配缩放系数衰减惩罚强度(默认减半)。
    ENGINE_CORR_GROUP = {'A': 'handicap', 'B': 'odds', 'C': 'metrics', 'D': 'odds', 'E': 'odds', 'F': 'odds'}
    group_support = {}
    for _r in engines_results:
        _key = _r['engine'][0]
        _g = ENGINE_CORR_GROUP.get(_key, _key)
        _c = _r['conclusion']
        if _r['engine'].startswith('A'):
            _c = convert_rq_to_standard(handicap, _c)
        group_support.setdefault(_g, {})
        group_support[_g][_c] = group_support[_g].get(_c, 0) + 1
    _n_groups = len(group_support) or 1
    _agree_groups = sum(1 for _d in group_support.values() if _d and max(_d, key=_d.get) == logic_conclusion)
    decorr_ratio = _agree_groups / _n_groups
    _decorr_scale = CONFIG.get('DECORR_PENALTY_SCALE', 0.5)
    if decorr_ratio < 1.0 and logic_conclusion != '观望':
        _eff = 1 - _decorr_scale * (1 - decorr_ratio)
        _orig_conf = system_confidence
        system_confidence = max(0, system_confidence * _eff)
        print('[V27去相关性] 独立信号簇仅{}/{}支持【{}】(B/D/E/F同源计为一簇), 惩罚缩放{:.0%}, 信心{:.1f}%->{:.1f}%'.format(
            _agree_groups, _n_groups, logic_conclusion, _decorr_scale, _orig_conf*100, system_confidence*100))

    # ===== [V27修复] 硬否决改为"强独立风险加权分": 移植V25分级精神 =====
    #   关键: 取消V26把"信心<阈值"本身当作否决信号(它是结果不是理由), 且数据面板仅"预警(降仓)"不计入否决,
    #   只有多个彼此独立的强风险信号凑够高加权分才降级观望, 避免"全是观望"。
    veto_score = 0.0
    veto_reasons = []
    conf_floor = CONFIG.get('CONFIDENCE_THRESHOLD', 0.65)
    if final_conclusion != '观望':
        if resonance.get('resonance_type', '') == '反向背离':
            veto_score += CONFIG.get('VETO_W_RESONANCE', 2.0)
            veto_reasons.append('双维度反向背离(干扰信号形态) 权重{:.1f}'.format(CONFIG.get('VETO_W_RESONANCE',2.0)))
        if engine_f_high_risk:
            veto_score += CONFIG.get('VETO_W_ENGINE_F', 1.0)
            veto_reasons.append('引擎F高风险(概率接近) 权重{:.1f}'.format(CONFIG.get('VETO_W_ENGINE_F',1.0)))
        if signal_count >= CONFIG.get('MULTI_SIGNAL_THRESHOLD', 3):
            veto_score += CONFIG.get('VETO_W_MULTI', 2.0)
            veto_reasons.append('多信号叠加({}个) 权重{:.1f}'.format(signal_count, CONFIG.get('VETO_W_MULTI',2.0)))
        # [V27] 全票一致+极端干扰信号(由V19分支登记的独立强风险)
        if yupan_extreme_flag:
            veto_score += CONFIG.get('VETO_W_RESONANCE', 2.0)
            veto_reasons.append('全票一致+极端干扰信号(悬殊概率) 权重{:.1f}'.format(CONFIG.get('VETO_W_RESONANCE',2.0)))
        # [V27] 市场"强制放弃"(极度胶着)仍视为独立强风险计入否决; 但仅"预警降仓"不计入
        if market_skip:
            veto_score += CONFIG.get('VETO_W_RESONANCE', 2.0)
            veto_reasons.append('数据面板极度胶着(强制放弃级) 权重{:.1f}'.format(CONFIG.get('VETO_W_RESONANCE',2.0)))
        veto_thr = CONFIG.get('VETO_SCORE_THRESHOLD', 4.0)
        if veto_score >= veto_thr:
            print('\n' + '=' * 54)
            print('[V27硬否决] 独立强风险加权分{:.1f}>={:.1f}, 原结论【{}】降级为【观望】:'.format(veto_score, veto_thr, final_conclusion))
            for _vr in veto_reasons:
                print('   - ' + _vr)
            print('[V27硬否决] 该场不具备下单条件, 输出方向不可作为建仓依据!')
            print('=' * 54)
            final_conclusion = '观望'
            system_confidence = min(system_confidence, conf_floor)
        elif veto_score > 0 or system_confidence < conf_floor or market_warn_only:
            # [V27分级降仓] 信心不足/数据面板预警/存在部分风险 -> 不移植V26的一刀切否决, 而是保留方向, 降仓提示
            half_floor = CONFIG.get('STAKE_HALF_FLOOR', 0.45)
            if system_confidence >= conf_floor:
                _stake = '标准仓(信心达标, 但有{}项风险信号, 建议略降仓)'.format(len(veto_reasons)) if veto_reasons else '标准仓'
            elif system_confidence >= half_floor:
                _stake = '建议半仓(信心{:.1f}%<{:.0f}%但未触发硬否决)'.format(system_confidence*100, conf_floor*100)
            else:
                _stake = '建议极小仓/可放弃(信心{:.1f}%<{:.0f}%)'.format(system_confidence*100, half_floor*100)
            print('\n' + '=' * 54)
            print('[V27分级降仓] 保留方向【{}】但不降级观望: {}'.format(final_conclusion, _stake))
            for _vr in veto_reasons:
                print('   - (风险) ' + _vr)
            print('[V27说明] 未达硬否决阈值(加权分{:.1f}<{:.1f}), 信心不足仅降仓不否定方向(修复V26"全是观望")'.format(veto_score, veto_thr))
            print('=' * 54)
        else:
            print('[V27决策] 风险信号不足且信心达标, 维持方向【{}】标准仓'.format(final_conclusion))
    # ===== [V36新增] 最终执行决策层: 置于V27去相关+降仓之后, 以最终信心+全局信号统一拍板 =====
    #   动机: 修复"#781"类脱节——投票阶段临时措辞说"较高信心(70.8%)", 但V27去相关/降仓后实际已压到
    #         "可放弃(44.3%)", 两者互相矛盾。V36把最终执行权收归此处, 明确覆盖上方所有临时措辞。
    #   原则: 60%只是可校准的初始执行基准, 不能只看单一百分比, 须综合独立信号簇/共振背离/引擎F高风险/
    #         数据面板预警/冷门风险等全局信号共同判定(全局观)。
    v36_enabled = CONFIG.get('V36_ENABLED', True)
    if v36_enabled:
        _v36_exec_base = CONFIG.get('ZONE_HIGH_CUT')
        if _v36_exec_base is None:
            _v36_exec_base = CONFIG.get('EXEC_BASE_THRESHOLD', 0.60)
        _v36_mid_cut = CONFIG.get('ZONE_MID_CUT')
        if _v36_mid_cut is None:
            _v36_mid_cut = CONFIG.get('STAKE_HALF_FLOOR', 0.45)
        _v36_veto_thr = CONFIG.get('VETO_SCORE_THRESHOLD', 4.0)
        _v36_crb_thresh = CONFIG.get('COLD_RISK_BOOST_THRESHOLD', 0.25)
        # 收集全局风险信号(用主流程恒存在的变量, 避免分支未定义)
        _v36_flags = []
        if resonance.get('resonance_type', '') == '反向背离':
            _v36_flags.append('反向背离(干扰信号)')
        if engine_f_high_risk:
            _v36_flags.append('引擎F高风险(概率接近)')
        if market_warn_only:
            _v36_flags.append('数据面板预警降仓')
        if engine_c_cold_risk_val > _v36_crb_thresh:
            _v36_flags.append('冷门风险{:.1f}%'.format(engine_c_cold_risk_val * 100))
        if decorr_ratio < 1.0 and logic_conclusion != '观望':
            _v36_flags.append('独立信号簇仅{}/{}'.format(_agree_groups, _n_groups))
        _v36_hard_veto = (final_conclusion == '观望') or market_skip or (veto_score >= _v36_veto_thr)
        # 分级拍板
        if _v36_hard_veto:
            _v36_level = '放弃'
            _v36_advice = '本场不具备执行条件, 输出方向不可作为建仓依据, 请直接放弃。'
        elif system_confidence >= _v36_exec_base and not _v36_flags:
            _v36_level = '正常跟进'
            _v36_advice = '最终执行信心达标且无全局风险信号, 可按标准仓正常参考方向【{}】。'.format(final_conclusion)
        elif system_confidence >= _v36_exec_base and _v36_flags:
            _v36_level = '降仓/防冷'
            _v36_advice = '信心虽达标, 但存在全局风险信号, 建议降仓并防冷, 切勿重仓。'
        elif system_confidence >= _v36_mid_cut:
            _v36_level = '半仓/谨慎'
            _v36_advice = '最终信心介于降仓线与正常线之间, 建议半仓或观望。'
        else:
            _v36_level = '放弃/极小仓'
            _v36_advice = '最终信心低于降仓线且独立证据不足, 建议放弃或仅极小仓娱乐。'
        print("\n" + "=" * 54)
        print("  V36 最终执行决策层 (以此为最终权威, 覆盖上方临时措辞)")
        print("=" * 54)
        print("[最终方向] 【{}】".format(final_conclusion))
        print("[V27后最终执行信心] {:.1f}%".format(system_confidence * 100))
        print("[执行基准] 正常线{:.0f}% / 降仓线{:.0f}% (基准可被V29校准覆盖)".format(_v36_exec_base * 100, _v36_mid_cut * 100))
        if _v36_flags:
            print("[全局风险信号] " + ' | '.join(_v36_flags))
        else:
            print("[全局风险信号] 无")
        print("[V36执行等级] {}".format(_v36_level))
        print("[V36执行建议] {}".format(_v36_advice))
        print("[V36说明] 最终执行不看投票阶段临时信心(如70.8%), 而看V27去相关+降仓后的最终信心({:.1f}%)与全局信号综合判定。".format(system_confidence * 100))
        print("=" * 54)

    # 【步骤8】共振信号最终提示
    print("\n" + "-" * 40)
    if resonance['resonance_type'] == '同向共振':
        print("[共振加持] 双维度共振信号与最终判定【{}】一致，信心倍增！".format(final_conclusion))
    elif resonance['resonance_type'] == '反向背离':
        print("[V20共振联动] 共振背离信号已计入多信号叠加系统，参与风控升级判定！")
        print("[共振警告] 双维度共振显示干扰信号，但综合判定为【{}】，请控制仓位！".format(final_conclusion))
    elif resonance['resonance_type'] in ['平局共振', '浅度让分平局']:
        if final_conclusion == '平':
            print("[共振确认] 双维度共振+综合判定均指向平局，平局信号极强！")
        else:
            print("[共振提醒] 双维度共振指向平局，但综合判定为【{}】，请自行权衡！".format(final_conclusion))
    elif resonance['resonance_type'] == '冷门预警':
        print("[共振提醒] 双维度共振提示冷门风险，综合判定为【{}】，建议小仓关注低概率！".format(final_conclusion))
    else:
        print("[共振提示] 未出现明显共振信号，按常规策略操作即可。")
    print("-" * 40)

    # [V17修复] 如果最终结论为观望，强烈提醒不要建仓
    if final_conclusion == '观望':
        print("\n" + "=" * 50)
        print("[!!! 重要提醒 !!!] 本场最终结论为【观望】")
        print("[!!! 重要提醒 !!!] 市场条件不佳或引擎分歧严重，请勿建仓本场！")
        print("[!!! 重要提醒 !!!] 耐心等待更好机会！")
        print("=" * 50 + "\n")

    # 【步骤9】比分预测展示 + [V18新增]比分-方向一致性校验
    score_pred = predict_score(data)
    
    # [V18新增] 比分-方向一致性校验
    # 注意：此时final_conclusion可能还未确定，使用投票共识结论
    # 我们需要在投票后、比分预测前做校验，所以先记录投票结论
    # 这里先获取比分，一致性校验放在后面（需要direction_conclusion）
    
    print("\n" + "=" * 40 + " 比分预测引擎 " + "=" * 40)
    print("[比分预测] 最可能比分: 【{}】 (概率: {})".format(
        score_pred['predicted_score'], score_pred['top3_probs'][0]))
    print("[备选比分] {} (概率: {}) | {} (概率: {})".format(
        score_pred['alt_scores'][0], score_pred['top3_probs'][1],
        score_pred['alt_scores'][1] if len(score_pred['alt_scores']) > 1 else '-',
        score_pred['top3_probs'][2] if len(score_pred['top3_probs']) > 2 else '-'))
    print("[比分推导] 主队期望进球: {} | 客队期望进球: {}".format(
        score_pred['home_exp'], score_pred['away_exp']))
    print("[比分结论] 预测结果: {}".format(score_pred['score_conclusion']))
    print("[比分概率] 胜 {} | 平 {} | 负 {}".format(
        score_pred['probabilities']['win'],
        score_pred['probabilities']['draw'],
        score_pred['probabilities']['lose']))
    
    # [V18新增] 比分-方向一致性校验（在final_conclusion确定后调用）
    # 这里先打印原始比分结论，后续在final_conclusion确定后做校验

    # [V18新增] 比分-方向一致性校验（需要在final_conclusion确定后执行）
    # 注意：由于final_conclusion在此处之前已确定，我们可以在此做校验
    # 但需要重新获取direction_conclusion，这里通过score_pred的比分方向与final_conclusion对比
    score_dir = score_pred.get('score_conclusion', '')
    if score_dir and final_conclusion != '观望' and score_dir != final_conclusion:
        # 调用一致性校验函数
        consistency = check_score_direction_consistency(score_pred, final_conclusion)
        print("\n" + "=" * 50)
        print("[V18比分-方向一致性校验]")
        print("[警告] {}".format(consistency['warning']))
        if consistency['adjusted']:
            print("[调整] 原始比分: {} ({}) -> 调整后比分: {} (方向: {})".format(
                score_pred['predicted_score'], score_dir, 
                consistency['adjusted_score'], final_conclusion
            ))
            # 更新score_pred中的比分
            score_pred['predicted_score'] = consistency['adjusted_score']
        print("=" * 50)
    
    # 【步骤10】数据指纹比分分析（V15+ 新增）
    fingerprint_result = fingerprint_score_predict(data)
    print_fingerprint_analysis(fingerprint_result)

    # 【步骤10.5】零球/一球数据指纹识别（V15+ 新增）
    goal_fp_result = check_goal_fingerprint(data, engines_results, resonance)
    print_goal_fingerprint_result(goal_fp_result)
    # 如果0球和1球指纹都有匹配，显示对比分析
    if goal_fp_result.get('matched') and len(goal_fp_result.get('all_matches', [])) > 1:
        compare_zero_vs_one_fingerprint(data, engines_results, resonance)

    # 【步骤11】智能复盘报告 + 赛后录入(错题集) [V38恢复]
    generate_review_report(data, shenjia_info, matched_results, engines_results, resonance, score_pred, final_conclusion)
    add_post_match_entry(data, shenjia_info, engines_results, resonance, final_conclusion)


# ==========================================
    # 7. 主循环
    # ==========================================
def compare_matches_by_id(id1, id2):
    """对比两场比赛的相似度（使用与find_similar_cases完全一致的6维算法）
    V15修复: 处理重复编号情况，返回所有匹配项供用户选择
    """
    # 查找比赛(可能有多条匹配)
    match1_list = [m for m in ERROR_BOOK if m.get('match_id') == id1]
    match2_list = [m for m in ERROR_BOOK if m.get('match_id') == id2]
    
    match1 = match1_list[0] if match1_list else None
    match2 = match2_list[0] if match2_list else None
    
    if len(match1_list) > 1:
        print("[提示] 编号 {} 存在 {} 条记录，使用第1条进行对比".format(id1, len(match1_list)))
    if len(match2_list) > 1:
        print("[提示] 编号 {} 存在 {} 条记录，使用第1条进行对比".format(id2, len(match2_list)))
    
    if not match1:
        print("[!] 未找到编号 {} 的比赛".format(id1))
        return
    if not match2:
        print("[!] 未找到编号 {} 的比赛".format(id2))
        return
    
    # 使用与find_similar_cases完全一致的算法
    # V15修复: 已移除嵌套的get_score和calculate_metrics定义，使用模块级函数
    # 计算Z/Y/X
    cur_z, cur_y, cur_x = calculate_metrics(match1['jc_win'], match1['jc_draw'], match1['jc_lose'])
    ref_z, ref_y, ref_x = calculate_metrics(match2['jc_win'], match2['jc_draw'], match2['jc_lose'])
    
    # 维度1: 赛事概率 (40%)
    jc_s = (get_score(match1['jc_win'], match2['jc_win']) +
            get_score(match1['jc_draw'], match2['jc_draw']) +
            get_score(match1['jc_lose'], match2['jc_lose'])) / 3.0
    
    # 维度2: 让分概率 (15%)
    rq_s = (get_score(match1['rq_win'], match2['rq_win']) +
            get_score(match1['rq_draw'], match2['rq_draw']) +
            get_score(match1['rq_lose'], match2['rq_lose'])) / 3.0
    
    # 维度3: 多家机构平均概率 (10%)
    avg_s = (get_score(match1['avg_win'], match2['avg_win']) +
             get_score(match1['avg_draw'], match2['avg_draw']) +
             get_score(match1['avg_lose'], match2['avg_lose'])) / 3.0
    
    # 维度4: 让分形态 (15%)
    h_diff = abs(match1['handicap'] - match2['handicap'])
    hcap_s = 1 - (h_diff / 2) if h_diff <= 2 else 0
    
    # 维度5: Z/Y/X指标 (15%)
    z_sim = 1 - (abs(cur_z - ref_z) / max(abs(cur_z), 1)) if cur_z != 0 else 1
    y_sim = 1 - (abs(cur_y - ref_y) / max(abs(cur_y), 1)) if cur_y != 0 else 1
    x_sim = 1 - (abs(cur_x - ref_x) / max(abs(cur_x), 1)) if cur_x != 0 else 1
    z_sim = max(0.0, min(1.0, z_sim))
    y_sim = max(0.0, min(1.0, y_sim))
    x_sim = max(0.0, min(1.0, x_sim))
    metric_s = (z_sim + y_sim + x_sim) / 3
    
    # 维度6: 身价对比 (5%)
    sj1 = match1.get('shenjia', '未输入')
    sj2 = match2.get('shenjia', '未输入')
    strength_s = 1.0 if sj1 == sj2 else (0.5 if '未输入' in [sj1, sj2] else 0.2)
    
    # 加权总分
    total = jc_s * 0.40 + rq_s * 0.15 + avg_s * 0.10 + hcap_s * 0.15 + metric_s * 0.15 + strength_s * 0.05
    
    # 打印对比报告
    print("\n" + "=" * 65)
    print("  比赛相似度对比报告")
    print("=" * 65)
    print("\n  比赛A [{}]  vs  比赛B [{}]".format(id1, id2))
    print("-" * 65)
    
    # 比赛A详情
    h1 = match1['handicap']
    h1_str = "主让{}球".format(h1) if h1 > 0 else "客让{}球".format(abs(h1)) if h1 < 0 else "平手/无让分"
    print("\n  【比赛A {}】".format(id1))
    print("    让分: {} | 身价: {}".format(h1_str, match1.get('shenjia', '未输入')))
    print("    赛事概率: 胜{:.2f} 平{:.2f} 客胜{:.2f}".format(
        match1['jc_win'], match1['jc_draw'], match1['jc_lose']))
    print("    让分概率: 胜{:.2f} 平{:.2f} 客胜{:.2f}".format(
        match1['rq_win'], match1['rq_draw'], match1['rq_lose']))
    print("    多家机构平均: 胜{:.2f} 平{:.2f} 客胜{:.2f}".format(
        match1['avg_win'], match1['avg_draw'], match1['avg_lose']))
    r1 = match1.get('real_result', '')
    s1 = match1.get('real_score', '')
    print("    结果: {} | 比分: {}".format(r1 if r1 else '待赛', s1 if s1 else '-'))
    
    # 比赛B详情
    h2 = match2['handicap']
    h2_str = "主让{}球".format(h2) if h2 > 0 else "客让{}球".format(abs(h2)) if h2 < 0 else "平手/无让分"
    print("\n  【比赛B {}】".format(id2))
    print("    让分: {} | 身价: {}".format(h2_str, match2.get('shenjia', '未输入')))
    print("    赛事概率: 胜{:.2f} 平{:.2f} 客胜{:.2f}".format(
        match2['jc_win'], match2['jc_draw'], match2['jc_lose']))
    print("    让分概率: 胜{:.2f} 平{:.2f} 客胜{:.2f}".format(
        match2['rq_win'], match2['rq_draw'], match2['rq_lose']))
    print("    多家机构平均: 胜{:.2f} 平{:.2f} 客胜{:.2f}".format(
        match2['avg_win'], match2['avg_draw'], match2['avg_lose']))
    r2 = match2.get('real_result', '')
    s2 = match2.get('real_score', '')
    print("    结果: {} | 比分: {}".format(r2 if r2 else '待赛', s2 if s2 else '-'))
    
    # 维度对比
    print("\n" + "-" * 65)
    print("  【六维相似度对比】")
    print("-" * 65)
    
    dims = [
        ('赛事概率', jc_s, '40%'),
        ('让分概率', rq_s, '15%'),
        ('多家机构平均概率', avg_s, '10%'),
        ('让分形态', hcap_s, '15%'),
        ('Z/Y/X指标', metric_s, '15%'),
        ('身价对比', strength_s, '5%'), ]
    
    print("\n  {:<14} {:<6} {:<10} {}".format('维度', '权重', '相似度', '评估'))
    print("  " + "-" * 50)
    
    for dim_name, dim_score, weight in dims:
        if dim_score >= 0.85:
            eval_str = "高度相似"
        elif dim_score >= 0.70:
            eval_str = "较相似"
        elif dim_score >= 0.50:
            eval_str = "一般"
        else:
            eval_str = "差异较大"
        bar = chr(9608) * int(dim_score * 20) + chr(9617) * (20 - int(dim_score * 20))
        print("  {:<14} {:<6} {:.4f}  {}  {}".format(dim_name, weight, dim_score, bar, eval_str))
    
    # 综合得分
    print("\n  " + "-" * 50)
    bar_total = chr(9608) * int(total * 20) + chr(9617) * (20 - int(total * 20))
    print("  {:<14} {:<6} {:.4f}  {}".format('综合得分', '100%', total, bar_total))
    
    if total >= 0.85:
        verdict = "高度相似（几乎可以互相参考）"
        verdict_color = "绿色"
    elif total >= 0.70:
        verdict = "较为相似（有一定参考价值）"
        verdict_color = "黄色"
    elif total >= 0.50:
        verdict = "一般相似（参考价值有限）"
        verdict_color = "橙色"
    else:
        verdict = "差异较大（不建议互相参考）"
        verdict_color = "红色"
    
    print("\n  判定结论: {} ({}域)".format(verdict, verdict_color))
    print("=" * 65)


def list_all_matches():
    """列出错题本中所有比赛及其编号"""
    print("\n" + "=" * 60)
    print("  错题本比赛列表 (共 {} 条)".format(len(ERROR_BOOK)))
    print("=" * 60)
    for idx, item in enumerate(ERROR_BOOK, 1):
        mid = item.get('match_id', '')
        h = item.get('handicap', 0)
        h_str = "主让{}球".format(h) if h > 0 else "客让{}球".format(abs(h)) if h < 0 else "平手/无让分"
        r = item.get('real_result', '')
        r_display = r if r else '待赛'
        print("  [{}] {} | 胜{}/平{}/负{} | 结果: {}".format(
            mid, h_str, item['jc_win'], item['jc_draw'], item['jc_lose'], r_display))
    print("=" * 60)




# ==========================================
# 新增功能：按编号调取比赛分析信息
# ==========================================

def view_match_by_id():
    """通过编号调取错题本中某场比赛的完整分析信息"""
    print("\n" + "=" * 60)
    print("  按编号查看比赛分析")
    print("=" * 60)
    
    # 显示所有可用编号
    print("\n当前错题本共 {} 条记录：\n".format(len(ERROR_BOOK)))
    print("  {:<8} {:<12} {:<10} {:<10} {:<8}".format("编号", "让分", "赛事概率", "结果", "比分"))
    print("  " + "-" * 55)
    
    for idx, item in enumerate(ERROR_BOOK, 1):
        mid = item.get('match_id', '未编号')
        h = item.get('handicap', 0)
        h_str = "主让{}球".format(h) if h > 0 else "客让{}球".format(abs(h)) if h < 0 else "平手/无让分"
        jc = "{:.2f}/{:.2f}/{:.2f}".format(item['jc_win'], item['jc_draw'], item['jc_lose'])
        r = item.get('real_result', '')
        r_display = r if r else '待赛'
        score = item.get('real_score', '')
        score_display = score if score else '-'
        print("  {:<8} {:<12} {:<10} {:<8} {:<8}".format(mid, h_str, jc, r_display, score_display))
    
    print("\n" + "-" * 60)
    
    # 获取用户输入
    match_input = input("请输入要查看的编号 (如 #001，输入0返回): ").strip()
    
    if match_input.upper() == '0':
        print("已取消。")
        return
    
    # 搜索匹配的编号
    target_item = None
    for item in ERROR_BOOK:
        item_id = item.get('match_id', '')
        if item_id and item_id.upper() == match_input.upper():
            target_item = item
            break
    
    if target_item is None:
        print("\n[错误] 未找到编号为 [{}] 的比赛记录！".format(match_input))
        print("[提示] 请检查编号是否正确，可通过选项7查看完整列表。")
        input("\n按回车键返回主菜单...")
        return
    
    # 找到匹配的记录，显示详细信息
    print("\n" + "=" * 60)
    print("  比赛编号: {}".format(target_item.get('match_id', '未编号')))
    print("=" * 60)
    
    # 基础数据
    h = target_item.get('handicap', 0)
    h_str = "主让{}球".format(h) if h > 0 else "客让{}球".format(abs(h)) if h < 0 else "平手/无让分"
    print("\n--- 基础数据 ---")
    print("  让分: {}".format(h_str))
    print("  身价对比: {}".format(target_item.get('shenjia', '未输入')))
    print("  赛事概率: 胜{}/平{}/负{}".format(
        target_item['jc_win'], target_item['jc_draw'], target_item['jc_lose']))
    print("  让分概率: 胜{}/平{}/负{}".format(
        target_item['rq_win'], target_item['rq_draw'], target_item['rq_lose']))
    print("  平均概率: 胜{}/平{}/负{}".format(
        target_item['avg_win'], target_item['avg_draw'], target_item['avg_lose']))
    
    # 赛果信息
    real_res = target_item.get('real_result', '')
    real_score = target_item.get('real_score', '')
    print("\n--- 赛果信息 ---")
    print("  真实结果: {}".format(real_res if real_res else '未录入'))
    if real_score:
        print("  真实比分: {}".format(real_score))
    
    # 引擎分析结果（如果已保存）
    engine_summary = target_item.get('engine_summary', '')
    resonance_type = target_item.get('resonance_type', '')
    match_context = target_item.get('match_context', '')
    
    print("\n--- 引擎分析结果 ---")
    if engine_summary:
        print("  引擎结论: {}".format(engine_summary))
    else:
        print("  引擎结论: 未保存（该记录为早期数据，未记录引擎分析结果）")
    
    if resonance_type:
        print("  共振类型: {}".format(resonance_type))
    else:
        print("  共振类型: 未记录")
    
    if match_context:
        print("  比赛上下文: {}".format(match_context))
    else:
        print("  比赛上下文: 未记录")
    
    # 提供重新分析的选项
    print("\n" + "-" * 40)
    reanalyze = input("是否对该比赛重新运行五引擎分析? (y/n): ").strip().lower()
    
    if reanalyze == 'y':
        print("\n[提示] 正在重新分析，请稍候...")
        # 直接使用 target_item 作为数据字典（错题本记录已包含所有必要字段：
        # handicap, jc_win/draw/lose, rq_win/draw/lose, avg_win/draw/lose 等）
        # 调用 analyze_data 进行完整分析
        analyze_data(target_item, target_item.get('shenjia', '未输入'))
    else:
        print("已取消重新分析。")
    
    input("\n按回车键返回主菜单...")



# ====================================================================
# [V37新增·自动校准模块] 纯独立功能: 默认关闭, 开启后只在每N场弹建议,
# 绝不自动改阈值; 你输入 y 才会把建议写入覆盖文件并在下次启动载入 CONFIG。
# 不触碰任何 V36/V27/V29 既有决策逻辑, 仅新增以下函数。
# ====================================================================

def _v37_paths():
    """[V37] 校准模块的状态文件/覆盖文件路径(与脚本同目录, 兜底用cwd)。"""
    base = _SCRIPT_PATH if _SCRIPT_PATH else os.path.abspath('.')
    d = os.path.dirname(base) if _SCRIPT_PATH else os.getcwd()
    return (os.path.join(d, 'calib_state_v37.json'),
            os.path.join(d, 'calib_override_v37.json'))

def _v37_read_json(path, default):
    import json
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def _v37_write_json(path, obj):
    import json
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def v37_load_override_into_config():
    """[V37] 启动时把上次你确认过的阈值覆盖载入 CONFIG(仅当覆盖文件存在)。
    不存在覆盖文件 => CONFIG 保持源码默认, 行为与V36完全一致。"""
    import json
    _state, override = _v37_paths()
    data = _v37_read_json(override, None)
    if not isinstance(data, dict) or not data:
        return False
    changed = []
    for k in ('EXEC_BASE_THRESHOLD', 'STAKE_HALF_FLOOR'):
        if k in data and isinstance(data[k], (int, float)):
            if CONFIG.get(k) != data[k]:
                CONFIG[k] = data[k]
                changed.append('{}={:.2f}'.format(k, data[k]))
    if changed:
        print('[V37自动校准] 已载入上次确认的阈值覆盖: ' + ', '.join(changed))
    return bool(changed)

def _v37_suggest_thresholds():
    """[V37] 复用既有 book_confidence_records() 的命中数据, 扫描出建议的正常线/降仓线。
    纯本地计算, 不改任何数据, 仅返回建议值(取不到则返回None)。"""
    try:
        recs = book_confidence_records()
    except Exception:
        recs = []
    recs = [r for r in recs if isinstance(r.get('confidence'), (int, float))
            and isinstance(r.get('hit'), bool)]
    if len(recs) < CONFIG.get('CALIB_MIN_SAMPLES', 15):
        return None
    recs = sorted(recs, key=lambda r: r['confidence'])
    lo, hi = CONFIG.get('CALIB_MIN_BASE_RANGE', (0.55, 0.85))
    min_high = CONFIG.get('CALIB_MIN_HIGH_SAMPLE', 15)
    hit_floor = CONFIG.get('CALIB_HIT_FLOOR', 0.50)
    overall = sum(1 for r in recs if r['hit']) / len(recs)
    best = None  # (gap, cut, hit_hi, hit_lo, n_hi)
    cut = lo
    while cut <= hi + 1e-9:
        high = [r for r in recs if r['confidence'] >= cut]
        low = [r for r in recs if r['confidence'] < cut]
        if len(high) >= min_high and low:
            hh = sum(1 for r in high if r['hit']) / len(high)
            hl = sum(1 for r in low if r['hit']) / len(low)
            if hh >= hit_floor and hh > hl:
                gap = hh - hl
                if best is None or gap > best[0]:
                    best = (gap, cut, hh, hl, len(high))
        cut = round(cut + 0.01, 4)
    if best is None:
        return {'overall': overall, 'n': len(recs)}
    _gap, cut, hh, hl, n_hi = best
    mid = round(min(0.60, max(0.35, cut - 0.15)), 2)
    return {'EXEC_BASE_sugg': round(cut, 2), 'STAKE_HALF_sugg': mid,
            'hit_hi': hh, 'hit_lo': hl, 'n_hi': n_hi,
            'overall': overall, 'n': len(recs)}

def auto_calibrate_v37():
    """[V37] 触发一次校准建议: 打印当前值vs建议值, 你输入 y 才写入覆盖文件生效。"""
    _state, override = _v37_paths()
    sugg = _v37_suggest_thresholds()
    print("\n" + "#" * 56)
    print("[V37 自动校准] 已积累足够新分析, 基于错题本命中数据给出阈值建议")
    print("#" * 56)
    cur_base = CONFIG.get('EXEC_BASE_THRESHOLD', 0.60)
    cur_mid = CONFIG.get('STAKE_HALF_FLOOR', 0.45)
    if not sugg or 'EXEC_BASE_sugg' not in sugg:
        n = sugg['n'] if sugg else 0
        print("  样本不足或数据无区分力(有效命中样本 {} 场), 本场次不调整, 维持当前阈值。".format(n))
        print("  当前: 正常线 {:.0f}% / 降仓线 {:.0f}%".format(cur_base * 100, cur_mid * 100))
        _v37_reset_count()
        return
    print("  有效命中样本 {} 场 | 整体命中率 {:.1f}%".format(sugg['n'], sugg['overall'] * 100))
    print("  高信心档命中率 {:.1f}% vs 低信心档 {:.1f}% (高信心样本 {} 场)".format(
        sugg['hit_hi'] * 100, sugg['hit_lo'] * 100, sugg['n_hi']))
    print("  当前: 正常线 {:.0f}% / 降仓线 {:.0f}%".format(cur_base * 100, cur_mid * 100))
    print("  建议: 正常线 {:.0f}% / 降仓线 {:.0f}%".format(
        sugg['EXEC_BASE_sugg'] * 100, sugg['STAKE_HALF_sugg'] * 100))
    ans = input("  是否应用以上建议? 仅当你输入 y 才会写入覆盖文件并生效 (y/n): ").strip().lower()
    if ans == 'y':
        import json
        _v37_write_json(override, {'EXEC_BASE_THRESHOLD': sugg['EXEC_BASE_sugg'],
                                   'STAKE_HALF_FLOOR': sugg['STAKE_HALF_sugg']})
        CONFIG['EXEC_BASE_THRESHOLD'] = sugg['EXEC_BASE_sugg']
        CONFIG['STAKE_HALF_FLOOR'] = sugg['STAKE_HALF_sugg']
        print("  [已应用] 阈值覆盖已保存, 本次会话立即生效, 下次启动自动载入。")
    else:
        print("  [未应用] 维持当前阈值。你随时可在代码里把 AUTO_CALIBRATE 设为 False 关闭本提示。")
    _v37_reset_count()

def _v37_reset_count():
    state, _ = _v37_paths()
    data = _v37_read_json(state, {})
    data['since_last'] = 0
    _v37_write_json(state, data)

def v37_startup_check():
    """[V37] main() 入口钩子: 载入覆盖阈值 + 提示当前自动校准状态。"""
    if not CONFIG.get('AUTO_CALIBRATE', False):
        return
    v37_load_override_into_config()
    state, _ = _v37_paths()
    data = _v37_read_json(state, {})
    print('[V37自动校准] 开关已开启; 距下次校准建议还差 {} 场(每{}场触发一次)。'.format(
        max(0, CONFIG.get('CALIBRATE_EVERY_N', 100) - data.get('since_last', 0)),
        CONFIG.get('CALIBRATE_EVERY_N', 100)))

def v37_after_analyze():
    """[V37] 每次选项1分析完调用: 仅累计计数; 开关关闭时不计数不触发。"""
    if not CONFIG.get('AUTO_CALIBRATE', False):
        return
    state, _ = _v37_paths()
    data = _v37_read_json(state, {})
    data['since_last'] = data.get('since_last', 0) + 1
    data['total_analyzed'] = data.get('total_analyzed', 0) + 1
    _v37_write_json(state, data)
    n = CONFIG.get('CALIBRATE_EVERY_N', 100)
    if data['since_last'] >= n:
        print('[V37] 已积累 {} 场新分析, 触发校准建议(仍需你确认)。'.format(n))
        auto_calibrate_v37()



# ==========================================
# [V38新增] 赛后录入: 把本场分析结果连同真实赛果写入错题集(错题本)
# ==========================================
def add_post_match_entry(data, shenjia_info, engine_results, resonance_info, final_conclusion):
    """[V38] 在分析流程末尾询问并录入真实赛果, 复用 save_to_code 写入 ERROR_BOOK(错题集)。
    录入后该场即成为历史样本, 供选项2全量回测 / 选项5共振批量测试 / 选项6相似度对比 /
    选项8批量复盘 / 选项10-13各项校准使用。返回新条目 match_id, 跳过返回 None。"""
    print("\n" + "=" * 40 + " 赛后录入(错题集) " + "=" * 40)
    ans = input("是否将本场结果录入错题集? (y=录入 / 其他键=跳过): ").strip().lower()
    if ans != "y":
        print("[提示] 已跳过赛后录入, 本场不写入错题本。")
        return None
    real_res = None
    while True:
        tmp = input("请输入本场真实赛果方向 (胜/平/负; 未开赛或暂不录入输入u): ").strip()
        if tmp in ("胜", "平", "负"):
            real_res = tmp
            break
        if tmp.lower() == "u":
            print("[提示] 未录入真实赛果, 已跳过赛后录入。")
            return None
        print("输入无效, 请输入 胜 / 平 / 负, 或输入 u 取消。")
    real_score = input("请输入最终比分 (如 2:1 或 2-1, 回车留空): ").strip()
    match_id = save_to_code(real_res, data, shenjia_info, real_score=real_score,
                            engine_results=engine_results, resonance_info=resonance_info)
    if match_id:
        try:
            v28_record_result_to_tracker(real_res, "让{}球".format(data.get("handicap", 0)))
        except Exception as _te:
            print("[提示] 信心追踪器记录已跳过: {}".format(_te))
        print("[错题集] 本场已写入错题本, 编号: {}".format(match_id))
        print("[错题集] 可用菜单 7.查看错题本列表 或 9.按编号查看分析 进行后续复盘/回测。")
        print("=" * 90)
    return match_id


def main():
    v37_startup_check()
    # === 主循环：显示菜单 -> 获取用户选择 -> 执行对应功能 ===
    while True:
        print("\n" + "=" * 40)
        print(" 赛事五引擎分析器 (V35 信心分档低概率结果校准版)")
        print("  [V13优化] 阈值参数回测优化 | 概率区间映射引擎(F) | 比分动态重构")
        print("  [V15增强] 重复编号自动修复 | 引擎性能自适应权重 | 信心指数评估 | 分歧放弃建议")
        print("  [功能] 双维度共振分析 | 编号对比 | 全量回测 | 智能复盘")
        print("=" * 40)
        print(" 1. 开始分析  2. 错题本全量回测  3. 智能复盘报告  4. 更新错题本条目  5. 共振批量测试  6. 比赛相似度对比  7. 查看错题本列表  8. 批量复盘测试  9. 按编号查看分析  10. 信心区间命中率报告  11. 冷门最近邻阈值回测(精确率/召回率)  12. 热门信心校准回测(分档命中率/Brier)  13. 信心分档低概率结果率校准(市场信心x相似度)  0. 退出")
        choice = input("选项: ").strip()
        if choice == '1':
            # 流程：获取输入 -> 验证数据 -> 获取附加信息 -> 防重检查 -> 执行分析
            data = get_data_input()
            if data:
                # V15修复: 验证输入数据
                if not validate_odds_data(data):
                    print("[错误] 数据验证失败，请重新输入")
                    input("\n按回车键返回主菜单...")
                    continue
                shenjia = get_extra_inputs()
                # [V15+补丁] 数据指纹检查（仅提示不拦截）
                check_and_warn_duplicate(data)
                        # [V28新增] 冷门赛前预过滤
                if CONFIG.get('COLD_PRE_FILTER_ENABLED', True):
                    is_cold, cold_reasons = cold_match_pre_filter(data)
                    if is_cold and CONFIG.get('COLD_PRE_FILTER_SKIP', True):
                        print("\n[V28] 本场通过冷门预过滤检测，已标记为高风险场次")
                        print("[V28] 根据配置COLD_PRE_FILTER_SKIP=True，本场已自动跳过")
                        print("[V28] 如需强制分析本场，请设置COLD_PRE_FILTER_SKIP=False")
                        input("\n按回车键返回主菜单...")
                        continue
                    elif is_cold:
                        print("\n[V28] 本场通过冷门预过滤检测，存在高风险特征，请谨慎操作")
                
                analyze_data(data, shenjia)
                v37_after_analyze()
        elif choice == '3':
            print("智能复盘报告功能已集成在每次分析中，请选1开始分析")
        elif choice == '2':
            verify_all_against_book()
        elif choice == '4':
            # 手动更新错题本条目
            print("\n--- 手动更新错题本条目 ---")
            print("当前错题本共 {} 条记录：".format(len(ERROR_BOOK)))
            for idx, item in enumerate(ERROR_BOOK, 1):
                h = item.get('handicap', 0)
                h_str = "主让{}球".format(h) if h > 0 else "客让{}球".format(abs(h)) if h < 0 else "平手/无让分"
                r = item.get('real_result', '')
                print("  [{}] {} | 胜{}/平{}/负{} | 结果: {}".format(
                    idx, h_str, item['jc_win'], item['jc_draw'], item['jc_lose'], r))
            try:
                num = int(input("请选择要更新的条目编号 (输入0取消): ").strip())
                if 1 <= num <= len(ERROR_BOOK):
                    old_item = ERROR_BOOK[num - 1]
                    print("\n当前记录详情：")
                    print("  让分: {} | 身价: {}".format(
                        "主让{}球".format(old_item['handicap']) if old_item['handicap'] > 0 else 
                        "客让{}球".format(abs(old_item['handicap'])) if old_item['handicap'] < 0 else "平手/无让分",
                        old_item.get('shenjia', '未输入')))
                    print("  赛事概率: 胜{}/平{}/负{}".format(
                        old_item['jc_win'], old_item['jc_draw'], old_item['jc_lose']))
                    print("  已有结果: 【{}】".format(old_item.get('real_result', '')))
                    new_res = input("请输入新的真实结果 (胜/平/负): ").strip()
                    if new_res in ['胜', '平', '负']:
                        # 更新内存中的错题本
                        old_item['real_result'] = new_res
                        # 同时更新文件中的记录
                        try:
                            with open(_SCRIPT_PATH, 'r', encoding='utf-8') as f:
                                file_content = f.read()
                            # 找到该条目的代码并替换
                            old_entry_pattern = r"\{[^}]*'handicap':\s*" + re.escape(str(old_item['handicap'])) + r"\s*,[^}]*'jc_win':\s*" + re.escape(str(old_item['jc_win'])) + r"\s*,[^}]*'jc_draw':\s*" + re.escape(str(old_item['jc_draw'])) + r"\s*,[^}]*'jc_lose':\s*" + re.escape(str(old_item['jc_lose'])) + r"[^}]*\}"
                            old_entry_match = re.search(old_entry_pattern, file_content)
                            if old_entry_match:
                                old_entry = old_entry_match.group(0)
                                # 构建新条目
                                new_entry_parts = []
                                for k, v in old_item.items():
                                    if isinstance(v, str):
                                        new_entry_parts.append("'{}': '{}'".format(k, v))
                                    else:
                                        new_entry_parts.append("'{}': {}".format(k, v))
                                new_entry = "    {" + ", ".join(new_entry_parts) + "}"
                                new_content = file_content.replace(old_entry, new_entry)
                                with open(_SCRIPT_PATH, 'w', encoding='utf-8') as f:
                                    f.write(new_content)
                            print("\n[OK] 已成功更新！结果已从【{}】更新为【{}】".format(
                                old_item.get('real_result', ''), new_res))
                        except Exception as e:
                            print("\n[!] 文件更新失败: {}".format(e))
                            print("    请手动在代码中修改错题本数据。")
                    else:
                        print("输入无效，已取消。")
                else:
                    print("已取消。")
            except ValueError:
                print("输入无效，请重新输入编号。")
            input("\n按回车键返回主菜单...")
        elif choice == '5':
            batch_resonance_test()

        elif choice == '6':
            # 比赛相似度对比
            print("\n--- 比赛相似度对比 ---")
            list_all_matches()
            id1 = input("请输入第一场比赛编号 (如 #001): ").strip()
            id2 = input("请输入第二场比赛编号 (如 #002): ").strip()
            compare_matches_by_id(id1, id2)
            input("\n按回车键返回主菜单...")
        elif choice == '7':
            # 查看错题本列表
            list_all_matches()
            input("\n按回车键返回主菜单...")
        elif choice == '8':
            # 批量复盘测试（六引擎全量分析）
            batch_review_test()
        elif choice == '9':
            # 按编号查看比赛分析
            view_match_by_id()
            input("\n按回车键返回主菜单...")

        elif choice == '10':
            # [V28新增] 信心区间命中率报告
            confidence_tracker.print_report()
            input("\n按回车键返回主菜单...")
        elif choice == '11':
            # [V34] 冷门最近邻阈值回测: 留一法评估各K的精确率/召回率, 判断最近邻能否预测冷门
            raw = input("自定义K列表(逗号分隔整数, 回车用默认5,10,20,30,50): ").strip()
            if raw:
                try:
                    k_list = [int(x) for x in raw.replace('，', ',').split(',') if x.strip()]
                except ValueError:
                    print('[提示] K解析失败, 改用默认列表')
                    k_list = None
            else:
                k_list = None
            calibrate_cold_template_threshold(k_list)
            input('\n按回车键返回主菜单...')
        elif choice == '12':
            # [V33] 热门信心校准回测: 分档命中率 + Brier + 高估/低估诊断
            calibrate_hot_confidence()
            input('\n按回车键返回主菜单...')
        elif choice == '13':
            # [V35] 信心分档低概率结果率校准: 市场信心代理 + 最近邻相似度交叉
            raw = input("自定义K(留一最近邻取前K场, 回车用默认30): ").strip()
            kk = None
            if raw:
                try:
                    kk = max(1, int(raw))
                except ValueError:
                    print('[提示] K解析失败, 用默认')
                    kk = None
            calibrate_confidence_cold(k=kk)
            input('\n按回车键返回主菜单...')
        elif choice == '0':
            print("感谢使用，再见！")
            break
        else:
            print("无效选项，请重新输入")


# ==========================================
# 批量测试：对错题本全部数据进行共振分析
# ==========================================

def batch_review_test():
    """批量复盘测试：对错题本全部数据进行智能复盘分析"""
    if not ERROR_BOOK:
        print("错题本为空")
        return
    print("\n" + "=" * 60)
    print(" 批量智能复盘测试 ({} 条数据)".format(len(ERROR_BOOK)))
    print("=" * 60)
    high_sim_count = 0
    cold_alert_count = 0
    agreement_count = 0
    for idx, case in enumerate(ERROR_BOOK, 1):
        shenjia = case.get('shenjia', '未输入')
        handicap = case['handicap']
        z, y, x = calculate_metrics(case['jc_win'], case['jc_draw'], case['jc_lose'])
        engine_c = engine_metrics(case, shenjia)
        case_data = dict(case)
        case_data['shenjia_info'] = shenjia
        matched = find_similar_cases(case_data)
        high_sim = [m for m in matched if m.get('similarity_score', 0) >= 0.85]
        if high_sim:
            high_sim_count += 1
        if engine_c.get('cold_risk', 0) >= CONFIG['COLD_RISK_THRESHOLD']:
            cold_alert_count += 1
        result_a = engine_pure_rq(case, shenjia)
        result_b = engine_combined(case, shenjia)
        result_d = engine_shape_decision(case)
        result_e = engine_critical_pattern(case)
        result_f = engine_zone_mapping(case, shenjia)
        # engine_c 已在上方计算过，直接复用
        engines = [result_a, result_b, engine_c, result_d, result_e, result_f]
        conclusions = []
        for r in engines:
            if r['engine'].startswith('A'):
                conclusions.append(convert_rq_to_standard(handicap, r['conclusion']))
            else:
                conclusions.append(r['conclusion'])
        vote_count = {}
        for c in conclusions:
            vote_count[c] = vote_count.get(c, 0) + 1
        if max(vote_count.values()) >= 4:
            agreement_count += 1
    print("\n--- 批量复盘统计 ---")
    print("  总数据量: {} 条".format(len(ERROR_BOOK)))
    print("  高相似度匹配(>=85%): {} 条 ({:.1f}%)".format(high_sim_count, high_sim_count / len(ERROR_BOOK) * 100))
    print("  冷门预警触发: {} 条 ({:.1f}%)".format(cold_alert_count, cold_alert_count / len(ERROR_BOOK) * 100))
    print("  引擎高度共识(>=4): {} 条 ({:.1f}%)".format(agreement_count, agreement_count / len(ERROR_BOOK) * 100))
    print("=" * 60)

def batch_resonance_test():
    """批量测试所有错题数据，统计共振分析结果"""
    if not ERROR_BOOK:
        print("错题本为空")
        return

    print("\n" + "=" * 60)
    print(" 双维度共振批量测试 ({} 条数据)".format(len(ERROR_BOOK)))
    print("=" * 60)

    yopank_count = 0  # 干扰信号警告数
    tongxiang_count = 0  # 同向共振
    pingju_count = 0  # 平局共振
    lengmen_count = 0  # 冷门预警
    normal_count = 0  # 正常

    # 存储各类共振的详细场次
    tongxiang_matches = []
    yopank_matches = []
    pingju_matches = []
    lengmen_matches = []
    normal_matches = []

    for idx, case in enumerate(ERROR_BOOK, 1):
        shenjia = case.get('shenjia', '未输入')
        handicap = case['handicap']

        # 计算引擎C
        z, y, x = calculate_metrics(case['jc_win'], case['jc_draw'], case['jc_lose'])
        engine_c = engine_metrics(case, shenjia)

        # 共振分析
        resonance = analyze_risk_and_standard(case, engine_c, shenjia)

        # 统计共振类型
        r_type = resonance['resonance_type']
        if r_type == '反向背离':
            yopank_count += 1
            yopank_matches.append((idx, case, resonance))
        elif r_type == '同向共振':
            tongxiang_count += 1
            tongxiang_matches.append((idx, case, resonance))
        elif r_type in ['平局共振', '浅度让分平局']:
            pingju_count += 1
            pingju_matches.append((idx, case, resonance))
        elif r_type == '冷门预警':
            lengmen_count += 1
            lengmen_matches.append((idx, case, resonance))
        else:
            normal_count += 1
            normal_matches.append((idx, case, resonance))

    print("\n--- 共振分析统计 ---")
    print("  总数据量: {} 条".format(len(ERROR_BOOK)))
    print("  同向共振: {} 条".format(tongxiang_count))
    print("  反向背离(干扰信号警告): {} 条".format(yopank_count))
    print("  平局共振: {} 条".format(pingju_count))
    print("  冷门预警: {} 条".format(lengmen_count))
    print("  正常: {} 条".format(normal_count))
    print("-" * 30)
    yopank_rate = yopank_count / len(ERROR_BOOK) * 100
    print("  干扰信号警告占比: {:.1f}%".format(yopank_rate))
    print("=" * 60)

    # ========== 同向共振明细 ==========
    if tongxiang_matches:
        print("\n" + "=" * 60)
        print("  【同向共振】详细场次 (共 {} 条)".format(len(tongxiang_matches)))
        print("=" * 60)
        for i, (idx, case, resonance) in enumerate(tongxiang_matches, 1):
            print("\n--- 场次 #{} ---".format(idx))
            print("  让分: {} | 概率: 主{:.2f} 平{:.2f} 客{:.2f}".format(
                "主让{}球".format(case['handicap']) if case['handicap'] > 0 else
                "客让{}球".format(abs(case['handicap'])) if case['handicap'] < 0 else "平手/无让分",
                case['jc_win'], case['jc_draw'], case['jc_lose']))
            print("  共振类型: {}".format(resonance['resonance_type']))
            print("  共振详情: {}".format(resonance['resonance_detail']))
            print("  建议: {}".format(resonance['recommendation']))
            print("  实际赛果: {}".format(case.get('real_result', '未知')))
            if case.get('real_score'):
                print("  实际比分: {}".format(case['real_score']))
            print("  引擎结论: {}".format(case.get('engine_summary', '未记录')))
            print("  比赛上下文: {}".format(case.get('match_context', '未记录')))

    # ========== 反向背离(干扰信号)明细 ==========
    if yopank_matches:
        print("\n" + "=" * 60)
        print("  【反向背离/干扰信号警告】详细场次 (共 {} 条)".format(len(yopank_matches)))
        print("=" * 60)
        for i, (idx, case, resonance) in enumerate(yopank_matches, 1):
            print("\n--- 场次 #{} ---".format(idx))
            print("  让分: {} | 概率: 主{:.2f} 平{:.2f} 客{:.2f}".format(
                "主让{}球".format(case['handicap']) if case['handicap'] > 0 else
                "客让{}球".format(abs(case['handicap'])) if case['handicap'] < 0 else "平手/无让分",
                case['jc_win'], case['jc_draw'], case['jc_lose']))
            print("  共振类型: {}".format(resonance['resonance_type']))
            print("  共振详情: {}".format(resonance['resonance_detail']))
            print("  建议: {}".format(resonance['recommendation']))
            print("  实际赛果: {}".format(case.get('real_result', '未知')))
            if case.get('real_score'):
                print("  实际比分: {}".format(case['real_score']))
            print("  引擎结论: {}".format(case.get('engine_summary', '未记录')))
            print("  比赛上下文: {}".format(case.get('match_context', '未记录')))

    # ========== 平局共振明细 ==========
    if pingju_matches:
        print("\n" + "=" * 60)
        print("  【平局共振】详细场次 (共 {} 条)".format(len(pingju_matches)))
        print("=" * 60)
        for i, (idx, case, resonance) in enumerate(pingju_matches, 1):
            print("\n--- 场次 #{} ---".format(idx))
            print("  让分: {} | 概率: 主{:.2f} 平{:.2f} 客{:.2f}".format(
                "主让{}球".format(case['handicap']) if case['handicap'] > 0 else
                "客让{}球".format(abs(case['handicap'])) if case['handicap'] < 0 else "平手/无让分",
                case['jc_win'], case['jc_draw'], case['jc_lose']))
            print("  共振类型: {}".format(resonance['resonance_type']))
            print("  共振详情: {}".format(resonance['resonance_detail']))
            print("  建议: {}".format(resonance['recommendation']))
            print("  实际赛果: {}".format(case.get('real_result', '未知')))
            if case.get('real_score'):
                print("  实际比分: {}".format(case['real_score']))
            print("  引擎结论: {}".format(case.get('engine_summary', '未记录')))
            print("  比赛上下文: {}".format(case.get('match_context', '未记录')))

    # ========== 冷门预警明细 ==========
    if lengmen_matches:
        print("\n" + "=" * 60)
        print("  【冷门预警】详细场次 (共 {} 条)".format(len(lengmen_matches)))
        print("=" * 60)
        for i, (idx, case, resonance) in enumerate(lengmen_matches, 1):
            print("\n--- 场次 #{} ---".format(idx))
            print("  让分: {} | 概率: 主{:.2f} 平{:.2f} 客{:.2f}".format(
                "主让{}球".format(case['handicap']) if case['handicap'] > 0 else
                "客让{}球".format(abs(case['handicap'])) if case['handicap'] < 0 else "平手/无让分",
                case['jc_win'], case['jc_draw'], case['jc_lose']))
            print("  共振类型: {}".format(resonance['resonance_type']))
            print("  共振详情: {}".format(resonance['resonance_detail']))
            print("  建议: {}".format(resonance['recommendation']))
            print("  实际赛果: {}".format(case.get('real_result', '未知')))
            if case.get('real_score'):
                print("  实际比分: {}".format(case['real_score']))
            print("  引擎结论: {}".format(case.get('engine_summary', '未记录')))
            print("  比赛上下文: {}".format(case.get('match_context', '未记录')))

    # ========== 正常场次明细 ==========
    if normal_matches:
        print("\n" + "=" * 60)
        print("  【正常场次】详细场次 (共 {} 条)".format(len(normal_matches)))
        print("=" * 60)
        for i, (idx, case, resonance) in enumerate(normal_matches, 1):
            print("\n--- 场次 #{} ---".format(idx))
            print("  让分: {} | 概率: 主{:.2f} 平{:.2f} 客{:.2f}".format(
                "主让{}球".format(case['handicap']) if case['handicap'] > 0 else
                "客让{}球".format(abs(case['handicap'])) if case['handicap'] < 0 else "平手/无让分",
                case['jc_win'], case['jc_draw'], case['jc_lose']))
            print("  共振类型: {}".format(resonance['resonance_type']))
            print("  共振详情: {}".format(resonance['resonance_detail']))
            print("  实际赛果: {}".format(case.get('real_result', '未知')))
            if case.get('real_score'):
                print("  实际比分: {}".format(case['real_score']))
            print("  引擎结论: {}".format(case.get('engine_summary', '未记录')))
            print("  比赛上下文: {}".format(case.get('match_context', '未记录')))

    print("\n" + "=" * 60)
    print(" 共振批量测试全部完成！")
    print("=" * 60)
    input("\n按回车键返回主菜单...")

if __name__ == "__main__":
    main()